#!/usr/bin/env python3
"""
Comparison Script: Current Approach vs. Extension-Based Approach
Shows what data each method can capture from the same feed files.
"""

import sys
from pathlib import Path
from collections import defaultdict

# Add proto/generated to path
sys.path.insert(0, str(Path(__file__).parent / "proto" / "generated"))

import gtfs_realtime_pb2
import nyct_subway_pb2


def current_approach(feed_file: Path):
    """
    Simulate what the current parser extracts.
    Uses standard GTFS-RT fields only - NO extensions.
    
    Returns:
        List of dicts with standard GTFS-RT data
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    
    with open(feed_file, "rb") as f:
        feed.ParseFromString(f.read())
    
    results = []
    
    for entity in feed.entity:
        if not entity.HasField('trip_update'):
            continue
            
        trip_update = entity.trip_update
        
        # Standard GTFS-RT fields (what we currently capture)
        for stop_update in trip_update.stop_time_update:
            results.append({
                'trip_id': trip_update.trip.trip_id,
                'route_id': trip_update.trip.route_id if trip_update.trip.HasField('route_id') else 'N/A',
                'stop_id': stop_update.stop_id,
                'arrival_time': stop_update.arrival.time if stop_update.HasField('arrival') else None,
                'departure_time': stop_update.departure.time if stop_update.HasField('departure') else None,
                # NO track_id - not available in standard fields
            })
    
    return results


def extension_approach(feed_file: Path):
    """
    New approach using MTA extensions.
    Extracts track_id data that current approach misses.
    
    Returns:
        List of dicts with extension data
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    
    with open(feed_file, "rb") as f:
        feed.ParseFromString(f.read())
    
    results = []
    
    for entity in feed.entity:
        if not entity.HasField('trip_update'):
            continue
            
        trip_update = entity.trip_update
        
        # Extract extension data
        train_id = None
        direction = None
        if trip_update.trip.HasExtension(nyct_subway_pb2.nyct_trip_descriptor):
            nyct_trip = trip_update.trip.Extensions[nyct_subway_pb2.nyct_trip_descriptor]
            if nyct_trip.HasField('train_id'):
                train_id = nyct_trip.train_id
            if nyct_trip.HasField('direction'):
                direction = nyct_trip.Direction.Name(nyct_trip.direction)
        
        for stop_update in trip_update.stop_time_update:
            # Check for track extension
            actual_track = None
            scheduled_track = None
            
            if stop_update.HasExtension(nyct_subway_pb2.nyct_stop_time_update):
                nyct_ext = stop_update.Extensions[nyct_subway_pb2.nyct_stop_time_update]
                
                if nyct_ext.HasField('actual_track'):
                    actual_track = nyct_ext.actual_track
                if nyct_ext.HasField('scheduled_track'):
                    scheduled_track = nyct_ext.scheduled_track
            
            results.append({
                'trip_id': trip_update.trip.trip_id,
                'route_id': trip_update.trip.route_id if trip_update.trip.HasField('route_id') else 'N/A',
                'stop_id': stop_update.stop_id,
                'train_id': train_id,
                'direction': direction,
                'scheduled_track': scheduled_track,
                'actual_track': actual_track,
                'arrival_time': stop_update.arrival.time if stop_update.HasField('arrival') else None,
            })
    
    return results


