# Dataflow Configuration
# Note: Dataflow jobs are typically launched via the gcloud CLI or Apache Beam
# This file provides the template and associated resources

# Dataflow Flex Template bucket
resource "google_storage_bucket" "dataflow_templates" {
  name          = "${var.project_id}-dataflow-templates"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true

  depends_on = [google_project_service.apis]
}

# Template metadata for the streaming pipeline
resource "google_storage_bucket_object" "pipeline_metadata" {
  name   = "templates/subway-pipeline-metadata.json"
  bucket = google_storage_bucket.dataflow_templates.name

  content = jsonencode({
    name        = "subway-gtfs-pipeline"
    description = "Streaming pipeline for NYC Subway GTFS-RT data ingestion"
    parameters = [
      {
        name        = "gtfs_ace_subscription"
        label       = "GTFS-RT ACE Pub/Sub Subscription"
        helpText    = "Pub/Sub subscription for GTFS-RT ACE messages"
        isOptional  = false
        regexes     = ["projects/[^/]+/subscriptions/[^/]+"]
      },
      {
        name        = "gtfs_bdfm_subscription"
        label       = "GTFS-RT BDFM Pub/Sub Subscription"
        helpText    = "Pub/Sub subscription for GTFS-RT BDFM messages"
        isOptional  = false
        regexes     = ["projects/[^/]+/subscriptions/[^/]+"]
      },
      {
        name        = "alerts_subscription"
        label       = "Service Alerts Pub/Sub Subscription"
        helpText    = "Pub/Sub subscription for service alert messages"
        isOptional  = false
        regexes     = ["projects/[^/]+/subscriptions/[^/]+"]
      },
      {
        name        = "output_table"
        label       = "BigQuery Vehicle Positions Table"
        helpText    = "BigQuery table for vehicle positions (project:dataset.table)"
        isOptional  = false
      },
      {
        name        = "alerts_table"
        label       = "BigQuery Alerts Table"
        helpText    = "BigQuery table for service alerts (project:dataset.table)"
        isOptional  = false
      }
    ]
  })
}

# Output the launch command for reference
output "dataflow_launch_command" {
  description = "Command to launch the Dataflow streaming job"
  value       = <<-CMD
    # Launch the Dataflow streaming job
    python -m ingestion.dataflow.pipeline \
      --runner=DataflowRunner \
      --project=${var.project_id} \
      --region=${var.region} \
      --job_name=subway-gtfs-pipeline \
      --temp_location=gs://${google_storage_bucket.dataflow_temp.name}/temp \
      --staging_location=gs://${google_storage_bucket.dataflow_staging.name}/staging \
      --service_account_email=${google_service_account.dataflow.email} \
      --max_num_workers=${var.dataflow_max_workers} \
      --machine_type=${var.dataflow_machine_type} \
      --gtfs_ace_subscription=projects/${var.project_id}/subscriptions/${google_pubsub_subscription.gtfs_rt.name} \
      --gtfs_bdfm_subscription=projects/${var.project_id}/subscriptions/${google_pubsub_subscription.gtfs_rt_bdfm.name} \
      --alerts_subscription=projects/${var.project_id}/subscriptions/${google_pubsub_subscription.service_alerts.name} \
      --output_table=${var.project_id}:${google_bigquery_dataset.subway.dataset_id}.${google_bigquery_table.vehicle_positions.table_id} \
      --alerts_table=${var.project_id}:${google_bigquery_dataset.subway.dataset_id}.${google_bigquery_table.service_alerts.table_id} \
      --streaming
  CMD
}
