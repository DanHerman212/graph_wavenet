"""
NYC Subway GTFS-RT Streaming Pipeline - TEST VERSION with Stateful Track Enrichment

This is a test pipeline that runs parallel to production. It implements stateful
processing to merge track data from trip_updates with vehicle position arrivals
BEFORE writing to BigQuery.

Key differences from production:
- Uses separate test Pub/Sub subscriptions
- Writes to separate test BigQuery table
- Implements stateful track enrichment
- Can be stopped/started independently

Usage:
    # Dataflow runner (test deployment)
    python3 pipeline_test.py \
        --runner=DataflowRunner \
        --project=YOUR_PROJECT \
        --region=us-east1 \
        --temp_location=gs://YOUR_BUCKET/temp \
        --staging_location=gs://YOUR_BUCKET/staging \
        --gtfs_ace_subscription=projects/PROJECT/subscriptions/gtfs-rt-ace-dataflow-test \
        --gtfs_bdfm_subscription=projects/PROJECT/subscriptions/gtfs-rt-bdfm-dataflow-test \
        --alerts_subscription=projects/PROJECT/subscriptions/service-alerts-dataflow-test \
        --output_table=PROJECT:subway.vehicle_positions_enriched \
        --alerts_table=PROJECT:subway.service_alerts_test \
        --streaming
"""

from __future__ import absolute_import
from __future__ import print_function

import argparse
import json
import logging
from datetime import timedelta

import apache_beam as beam
from apache_beam import coders
from apache_beam.transforms.userstate import ReadModifyWriteStateSpec
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
from apache_beam.io.gcp.bigquery import BigQueryDisposition, WriteToBigQuery

from transforms.parse_gtfs import ExtractVehiclePositions, ValidateVehiclePosition
from transforms.parse_alerts import ExtractAlerts, ValidateAlert
from schemas import VEHICLE_POSITIONS_SCHEMA, SERVICE_ALERTS_SCHEMA

logger = logging.getLogger(__name__)


class SubwayPipelineOptions(PipelineOptions):
    """Custom pipeline options for the subway ingestion pipeline."""
    
    @classmethod
    def _add_argparse_args(cls, parser):
        parser.add_argument(
            "--gtfs_ace_subscription",
            required=True,
            help="Pub/Sub subscription for GTFS-RT ACE messages"
        )
        parser.add_argument(
            "--gtfs_bdfm_subscription",
            required=True,
            help="Pub/Sub subscription for GTFS-RT BDFM messages"
        )
        parser.add_argument(
            "--alerts_subscription",
            required=True,
            help="Pub/Sub subscription for service alert messages"
        )
        parser.add_argument(
            "--output_table",
            required=True,
            help="BigQuery table for vehicle positions (project:dataset.table)"
        )
        parser.add_argument(
            "--alerts_table",
            required=True,
            help="BigQuery table for service alerts (project:dataset.table)"
        )


class TrackDataCoder(coders.Coder):
    """Custom coder for track data state storage."""
    
    def encode(self, value):
        return json.dumps(value).encode('utf-8')
    
    def decode(self, encoded):
        return json.loads(encoded.decode('utf-8'))
    
    def is_deterministic(self):
        return True


class EnrichWithTrackData(beam.DoFn):
    """Stateful DoFn that enriches vehicle positions with track data.
    
    Maintains a state store of track assignments from trip_updates.
    When vehicle positions arrive, looks up cached track data and merges it.
    """
    
    # State spec: stores track data keyed by (trip_id, stop_id)
    TRACK_STATE = ReadModifyWriteStateSpec('track_cache', TrackDataCoder())
    
    def __init__(self):
        self.enriched_count = beam.metrics.Metrics.counter(self.__class__, "enriched_records")
        self.no_track_data = beam.metrics.Metrics.counter(self.__class__, "no_track_data")
        self.track_cached = beam.metrics.Metrics.counter(self.__class__, "track_data_cached")
        self.stale_data = beam.metrics.Metrics.counter(self.__class__, "stale_track_data")
    
    def process(
        self,
        element,
        track_state=beam.DoFn.StateParam(TRACK_STATE)
    ):
        """Process vehicle position or trip update and enrich with track data.
        
        Args:
            element: Tuple of (key, record) where key is "trip_id|stop_id"
            track_state: State storage for track assignments
            
        Yields:
            Enriched vehicle position records (only for actual arrivals)
        """
        # Unpack the keyed element
        key, record = element
        
        trip_id = record.get("trip_id")
        stop_id = record.get("stop_id")
        current_status = record.get("current_status")
        
        if not trip_id or not stop_id:
            return
        
        # Create state key
        state_key = "{0}|{1}".format(trip_id, stop_id)
        
        # Case 1: Trip update with track data - store in state
        if current_status == "IN_TRANSIT_TO":
            scheduled_track = record.get("scheduled_track")
            actual_track = record.get("actual_track")
            
            # Only cache if we have track data
            if scheduled_track or actual_track:
                track_data = {
                    "scheduled_track": scheduled_track,
                    "actual_track": actual_track,
                    "train_id": record.get("train_id"),
                    "nyct_direction": record.get("nyct_direction"),
                    "cached_at": record.get("vehicle_timestamp"),
                }
                
                # Store in state
                track_state.write(track_data)
                self.track_cached.inc()
                
                logger.debug("Cached track data for {0}: {1}".format(state_key, actual_track))
            
            # Don't yield trip updates - only actual arrivals
            return
        
        # Case 2: Actual arrival (STOPPED_AT, INCOMING_AT) - enrich with cached track data
        elif current_status in ("STOPPED_AT", "INCOMING_AT"):
            # Try to read track data from state
            cached_track_data = track_state.read()
            
            if cached_track_data:
                # Check if data is stale (more than 15 minutes old)
                from datetime import datetime
                try:
                    cached_time = datetime.fromisoformat(cached_track_data["cached_at"].replace("Z", "+00:00"))
                    arrival_time = datetime.fromisoformat(record["vehicle_timestamp"].replace("Z", "+00:00"))
                    age_minutes = (arrival_time - cached_time).total_seconds() / 60
                    
                    if age_minutes > 15:
                        self.stale_data.inc()
                        logger.warning("Stale track data for {0}: {1:.1f} min old".format(state_key, age_minutes))
                    else:
                        # Merge cached track data into the record
                        record["scheduled_track"] = cached_track_data.get("scheduled_track")
                        record["actual_track"] = cached_track_data.get("actual_track")
                        
                        # Also enrich with train_id and direction if missing
                        if not record.get("train_id"):
                            record["train_id"] = cached_track_data.get("train_id")
                        if not record.get("nyct_direction"):
                            record["nyct_direction"] = cached_track_data.get("nyct_direction")
                        
                        self.enriched_count.inc()
                        logger.debug("Enriched arrival at {0} with track: {1}".format(stop_id, record['actual_track']))
                except Exception as e:
                    logger.error("Error checking data age: {0}".format(e))
            else:
                self.no_track_data.inc()
                logger.debug("No cached track data for {0}".format(state_key))
            
            # Yield the (possibly enriched) arrival record
            yield record


