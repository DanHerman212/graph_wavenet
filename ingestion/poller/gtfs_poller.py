"""
GTFS-RT Poller for NYC Subway

Fetches GTFS-RT protobuf data from MTA, converts to JSON,
and publishes to Pub/Sub.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from google.cloud import pubsub_v1
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2

from config import Config, get_config

logger = logging.getLogger(__name__)


class GTFSPoller:
    """Fetches GTFS-RT feed, converts to JSON, and publishes to Pub/Sub."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        self.publisher = pubsub_v1.PublisherClient()
        self.topic_path = self.config.gtfs_topic
        self._session = requests.Session()

    def fetch_feed(self) -> Optional[bytes]:
        """Fetch the raw GTFS-RT feed from MTA."""
        for attempt in range(self.config.max_retries):
            try:
                response = self._session.get(
                    self.config.gtfs_ace_url,
                    timeout=self.config.request_timeout_seconds,
                )
                response.raise_for_status()
                return response.content
            except requests.exceptions.RequestException as e:
                logger.warning(f"Fetch failed (attempt {attempt + 1}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_backoff_seconds * (2 ** attempt))
        return None

    def protobuf_to_json(self, data: bytes) -> Optional[str]:
        """Convert GTFS-RT protobuf to JSON string."""
        try:
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(data)
            feed_dict = MessageToDict(feed, preserving_proto_field_name=True)
            feed_dict["_ingest_time"] = datetime.now(timezone.utc).isoformat()
            return json.dumps(feed_dict)
        except Exception as e:
            logger.error(f"Failed to parse protobuf: {e}")
            return None

    def publish(self, json_data: str) -> bool:
        """Publish JSON feed data to Pub/Sub."""
        try:
            future = self.publisher.publish(
                self.topic_path,
                json_data.encode("utf-8"),
                feed_type="gtfs-rt",
                feed_id="ace",
            )
            future.result(timeout=30)
            return True
        except Exception as e:
            logger.error(f"Failed to publish: {e}")
            return False

    def poll_once(self) -> dict:
        """Perform a single poll cycle."""
        raw_data = self.fetch_feed()
        if raw_data is None:
            return {"success": False, "bytes": 0, "entities": 0}

        json_data = self.protobuf_to_json(raw_data)
        if json_data is None:
            return {"success": False, "bytes": 0, "entities": 0}

        try:
            entity_count = len(json.loads(json_data).get("entity", []))
        except:
            entity_count = 0

        published = self.publish(json_data)
        return {"success": published, "bytes": len(json_data), "entities": entity_count}

    def run(self):
        """Run the polling loop continuously."""
        logger.info(f"Starting GTFS poller, interval: {self.config.poll_interval_seconds}s")
        while True:
            start_time = time.time()
            try:
                result = self.poll_once()
                if result["success"]:
                    logger.info(f"Published: {result['entities']} entities, {result['bytes']} bytes")
                else:
                    logger.warning("Poll failed")
            except Exception as e:
                logger.error(f"Error: {e}", exc_info=True)
            elapsed = time.time() - start_time
            sleep_time = max(0, self.config.poll_interval_seconds - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    GTFSPoller().run()


if __name__ == "__main__":
    main()
