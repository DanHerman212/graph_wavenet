"""
NYC Subway GTFS-RT Streaming Pipeline

Apache Beam pipeline for ingesting GTFS-RT and service alert data
from Pub/Sub into BigQuery.

Usage:
    # Local runner (for testing)
    python pipeline.py --runner=DirectRunner

    # Dataflow runner (production)
    python pipeline.py \
        --runner=DataflowRunner \
        --project=YOUR_PROJECT \
        --region=us-east1 \
        --temp_location=gs://YOUR_BUCKET/temp \
        --staging_location=gs://YOUR_BUCKET/staging \
        --gtfs_subscription=projects/PROJECT/subscriptions/gtfs-rt-ace-dataflow \
        --alerts_subscription=projects/PROJECT/subscriptions/service-alerts-dataflow \
        --sensor_table=PROJECT:subway.sensor_data \
        --alerts_table=PROJECT:subway.service_alerts \
        --streaming
"""

import argparse
import logging
from typing import Optional

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
from apache_beam.io.gcp.bigquery import BigQueryDisposition, WriteToBigQuery

from transforms.parse_gtfs import ParseGTFSMessage, AddProcessingMetadata
from transforms.parse_alerts import ParseAlertMessage, EnrichAlertData, FilterACEAlerts
from schemas import SENSOR_DATA_SCHEMA, SERVICE_ALERTS_SCHEMA

logger = logging.getLogger(__name__)


class SubwayPipelineOptions(PipelineOptions):
    """Custom pipeline options for the subway ingestion pipeline."""
    
    @classmethod
    def _add_argparse_args(cls, parser):
        parser.add_argument(
            "--gtfs_subscription",
            required=True,
            help="Pub/Sub subscription for GTFS-RT messages"
        )
        parser.add_argument(
            "--alerts_subscription",
            required=True,
            help="Pub/Sub subscription for service alert messages"
        )
        parser.add_argument(
            "--sensor_table",
            required=True,
            help="BigQuery table for sensor data (project:dataset.table)"
        )
        parser.add_argument(
            "--alerts_table",
            required=True,
            help="BigQuery table for service alerts (project:dataset.table)"
        )
        parser.add_argument(
            "--dead_letter_topic",
            default=None,
            help="Pub/Sub topic for failed messages (optional)"
        )


def build_sensor_data_pipeline(
    pipeline: beam.Pipeline,
    options: SubwayPipelineOptions
) -> beam.PCollection:
    """Build the sensor data ingestion branch of the pipeline.
    
    Args:
        pipeline: The Beam pipeline
        options: Pipeline options
        
    Returns:
        PCollection of successfully written records
    """
    # Read from Pub/Sub
    raw_messages = (
        pipeline
        | "ReadGTFSMessages" >> beam.io.ReadFromPubSub(
            subscription=options.gtfs_subscription
        )
    )
    
    # Parse and validate messages
    parsed_messages = (
        raw_messages
        | "ParseGTFSMessages" >> beam.ParDo(ParseGTFSMessage())
        | "AddMetadata" >> beam.ParDo(AddProcessingMetadata())
    )
    
    # Write to BigQuery
    write_result = (
        parsed_messages
        | "WriteSensorData" >> WriteToBigQuery(
            table=options.sensor_table,
            schema=SENSOR_DATA_SCHEMA,
            create_disposition=BigQueryDisposition.CREATE_IF_NEEDED,
            write_disposition=BigQueryDisposition.WRITE_APPEND,
            method="STREAMING_INSERTS",
            insert_retry_strategy="RETRY_ON_TRANSIENT_ERROR",
        )
    )
    
    return parsed_messages


def build_alerts_pipeline(
    pipeline: beam.Pipeline,
    options: SubwayPipelineOptions
) -> beam.PCollection:
    """Build the service alerts ingestion branch of the pipeline.
    
    Args:
        pipeline: The Beam pipeline
        options: Pipeline options
        
    Returns:
        PCollection of successfully written records
    """
    # Read from Pub/Sub
    raw_alerts = (
        pipeline
        | "ReadAlertMessages" >> beam.io.ReadFromPubSub(
            subscription=options.alerts_subscription
        )
    )
    
    # Parse, validate, and enrich alerts
    parsed_alerts = (
        raw_alerts
        | "ParseAlerts" >> beam.ParDo(ParseAlertMessage())
        | "FilterACE" >> beam.ParDo(FilterACEAlerts())
        | "EnrichAlerts" >> beam.ParDo(EnrichAlertData())
    )
    
    # Write to BigQuery
    write_result = (
        parsed_alerts
        | "WriteAlerts" >> WriteToBigQuery(
            table=options.alerts_table,
            schema=SERVICE_ALERTS_SCHEMA,
            create_disposition=BigQueryDisposition.CREATE_IF_NEEDED,
            write_disposition=BigQueryDisposition.WRITE_APPEND,
            method="STREAMING_INSERTS",
            insert_retry_strategy="RETRY_ON_TRANSIENT_ERROR",
        )
    )
    
    return parsed_alerts


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
    logger.info(f"GTFS subscription: {subway_options.gtfs_subscription}")
    logger.info(f"Alerts subscription: {subway_options.alerts_subscription}")
    logger.info(f"Sensor table: {subway_options.sensor_table}")
    logger.info(f"Alerts table: {subway_options.alerts_table}")
    
    # Build and run the pipeline
    with beam.Pipeline(options=pipeline_options) as p:
        # Build sensor data branch
        sensor_data = build_sensor_data_pipeline(p, subway_options)
        
        # Build alerts branch
        alerts = build_alerts_pipeline(p, subway_options)
        
        # Log counts (for debugging)
        _ = (
            sensor_data
            | "CountSensorData" >> beam.combiners.Count.Globally()
            | "LogSensorCount" >> beam.Map(
                lambda x: logger.info(f"Processed {x} sensor records")
            )
        )
        
        _ = (
            alerts
            | "CountAlerts" >> beam.combiners.Count.Globally()
            | "LogAlertCount" >> beam.Map(
                lambda x: logger.info(f"Processed {x} alerts")
            )
        )
    
    logger.info("Pipeline completed")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    run()
