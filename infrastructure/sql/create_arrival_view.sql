-- BigQuery View: Actual Arrivals with Track Assignments
-- Combines vehicle positions (STOPPED_AT/INCOMING_AT) with track predictions from trip_updates

CREATE OR REPLACE VIEW `realtime-headway-prediction.subway.arrivals_with_tracks` AS

WITH vehicle_arrivals AS (
  -- Get actual vehicle positions (where trains ARE)
  SELECT 
    entity_id,
    trip_id,
    route_id,
    start_time,
    start_date,
    direction,
    path_id,
    stop_id,
    current_stop_sequence,
    current_status,
    vehicle_timestamp,
    feed_timestamp,
    ingest_time
  FROM `realtime-headway-prediction.subway.vehicle_positions`
  WHERE current_status IN ('STOPPED_AT', 'INCOMING_AT')
),

track_predictions AS (
  -- Get track predictions from trip_updates (where trains WILL BE)
  SELECT 
    trip_id,
    stop_id,
    train_id,
    nyct_direction,
    scheduled_track,
    actual_track,
    vehicle_timestamp as predicted_arrival,
    feed_timestamp,
    ROW_NUMBER() OVER (
      PARTITION BY trip_id, stop_id, DATE(vehicle_timestamp)
      ORDER BY feed_timestamp DESC
    ) as rn
  FROM `realtime-headway-prediction.subway.vehicle_positions`
  WHERE current_status = 'IN_TRANSIT_TO'
    AND actual_track IS NOT NULL
)

-- Join vehicle positions with their track predictions
SELECT 
  v.entity_id,
  v.trip_id,
  v.route_id,
  v.start_time,
  v.start_date,
  v.direction,
  v.path_id,
  t.train_id,
  t.nyct_direction,
  t.scheduled_track,
  t.actual_track,
  v.stop_id,
  v.current_stop_sequence,
  v.current_status,
  v.vehicle_timestamp as actual_arrival,
  t.predicted_arrival,
  TIMESTAMP_DIFF(v.vehicle_timestamp, t.predicted_arrival, SECOND) as prediction_error_seconds,
  v.feed_timestamp,
  v.ingest_time
FROM vehicle_arrivals v
LEFT JOIN track_predictions t
  ON v.trip_id = t.trip_id
  AND v.stop_id = t.stop_id
  AND t.rn = 1  -- Most recent prediction for this trip+stop
  AND ABS(TIMESTAMP_DIFF(v.vehicle_timestamp, t.predicted_arrival, MINUTE)) < 15  -- Within 15 min
ORDER BY v.vehicle_timestamp DESC;
