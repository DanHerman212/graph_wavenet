#!/usr/bin/env python3
"""
POC Poller for ACE Line - Track ID Extraction
Fetches GTFS-RT feed and saves raw binary snapshots for later parsing.
"""

import os
import time
import requests
from datetime import datetime
from pathlib import Path


# ACE Line feed URL (no API key needed for MTA feeds)
FEED_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-ace"

# Output directory
FEEDS_DIR = Path(__file__).parent / "feeds"
FEEDS_DIR.mkdir(exist_ok=True)


def poll_and_save(num_samples=10, interval_seconds=15):
    """
    Poll the ACE line feed multiple times and save raw binary snapshots.
    
    Args:
        num_samples: Number of feed samples to collect
        interval_seconds: Time between polls
    """
    print(f"Starting POC poller for ACE line")
    print(f"Will collect {num_samples} samples, {interval_seconds}s apart")
    print(f"Saving to: {FEEDS_DIR}")
    print("-" * 60)
    
    for i in range(num_samples):
        try:
            # Fetch the feed
            print(f"\n[{i+1}/{num_samples}] Fetching feed at {datetime.now().strftime('%H:%M:%S')}")
            response = requests.get(FEED_URL, timeout=10)
            response.raise_for_status()
            
            # CRITICAL: Save raw bytes, not decoded text
            timestamp = int(time.time())
            filename = FEEDS_DIR / f"gtfs_ace_{timestamp}.pb"
            
            with open(filename, "wb") as f:
                f.write(response.content)
            
            size_kb = len(response.content) / 1024
            print(f"✓ Saved {filename.name} ({size_kb:.1f} KB)")
            
            # Wait before next poll (skip on last iteration)
            if i < num_samples - 1:
                print(f"  Waiting {interval_seconds}s until next poll...")
                time.sleep(interval_seconds)
                
        except requests.RequestException as e:
            print(f"✗ Error fetching feed: {e}")
            continue
        except IOError as e:
            print(f"✗ Error saving file: {e}")
            continue
    
    print("\n" + "=" * 60)
    print(f"Collection complete! Saved {len(list(FEEDS_DIR.glob('*.pb')))} feed snapshots")
    print(f"Next step: Run extractor.py to parse track_id data")


if __name__ == "__main__":
    # Collect 10 samples over ~2.5 minutes
    poll_and_save(num_samples=10, interval_seconds=15)
