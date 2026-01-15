"""
BigQuery Schema Definitions for NYC Subway Data

Provides schema definitions used by the Dataflow pipeline.
"""

from . import (
    VEHICLE_POSITIONS_SCHEMA,
    SERVICE_ALERTS_SCHEMA,
    get_vehicle_positions_schema_string,
    get_alerts_schema_string,
    # Backwards compatibility
    SENSOR_DATA_SCHEMA,
    get_sensor_data_schema_string,
)

__all__ = [
    "VEHICLE_POSITIONS_SCHEMA",
    "SERVICE_ALERTS_SCHEMA",
    "get_vehicle_positions_schema_string",
    "get_alerts_schema_string",
    # Backwards compatibility
    "SENSOR_DATA_SCHEMA",
    "get_sensor_data_schema_string",
]
