"""
BigQuery Schema Definitions for NYC Subway Data
"""

from typing import Dict, List

# Schema for vehicle_positions table - captures real-time train positions
VEHICLE_POSITIONS_SCHEMA = {
    "fields": [
        # Entity identifiers
        {"name": "entity_id", "type": "STRING", "mode": "REQUIRED"},
        
        # Trip information
        {"name": "trip_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "route_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "start_time", "type": "STRING", "mode": "NULLABLE"},
        {"name": "start_date", "type": "STRING", "mode": "NULLABLE"},
        
        # Extracted from trip_id
        {"name": "direction", "type": "STRING", "mode": "REQUIRED"},  # N or S
        {"name": "path_id", "type": "STRING", "mode": "NULLABLE"},    # e.g., "55R"
        
        # MTA Extension Fields - Track Information
        {"name": "train_id", "type": "STRING", "mode": "NULLABLE"},        # Physical train identifier
        {"name": "nyct_direction", "type": "STRING", "mode": "NULLABLE"},  # NORTH, SOUTH, EAST, WEST
        {"name": "scheduled_track", "type": "STRING", "mode": "NULLABLE"}, # Pre-planned track (e.g., "F3")
        {"name": "actual_track", "type": "STRING", "mode": "NULLABLE"},    # Real-time track assignment (e.g., "F3")
        
        # Current position
        {"name": "stop_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "current_stop_sequence", "type": "INTEGER", "mode": "NULLABLE"},
        {"name": "current_status", "type": "STRING", "mode": "NULLABLE"},  # STOPPED_AT, INCOMING_AT, IN_TRANSIT_TO
        
        # Timestamps
        {"name": "vehicle_timestamp", "type": "TIMESTAMP", "mode": "REQUIRED"},  # When vehicle reported
        {"name": "feed_timestamp", "type": "TIMESTAMP", "mode": "REQUIRED"},     # Feed generation time
        {"name": "ingest_time", "type": "TIMESTAMP", "mode": "REQUIRED"},        # When we received it
    ]
}

# Schema for service_alerts table
SERVICE_ALERTS_SCHEMA = {
    "fields": [
        {"name": "alert_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "alert_type", "type": "STRING", "mode": "NULLABLE"},
        {"name": "affected_routes", "type": "STRING", "mode": "REPEATED"},
        {"name": "affected_stops", "type": "STRING", "mode": "REPEATED"},
        {"name": "active_period_start", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "active_period_end", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "header_text", "type": "STRING", "mode": "NULLABLE"},
        {"name": "description_text", "type": "STRING", "mode": "NULLABLE"},
        {"name": "created_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "updated_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
        {"name": "feed_timestamp", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "ingest_time", "type": "TIMESTAMP", "mode": "REQUIRED"},
    ]
}


def get_vehicle_positions_schema_string() -> str:
    """Get vehicle positions schema as comma-separated string for BigQuery IO."""
    fields = []
    for field in VEHICLE_POSITIONS_SCHEMA["fields"]:
        field_str = f"{field['name']}:{field['type']}"
        fields.append(field_str)
    return ",".join(fields)


def get_alerts_schema_string() -> str:
    """Get alerts schema as comma-separated string for BigQuery IO."""
    fields = []
    for field in SERVICE_ALERTS_SCHEMA["fields"]:
        field_type = field["type"]
        if field["mode"] == "REPEATED":
            field_type = f"ARRAY<{field_type}>"
        field_str = f"{field['name']}:{field_type}"
        fields.append(field_str)
    return ",".join(fields)


# Backwards compatibility aliases
SENSOR_DATA_SCHEMA = VEHICLE_POSITIONS_SCHEMA
get_sensor_data_schema_string = get_vehicle_positions_schema_string