def compare_feeds(feeds_dir: Path):
    """
    Run both approaches on saved feeds and compare results.
    """
    feed_files = sorted(feeds_dir.glob("*.pb"))
    
    if not feed_files:
        print(f"No feed files found in {feeds_dir}")
        return
    
    print("=" * 80)
    print("COMPARISON: Current Approach vs. Extension-Based Approach")
    print("=" * 80)
    
    # Use first feed file for detailed comparison
    sample_file = feed_files[0]
    print(f"\nAnalyzing sample feed: {sample_file.name}\n")
    
    # Current approach
    print("Running CURRENT approach (standard GTFS-RT only)...")
    current_data = current_approach(sample_file)
    print(f"  ✓ Extracted {len(current_data)} stop updates")
    
    # Extension approach
    print("\nRunning EXTENSION approach (with MTA track data)...")
    extension_data = extension_approach(sample_file)
    with_actual = sum(1 for d in extension_data if d['actual_track'])
    with_scheduled = sum(1 for d in extension_data if d['scheduled_track'])
    with_train_id = sum(1 for d in extension_data if d['train_id'])
    print(f"  ✓ Extracted {len(extension_data)} stop updates")
    print(f"    + {with_actual} have actual_track")
    print(f"    + {with_scheduled} have scheduled_track")
    print(f"    + {with_train_id} have train_id")
    
    # Comparison
    print("\n" + "-" * 80)
    print("KEY DIFFERENCES:")
    print("-" * 80)
    
    print(f"\n1. Data Availability:")
    print(f"   Current:   {len(current_data)} stop updates, NO track_id")
    print(f"   Extension: {len(extension_data)} stop updates, {with_actual} with actual_track")
    
    if with_actual > 0:
        coverage = 100 * with_actual / len(extension_data)
        print(f"\n   ⚠️  Current approach misses {coverage:.1f}% of available track data!")
    
    print(f"\n2. Additional Fields Available:")
    print(f"   - train_id: Physical train identifier (not in standard GTFS-RT)")
    print(f"   - direction: Cardinal direction enum (NORTH/SOUTH/EAST/WEST)")
    print(f"   - scheduled_track: Pre-planned track assignment")
    print(f"   - actual_track: Real-time track assignment (THE KEY FIELD)")
    
    # Show side-by-side examples
    print("\n" + "-" * 80)
    print("SIDE-BY-SIDE EXAMPLE (Same Trip/Stop):")
    print("-" * 80)
    
    if extension_data:
        # Find an entry with actual_track
        sample = next((d for d in extension_data if d['actual_track']), extension_data[0])
        
        # Find corresponding entry in current data
        current_sample = next(
            (d for d in current_data 
             if d['trip_id'] == sample['trip_id'] and d['stop_id'] == sample['stop_id']),
            None
        )
        
        print("\nCURRENT APPROACH:")
        if current_sample:
            for key, value in current_sample.items():
                print(f"  {key:20} {value}")
        
        print("\nEXTENSION APPROACH:")
        for key, value in sample.items():
            marker = " ⭐ NEW!" if key in ['train_id', 'direction', 'scheduled_track', 'actual_track'] else ""
            print(f"  {key:20} {value}{marker}")
    
    # Analyze all feeds
    print("\n" + "=" * 80)
    print(f"FULL ANALYSIS ({len(feed_files)} feeds)")
    print("=" * 80)
    
    total_current = 0
    total_extension = 0
    total_with_track = 0
    
    for feed_file in feed_files:
        current = current_approach(feed_file)
        extension = extension_approach(feed_file)
        with_track = sum(1 for d in extension if d['actual_track'])
        
        total_current += len(current)
        total_extension += len(extension)
        total_with_track += with_track
    
    print(f"\nAcross all {len(feed_files)} feed snapshots:")
    print(f"  Current approach:   {total_current} stop updates")
    print(f"  Extension approach: {total_extension} stop updates")
    print(f"                      {total_with_track} with actual_track ({100*total_with_track/total_extension:.1f}%)")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATION:")
    print("=" * 80)
    print("\n✅ The extension-based approach captures significantly more data.")
    print("✅ The actual_track field provides critical routing information.")
    print("✅ This data is essential for accurate train arrival predictions.")
    print("\nNext steps:")
    print("  1. Update ingestion pipeline to use extension-based parsing")
    print("  2. Store track_id alongside existing arrival data")
    print("  3. Incorporate track patterns into prediction model")


if __name__ == "__main__":
    feeds_dir = Path(__file__).parent / "feeds"
    compare_feeds(feeds_dir)
