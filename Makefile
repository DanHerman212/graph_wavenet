# NYC Subway Headway Prediction Pipeline
# Makefile for deployment automation

.PHONY: help init deploy-infra deploy-ingestion stop-ingestion deploy-dataflow teardown ssh logs

# Configuration
TF_DIR := infrastructure/terraform
POLLER_DIR := ingestion/poller
DATAFLOW_DIR := ingestion/dataflow
VM_NAME := gtfs-poller-vm
ZONE := us-east1-b

# Default target
help:
	@echo "NYC Subway Pipeline - Deployment Commands"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make init            - Initialize Terraform"
	@echo "  make deploy-infra    - Create GCP resources (Pub/Sub, BigQuery, VM)"
	@echo "  make teardown        - Destroy all GCP resources"
	@echo ""
	@echo "Ingestion (with track_id extraction):"
	@echo "  make deploy-ingestion - Deploy and start pollers on VM"
	@echo "  make stop-ingestion   - Stop pollers on VM"
	@echo "  make restart-ingestion - Restart pollers on VM"
	@echo ""
	@echo "Dataflow (processes track_id fields):"
	@echo "  make deploy-dataflow  - Launch Dataflow streaming pipeline"
	@echo "  make stop-dataflow    - Cancel Dataflow job"
	@echo ""
	@echo "Utilities:"
	@echo "  make ssh              - SSH into poller VM"
	@echo "  make logs             - View poller logs on VM"
	@echo "  make status           - Check status of all services"
	@echo "  make verify-tracks    - Verify track_id data in BigQuery"

# =============================================================================
# Infrastructure
# =============================================================================

init:
	@echo "Initializing Terraform..."
	cd $(TF_DIR) && terraform init

deploy-infra: init
	@echo "Deploying GCP infrastructure..."
	cd $(TF_DIR) && terraform apply
	@echo ""
	@echo "Infrastructure deployed. Run 'make deploy-ingestion' to start polling."

teardown:
	@echo "WARNING: This will destroy all GCP resources!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	cd $(TF_DIR) && terraform destroy

# =============================================================================
# Ingestion (Pollers)
# =============================================================================

