# BigQuery Configuration for Subway Data Warehouse

# Dataset for subway data
resource "google_bigquery_dataset" "subway" {
  dataset_id    = var.bigquery_dataset_id
  friendly_name = "NYC Subway Data"
  description   = "Data warehouse for NYC Subway ACE and BDFM line vehicle positions and service alerts"
  location      = var.region

  default_table_expiration_ms = var.retention_days * 24 * 60 * 60 * 1000

  labels = {
    environment = var.environment
    project     = "graph-wavenet"
  }

  # Grant special group access for project owners/editors
  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }

  access {
    role          = "WRITER"
    special_group = "projectWriters"
  }

  access {
    role          = "READER"
    special_group = "projectReaders"
  }

  # Dataflow service account needs write access
  access {
    role          = "WRITER"
    user_by_email = google_service_account.dataflow.email
  }

  depends_on = [google_project_service.apis]
}

# Table for vehicle positions (real-time train locations)
resource "google_bigquery_table" "vehicle_positions" {
  dataset_id          = google_bigquery_dataset.subway.dataset_id
  table_id            = "vehicle_positions"
  deletion_protection = false

  description = "Real-time vehicle positions for ACE and BDFM subway lines"

  time_partitioning {
    type  = "DAY"
    field = "vehicle_timestamp"
  }

  clustering = ["route_id", "direction", "stop_id"]

  schema = jsonencode([
    {
      name        = "entity_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Unique entity ID from GTFS-RT feed"
    },
    {
      name        = "trip_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "GTFS trip identifier"
    },
    {
      name        = "route_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Route identifier (A, C, E, or H)"
    },
    {
      name        = "start_time"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Scheduled trip start time (HH:MM:SS)"
    },
    {
      name        = "start_date"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Trip start date (YYYYMMDD)"
    },
    {
      name        = "direction"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Direction (N=Northbound, S=Southbound, U=Unknown)"
    },
    {
      name        = "path_id"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Path identifier extracted from trip_id (e.g., 55R)"
    },
    {
      name        = "stop_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Current station stop ID"
    },
    {
      name        = "current_stop_sequence"
      type        = "INTEGER"
      mode        = "NULLABLE"
      description = "Position of current stop in trip sequence"
    },
    {
      name        = "current_status"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Vehicle status (STOPPED_AT, INCOMING_AT, IN_TRANSIT_TO)"
    },
    {
      name        = "vehicle_timestamp"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "When vehicle reported this position"
    },
    {
      name        = "feed_timestamp"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "When MTA generated the feed"
    },
    {
      name        = "ingest_time"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "When message was ingested by poller"
    }
  ])

  labels = {
    environment = var.environment
    data_type   = "vehicle-positions"
  }
}

# Table for service alerts
resource "google_bigquery_table" "service_alerts" {
  dataset_id          = google_bigquery_dataset.subway.dataset_id
  table_id            = "service_alerts"
  deletion_protection = false

  description = "Service alerts for ACE and BDFM subway lines (delays, planned work, incidents)"

  time_partitioning {
    type  = "DAY"
    field = "feed_timestamp"
  }

  clustering = ["alert_type"]

  schema = jsonencode([
    {
      name        = "alert_id"
      type        = "STRING"
      mode        = "REQUIRED"
      description = "Unique alert identifier from MTA feed"
    },
    {
      name        = "alert_type"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Alert category (Delays, Planned - Stops Skipped, etc.)"
    },
    {
      name        = "affected_routes"
      type        = "STRING"
      mode        = "REPEATED"
      description = "Routes affected by this alert (ACE and BDFM lines)"
    },
    {
      name        = "affected_stops"
      type        = "STRING"
      mode        = "REPEATED"
      description = "Stops mentioned in alert"
    },
    {
      name        = "active_period_start"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When alert becomes active"
    },
    {
      name        = "active_period_end"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When alert expires"
    },
    {
      name        = "header_text"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Short alert description"
    },
    {
      name        = "description_text"
      type        = "STRING"
      mode        = "NULLABLE"
      description = "Detailed alert description"
    },
    {
      name        = "created_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When alert was created"
    },
    {
      name        = "updated_at"
      type        = "TIMESTAMP"
      mode        = "NULLABLE"
      description = "When alert was last updated"
    },
    {
      name        = "feed_timestamp"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "When MTA generated the feed"
    },
    {
      name        = "ingest_time"
      type        = "TIMESTAMP"
      mode        = "REQUIRED"
      description = "When message was ingested by poller"
    }
  ])

  labels = {
    environment = var.environment
    data_type   = "service-alerts"
  }
}
