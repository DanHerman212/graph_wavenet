#!/bin/bash
# Launch Dataflow streaming job
# Run from project root after infrastructure is deployed

set -e

# Load configuration
PROJECT_ID="${1:-$(terraform -chdir=infrastructure/terraform output -raw project_id)}"
REGION="${2:-$(terraform -chdir=infrastructure/terraform output -raw region)}"

echo "=== Launching Dataflow Streaming Job ==="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo ""

# Get resource names from Terraform outputs
GTFS_SUB=$(terraform -chdir=infrastructure/terraform output -raw gtfs_subscription_name)
ALERTS_SUB=$(terraform -chdir=infrastructure/terraform output -raw alerts_subscription_name)
STAGING_BUCKET=$(terraform -chdir=infrastructure/terraform output -raw dataflow_staging_bucket)
TEMP_BUCKET=$(terraform -chdir=infrastructure/terraform output -raw dataflow_temp_bucket)
SERVICE_ACCOUNT=$(terraform -chdir=infrastructure/terraform output -raw dataflow_service_account)

# BigQuery tables
SENSOR_TABLE="${PROJECT_ID}:subway.sensor_data"
ALERTS_TABLE="${PROJECT_ID}:subway.service_alerts"

echo "Subscriptions:"
echo "  GTFS: ${GTFS_SUB}"
echo "  Alerts: ${ALERTS_SUB}"
echo ""

# Navigate to dataflow directory
cd ingestion/dataflow

# Install dependencies if needed
pip install -r requirements.txt

# Launch the pipeline
echo "Launching pipeline..."
python pipeline.py \
    --runner=DataflowRunner \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --job_name="subway-gtfs-pipeline-$(date +%Y%m%d-%H%M%S)" \
    --temp_location="gs://${TEMP_BUCKET}/temp" \
    --staging_location="gs://${STAGING_BUCKET}/staging" \
    --service_account_email="${SERVICE_ACCOUNT}" \
    --max_num_workers=2 \
    --machine_type=n1-standard-1 \
    --gtfs_subscription="projects/${PROJECT_ID}/subscriptions/${GTFS_SUB}" \
    --alerts_subscription="projects/${PROJECT_ID}/subscriptions/${ALERTS_SUB}" \
    --sensor_table="${SENSOR_TABLE}" \
    --alerts_table="${ALERTS_TABLE}" \
    --streaming

echo ""
echo "=== Pipeline Launched ==="
echo ""
echo "Monitor at: https://console.cloud.google.com/dataflow/jobs/${REGION}?project=${PROJECT_ID}"
echo ""
