#!/bin/bash
# Launch TEST Dataflow streaming job with stateful enrichment
# This runs in parallel to the production pipeline for testing
# 
# Run from project root after infrastructure is deployed:
#   bash infrastructure/scripts/launch_dataflow_test.sh

set -e

# Load configuration
PROJECT_ID="${1:-$(terraform -chdir=infrastructure/terraform output -raw project_id)}"
REGION="${2:-$(terraform -chdir=infrastructure/terraform output -raw region)}"

echo "========================================================================="
echo "=== Launching TEST Dataflow Job with Stateful Track Enrichment ==="
echo "========================================================================="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo ""

# Get resource names from Terraform outputs
STAGING_BUCKET=$(terraform -chdir=infrastructure/terraform output -raw dataflow_staging_bucket)
TEMP_BUCKET=$(terraform -chdir=infrastructure/terraform output -raw dataflow_temp_bucket)
SERVICE_ACCOUNT=$(terraform -chdir=infrastructure/terraform output -raw dataflow_service_account)

# TEST subscriptions (these will be created by terraform)
GTFS_ACE_SUB_TEST="projects/${PROJECT_ID}/subscriptions/gtfs-rt-ace-dataflow-test"
GTFS_BDFM_SUB_TEST="projects/${PROJECT_ID}/subscriptions/gtfs-rt-bdfm-dataflow-test"
ALERTS_SUB_TEST="projects/${PROJECT_ID}/subscriptions/service-alerts-dataflow-test"

# TEST BigQuery tables
VEHICLE_TABLE_TEST="${PROJECT_ID}:subway.vehicle_positions_enriched"
ALERTS_TABLE_TEST="${PROJECT_ID}:subway.service_alerts_test"

echo "Test Subscriptions:"
echo "  GTFS ACE: ${GTFS_ACE_SUB_TEST}"
echo "  GTFS BDFM: ${GTFS_BDFM_SUB_TEST}"
echo "  Alerts: ${ALERTS_SUB_TEST}"
echo ""
echo "Test Tables:"
echo "  Vehicles: ${VEHICLE_TABLE_TEST}"
echo "  Alerts: ${ALERTS_TABLE_TEST}"
echo ""

# Navigate to dataflow directory
cd ingestion/dataflow

# Install dependencies if needed
pip install -r requirements.txt

# Launch the TEST pipeline
echo "Launching TEST pipeline with stateful enrichment..."
python pipeline_test.py \
    --runner=DataflowRunner \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --job_name="subway-gtfs-pipeline-TEST-$(date +%Y%m%d-%H%M%S)" \
    --temp_location="gs://${TEMP_BUCKET}/temp-test" \
    --staging_location="gs://${STAGING_BUCKET}/staging-test" \
    --service_account_email="${SERVICE_ACCOUNT}" \
    --max_num_workers=2 \
    --machine_type=n1-standard-1 \
    --gtfs_ace_subscription="${GTFS_ACE_SUB_TEST}" \
    --gtfs_bdfm_subscription="${GTFS_BDFM_SUB_TEST}" \
    --alerts_subscription="${ALERTS_SUB_TEST}" \
    --output_table="${VEHICLE_TABLE_TEST}" \
    --alerts_table="${ALERTS_TABLE_TEST}" \
    --streaming

echo ""
echo "========================================================================="
echo "=== TEST Pipeline Launched ==="
echo "========================================================================="
echo ""
echo "Monitor at: https://console.cloud.google.com/dataflow/jobs/${REGION}?project=${PROJECT_ID}"
echo ""
echo "Compare results:"
echo "  Production: SELECT * FROM \`${PROJECT_ID}.subway.vehicle_positions\` LIMIT 10"
echo "  Test:       SELECT * FROM \`${VEHICLE_TABLE_TEST}\` LIMIT 10"
echo ""
echo "Check track enrichment:"
echo "  SELECT actual_track, COUNT(*) as count"
echo "  FROM \`${VEHICLE_TABLE_TEST}\`"
echo "  WHERE actual_track IS NOT NULL"
echo "  GROUP BY actual_track"
echo "  ORDER BY count DESC"
echo ""