def run(argv=None):
    """Main entry point for the TEST pipeline."""
    # Parse arguments
    parser = argparse.ArgumentParser()
    known_args, pipeline_args = parser.parse_known_args(argv)
    
    # Create pipeline options
    pipeline_options = PipelineOptions(pipeline_args)
    subway_options = pipeline_options.view_as(SubwayPipelineOptions)
    
    # Enable streaming mode
    pipeline_options.view_as(StandardOptions).streaming = True
    
    logger.info("=" * 80)
    logger.info("Starting TEST NYC Subway GTFS-RT streaming pipeline with stateful enrichment")
    logger.info("=" * 80)
    logger.info("GTFS ACE subscription: {0}".format(subway_options.gtfs_ace_subscription))
    logger.info("GTFS BDFM subscription: {0}".format(subway_options.gtfs_bdfm_subscription))
    logger.info("Alerts subscription: {0}".format(subway_options.alerts_subscription))
    logger.info("Output table: {0}".format(subway_options.output_table))
    logger.info("Alerts table: {0}".format(subway_options.alerts_table))
    logger.info("=" * 80)
    
    # Build and run the pipeline
    with beam.Pipeline(options=pipeline_options) as p:
        
        # =====================================================================
        # Vehicle Positions Branch (ACE + BDFM merged) WITH TRACK ENRICHMENT
        # =====================================================================
        
        # Read ACE feed
        gtfs_ace = (
            p
            | "ReadGTFS_ACE" >> beam.io.ReadFromPubSub(
                subscription=subway_options.gtfs_ace_subscription
            )
        )
        
        # Read BDFM feed
        gtfs_bdfm = (
            p
            | "ReadGTFS_BDFM" >> beam.io.ReadFromPubSub(
                subscription=subway_options.gtfs_bdfm_subscription
            )
        )
        
        # Merge both feeds and extract vehicle positions + trip updates
        all_records = (
            (gtfs_ace, gtfs_bdfm)
            | "MergeGTFSFeeds" >> beam.Flatten()
            | "ExtractVehicles" >> beam.ParDo(ExtractVehiclePositions())
            | "ValidateVehicles" >> beam.ParDo(ValidateVehiclePosition())
        )
        
        # Key by (trip_id, stop_id) for stateful processing
        keyed_records = (
            all_records
            | "KeyByTripStop" >> beam.Map(
                lambda x: ("{0}|{1}".format(x['trip_id'], x['stop_id']), x)
            )
        )
        
        # Apply stateful enrichment
        enriched_arrivals = (
            keyed_records
            | "EnrichWithTracks" >> beam.ParDo(EnrichWithTrackData())
        )
        
        # Write enriched vehicle positions to BigQuery
        _ = (
            enriched_arrivals
            | "WriteEnrichedVehicles" >> WriteToBigQuery(
                table=subway_options.output_table,
                schema=VEHICLE_POSITIONS_SCHEMA,
                create_disposition=BigQueryDisposition.CREATE_IF_NEEDED,
                write_disposition=BigQueryDisposition.WRITE_APPEND,
                method="STREAMING_INSERTS",
                insert_retry_strategy="RETRY_ON_TRANSIENT_ERROR",
            )
        )
        
        # =====================================================================
        # Service Alerts Branch (unchanged from production)
        # =====================================================================
        alerts = (
            p
            | "ReadAlerts" >> beam.io.ReadFromPubSub(
                subscription=subway_options.alerts_subscription
            )
            | "ExtractAlerts" >> beam.ParDo(ExtractAlerts())
            | "ValidateAlerts" >> beam.ParDo(ValidateAlert())
        )
        
        # Write alerts to BigQuery
        _ = (
            alerts
            | "WriteAlerts" >> WriteToBigQuery(
                table=subway_options.alerts_table,
                schema=SERVICE_ALERTS_SCHEMA,
                create_disposition=BigQueryDisposition.CREATE_IF_NEEDED,
                write_disposition=BigQueryDisposition.WRITE_APPEND,
                method="STREAMING_INSERTS",
                insert_retry_strategy="RETRY_ON_TRANSIENT_ERROR",
            )
        )
    
    logger.info("TEST Pipeline completed")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    run()
