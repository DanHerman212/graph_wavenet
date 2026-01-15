"""
Data Loader for Graph WaveNet Training

Loads headway data from BigQuery and prepares it for training.

PLACEHOLDER - Phase 2 Implementation
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from google.cloud import bigquery


class SubwayDataLoader:
    """
    Data loader for NYC Subway headway data.
    
    Loads data from BigQuery, computes headways, and prepares
    sequences for training Graph WaveNet.
    
    Args:
        project_id: GCP project ID
        dataset_id: BigQuery dataset ID
        table_id: BigQuery table ID
    """
    
    def __init__(
        self,
        project_id: str,
        dataset_id: str = "subway",
        table_id: str = "sensor_data",
    ):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.table_id = table_id
        self.client = bigquery.Client(project=project_id)
        
        # Station ordering for graph construction
        self.station_order: List[str] = []
        self.station_to_idx: Dict[str, int] = {}

    def load_headway_data(
        self,
        start_date: str,
        end_date: str,
        routes: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Load headway data from BigQuery.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            routes: List of routes to include (default: A, C, E)
            
        Returns:
            DataFrame with headway calculations
        """
        routes = routes or ["A", "C", "E"]
        routes_str = ", ".join(f"'{r}'" for r in routes)
        
        query = f"""
        WITH ordered_arrivals AS (
            SELECT
                route_id,
                direction,
                stop_id,
                trip_id,
                arrival_time,
                LAG(arrival_time) OVER (
                    PARTITION BY route_id, direction, stop_id
                    ORDER BY arrival_time
                ) AS prev_arrival_time
            FROM `{self.project_id}.{self.dataset_id}.{self.table_id}`
            WHERE 
                arrival_time IS NOT NULL
                AND route_id IN ({routes_str})
                AND DATE(arrival_time) BETWEEN '{start_date}' AND '{end_date}'
        )
        SELECT
            route_id,
            direction,
            stop_id,
            trip_id,
            arrival_time,
            TIMESTAMP_DIFF(arrival_time, prev_arrival_time, SECOND) AS headway_seconds,
            DATE(arrival_time) AS date,
            EXTRACT(HOUR FROM arrival_time) AS hour,
            EXTRACT(DAYOFWEEK FROM arrival_time) AS day_of_week
        FROM ordered_arrivals
        WHERE 
            prev_arrival_time IS NOT NULL
            AND TIMESTAMP_DIFF(arrival_time, prev_arrival_time, SECOND) > 0
            AND TIMESTAMP_DIFF(arrival_time, prev_arrival_time, SECOND) < 3600  -- Filter outliers
        ORDER BY arrival_time
        """
        
        df = self.client.query(query).to_dataframe()
        
        # Build station index
        self._build_station_index(df)
        
        return df

    def _build_station_index(self, df: pd.DataFrame):
        """Build ordered list of stations and index mapping."""
        # Get unique stations, ordered by frequency
        station_counts = df.groupby("stop_id").size().sort_values(ascending=False)
        self.station_order = station_counts.index.tolist()
        self.station_to_idx = {s: i for i, s in enumerate(self.station_order)}

    def build_adjacency_matrix(
        self,
        df: pd.DataFrame,
        threshold: float = 0.1,
    ) -> np.ndarray:
        """
        Build static adjacency matrix from track connectivity.
        
        Args:
            df: DataFrame with trip data
            threshold: Threshold for edge weights
            
        Returns:
            Adjacency matrix of shape (num_stations, num_stations)
        """
        num_stations = len(self.station_order)
        adj = np.zeros((num_stations, num_stations))
        
        # Build adjacency from consecutive stops in trips
        for (route, direction, trip), group in df.groupby(
            ["route_id", "direction", "trip_id"]
        ):
            stops = group.sort_values("arrival_time")["stop_id"].tolist()
            
            for i in range(len(stops) - 1):
                from_station = stops[i]
                to_station = stops[i + 1]
                
                if from_station in self.station_to_idx and to_station in self.station_to_idx:
                    from_idx = self.station_to_idx[from_station]
                    to_idx = self.station_to_idx[to_station]
                    adj[from_idx, to_idx] += 1
        
        # Normalize
        row_sums = adj.sum(axis=1, keepdims=True)
        adj = np.where(row_sums > 0, adj / row_sums, 0)
        
        # Threshold
        adj = np.where(adj > threshold, adj, 0)
        
        return adj

    def create_sequences(
        self,
        df: pd.DataFrame,
        input_window: int = 12,
        output_horizon: int = 12,
        resample_interval: str = "5T",
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create training sequences from headway data.
        
        Args:
            df: DataFrame with headway data
            input_window: Number of historical time steps
            output_horizon: Number of future time steps to predict
            resample_interval: Time interval for resampling (default: 5 minutes)
            
        Returns:
            Tuple of (X, y) arrays for training
        """
        # Resample to regular intervals
        df = df.set_index("arrival_time")
        
        # Pivot to get station-time matrix
        pivot = df.pivot_table(
            values="headway_seconds",
            index=pd.Grouper(freq=resample_interval),
            columns="stop_id",
            aggfunc="mean",
        )
        
        # Fill missing values with column mean
        pivot = pivot.fillna(pivot.mean())
        
        # Reorder columns to match station order
        available_stations = [s for s in self.station_order if s in pivot.columns]
        pivot = pivot[available_stations]
        
        # Normalize
        mean = pivot.mean()
        std = pivot.std()
        normalized = (pivot - mean) / (std + 1e-8)
        
        # Create sequences
        data = normalized.values
        X, y = [], []
        
        total_window = input_window + output_horizon
        
        for i in range(len(data) - total_window + 1):
            X.append(data[i:i + input_window])
            y.append(data[i + input_window:i + total_window])
        
        X = np.array(X)
        y = np.array(y)
        
        # Add feature dimension
        X = X[..., np.newaxis]
        
        return X, y

    def train_test_split(
        self,
        X: np.ndarray,
        y: np.ndarray,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
    ) -> Dict[str, np.ndarray]:
        """
        Split data into train/validation/test sets.
        
        Uses temporal split (no shuffling) to prevent data leakage.
        """
        n = len(X)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))
        
        return {
            "X_train": X[:train_end],
            "y_train": y[:train_end],
            "X_val": X[train_end:val_end],
            "y_val": y[train_end:val_end],
            "X_test": X[val_end:],
            "y_test": y[val_end:],
        }


# TODO: Phase 2 Implementation
# - Add caching for large datasets
# - Implement streaming data loading
# - Add data augmentation
# - Implement feature engineering (temporal embeddings, etc.)
