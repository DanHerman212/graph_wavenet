# Outputs for the NYC Subway Pipeline Infrastructure

output "project_id" {
  description = "GCP Project ID"
  value       = var.project_id
}

output "region" {
  description = "GCP Region"
  value       = var.region
}

# Pub/Sub outputs
output "gtfs_ace_topic_name" {
  description = "Name of the GTFS-RT ACE Pub/Sub topic"
  value       = google_pubsub_topic.gtfs_rt.name
}

output "gtfs_ace_topic_id" {
  description = "Full ID of the GTFS-RT ACE Pub/Sub topic"
  value       = google_pubsub_topic.gtfs_rt.id
}

output "gtfs_bdfm_topic_name" {
  description = "Name of the GTFS-RT BDFM Pub/Sub topic"
  value       = google_pubsub_topic.gtfs_rt_bdfm.name
}

output "gtfs_bdfm_topic_id" {
  description = "Full ID of the GTFS-RT BDFM Pub/Sub topic"
  value       = google_pubsub_topic.gtfs_rt_bdfm.id
}

output "alerts_topic_name" {
  description = "Name of the Service Alerts Pub/Sub topic"
  value       = google_pubsub_topic.service_alerts.name
}

output "alerts_topic_id" {
  description = "Full ID of the Service Alerts Pub/Sub topic"
  value       = google_pubsub_topic.service_alerts.id
}

output "gtfs_ace_subscription_name" {
  description = "Name of the GTFS-RT ACE Pub/Sub subscription"
  value       = google_pubsub_subscription.gtfs_rt.name
}

output "gtfs_bdfm_subscription_name" {
  description = "Name of the GTFS-RT BDFM Pub/Sub subscription"
  value       = google_pubsub_subscription.gtfs_rt_bdfm.name
}

output "alerts_subscription_name" {
  description = "Name of the Service Alerts Pub/Sub subscription"
  value       = google_pubsub_subscription.service_alerts.name
}

# BigQuery outputs
output "bigquery_dataset_id" {
  description = "BigQuery dataset ID"
  value       = google_bigquery_dataset.subway.dataset_id
}

output "vehicle_positions_table_id" {
  description = "Full table ID for vehicle positions"
  value       = "${google_bigquery_dataset.subway.project}:${google_bigquery_dataset.subway.dataset_id}.${google_bigquery_table.vehicle_positions.table_id}"
}

output "service_alerts_table_id" {
  description = "Full table ID for service alerts"
  value       = "${google_bigquery_dataset.subway.project}:${google_bigquery_dataset.subway.dataset_id}.${google_bigquery_table.service_alerts.table_id}"
}

# Compute outputs
output "poller_vm_name" {
  description = "Name of the poller VM"
  value       = google_compute_instance.poller.name
}

output "poller_vm_ip" {
  description = "External IP of the poller VM"
  value       = google_compute_instance.poller.network_interface[0].access_config[0].nat_ip
}

output "poller_vm_internal_ip" {
  description = "Internal IP of the poller VM"
  value       = google_compute_instance.poller.network_interface[0].network_ip
}

# Service Account outputs
output "poller_service_account" {
  description = "Email of the poller service account"
  value       = google_service_account.poller.email
}

output "dataflow_service_account" {
  description = "Email of the Dataflow service account"
  value       = google_service_account.dataflow.email
}

# GCS outputs
output "dataflow_staging_bucket" {
  description = "GCS bucket for Dataflow staging"
  value       = google_storage_bucket.dataflow_staging.name
}

output "dataflow_temp_bucket" {
  description = "GCS bucket for Dataflow temp files"
  value       = google_storage_bucket.dataflow_temp.name
}

# Connection strings for applications
output "connection_config" {
  description = "Configuration values for the poller application"
  value = {
    gtfs_ace_topic  = google_pubsub_topic.gtfs_rt.id
    gtfs_bdfm_topic = google_pubsub_topic.gtfs_rt_bdfm.id
    alerts_topic    = google_pubsub_topic.service_alerts.id
    project_id      = var.project_id
    vehicle_positions_table = "${var.project_id}:${google_bigquery_dataset.subway.dataset_id}.${google_bigquery_table.vehicle_positions.table_id}"
    alerts_table    = "${var.project_id}:${google_bigquery_dataset.subway.dataset_id}.${google_bigquery_table.service_alerts.table_id}"
  }
}
