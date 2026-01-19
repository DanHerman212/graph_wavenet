# Pub/Sub Configuration for GTFS-RT and Service Alerts

# Dead Letter Topic for failed messages
resource "google_pubsub_topic" "dead_letter" {
  name = "subway-dead-letter"

  message_retention_duration = "604800s" # 7 days

  depends_on = [google_project_service.apis]
}

# GTFS-RT Topic for ACE vehicle positions and trip updates
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

# GTFS-RT Topic for BDFM vehicle positions and trip updates
resource "google_pubsub_topic" "gtfs_rt_bdfm" {
  name = "gtfs-rt-bdfm"

  message_retention_duration = "86400s" # 24 hours

  labels = {
    environment = var.environment
    feed_type   = "gtfs-rt"
    routes      = "bdfm"
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

# Subscription for GTFS-RT ACE messages (consumed by Dataflow)
# Note: Dataflow handles its own deduplication and retry logic
resource "google_pubsub_subscription" "gtfs_rt" {
  name  = "gtfs-rt-ace-dataflow"
  topic = google_pubsub_topic.gtfs_rt.id

  # 7 days retention
  message_retention_duration = "604800s"
  retain_acked_messages      = false

  # Acknowledgement deadline
  ack_deadline_seconds = 60

  # Expiration policy (never expire)
  expiration_policy {
    ttl = ""
  }

  labels = {
    environment = var.environment
    consumer    = "dataflow"
  }
}

# Subscription for GTFS-RT BDFM messages (consumed by Dataflow)
resource "google_pubsub_subscription" "gtfs_rt_bdfm" {
  name  = "gtfs-rt-bdfm-dataflow"
  topic = google_pubsub_topic.gtfs_rt_bdfm.id

  # 7 days retention
  message_retention_duration = "604800s"
  retain_acked_messages      = false

  # Acknowledgement deadline
  ack_deadline_seconds = 60

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
# Note: Dataflow handles its own deduplication and retry logic
resource "google_pubsub_subscription" "service_alerts" {
  name  = "service-alerts-dataflow"
  topic = google_pubsub_topic.service_alerts.id

  message_retention_duration = "604800s"
  retain_acked_messages      = false

  ack_deadline_seconds = 60

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

# =============================================================================
# TEST SUBSCRIPTIONS - For testing stateful enrichment pipeline in parallel
# =============================================================================

# Test subscription for GTFS-RT ACE messages
resource "google_pubsub_subscription" "gtfs_rt_test" {
  name  = "gtfs-rt-ace-dataflow-test"
  topic = google_pubsub_topic.gtfs_rt.id

  message_retention_duration = "604800s"
  retain_acked_messages      = false
  ack_deadline_seconds       = 60

  expiration_policy {
    ttl = ""
  }

  labels = {
    environment = var.environment
    consumer    = "dataflow-test"
    purpose     = "testing-stateful-enrichment"
  }
}

# Test subscription for GTFS-RT BDFM messages
resource "google_pubsub_subscription" "gtfs_rt_bdfm_test" {
  name  = "gtfs-rt-bdfm-dataflow-test"
  topic = google_pubsub_topic.gtfs_rt_bdfm.id

  message_retention_duration = "604800s"
  retain_acked_messages      = false
  ack_deadline_seconds       = 60

  expiration_policy {
    ttl = ""
  }

  labels = {
    environment = var.environment
    consumer    = "dataflow-test"
    purpose     = "testing-stateful-enrichment"
  }
}

# Test subscription for Service Alerts
resource "google_pubsub_subscription" "service_alerts_test" {
  name  = "service-alerts-dataflow-test"
  topic = google_pubsub_topic.service_alerts.id

  message_retention_duration = "604800s"
  retain_acked_messages      = false
  ack_deadline_seconds       = 60

  expiration_policy {
    ttl = ""
  }

  labels = {
    environment = var.environment
    consumer    = "dataflow-test"
    purpose     = "testing-stateful-enrichment"
  }
}

# Get current project for service account reference
data "google_project" "current" {}