deploy-ingestion:
	@echo "Deploying poller code to VM (with protobuf track extraction)..."
	# Copy poller code to user's home directory first (no root needed)
	gcloud compute scp --recurse $(POLLER_DIR)/* $(VM_NAME):~/poller-staging/ --zone=$(ZONE)
	# Ensure directory exists, create venv if needed, move files, install deps (protobuf v6), start service
	gcloud compute ssh $(VM_NAME) --zone=$(ZONE) --command="\
		sudo mkdir -p /opt/gtfs-poller && \
		sudo cp -r ~/poller-staging/* /opt/gtfs-poller/ && \
		rm -rf ~/poller-staging && \
		cd /opt/gtfs-poller && \
		if [ ! -f venv/bin/activate ]; then sudo python3 -m venv venv; fi && \
		sudo chown -R \$$(id -u):\$$(id -g) venv && \
		. venv/bin/activate && \
		pip install -q -r requirements.txt && \
		sudo systemctl restart gtfs-poller && \
		sudo systemctl status gtfs-poller --no-pager"
	@echo ""
	@echo "✓ Poller deployed with track_id extraction enabled"
	@echo "  - Capturing: actual_track, scheduled_track, train_id, direction"
	@echo "  - Use 'make logs' to verify track data is being extracted"

stop-ingestion:
	@echo "Stopping pollers..."
	gcloud compute ssh $(VM_NAME) --zone=$(ZONE) --command="sudo systemctl stop gtfs-poller"
	@echo "Pollers stopped."

restart-ingestion:
	@echo "Restarting pollers..."
	gcloud compute ssh $(VM_NAME) --zone=$(ZONE) --command="sudo systemctl restart gtfs-poller"
	@echo "Pollers restarted."

# =============================================================================
# Dataflow
# =============================================================================

deploy-dataflow:
	@echo "Launching Dataflow streaming pipeline (with track_id support)..."
	@# Get project ID from terraform
	$(eval PROJECT_ID := $(shell cd $(TF_DIR) && terraform output -raw project_id 2>/dev/null))
	$(eval SERVICE_ACCOUNT := $(shell cd $(TF_DIR) && terraform output -raw dataflow_service_account 2>/dev/null))
	$(eval TEMP_BUCKET := $(shell cd $(TF_DIR) && terraform output -raw dataflow_temp_bucket 2>/dev/null))
	$(eval STAGING_BUCKET := $(shell cd $(TF_DIR) && terraform output -raw dataflow_staging_bucket 2>/dev/null))
	@if [ -z "$(PROJECT_ID)" ]; then echo "Error: Run 'make deploy-infra' first"; exit 1; fi
	cd $(DATAFLOW_DIR) && python3 pipeline.py \
		--project=$(PROJECT_ID) \
		--region=us-east1 \
		--runner=DataflowRunner \
		--streaming \
		--job_name=subway-ingestion-track-enhanced \
		--temp_location=gs://$(TEMP_BUCKET)/temp \
		--staging_location=gs://$(STAGING_BUCKET)/staging \
		--service_account_email=$(SERVICE_ACCOUNT) \
		--setup_file=./setup.py \
		--machine_type=e2-medium \
		--max_num_workers=2 \
		--gtfs_ace_subscription=projects/$(PROJECT_ID)/subscriptions/gtfs-rt-ace-dataflow \
		--gtfs_bdfm_subscription=projects/$(PROJECT_ID)/subscriptions/gtfs-rt-bdfm-dataflow \
		--alerts_subscription=projects/$(PROJECT_ID)/subscriptions/service-alerts-dataflow \
		--output_table=$(PROJECT_ID):subway.vehicle_positions \
		--alerts_table=$(PROJECT_ID):subway.service_alerts
	@echo ""
	@echo "✓ Dataflow job launched with track_id fields"
	@echo "  View at: https://console.cloud.google.com/dataflow/jobs"
	@echo "  New fields: train_id, nyct_direction, scheduled_track, actual_track"

stop-dataflow:
	@echo "Cancelling Dataflow job..."
	$(eval PROJECT_ID := $(shell cd $(TF_DIR) && terraform output -raw project_id 2>/dev/null))
	gcloud dataflow jobs list --filter="name:subway-ingestion AND state=Running" \
		--format="value(id)" --region=us-east1 | \
		xargs -I {} gcloud dataflow jobs cancel {} --region=us-east1
	@echo "Dataflow job cancelled."

# =============================================================================
# Utilities
# =============================================================================

ssh:
	gcloud compute ssh $(VM_NAME) --zone=$(ZONE)

logs:
	gcloud compute ssh $(VM_NAME) --zone=$(ZONE) --command="tail -f /var/log/gtfs-poller/stderr.log"

status:
	@echo "=== Infrastructure ==="
	@cd $(TF_DIR) && terraform output 2>/dev/null || echo "Not deployed"
	@echo ""
	@echo "=== Poller VM ==="
	@gcloud compute instances describe $(VM_NAME) --zone=$(ZONE) --format="value(status)" 2>/dev/null || echo "Not running"
	@echo ""
	@echo "=== Dataflow Jobs ==="
	@gcloud dataflow jobs list --filter="state=Running" --region=us-east1 --format="table(name,state,createTime)" 2>/dev/null || echo "None"
verify-tracks:
	@echo "Verifying track_id data in BigQuery..."
	$(eval PROJECT_ID := $(shell cd $(TF_DIR) && terraform output -raw project_id 2>/dev/null))
	@if [ -z "$(PROJECT_ID)" ]; then echo "Error: Infrastructure not deployed"; exit 1; fi
	@echo ""
	@echo "Sample records with track_id:"
	bq query --use_legacy_sql=false --format=pretty --max_rows=10 \
		"SELECT trip_id, stop_id, actual_track, scheduled_track, train_id, \
		 nyct_direction, vehicle_timestamp \
		 FROM $(PROJECT_ID).subway.vehicle_positions \
		 WHERE actual_track IS NOT NULL \
		 ORDER BY vehicle_timestamp DESC \
		 LIMIT 10"
	@echo ""
	@echo "Track coverage statistics:"
	bq query --use_legacy_sql=false --format=pretty \
		"SELECT \
		   COUNT(*) as total_records, \
		   COUNTIF(actual_track IS NOT NULL) as with_actual_track, \
		   COUNTIF(scheduled_track IS NOT NULL) as with_scheduled_track, \
		   COUNTIF(train_id IS NOT NULL) as with_train_id, \
		   ROUND(100.0 * COUNTIF(actual_track IS NOT NULL) / COUNT(*), 1) as track_coverage_pct \
		 FROM $(PROJECT_ID).subway.vehicle_positions \
		 WHERE DATE(vehicle_timestamp) = CURRENT_DATE()"