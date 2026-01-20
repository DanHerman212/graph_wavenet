# Ingestion Pipeline Operations Guide

This guide covers the deployment and operation of the NYC Subway data ingestion pipeline with stateful track enrichment.

## Overview

The pipeline consists of:
1. **Pollers** (GCE VM) - Fetch GTFS-RT feeds every 30 seconds → Pub/Sub
2. **Dataflow** (Streaming) - Parse messages, enrich arrivals with track data, write to BigQuery
3. **BigQuery** - Data warehouse with arrival records enriched with track assignments

**Key Feature:** Track data from trip_updates is cached in-memory and merged into arrival records during streaming, achieving 99% track coverage without SQL joins.

## Prerequisites

- Google Cloud Platform account with billing enabled
- `gcloud` CLI installed and authenticated
- Terraform >= 1.0
- Python 3.10+

## Quick Start

```bash
# Clone and configure
git clone <repo>
cd graph_wavenet

# Set your GCP project
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your project_id

# Deploy everything
cd ../..
make deploy-infra       # Create GCP resources
make deploy-ingestion   # Start data collection
make deploy-dataflow    # Start streaming to BigQuery
```

---

## Makefile Commands

### Infrastructure

| Command | Description |
|---------|-------------|
| `make init` | Initialize Terraform |
| `make deploy-infra` | Create all GCP resources (Pub/Sub, BigQuery, VM) |
| `make teardown` | Destroy all GCP resources (with confirmation prompt) |

### Ingestion

| Command | Description |
|---------|-------------|
| `make deploy-ingestion` | Deploy poller code to VM and start polling |
| `make stop-ingestion` | Stop the polling service |
| `make restart-ingestion` | Restart the polling service |

### Dataflow

| Command | Description |
|---------|-------------|
| `make deploy-dataflow` | Launch the streaming Dataflow pipeline |
| `make stop-dataflow` | Cancel the Dataflow job |

### Utilities

| Command | Description |
|---------|-------------|
| `make ssh` | SSH into the poller VM |
| `make logs` | Tail poller logs in real-time |
| `make status` | Check status of all services |
| `make help` | Show all available commands |

---

## Typical Workflows

### Start Data Collection

```bash
make deploy-infra
make deploy-ingestion
make deploy-dataflow
make status             # Verify everything is running
```

### Monitor the Pipeline

```bash
make logs               # Watch poller output
make status             # Check all services
```

### Stop Data Collection

```bash
make stop-dataflow
make stop-ingestion
```

### Clean Up Everything

```bash
make teardown           # Destroys all GCP resources
```

---

## Configuration

### Terraform Variables

Edit `infrastructure/terraform/terraform.tfvars`:

```hcl
# Required
project_id = "your-gcp-project-id"

# Optional (defaults shown)
# region                = "us-east1"
# zone                  = "us-east1-b"
# environment           = "dev"
# poller_machine_type   = "e2-small"
# dataflow_machine_type = "n1-standard-1"
# dataflow_max_workers  = 2
# bigquery_dataset_id   = "subway"
# retention_days        = 90
```

### Environment Variables

The poller VM automatically receives these from Terraform:

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID |
| `GTFS_TOPIC` | Pub/Sub topic for vehicle positions |
| `ALERTS_TOPIC` | Pub/Sub topic for service alerts |

---

## Troubleshooting

### Poller Not Publishing

1. Check poller logs:
   ```bash
   make logs
   ```

2. Verify Pub/Sub topics exist:
   ```bash
   gcloud pubsub topics list
   ```

3. Check service account permissions:
   ```bash
   gcloud projects get-iam-policy $(gcloud config get-value project)
   ```

### Dataflow Job Failing

1. View job logs in Cloud Console:
   ```
   https://console.cloud.google.com/dataflow/jobs
   ```

2. Check subscription has messages:
   ```bash
   gcloud pubsub subscriptions pull gtfs-rt-ace-dataflow --auto-ack --limit=1
   ```

### No Data in BigQuery

1. Verify Dataflow job is running:
   ```bash
   make status
   ```

2. Check for errors in Dataflow logs

3. Query recent arrivals with track data:
   ```sql
   SELECT 
     COUNT(*) as total_arrivals,
     COUNTIF(actual_track IS NOT NULL) as with_track_data,
     ROUND(100.0 * COUNTIF(actual_track IS NOT NULL) / COUNT(*), 1) as enrichment_pct
   FROM subway.vehicle_positions
   WHERE vehicle_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
   ```

### Track Data Missing

The pipeline uses stateful processing to enrich arrivals with track assignments. If enrichment percentage is low:

1. Check Dataflow metrics for `enriched_records` and `no_track_data` counters
2. Verify trip_updates are being processed (contain track data before arrivals)
3. Check for `stale_track_data` warnings (cached data > 15 minutes old)

**Expected:** ~99% of arrival records should have track data enriched.

---

## Cost Estimation

| Resource | Specification | Est. Monthly Cost |
|----------|---------------|-------------------|
| GCE VM (poller) | e2-small, 24/7 | ~$15 |
| Dataflow | 1 worker, streaming | ~$50 |
| Pub/Sub | ~2.5M messages/month | ~$1 |
| BigQuery | ~10GB storage + queries | ~$5 |
| **Total** | | **~$70/month** |

*Costs vary by region and usage patterns.*
