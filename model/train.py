"""
Graph WaveNet Training Script

PLACEHOLDER - Phase 2 Implementation

This script will handle:
1. Loading data from BigQuery
2. Building the model
3. Training with early stopping
4. Evaluation and metrics
5. Model export
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import tensorflow as tf

from data.loader import SubwayDataLoader
from graph_wavenet import build_graph_wavenet

logger = logging.getLogger(__name__)


def train(
    project_id: str,
    start_date: str,
    end_date: str,
    epochs: int = 100,
    batch_size: int = 64,
    learning_rate: float = 0.001,
    output_dir: str = "./checkpoints",
):
    """
    Train Graph WaveNet model on subway headway data.
    
    Args:
        project_id: GCP project ID
        start_date: Training data start date
        end_date: Training data end date
        epochs: Number of training epochs
        batch_size: Training batch size
        learning_rate: Adam learning rate
        output_dir: Directory for saving checkpoints
    """
    logger.info("Loading data from BigQuery...")
    
    # Load data
    loader = SubwayDataLoader(project_id=project_id)
    df = loader.load_headway_data(start_date, end_date)
    
    logger.info(f"Loaded {len(df)} headway records")
    logger.info(f"Stations: {len(loader.station_order)}")
    
    # Build adjacency matrix
    adj_matrix = loader.build_adjacency_matrix(df)
    logger.info(f"Adjacency matrix shape: {adj_matrix.shape}")
    
    # Create sequences
    X, y = loader.create_sequences(df)
    logger.info(f"Sequence shapes: X={X.shape}, y={y.shape}")
    
    # Split data
    data = loader.train_test_split(X, y)
    logger.info(
        f"Train: {len(data['X_train'])}, "
        f"Val: {len(data['X_val'])}, "
        f"Test: {len(data['X_test'])}"
    )
    
    # Build model
    num_nodes = X.shape[2]
    input_window = X.shape[1]
    output_horizon = y.shape[1]
    
    model = build_graph_wavenet(
        num_nodes=num_nodes,
        input_window=input_window,
        output_horizon=output_horizon,
        static_adj=adj_matrix,
    )
    
    model.summary()
    
    # Callbacks
    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=10,
            restore_best_weights=True,
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=f"{output_dir}/model_{{epoch:02d}}_{{val_loss:.4f}}.h5",
            save_best_only=True,
            monitor="val_loss",
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=5,
            min_lr=1e-6,
        ),
        tf.keras.callbacks.TensorBoard(
            log_dir=f"{output_dir}/logs/{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        ),
    ]
    
    # Train
    logger.info("Starting training...")
    history = model.fit(
        data["X_train"],
        data["y_train"],
        validation_data=(data["X_val"], data["y_val"]),
        epochs=epochs,
        batch_size=batch_size,
        callbacks=callbacks,
    )
    
    # Evaluate
    logger.info("Evaluating on test set...")
    test_loss = model.evaluate(data["X_test"], data["y_test"])
    logger.info(f"Test loss: {test_loss}")
    
    # Make predictions
    predictions = model.predict(data["X_test"])
    
    # Calculate metrics
    mae = np.mean(np.abs(predictions - data["y_test"]))
    rmse = np.sqrt(np.mean((predictions - data["y_test"]) ** 2))
    
    logger.info(f"Test MAE: {mae:.2f} seconds")
    logger.info(f"Test RMSE: {rmse:.2f} seconds")
    
    # Save final model
    model.save(f"{output_dir}/graph_wavenet_final.h5")
    logger.info(f"Model saved to {output_dir}/graph_wavenet_final.h5")
    
    return history, model


def main():
    parser = argparse.ArgumentParser(description="Train Graph WaveNet model")
    parser.add_argument("--project-id", required=True, help="GCP project ID")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--epochs", type=int, default=100, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=64, help="Batch size")
    parser.add_argument("--learning-rate", type=float, default=0.001, help="Learning rate")
    parser.add_argument("--output-dir", default="./checkpoints", help="Output directory")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    train(
        project_id=args.project_id,
        start_date=args.start_date,
        end_date=args.end_date,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
