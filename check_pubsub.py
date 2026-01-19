import subprocess
import json
import base64

# Pull a message from ACE subscription
result = subprocess.run(
    ["gcloud", "pubsub", "subscriptions", "pull", "gtfs-rt-bdfm-dataflow", "--limit=1", "--format=json"],
    capture_output=True,
    text=True
)

if result.returncode == 0 and result.stdout.strip():
    messages = json.loads(result.stdout)
    if messages:
        # Decode the base64 message data
        msg_data = base64.b64decode(messages[0]["message"]["data"]).decode("utf-8")
        data = json.loads(msg_data)
        
        print(f"Total entities: {len(data.get('entity', []))}")
        print("\nFirst 5 entity types:")
        for i, entity in enumerate(data.get("entity", [])[:5]):
            entity_type = "vehicle" if "vehicle" in entity else "trip_update" if "trip_update" in entity else "unknown"
            print(f"\n  Entity {i}: {entity_type}")
            
            if entity_type == "trip_update":
                trip_update = entity.get("trip_update", {})
                trip = trip_update.get("trip", {})
                print(f"    Trip ID: {trip.get('trip_id')}")
                print(f"    Train ID: {trip.get('train_id')}")
                
                # Check first stop for track info
                if trip_update.get("stop_time_update"):
                    first_stop = trip_update["stop_time_update"][0]
                    print(f"    First stop: {first_stop.get('stop_id')}")
                    print(f"    Actual track: {first_stop.get('actual_track')}")
                    print(f"    Scheduled track: {first_stop.get('scheduled_track')}")
else:
    print("No messages available or error pulling")
    print(result.stderr)
