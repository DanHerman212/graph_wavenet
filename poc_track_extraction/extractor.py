#!/usr/bin/env python3
"""
POC Track ID Extractor
Parses saved GTFS-RT feeds to extract actual_track data from MTA extensions.
"""

import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Add proto/generated to path so we can import the compiled protobuf modules
sys.path.insert(0, str(Path(__file__).parent / "proto" / "generated"))

import gtfs_realtime_pb2
import nyct_subway_pb2  # This registers the extension ID 1001


def extract_track_data(feed_file: Path):
    """
    Extract track_id information from a saved GTFS-RT feed.
    
    Args:
        feed_file: Path to the .pb feed file
        
    Returns:
        List of dicts with trip/stop/track information
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    
    # Load the raw binary file
    with open(feed_file, "rb") as f:
        feed.ParseFromString(f.read())
    
    results = []
    
    # Iterate through entities in the feed
    for entity in feed.entity:
        if not entity.HasField('trip_update'):
            continue
            
        trip_update = entity.trip_update
        trip_id = trip_update.trip.trip_id
        route_id = trip_update.trip.route_id if trip_update.trip.HasField('route_id') else 'N/A'
        
        # Check for NYCT trip descriptor extension
        train_id = None
        direction = None
        if trip_update.trip.HasExtension(nyct_subway_pb2.nyct_trip_descriptor):
            nyct_trip = trip_update.trip.Extensions[nyct_subway_pb2.nyct_trip_descriptor]
            if nyct_trip.HasField('train_id'):
                train_id = nyct_trip.train_id
            if nyct_trip.HasField('direction'):
                direction = nyct_trip.Direction.Name(nyct_trip.direction)
        
        # Iterate through stop updates (future stops)
        for stop_update in trip_update.stop_time_update:
            stop_id = stop_update.stop_id
            
            # Initialize track fields
            scheduled_track = None
            actual_track = None
            
            # CHECK FOR THE MTA EXTENSION
            if stop_update.HasExtension(nyct_subway_pb2.nyct_stop_time_update):
                # Extract the extension object
                nyct_ext = stop_update.Extensions[nyct_subway_pb2.nyct_stop_time_update]
                
                # Check for track fields
                if nyct_ext.HasField('scheduled_track'):
                    scheduled_track = nyct_ext.scheduled_track
                    
                if nyct_ext.HasField('actual_track'):
                    actual_track = nyct_ext.actual_track
            
            # Only include if we have track data
            if scheduled_track or actual_track:
                results.append({
                    'trip_id': trip_id,
                    'route_id': route_id,
                    'train_id': train_id,
                    'direction': direction,
                    'stop_id': stop_id,
                    'scheduled_track': scheduled_track,
                    'actual_track': actual_track,
                })
    
    return results


def process_all_feeds(feeds_dir: Path):
    """
    Process all .pb files in the feeds directory.
    
    Args:
        feeds_dir: Directory containing saved feed files
    """
    feed_files = sorted(feeds_dir.glob("*.pb"))
    
    if not feed_files:
        print(f"No feed files found in {feeds_dir}")
        return
    
    print(f"Found {len(feed_files)} feed files to process")
    print("=" * 80)
    
    all_track_data = []
    feed_summary = []
    
    for feed_file in feed_files:
        print(f"\nProcessing: {feed_file.name}")
        
        try:
            track_data = extract_track_data(feed_file)
            all_track_data.extend(track_data)
            
            # Count tracks with actual_track field
            with_actual = sum(1 for d in track_data if d['actual_track'])
            with_scheduled = sum(1 for d in track_data if d['scheduled_track'])
            
            print(f"  ✓ Found {len(track_data)} stop updates with track data")
            print(f"    - {with_actual} have actual_track")
            print(f"    - {with_scheduled} have scheduled_track")
            
            feed_summary.append({
                'file': feed_file.name,
                'total': len(track_data),
                'actual': with_actual,
                'scheduled': with_scheduled
            })
            
        except Exception as e:
            print(f"  ✗ Error processing {feed_file.name}: {e}")
            continue
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    # Overall statistics
    total_entries = len(all_track_data)
    with_actual = sum(1 for d in all_track_data if d['actual_track'])
    with_scheduled = sum(1 for d in all_track_data if d['scheduled_track'])
    
    print(f"\nTotal stop updates with track data: {total_entries}")
    print(f"  - With actual_track: {with_actual} ({100*with_actual/total_entries:.1f}%)")
    print(f"  - With scheduled_track: {with_scheduled} ({100*with_scheduled/total_entries:.1f}%)")
    
    # Show unique track codes found
    if with_actual > 0:
        unique_actual = set(d['actual_track'] for d in all_track_data if d['actual_track'])
        print(f"\nUnique actual_track codes found: {sorted(unique_actual)}")
    
    if with_scheduled > 0:
        unique_scheduled = set(d['scheduled_track'] for d in all_track_data if d['scheduled_track'])
        print(f"Unique scheduled_track codes found: {sorted(unique_scheduled)}")
    
    # Show sample data
    if all_track_data:
        print("\n" + "-" * 80)
        print("SAMPLE TRACK DATA (first 10 entries with actual_track):")
        print("-" * 80)
        samples = [d for d in all_track_data if d['actual_track']][:10]
        
        for i, data in enumerate(samples, 1):
            print(f"\n{i}. Route {data['route_id']} - Trip {data['trip_id']}")
            print(f"   Stop: {data['stop_id']}")
            print(f"   Train ID: {data['train_id']}")
            print(f"   Direction: {data['direction']}")
            print(f"   Scheduled Track: {data['scheduled_track']}")
            print(f"   Actual Track: {data['actual_track']}")
    
    # Export to CSV
    csv_file = Path(__file__).parent / "track_data_extract.csv"
    export_to_csv(all_track_data, csv_file)
    print(f"\n✓ Full data exported to: {csv_file}")


def export_to_csv(track_data, output_file):
    """Export track data to CSV."""
    import csv
    
    if not track_data:
        return
    
    with open(output_file, 'w', newline='') as f:
        fieldnames = ['trip_id', 'route_id', 'train_id', 'direction', 'stop_id', 
                      'scheduled_track', 'actual_track']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(track_data)


if __name__ == "__main__":
    feeds_dir = Path(__file__).parent / "feeds"
    process_all_feeds(feeds_dir)
