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
	@echo "Ingestion:"
	@echo "  make deploy-ingestion - Deploy and start pollers on VM"
	@echo "  make stop-ingestion   - Stop pollers on VM"
	@echo "  make restart-ingestion - Restart pollers on VM"
	@echo ""
	@echo "Dataflow:"
	@echo "  make deploy-dataflow  - Launch Dataflow streaming pipeline"
	@echo "  make stop-dataflow    - Cancel Dataflow job"
	@echo ""
	@echo "Utilities:"
	@echo "  make ssh              - SSH into poller VM"
	@echo "  make logs             - View poller logs on VM"
	@echo "  make status           - Check status of all services"

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
	@echo "Deploying poller code to VM..."
	# Copy poller code to user's home directory first (no root needed)
	gcloud compute scp --recurse $(POLLER_DIR)/* $(VM_NAME):~/poller-staging/ --zone=$(ZONE)
	# Move files to /opt with sudo, install dependencies, and start service
	gcloud compute ssh $(VM_NAME) --zone=$(ZONE) --command="\
		sudo cp -r ~/poller-staging/* /opt/gtfs-poller/ && \
		rm -rf ~/poller-staging && \
		cd /opt/gtfs-poller && \
		source venv/bin/activate && \
		pip install -q -r requirements.txt && \
		sudo systemctl restart gtfs-poller && \
		sudo systemctl status gtfs-poller --no-pager"
	@echo ""
	@echo "Ingestion deployed and running. Use 'make logs' to view output."

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
	@echo "Launching Dataflow streaming pipeline..."
	@# Get project ID from terraform
	$(eval PROJECT_ID := $(shell cd $(TF_DIR) && terraform output -raw project_id 2>/dev/null))
	@if [ -z "$(PROJECT_ID)" ]; then echo "Error: Run 'make deploy-infra' first"; exit 1; fi
	cd $(DATAFLOW_DIR) && python pipeline.py \
		--project=$(PROJECT_ID) \
		--region=us-east1 \
		--runner=DataflowRunner \
		--streaming \
		--job_name=subway-ingestion \
		--gtfs_subscription=projects/$(PROJECT_ID)/subscriptions/gtfs-rt-ace-dataflow \
		--alerts_subscription=projects/$(PROJECT_ID)/subscriptions/service-alerts-dataflow \
		--output_table=$(PROJECT_ID):subway.vehicle_positions \
		--alerts_table=$(PROJECT_ID):subway.service_alerts
	@echo ""
	@echo "Dataflow job launched. View at: https://console.cloud.google.com/dataflow/jobs"

stop-dataflow:
	@echo "Cancelling Dataflow job..."
	$(eval PROJECT_ID := $(shell cd $(TF_DIR) && terraform output -raw project_id 2>/dev/null))
	gcloud dataflow jobs list --filter="name=subway-ingestion AND state=Running" \
		--format="value(id)" --region=us-east1 | \
		xargs -I {} gcloud dataflow jobs cancel {} --region=us-east1
	@echo "Dataflow job cancelled."

# =============================================================================
# Utilities
# =============================================================================

ssh:
	gcloud compute ssh $(VM_NAME) --zone=$(ZONE)

logs:
	gcloud compute ssh $(VM_NAME) --zone=$(ZONE) --command="sudo journalctl -u gtfs-poller -f"

status:
	@echo "=== Infrastructure ==="
	@cd $(TF_DIR) && terraform output 2>/dev/null || echo "Not deployed"
	@echo ""
	@echo "=== Poller VM ==="
	@gcloud compute instances describe $(VM_NAME) --zone=$(ZONE) --format="value(status)" 2>/dev/null || echo "Not running"
	@echo ""
	@echo "=== Dataflow Jobs ==="
	@gcloud dataflow jobs list --filter="state=Running" --region=us-east1 --format="table(name,state,createTime)" 2>/dev/null || echo "None"
