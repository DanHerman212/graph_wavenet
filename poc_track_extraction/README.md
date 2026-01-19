# POC: Track ID Extraction from GTFS-RT

This proof of concept demonstrates how to extract `actual_track` data from MTA GTFS-RT feeds using Protocol Buffer extensions.

## Background

The MTA includes track assignment data (`actual_track`, `scheduled_track`) in their GTFS-RT feeds, but this data is **not part of the standard GTFS-RT specification**. It's stored in MTA-specific Protocol Buffer extensions that require special handling.

Standard GTFS-RT parsers (like the one currently used in the main ingestion pipeline) cannot access this data because they only understand the base specification.

## What This POC Does

1. **Polls** the ACE line GTFS-RT feed and saves raw binary snapshots
2. **Extracts** track_id data using compiled MTA protobuf extensions
3. **Compares** what the current approach captures vs. the extension-based approach

## Setup

### 1. Install Dependencies

```bash
cd poc_track_extraction
pip install -r requirements.txt
```

The protobuf compiler (`protoc`) has already been installed and the proto files compiled.

### 2. Verify Compiled Protos

The following files should exist:
- `proto/generated/gtfs_realtime_pb2.py` - Standard GTFS-RT
- `proto/generated/nyct_subway_pb2.py` - MTA extensions (includes track_id)

## Usage

### Step 1: Collect Feed Samples

Run the poller to collect raw GTFS-RT feed snapshots:

```bash
python poller.py
```

This will:
- Fetch the ACE line feed 10 times over ~2.5 minutes
- Save raw binary snapshots to `feeds/gtfs_ace_<timestamp>.pb`
- Each snapshot is ~20-50 KB

### Step 2: Extract Track Data

Parse the saved feeds to extract track_id information:

```bash
python extractor.py
```

This will:
- Process all `.pb` files in the `feeds/` directory
- Extract `actual_track` and `scheduled_track` for each stop update
- Show summary statistics and sample data
- Export full results to `track_data_extract.csv`

### Step 3: Compare Approaches

See what data each approach can capture:

```bash
python comparison.py
```

This will:
- Run both the current (standard) and extension-based parsers
- Show side-by-side comparison of captured data
- Highlight the additional fields available with extensions
- Demonstrate the percentage of track data currently being missed

## Key Files

| File | Purpose |
|------|---------|
| `proto/gtfs-realtime.proto` | Standard Google GTFS-RT definition |
| `proto/nyct-subway.proto` | MTA extensions (includes track fields) |
| `proto/generated/*.py` | Compiled Python protobuf modules |
| `poller.py` | Fetches and saves raw feed snapshots |
| `extractor.py` | Parses feeds using MTA extensions |
| `comparison.py` | Compares current vs. extension approach |
| `feeds/*.pb` | Archived raw binary feed snapshots (gitignored) |

## Expected Results

You should see:
- **actual_track** values like "A2", "B1", "C4" (chaining codes)
- **scheduled_track** values (pre-planned assignments)
- **train_id** values (physical train identifiers)
- **direction** enums (NORTH, SOUTH, EAST, WEST)

### Track Code Format

Track codes like "A2" are "chaining codes" used by MTA operations:
- First character: Track designation (A, B, C, etc.)
- Second character: Direction/type indicator
- These map to physical tracks but are NOT the same as public track numbers

## What's Missing in Current Approach

The current pipeline uses standard GTFS-RT parsing which captures:
- ✅ trip_id
- ✅ route_id
- ✅ stop_id
- ✅ arrival/departure times
- ❌ actual_track (MISSING!)
- ❌ scheduled_track (MISSING!)
- ❌ train_id (MISSING!)
- ❌ direction enum (MISSING!)

## Integration Path

To integrate this into the main pipeline:

1. **Update poller** ([ingestion/poller/gtfs_poller.py](ingestion/poller/gtfs_poller.py))
   - Save raw bytes instead of parsing immediately
   - Archive feed snapshots for reprocessing

2. **Compile protos** in main project
   - Add proto definitions to project
   - Compile to Python modules
   - Add to Dataflow requirements

3. **Update transform** ([ingestion/dataflow/transforms/parse_gtfs.py](ingestion/dataflow/transforms/parse_gtfs.py))
   - Import compiled extension modules
   - Access extensions via `stop_update.Extensions[nyct_subway_pb2.nyct_stop_time_update]`
   - Extract `actual_track` field

4. **Update schema** ([ingestion/dataflow/schemas/bigquery_schemas.py](ingestion/dataflow/schemas/bigquery_schemas.py))
   - Add `actual_track` STRING field
   - Add `scheduled_track` STRING field
   - Add `train_id` STRING field

## Troubleshooting

### "No module named 'gtfs_realtime_pb2'"
Make sure you're running from the `poc_track_extraction/` directory. The scripts add `proto/generated/` to the Python path.

### "No feed files found"
Run `poller.py` first to collect feed samples.

### Empty results from extractor
This can happen if:
- Feeds were collected during off-peak hours (fewer trains)
- No trains are actively approaching stations (track assignments only appear when relevant)
- Try collecting samples during rush hour for more data

## Next Steps

After validating the POC:
1. Review extracted track codes and confirm they match expectations
2. Discuss integration timeline with team
3. Plan BigQuery schema migration
4. Update Dataflow pipeline with extension-based parsing
