# Implementation Plan: NYC Subway Headway Prediction

## Phase 1: Data Ingestion Pipeline (Weeks 1-5)

### Week 1: Infrastructure Setup

#### 1.1 GCP Project Configuration
- [ ] Create GCP project
- [ ] Enable required APIs:
  - Compute Engine
  - Pub/Sub
  - Dataflow
  - BigQuery
- [ ] Set up service accounts with appropriate IAM roles
- [ ] Configure VPC networking

#### 1.2 Terraform Deployment
- [ ] Deploy Pub/Sub topics and subscriptions
- [ ] Create BigQuery dataset and tables
- [ ] Provision Compute Engine VM
- [ ] Configure Dataflow job template

### Week 2: Poller Development

#### 2.1 GTFS-RT Poller
- [ ] Implement Protocol Buffer parsing for GTFS-RT
- [ ] Handle MTA Mercury extensions (NYCT format)
- [ ] Implement 30-second polling loop
- [ ] Add retry logic and error handling
- [ ] Implement ghost train detection

#### 2.2 Service Alerts Poller
- [ ] Parse ServiceAlert entities
- [ ] Extract EntitySelectors (route_id, stop_id)
- [ ] Track active_period for alert lifecycle
- [ ] Handle alert deduplication

#### 2.3 Pub/Sub Publisher
- [ ] Implement batched publishing
- [ ] Add message attributes for routing
- [ ] Configure acknowledgment settings

### Week 3: Dataflow Pipeline

#### 3.1 Apache Beam Pipeline
- [ ] Create streaming pipeline from Pub/Sub
- [ ] Implement GTFS message parsing transforms
- [ ] Implement alerts parsing transforms
- [ ] Configure windowing (30-second tumbling windows)
- [ ] Add dead-letter queue for failed messages

#### 3.2 BigQuery Sink
- [ ] Define table schemas
- [ ] Implement BigQuery write transforms
- [ ] Configure partitioning (by date) and clustering
- [ ] Set up streaming inserts

### Week 4: Testing & Deployment

#### 4.1 Unit Testing
- [ ] Test Protocol Buffer parsing
- [ ] Test transform functions
- [ ] Mock Pub/Sub and BigQuery

#### 4.2 Integration Testing
- [ ] End-to-end pipeline test
- [ ] Load testing with synthetic data
- [ ] Verify data quality

#### 4.3 Production Deployment
- [ ] Deploy poller to VM with systemd service
- [ ] Launch Dataflow streaming job
- [ ] Set up monitoring and alerting

### Week 5-8: Data Collection (30 days)

#### Monitoring Checklist
- [ ] Daily data volume verification
- [ ] Pipeline health monitoring
- [ ] Cost tracking
- [ ] Data quality audits

---

## Phase 2: Model Training (Weeks 9-12) [PLACEHOLDER]

### Week 9: Data Preparation

#### 2.1 Feature Engineering
- [ ] Calculate headway from consecutive arrivals
- [ ] Compute PRDM (Percentage Regularity Deviation Mean)
- [ ] Extract temporal features (hour, day of week, is_peak)
- [ ] Build static graph from GTFS stops/trips

#### 2.2 Graph Construction
- [ ] Define nodes (stations on A/C/E)
- [ ] Define edges (track segments, transfers)
- [ ] Compute distance-based adjacency matrix
- [ ] Normalize adjacency matrix

### Week 10: Model Development

#### 2.3 Graph WaveNet Architecture
- [ ] Implement Adaptive Adjacency Layer
- [ ] Implement Diffusion Graph Convolution
- [ ] Implement Dilated Causal Convolution (TCN)
- [ ] Implement Gated Activation Units
- [ ] Assemble full Graph WaveNet model

#### 2.4 Training Infrastructure
- [ ] Set up training on GPU (Vertex AI or local)
- [ ] Implement data loader for BigQuery
- [ ] Configure hyperparameters
- [ ] Implement early stopping and checkpointing

### Week 11: Training & Evaluation

#### 2.5 Model Training
- [ ] Train on 70% of data
- [ ] Validate on 15% of data
- [ ] Hyperparameter tuning

#### 2.6 Evaluation
- [ ] Evaluate on held-out 15% test set
- [ ] Compute MAE, RMSE, MAPE
- [ ] Analyze predictions by route/direction
- [ ] Visualize learned adjacency matrix

### Week 12: Deployment [PLACEHOLDER]

#### 2.7 Model Serving
- [ ] Export trained model
- [ ] Deploy to Vertex AI Endpoint
- [ ] Create prediction API
- [ ] Set up batch prediction job

---

## Data Schemas

### BigQuery: `subway.sensor_data`

| Field | Type | Description |
|-------|------|-------------|
| event_id | STRING | Unique identifier (trip_id + stop_id + timestamp) |
| timestamp | TIMESTAMP | Event timestamp |
| route_id | STRING | A, C, or E |
| direction | STRING | N (Northbound) or S (Southbound) |
| trip_id | STRING | GTFS trip identifier |
| stop_id | STRING | Station stop ID |
| stop_sequence | INTEGER | Order in trip |
| arrival_time | TIMESTAMP | Actual/predicted arrival |
| departure_time | TIMESTAMP | Actual/predicted departure |
| current_status | STRING | INCOMING_AT, STOPPED_AT, IN_TRANSIT_TO |
| vehicle_id | STRING | Train identifier |
| congestion_level | STRING | If available |
| ingest_time | TIMESTAMP | When message was ingested |

### BigQuery: `subway.service_alerts`

| Field | Type | Description |
|-------|------|-------------|
| alert_id | STRING | Unique alert identifier |
| timestamp | TIMESTAMP | Alert timestamp |
| active_period_start | TIMESTAMP | When alert becomes active |
| active_period_end | TIMESTAMP | When alert expires |
| cause | STRING | Alert cause category |
| effect | STRING | Alert effect type |
| header_text | STRING | Alert headline |
| description_text | STRING | Full alert text |
| affected_routes | ARRAY<STRING> | List of affected route_ids |
| affected_stops | ARRAY<STRING> | List of affected stop_ids |
| severity | STRING | Alert severity level |
| ingest_time | TIMESTAMP | When alert was ingested |

---

## Cost Estimates (30-day collection)

| Resource | Specification | Monthly Cost |
|----------|---------------|--------------|
| GCE VM | e2-small (2 vCPU, 2 GB) | ~$15 |
| Pub/Sub | ~50M messages | ~$20 |
| Dataflow | 1 worker, streaming | ~$150 |
| BigQuery | Storage ~10 GB | ~$0.20 |
| BigQuery | Streaming inserts | ~$5 |
| **Total** | | **~$190** |

---

## Key Metrics

### Data Quality
- **Completeness**: % of expected arrivals captured
- **Timeliness**: Lag between MTA feed and BigQuery
- **Accuracy**: Ghost train detection rate

### Model Performance (Phase 2)
- **MAE**: Mean Absolute Error (target < 60 seconds)
- **PRDM**: Percentage Regularity Deviation Mean
- **Horizon**: 12-step (60 min) prediction accuracy

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| MTA API rate limiting | Implement exponential backoff, monitor 429s |
| Ghost trains in data | Implement detection algorithm from research |
| Pipeline failures | Dead-letter queue, alerting, auto-restart |
| Data gaps | Fill with interpolation, flag in metadata |
| Cost overrun | Set billing alerts, optimize Dataflow |

---

## References

1. MTA GTFS-RT Documentation
2. Graph WaveNet Paper (Wu et al., 2019)
3. Google Cloud Dataflow Documentation
4. Apache Beam Programming Guide
