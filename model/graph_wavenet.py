"""
Graph WaveNet Model for NYC Subway Headway Prediction

PLACEHOLDER - Phase 2 Implementation

This module will contain the full Graph WaveNet architecture combining:
1. Adaptive Adjacency Layer - Learning hidden spatial dependencies
2. Spatial-Temporal Layer - Combined graph and temporal convolutions
3. Output Module - Predicting headways for multiple horizons

Reference: Graph WaveNet for Deep Spatial-Temporal Graph Modeling (Wu et al., 2019)
"""

import tensorflow as tf
from tensorflow.keras import Model
from tensorflow.keras.layers import Input, Dense, Conv1D, Dropout

from layers import (
    AdaptiveAdjacencyLayer,
    CombinedAdjacencyLayer,
    GraphConvBlock,
    TemporalConvStack,
)


class GraphWaveNet(Model):
    """
    Graph WaveNet for spatial-temporal forecasting.
    
    Architecture:
    1. Input projection
    2. Stacked spatial-temporal blocks:
       - Graph convolution (diffusion + adaptive)
       - Temporal convolution (dilated causal)
    3. Output layers (skip connections → ReLU → Dense → output)
    
    Args:
        num_nodes: Number of stations in the graph
        input_dim: Number of input features per node
        output_dim: Number of output features (prediction horizon)
        static_adj: Static adjacency matrix (physical graph)
        embedding_dim: Dimension for adaptive adjacency embeddings
        num_temporal_layers: Number of temporal conv layers
        temporal_channels: Channels in temporal convolutions
        spatial_channels: Channels in graph convolutions
        skip_channels: Channels for skip connections
        dropout_rate: Dropout rate for regularization
    """
    
    def __init__(
        self,
        num_nodes: int,
        input_dim: int = 1,
        output_dim: int = 12,
        static_adj=None,
        embedding_dim: int = 10,
        num_temporal_layers: int = 8,
        temporal_channels: int = 32,
        spatial_channels: int = 32,
        skip_channels: int = 256,
        dropout_rate: float = 0.3,
        **kwargs
    ):
        super(GraphWaveNet, self).__init__(**kwargs)
        
        self.num_nodes = num_nodes
        self.input_dim = input_dim
        self.output_dim = output_dim
        
        # Adaptive adjacency layer
        self.adjacency = CombinedAdjacencyLayer(
            num_nodes=num_nodes,
            embedding_dim=embedding_dim,
            static_adj=static_adj,
        )
        
        # Input projection
        self.input_projection = Conv1D(
            filters=temporal_channels,
            kernel_size=1,
            padding="same",
            activation="relu",
        )
        
        # Temporal convolution stack
        self.temporal_stack = TemporalConvStack(
            num_layers=num_temporal_layers,
            dilation_channels=temporal_channels,
            residual_channels=temporal_channels,
            skip_channels=skip_channels,
        )
        
        # Graph convolution block
        self.graph_conv = GraphConvBlock(
            output_dim=spatial_channels,
            num_diffusion_steps=2,
            dropout_rate=dropout_rate,
        )
        
        # Output layers
        self.output_conv1 = Conv1D(
            filters=skip_channels // 2,
            kernel_size=1,
            padding="same",
            activation="relu",
        )
        
        self.output_conv2 = Conv1D(
            filters=output_dim,
            kernel_size=1,
            padding="same",
            activation=None,
        )
        
        self.dropout = Dropout(dropout_rate)

    def call(self, inputs, training=None):
        """
        Forward pass of Graph WaveNet.
        
        Args:
            inputs: Input tensor of shape (batch, time, nodes, features)
            training: Whether in training mode
            
        Returns:
            Predictions of shape (batch, nodes, output_dim)
        """
        # Get batch size and reshape if needed
        batch_size = tf.shape(inputs)[0]
        
        # Compute adaptive adjacency
        adj_matrix = self.adjacency(inputs, training=training)
        
        # Input projection
        x = self.input_projection(inputs)
        
        # Temporal convolutions
        x = self.temporal_stack(x, training=training)
        
        # Graph convolution
        x = self.graph_conv(x, adj_matrix, training=training)
        
        # Output layers
        x = tf.nn.relu(x)
        x = self.output_conv1(x)
        x = self.dropout(x, training=training)
        x = self.output_conv2(x)
        
        # Take last time step for prediction
        output = x[:, -1, :]
        
        return output

    def get_config(self):
        return {
            "num_nodes": self.num_nodes,
            "input_dim": self.input_dim,
            "output_dim": self.output_dim,
        }


def build_graph_wavenet(
    num_nodes: int,
    input_window: int = 12,
    output_horizon: int = 12,
    input_features: int = 1,
    static_adj=None,
) -> Model:
    """
    Build a Graph WaveNet model.
    
    Args:
        num_nodes: Number of stations
        input_window: Number of historical time steps (default: 12 = 60 min at 5-min intervals)
        output_horizon: Number of future steps to predict
        input_features: Number of input features per node
        static_adj: Pre-computed static adjacency matrix
        
    Returns:
        Compiled Keras model
    """
    # Input: (batch, time_steps, nodes, features)
    inputs = Input(shape=(input_window, num_nodes, input_features))
    
    # Build model
    model = GraphWaveNet(
        num_nodes=num_nodes,
        input_dim=input_features,
        output_dim=output_horizon,
        static_adj=static_adj,
    )
    
    outputs = model(inputs)
    
    # Create functional model
    full_model = Model(inputs=inputs, outputs=outputs, name="GraphWaveNet")
    
    # Compile with MAE loss (robust to outliers in transit data)
    full_model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss="mae",
        metrics=["mse", "mae"],
    )
    
    return full_model


# TODO: Phase 2 Implementation
# - Complete spatial-temporal block integration
# - Add support for multiple graph structures
# - Implement batch processing for large graphs
# - Add uncertainty estimation
# - Implement attention mechanisms
