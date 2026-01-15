# Pub/Sub Configuration for GTFS-RT and Service Alerts

# Dead Letter Topic for failed messages
resource "google_pubsub_topic" "dead_letter" {
  name = "subway-dead-letter"

  message_retention_duration = "604800s" # 7 days

  depends_on = [google_project_service.apis]
}

# GTFS-RT Topic for vehicle positions and trip updates
resource "google_pubsub_topic" "gtfs_rt" {
  name = "gtfs-rt-ace"

  message_retention_duration = "86400s" # 24 hours

  labels = {
    environment = var.environment
    feed_type   = "gtfs-rt"
    routes      = "ace"
  }

  depends_on = [google_project_service.apis]
}

# Service Alerts Topic
resource "google_pubsub_topic" "service_alerts" {
  name = "service-alerts"

  message_retention_duration = "86400s" # 24 hours

  labels = {
    environment = var.environment
    feed_type   = "alerts"
  }

  depends_on = [google_project_service.apis]
}

# Subscription for GTFS-RT messages (consumed by Dataflow)
resource "google_pubsub_subscription" "gtfs_rt" {
  name  = "gtfs-rt-ace-dataflow"
  topic = google_pubsub_topic.gtfs_rt.id

  # 7 days retention
  message_retention_duration = "604800s"
  retain_acked_messages      = false

  # Acknowledgement deadline
  ack_deadline_seconds = 60

  # Exactly-once delivery for streaming
  enable_exactly_once_delivery = true

  # Exponential backoff for retries
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  # Dead letter policy
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }

  # Expiration policy (never expire)
  expiration_policy {
    ttl = ""
  }

  labels = {
    environment = var.environment
    consumer    = "dataflow"
  }
}

# Subscription for Service Alerts (consumed by Dataflow)
resource "google_pubsub_subscription" "service_alerts" {
  name  = "service-alerts-dataflow"
  topic = google_pubsub_topic.service_alerts.id

  message_retention_duration = "604800s"
  retain_acked_messages      = false

  ack_deadline_seconds = 60

  enable_exactly_once_delivery = true

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }

  expiration_policy {
    ttl = ""
  }

  labels = {
    environment = var.environment
    consumer    = "dataflow"
  }
}

# Dead letter subscription for monitoring failed messages
resource "google_pubsub_subscription" "dead_letter" {
  name  = "subway-dead-letter-monitor"
  topic = google_pubsub_topic.dead_letter.id

  message_retention_duration = "604800s"
  retain_acked_messages      = true

  ack_deadline_seconds = 300

  expiration_policy {
    ttl = ""
  }

  labels = {
    environment = var.environment
    purpose     = "monitoring"
  }
}

# Grant Pub/Sub publisher role to dead letter topic for retries
resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  topic  = google_pubsub_topic.dead_letter.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "dead_letter_subscriber" {
  subscription = google_pubsub_subscription.gtfs_rt.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "alerts_dead_letter_subscriber" {
  subscription = google_pubsub_subscription.service_alerts.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

# Get current project for service account reference
data "google_project" "current" {}
