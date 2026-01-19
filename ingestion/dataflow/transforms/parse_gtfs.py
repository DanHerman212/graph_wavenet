"""
Parse GTFS-RT Vehicle Position Messages

Transforms for extracting vehicle position data from GTFS-RT JSON messages.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterator, Optional

import apache_beam as beam
from apache_beam.metrics import Metrics

logger = logging.getLogger(__name__)


def parse_trip_id(trip_id: str) -> Dict[str, Optional[str]]:
    """Extract direction and path_id from trip_id.
    
    Format: "060300_A..N55R"
        - 060300: start time identifier
        - A: route_id
        - N: direction (N=northbound, S=southbound)
        - 55R: path identifier
    
    Args:
        trip_id: GTFS trip identifier string
        
    Returns:
        Dictionary with 'direction' and 'path_id' keys
    """
    try:
        # Split on underscore: ["060300", "A..N55R"]
        parts = trip_id.split("_")
        if len(parts) < 2:
            return {"direction": "U", "path_id": None}
        
        # Split on double dot: ["A", "N55R"]
        route_and_path = parts[1].split("..")
        if len(route_and_path) < 2:
            return {"direction": "U", "path_id": None}
        
        direction_path = route_and_path[1]  # "N55R"
        
        if not direction_path:
            return {"direction": "U", "path_id": None}
        
        direction = direction_path[0]  # "N"
        path_id = direction_path[1:] if len(direction_path) > 1 else None  # "55R"
        
        # Validate direction
        if direction not in ("N", "S"):
            direction = "U"  # Unknown
        
        return {"direction": direction, "path_id": path_id}
        
    except Exception:
        return {"direction": "U", "path_id": None}


def unix_to_iso(timestamp) -> str:
    """Convert Unix timestamp to ISO format string.
    
    Args:
        timestamp: Unix timestamp as int, float, or string
        
    Returns:
        ISO format timestamp string
    """
    if isinstance(timestamp, str):
        timestamp = int(timestamp)
    return datetime.utcfromtimestamp(timestamp).isoformat() + "Z"


class ExtractVehiclePositions(beam.DoFn):
    """Extract vehicle position entities from GTFS-RT feed JSON.
    
    Now processes both vehicle positions and trip_updates to capture track_id.
    For trip_updates, we extract future stop arrivals with track assignments.
    """
    
    def __init__(self):
        self.messages_processed = Metrics.counter(self.__class__, "messages_processed")
        self.vehicles_extracted = Metrics.counter(self.__class__, "vehicles_extracted")
        self.trip_updates_processed = Metrics.counter(self.__class__, "trip_updates_processed")
        self.parse_errors = Metrics.counter(self.__class__, "parse_errors")
        self.invalid_vehicles = Metrics.counter(self.__class__, "invalid_vehicles")
    
    def process(self, element) -> Iterator[Dict[str, Any]]:
        """Process a GTFS-RT feed message and extract vehicle positions.
        
        Args:
            element: Pub/Sub message containing JSON feed data
            
        Yields:
            Flattened vehicle position records for BigQuery
        """
        try:
            # Decode JSON message
            if isinstance(element, bytes):
                data = json.loads(element.decode("utf-8"))
            else:
                data = json.loads(element)
            
            self.messages_processed.inc()
            
            # Extract feed-level metadata
            header = data.get("header", {})
            feed_timestamp = header.get("timestamp")
            ingest_time = data.get("_ingest_time")
            
            if feed_timestamp:
                feed_timestamp = unix_to_iso(feed_timestamp)
            
            # Process each entity
            for entity in data.get("entity", []):
                # Process vehicle positions
                if "vehicle" in entity:
                    record = self._process_vehicle_entity(entity, feed_timestamp, ingest_time)
                    if record:
                        self.vehicles_extracted.inc()
                        yield record
                
                # Process trip updates (contains track_id for future stops)
                elif "trip_update" in entity:
                    for record in self._process_trip_update_entity(entity, feed_timestamp, ingest_time):
                        self.trip_updates_processed.inc()
                        yield record
                
        except json.JSONDecodeError as e:
            self.parse_errors.inc()
            logger.error(f"JSON parse error: {e}")
        except Exception as e:
            self.parse_errors.inc()
            logger.error(f"Error processing message: {e}")
    
    def _process_vehicle_entity(self, entity: Dict, feed_timestamp: str, ingest_time: str) -> Optional[Dict[str, Any]]:
        """Process a vehicle position entity."""
        vehicle = entity["vehicle"]
        trip = vehicle.get("trip", {})
        
        # Extract required fields
        trip_id = trip.get("trip_id")
        route_id = trip.get("route_id")
        stop_id = vehicle.get("stop_id")
        vehicle_timestamp = vehicle.get("timestamp")
        
        # Validate required fields
        if not all([trip_id, route_id, stop_id, vehicle_timestamp]):
            self.invalid_vehicles.inc()
            return None
        
        # Parse direction and path from trip_id
        # Parse direction and path from trip_id
        parsed = parse_trip_id(trip_id)
        
        # Extract MTA extension fields (added by poller)
        train_id = trip.get("train_id")
        nyct_direction = trip.get("direction")  # NORTH/SOUTH/EAST/WEST from extension
        
        # Build output record
        return {
            "entity_id": entity.get("id"),
            "trip_id": trip_id,
            "route_id": route_id,
            "start_time": trip.get("start_time"),
            "start_date": trip.get("start_date"),
            "direction": parsed["direction"],
            "path_id": parsed["path_id"],
            "train_id": train_id,
            "nyct_direction": nyct_direction,
            "scheduled_track": None,  # Not in vehicle position
            "actual_track": None,     # Not in vehicle position
            "stop_id": stop_id,
            "current_stop_sequence": vehicle.get("current_stop_sequence"),
            "current_status": vehicle.get("current_status"),
            "vehicle_timestamp": unix_to_iso(vehicle_timestamp),
            "feed_timestamp": feed_timestamp,
            "ingest_time": ingest_time,
        }
    
    def _process_trip_update_entity(self, entity: Dict, feed_timestamp: str, ingest_time: str) -> Iterator[Dict[str, Any]]:
        """Process a trip_update entity and extract future stop arrivals with track data."""
        trip_update = entity.get("trip_update", {})
        trip = trip_update.get("trip", {})
        
        trip_id = trip.get("trip_id")
        route_id = trip.get("route_id")
        
        if not trip_id or not route_id:
            return
        
        # Parse direction and path from trip_id
        parsed = parse_trip_id(trip_id)
        
        # Extract MTA extension fields
        train_id = trip.get("train_id")
        nyct_direction = trip.get("direction")
        
        # Process each stop time update
        for stop_update in trip_update.get("stop_time_update", []):
            stop_id = stop_update.get("stop_id")
            
            # Get arrival or departure time
            arrival_time = None
            if "arrival" in stop_update and stop_update["arrival"].get("time"):
                arrival_time = stop_update["arrival"]["time"]
            elif "departure" in stop_update and stop_update["departure"].get("time"):
                arrival_time = stop_update["departure"]["time"]
            
            if not stop_id or not arrival_time:
                continue
            
            # Extract track information
            scheduled_track = stop_update.get("scheduled_track")
            actual_track = stop_update.get("actual_track")
            
            yield {
                "entity_id": f"{entity.get('id')}__{stop_id}",  # Unique ID for each stop
                "trip_id": trip_id,
                "route_id": route_id,
                "start_time": trip.get("start_time"),
                "start_date": trip.get("start_date"),
                "direction": parsed["direction"],
                "path_id": parsed["path_id"],
                "train_id": train_id,
                "nyct_direction": nyct_direction,
                "scheduled_track": scheduled_track,
                "actual_track": actual_track,
                "stop_id": stop_id,
                "current_stop_sequence": stop_update.get("stop_sequence"),
                "current_status": "IN_TRANSIT_TO",  # Future stop
                "vehicle_timestamp": unix_to_iso(arrival_time),
                "feed_timestamp": feed_timestamp,
                "ingest_time": ingest_time,
            }


class ValidateVehiclePosition(beam.DoFn):
    """Validate vehicle position records before writing to BigQuery."""
    
    def __init__(self):
        self.valid_records = Metrics.counter(self.__class__, "valid_records")
        self.invalid_records = Metrics.counter(self.__class__, "invalid_records")
    
    def process(self, element) -> Iterator[Dict[str, Any]]:
        """Validate a vehicle position record.
        
        Args:
            element: Vehicle position dictionary
            
        Yields:
            Validated record if all required fields present
        """
        required_fields = [
            "entity_id", "trip_id", "route_id", "direction",
            "stop_id", "vehicle_timestamp", "feed_timestamp", "ingest_time"
        ]
        
        for field in required_fields:
            if not element.get(field):
                self.invalid_records.inc()
                logger.warning(f"Missing required field: {field}")
                return
        
        # Validate route_id is from ACE or BDFM feeds
        valid_routes = ("A", "B", "C", "D", "E", "F", "H", "M", "S")
        if element["route_id"] not in valid_routes:
            self.invalid_records.inc()
            logger.warning(f"Invalid route_id: {element['route_id']}")
            return
        
        # Validate direction
        if element["direction"] not in ("N", "S", "U"):
            element["direction"] = "U"
        
        self.valid_records.inc()
        yield element
