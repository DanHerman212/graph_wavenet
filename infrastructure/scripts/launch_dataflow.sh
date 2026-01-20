#!/bin/bash
# Launch Dataflow streaming job with stateful enrichment
# 
# Run from project root after infrastructure is deployed:
#   bash infrastructure/scripts/launch_dataflow.sh

set -e

# Load configuration
PROJECT_ID="${1:-$(terraform -chdir=infrastructure/terraform output -raw project_id)}"
REGION="${2:-$(terraform -chdir=infrastructure/terraform output -raw region)}"

echo "========================================================================="
echo "=== Launching Dataflow Job with Stateful Track Enrichment ==="
echo "========================================================================="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo ""

# Get resource names from Terraform outputs
STAGING_BUCKET=$(terraform -chdir=infrastructure/terraform output -raw dataflow_staging_bucket)
TEMP_BUCKET=$(terraform -chdir=infrastructure/terraform output -raw dataflow_temp_bucket)
SERVICE_ACCOUNT=$(terraform -chdir=infrastructure/terraform output -raw dataflow_service_account)

# Pub/Sub subscriptions
GTFS_ACE_SUB="projects/${PROJECT_ID}/subscriptions/gtfs-rt-ace-dataflow"
GTFS_BDFM_SUB="projects/${PROJECT_ID}/subscriptions/gtfs-rt-bdfm-dataflow"
ALERTS_SUB="projects/${PROJECT_ID}/subscriptions/service-alerts-dataflow"

# BigQuery tables
VEHICLE_TABLE="${PROJECT_ID}:subway.vehicle_positions"
ALERTS_TABLE="${PROJECT_ID}:subway.service_alerts"

echo "Subscriptions:"
echo "  GTFS ACE: ${GTFS_ACE_SUB}"
echo "  GTFS BDFM: ${GTFS_BDFM_SUB}"
echo "  Alerts: ${ALERTS_SUB}"
echo ""
echo "Tables:"
echo "  Vehicles: ${VEHICLE_TABLE}"
echo "  Alerts: ${ALERTS_TABLE}"
echo ""

# Navigate to dataflow directory
cd ingestion/dataflow

# Install dependencies if needed
pip3 install -r requirements.txt

# Launch the pipeline
echo "Launching pipeline with stateful enrichment..."
python3 pipeline.py \
    --runner=DataflowRunner \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --job_name="subway-gtfs-pipeline-$(date +%Y%m%d-%H%M%S)" \
    --temp_location="gs://${TEMP_BUCKET}/temp" \
    --staging_location="gs://${STAGING_BUCKET}/staging" \
    --service_account_email="${SERVICE_ACCOUNT}" \
    --setup_file="./setup.py" \
    --max_num_workers=2 \
    --machine_type=n1-standard-1 \
    --gtfs_ace_subscription="${GTFS_ACE_SUB}" \
    --gtfs_bdfm_subscription="${GTFS_BDFM_SUB}" \
    --alerts_subscription="${ALERTS_SUB}" \
    --output_table="${VEHICLE_TABLE}" \
    --alerts_table="${ALERTS_TABLE}" \
    --streaming

echo ""
echo "========================================================================="
echo "=== Pipeline Launched ==="
echo "========================================================================="
echo ""
echo "Monitor at: https://console.cloud.google.com/dataflow/jobs/${REGION}?project=${PROJECT_ID}"
echo ""
echo "Query enriched data:"
echo "  SELECT * FROM \`${VEHICLE_TABLE}\` LIMIT 10"
echo ""
echo "Check track enrichment:"
echo "  SELECT actual_track, COUNT(*) as count"
echo "  FROM \`${VEHICLE_TABLE}\`"
echo "  WHERE actual_track IS NOT NULL"
echo "  GROUP BY actual_track"
echo "  ORDER BY count DESC"
echo ""

