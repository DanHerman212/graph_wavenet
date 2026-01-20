# Migration Note

## Current Test Resources in Use

The production pipeline is currently using resources with "-test" suffixes:

### Pub/Sub Subscriptions (Active)
- `gtfs-rt-ace-dataflow-test`
- `gtfs-rt-bdfm-dataflow-test`
- `service-alerts-dataflow-test`

### BigQuery Tables (Active)
- `subway.vehicle_positions_enriched`
- `subway.service_alerts_test`

### Dataflow Job
- Job name: `subway-gtfs-pipeline-test-*`
- Status: Running
- Performance: 99% track enrichment rate

## Migration Steps (when ready)

To rename resources to production names:

1. **Cancel current job:**
   ```bash
   gcloud dataflow jobs list --region=us-east1 --status=active --filter="name:test"
   # Note the job ID, then:
   gcloud dataflow jobs cancel <JOB_ID> --region=us-east1
   ```

2. **Update Terraform and apply:**
   The Terraform files have been updated to use production names. Apply changes:
   ```bash
   cd infrastructure/terraform
   terraform plan  # Review changes
   terraform apply # Creates new subscriptions with production names
   ```

3. **Launch pipeline with production resources:**
   ```bash
   bash infrastructure/scripts/launch_dataflow.sh
   ```

4. **Clean up test resources:**
   ```bash
   # Delete test subscriptions
   gcloud pubsub subscriptions delete gtfs-rt-ace-dataflow-test
   gcloud pubsub subscriptions delete gtfs-rt-bdfm-dataflow-test
   gcloud pubsub subscriptions delete service-alerts-dataflow-test
   
   # Rename or delete test tables
   bq cp subway.vehicle_positions_enriched subway.vehicle_positions
   bq rm -t subway.vehicle_positions_enriched
   bq rm -t subway.service_alerts_test
   ```

## OR: Keep Current Names

If you prefer to keep the current names, update these files:
- `infrastructure/scripts/launch_dataflow.sh` - Change subscription and table names back to *-test
- `infrastructure/terraform/pubsub.tf` - Revert subscription names
- `infrastructure/terraform/bigquery.tf` - Revert table names

The pipeline is working perfectly as-is, this is just a naming convention decision.
