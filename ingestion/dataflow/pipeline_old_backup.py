"""
NYC Subway GTFS-RT Streaming Pipeline

Apache Beam pipeline for ingesting GTFS-RT and service alert data
from Pub/Sub into BigQuery.

Usage:
    # Local runner (for testing)
    python3 pipeline.py --runner=DirectRunner

    # Dataflow runner (production)
    python3 pipeline.py \
        --runner=DataflowRunner \
        --project=YOUR_PROJECT \
        --region=us-east1 \
        --temp_location=gs://YOUR_BUCKET/temp \
        --staging_location=gs://YOUR_BUCKET/staging \
        --gtfs_ace_subscription=projects/PROJECT/subscriptions/gtfs-rt-ace-dataflow \
        --gtfs_bdfm_subscription=projects/PROJECT/subscriptions/gtfs-rt-bdfm-dataflow \
        --alerts_subscription=projects/PROJECT/subscriptions/service-alerts-dataflow \
        --output_table=PROJECT:subway.vehicle_positions \
        --alerts_table=PROJECT:subway.service_alerts \
        --streaming
"""

import argparse
import logging

import apache_beam as beam
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


def run(argv=None):
    """Main entry point for the pipeline."""
    # Parse arguments
    parser = argparse.ArgumentParser()
    known_args, pipeline_args = parser.parse_known_args(argv)
    
    # Create pipeline options
    pipeline_options = PipelineOptions(pipeline_args)
    subway_options = pipeline_options.view_as(SubwayPipelineOptions)
    
    # Enable streaming mode
    pipeline_options.view_as(StandardOptions).streaming = True
    
    logger.info("Starting NYC Subway GTFS-RT streaming pipeline")
    logger.info(f"GTFS ACE subscription: {subway_options.gtfs_ace_subscription}")
    logger.info(f"GTFS BDFM subscription: {subway_options.gtfs_bdfm_subscription}")
    logger.info(f"Alerts subscription: {subway_options.alerts_subscription}")
    logger.info(f"Output table: {subway_options.output_table}")
    logger.info(f"Alerts table: {subway_options.alerts_table}")
    
    # Build and run the pipeline
    with beam.Pipeline(options=pipeline_options) as p:
        
        # =====================================================================
        # Vehicle Positions Branch (ACE + BDFM merged)
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
        
        # Merge both feeds and extract vehicle positions
        vehicle_positions = (
            (gtfs_ace, gtfs_bdfm)
            | "MergeGTFSFeeds" >> beam.Flatten()
            | "ExtractVehicles" >> beam.ParDo(ExtractVehiclePositions())
            | "ValidateVehicles" >> beam.ParDo(ValidateVehiclePosition())
        )
        
        # Write vehicle positions to BigQuery
        _ = (
            vehicle_positions
            | "WriteVehicles" >> WriteToBigQuery(
                table=subway_options.output_table,
                schema=VEHICLE_POSITIONS_SCHEMA,
                create_disposition=BigQueryDisposition.CREATE_NEVER,
                write_disposition=BigQueryDisposition.WRITE_APPEND,
                method="STREAMING_INSERTS",
                insert_retry_strategy="RETRY_ON_TRANSIENT_ERROR",
            )
        )
        
        # =====================================================================
        # Service Alerts Branch
        # =====================================================================
        alerts = (
            p
            # Read alert messages from Pub/Sub
            | "ReadAlerts" >> beam.io.ReadFromPubSub(
                subscription=subway_options.alerts_subscription
            )
            # Extract individual alerts (filtered to A/C/E only)
            | "ExtractAlerts" >> beam.ParDo(ExtractAlerts())
            # Validate required fields
            | "ValidateAlerts" >> beam.ParDo(ValidateAlert())
        )
        
        # Write alerts to BigQuery
        _ = (
            alerts
            | "WriteAlerts" >> WriteToBigQuery(
                table=subway_options.alerts_table,
                schema=SERVICE_ALERTS_SCHEMA,
                create_disposition=BigQueryDisposition.CREATE_NEVER,
                write_disposition=BigQueryDisposition.WRITE_APPEND,
                method="STREAMING_INSERTS",
                insert_retry_strategy="RETRY_ON_TRANSIENT_ERROR",
            )
        )
    
    logger.info("Pipeline completed")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    run()
