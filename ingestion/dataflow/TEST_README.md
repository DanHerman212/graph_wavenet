# Testing the Stateful Track Enrichment Pipeline

This directory contains a test version of the Dataflow pipeline that implements stateful processing to merge track data with arrival data **before** writing to BigQuery.

## What's Different

### Production Pipeline (`pipeline.py`)
- Writes all vehicle positions and trip updates to BigQuery
- Track data only available in `IN_TRANSIT_TO` records (future predictions)
- Requires SQL view to join arrivals with track predictions

### Test Pipeline (`pipeline_test.py`)
- Uses **stateful processing** to cache track assignments in memory
- Enriches arrival records (`STOPPED_AT`/`INCOMING_AT`) with track data from cached predictions
- Writes **only enriched arrivals** to BigQuery (no trip updates)
- **No SQL view needed** - data is complete at write time

## Architecture

```
Pub/Sub Topic (shared)
    ├─> Production Subscription → Production Pipeline → vehicle_positions
    └─> Test Subscription       → Test Pipeline       → vehicle_positions_enriched
```

Both pipelines receive the same messages but process them differently.

## Deployment Steps

### 1. Apply Terraform Changes

This creates the test subscriptions and tables:

```bash
cd infrastructure/terraform
terraform apply
```

This will create:
- `gtfs-rt-ace-dataflow-test` subscription
- `gtfs-rt-bdfm-dataflow-test` subscription
- `service-alerts-dataflow-test` subscription
- `subway.vehicle_positions_enriched` table
- `subway.service_alerts_test` table

### 2. Launch Test Pipeline

```bash
cd /Users/danherman/Desktop/graph_wavenet
bash infrastructure/scripts/launch_dataflow_test.sh
```

The script will:
- Install dependencies
- Launch the test Dataflow job
- Provide monitoring links and comparison queries

### 3. Monitor and Compare

**View Dataflow Jobs:**
```
https://console.cloud.google.com/dataflow/jobs
```

**Compare Data:**
```sql
-- Production (mix of arrivals and predictions, track data only in predictions)
SELECT 
  current_status,
  COUNT(*) as count,
  COUNTIF(actual_track IS NOT NULL) as with_track
FROM `realtime-headway-prediction.subway.vehicle_positions`
WHERE DATE(vehicle_timestamp) = CURRENT_DATE()
GROUP BY current_status;

-- Test (only arrivals, all enriched with track data)
SELECT 
  current_status,
  COUNT(*) as count,
  COUNTIF(actual_track IS NOT NULL) as with_track
FROM `realtime-headway-prediction.subway.vehicle_positions_enriched`
WHERE DATE(vehicle_timestamp) = CURRENT_DATE()
GROUP BY current_status;
```

**Check Track Coverage:**
```sql
-- How many arrivals have track data?
SELECT 
  route_id,
  COUNT(*) as total_arrivals,
  COUNTIF(actual_track IS NOT NULL) as with_track,
  ROUND(COUNTIF(actual_track IS NOT NULL) / COUNT(*) * 100, 1) as coverage_pct
FROM `realtime-headway-prediction.subway.vehicle_positions_enriched`
WHERE DATE(vehicle_timestamp) = CURRENT_DATE()
GROUP BY route_id;
```

**View Recent Enriched Arrivals:**
```sql
SELECT 
  vehicle_timestamp,
  route_id,
  stop_id,
  actual_track,
  scheduled_track,
  train_id,
  current_status
FROM `realtime-headway-prediction.subway.vehicle_positions_enriched`
ORDER BY vehicle_timestamp DESC
LIMIT 50;
```

## How It Works

### Stateful Processing Flow

1. **Trip Update arrives** (`IN_TRANSIT_TO` with track data)
   - Extract `(trip_id, stop_id)` as key
   - Cache `{actual_track, scheduled_track, train_id}` in state
   - Set 30-minute expiration timer
   - Don't write to BigQuery

2. **Vehicle Arrival arrives** (`STOPPED_AT`/`INCOMING_AT`)
   - Look up `(trip_id, stop_id)` in state cache
   - If found and not stale (< 15 min old):
     - Merge track data into record
     - Write enriched record to BigQuery
   - If not found:
     - Write record with NULL track fields

### State Management

- **State Storage**: Beam `ReadModifyWriteStateSpec` with custom coder
- **State Key**: `"{trip_id}|{stop_id}"` 
- **State Expiration**: 30 minutes (automatic cleanup)
- **Staleness Check**: Warns if cached data > 15 minutes old

### Metrics

The pipeline tracks:
- `enriched_records`: Arrivals successfully enriched with track data
- `no_track_data`: Arrivals with no cached track data available
- `track_data_cached`: Track assignments cached from trip updates
- `stale_track_data`: Cached data older than 15 minutes

View metrics in the Dataflow UI under "Custom Counters"

## Stopping the Test

```bash
# List running jobs
gcloud dataflow jobs list --region=us-east1 --status=active

# Stop the test job
gcloud dataflow jobs cancel <JOB_ID> --region=us-east1
```

The test subscriptions will continue accumulating messages, so you can restart testing anytime.

## Cleanup

To remove test resources (after successful validation):

```bash
cd infrastructure/terraform

# Remove test subscriptions and tables from pubsub.tf and bigquery.tf
# Then apply:
terraform apply
```

## Production Migration

Once validated, you can:

1. **Option A: Replace production pipeline**
   - Rename `pipeline_test.py` → `pipeline.py`
   - Update `launch_dataflow.sh` to use new subscriptions
   - Update SQL views/queries to use enriched data

2. **Option B: Keep both pipelines**
   - Use test pipeline for enriched data
   - Keep production for raw data and analysis
   - Choose which table to query based on use case

## Troubleshooting

**No data appearing in test table:**
- Check Dataflow job logs for errors
- Verify test subscriptions are receiving messages
- Check metric counters in Dataflow UI

**Low track enrichment rate:**
- Check `no_track_data` metric
- May indicate trip updates arriving after arrivals
- Consider increasing state retention or investigating timing

**High staleness warnings:**
- Track data is old (> 15 min) when arrival occurs
- May indicate long gaps between updates
- Check MTA feed frequency and delays
