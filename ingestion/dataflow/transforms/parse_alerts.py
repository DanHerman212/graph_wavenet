"""
Parse Service Alerts Transform

Transforms for extracting service alerts from MTA JSON feed.
Filters to A/C/E lines only.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Set

import apache_beam as beam
from apache_beam.metrics import Metrics

logger = logging.getLogger(__name__)

# Routes we care about
TARGET_ROUTES = {"A", "C", "E"}


def unix_to_iso(timestamp) -> Optional[str]:
    """Convert Unix timestamp to ISO format string.
    
    Args:
        timestamp: Unix timestamp as int, float, or string
        
    Returns:
        ISO format timestamp string, or None if invalid
    """
    if timestamp is None:
        return None
    try:
        if isinstance(timestamp, str):
            timestamp = int(timestamp)
        return datetime.utcfromtimestamp(timestamp).isoformat() + "Z"
    except (ValueError, TypeError, OSError):
        return None


def get_plain_text(translation_obj: Optional[Dict]) -> Optional[str]:
    """Extract plain English text from a translation object.
    
    Args:
        translation_obj: Object with 'translation' array containing text/language pairs
        
    Returns:
        Plain English text, or None if not found
    """
    if not translation_obj:
        return None
    
    translations = translation_obj.get("translation", [])
    for t in translations:
        if t.get("language") == "en":
            return t.get("text")
    
    # Fallback to first translation if no 'en' found
    if translations:
        return translations[0].get("text")
    
    return None


class ExtractAlerts(beam.DoFn):
    """Extract service alert entities from MTA alerts JSON feed.
    
    Filters to alerts affecting A/C/E lines only.
    """
    
    def __init__(self):
        self.messages_processed = Metrics.counter(self.__class__, "messages_processed")
        self.alerts_extracted = Metrics.counter(self.__class__, "alerts_extracted")
        self.alerts_filtered = Metrics.counter(self.__class__, "alerts_filtered")
        self.parse_errors = Metrics.counter(self.__class__, "parse_errors")
    
    def process(self, element) -> Iterator[Dict[str, Any]]:
        """Process an MTA alerts feed message and extract relevant alerts.
        
        Args:
            element: Pub/Sub message containing JSON feed data
            
        Yields:
            Flattened alert records for BigQuery
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
            feed_timestamp = unix_to_iso(header.get("timestamp"))
            ingest_time = data.get("_ingest_time")
            
            # Process each entity
            for entity in data.get("entity", []):
                alert = entity.get("alert")
                if not alert:
                    continue
                
                # Extract affected routes and stops
                informed_entities = alert.get("informed_entity", [])
                affected_routes: Set[str] = set()
                affected_stops: Set[str] = set()
                
                for ie in informed_entities:
                    route_id = ie.get("route_id")
                    if route_id:
                        affected_routes.add(route_id)
                    stop_id = ie.get("stop_id")
                    if stop_id:
                        affected_stops.add(stop_id)
                
                # Filter: only include alerts affecting A/C/E
                ace_routes = affected_routes & TARGET_ROUTES
                if not ace_routes:
                    self.alerts_filtered.inc()
                    continue
                
                # Extract Mercury extension fields
                mercury = alert.get("transit_realtime.mercury_alert", {})
                
                # Extract active periods (use first period for simplicity)
                active_periods = alert.get("active_period", [])
                active_start = None
                active_end = None
                if active_periods:
                    active_start = unix_to_iso(active_periods[0].get("start"))
                    active_end = unix_to_iso(active_periods[0].get("end"))
                
                # Build output record
                record = {
                    "alert_id": entity.get("id"),
                    "alert_type": mercury.get("alert_type"),
                    "affected_routes": sorted(ace_routes),  # Only A/C/E routes
                    "affected_stops": sorted(affected_stops),
                    "active_period_start": active_start,
                    "active_period_end": active_end,
                    "header_text": get_plain_text(alert.get("header_text")),
                    "description_text": get_plain_text(alert.get("description_text")),
                    "created_at": unix_to_iso(mercury.get("created_at")),
                    "updated_at": unix_to_iso(mercury.get("updated_at")),
                    "feed_timestamp": feed_timestamp,
                    "ingest_time": ingest_time,
                }
                
                self.alerts_extracted.inc()
                yield record
                
        except json.JSONDecodeError as e:
            self.parse_errors.inc()
            logger.error(f"JSON parse error: {e}")
        except Exception as e:
            self.parse_errors.inc()
            logger.error(f"Error processing message: {e}")


class ValidateAlert(beam.DoFn):
    """Validate alert records before writing to BigQuery."""
    
    def __init__(self):
        self.valid_records = Metrics.counter(self.__class__, "valid_records")
        self.invalid_records = Metrics.counter(self.__class__, "invalid_records")
    
    def process(self, element) -> Iterator[Dict[str, Any]]:
        """Validate an alert record.
        
        Args:
            element: Alert dictionary
            
        Yields:
            Validated record if all required fields present
        """
        required_fields = ["alert_id", "feed_timestamp", "ingest_time"]
        
        for field in required_fields:
            if not element.get(field):
                self.invalid_records.inc()
                logger.warning(f"Missing required field: {field}")
                return
        
        # Ensure arrays are lists (not None)
        if element.get("affected_routes") is None:
            element["affected_routes"] = []
        if element.get("affected_stops") is None:
            element["affected_stops"] = []
        
        self.valid_records.inc()
        yield element
