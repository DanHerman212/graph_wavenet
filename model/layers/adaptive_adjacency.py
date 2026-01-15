"""
Adaptive Adjacency Layer for Graph WaveNet

Learns the hidden spatial dependencies between subway stations
that are not captured by the physical track graph.

Reference: Graph WaveNet for Deep Spatial-Temporal Graph Modeling (Wu et al., 2019)
"""

import tensorflow as tf
from tensorflow.keras.layers import Layer


class AdaptiveAdjacencyLayer(Layer):
    """
    Implements the learned graph structure mechanism of Graph WaveNet.
    
    This layer learns two node embedding matrices (E1, E2) that capture
    source and target relationships between nodes. The adaptive adjacency
    matrix is computed as:
    
        A_adp = SoftMax(ReLU(E1 * E2^T))
    
    This allows the model to discover hidden spatial dependencies that
    aren't present in the physical graph (e.g., delays propagating through
    transfer stations or shared infrastructure).
    
    Args:
        num_nodes: Number of nodes (stations) in the graph
        embedding_dim: Dimension of node embeddings (default: 10)
        use_softmax: Whether to apply softmax normalization (default: True)
    """
    
    def __init__(
        self,
        num_nodes: int,
        embedding_dim: int = 10,
        use_softmax: bool = True,
        **kwargs
    ):
        super(AdaptiveAdjacencyLayer, self).__init__(**kwargs)
        self.num_nodes = num_nodes
        self.embedding_dim = embedding_dim
        self.use_softmax = use_softmax

    def build(self, input_shape):
        """Initialize the learnable node embeddings."""
        # Source node embeddings (E1)
        self.node_embeddings_1 = self.add_weight(
            name="E1",
            shape=(self.num_nodes, self.embedding_dim),
            initializer="glorot_uniform",
            trainable=True,
            regularizer=tf.keras.regularizers.l2(1e-4),
        )
        
        # Target node embeddings (E2)
        self.node_embeddings_2 = self.add_weight(
            name="E2",
            shape=(self.num_nodes, self.embedding_dim),
            initializer="glorot_uniform",
            trainable=True,
            regularizer=tf.keras.regularizers.l2(1e-4),
        )
        
        super(AdaptiveAdjacencyLayer, self).build(input_shape)

    def call(self, inputs, training=None):
        """
        Compute the adaptive adjacency matrix.
        
        Args:
            inputs: Not used, but required for Keras compatibility
            training: Whether in training mode
            
        Returns:
            Adaptive adjacency matrix of shape (num_nodes, num_nodes)
        """
        # Compute similarity matrix: E1 * E2^T
        matmul = tf.matmul(
            self.node_embeddings_1,
            self.node_embeddings_2,
            transpose_b=True
        )
        
        # Apply ReLU to sparsify the graph (remove weak/negative connections)
        activation = tf.nn.relu(matmul)
        
        # Apply SoftMax to normalize edge weights (row-wise)
        if self.use_softmax:
            adj_matrix = tf.nn.softmax(activation, axis=-1)
        else:
            # Alternative: row normalization without softmax
            row_sum = tf.reduce_sum(activation, axis=-1, keepdims=True)
            adj_matrix = activation / (row_sum + 1e-8)
        
        return adj_matrix

    def get_config(self):
        """Return layer configuration for serialization."""
        config = super(AdaptiveAdjacencyLayer, self).get_config()
        config.update({
            "num_nodes": self.num_nodes,
            "embedding_dim": self.embedding_dim,
            "use_softmax": self.use_softmax,
        })
        return config

    @classmethod
    def from_config(cls, config):
        """Create layer from configuration."""
        return cls(**config)


class CombinedAdjacencyLayer(Layer):
    """
    Combines static (physical) and adaptive (learned) adjacency matrices.
    
    The Graph WaveNet uses both:
    1. Static adjacency: Derived from physical track connectivity
    2. Adaptive adjacency: Learned end-to-end from data
    
    Args:
        num_nodes: Number of nodes in the graph
        embedding_dim: Dimension for adaptive embeddings
        static_adj: Pre-computed static adjacency matrix (optional)
    """
    
    def __init__(
        self,
        num_nodes: int,
        embedding_dim: int = 10,
        static_adj=None,
        **kwargs
    ):
        super(CombinedAdjacencyLayer, self).__init__(**kwargs)
        self.num_nodes = num_nodes
        self.embedding_dim = embedding_dim
        self._static_adj = static_adj
        
        # Create adaptive layer
        self.adaptive_layer = AdaptiveAdjacencyLayer(
            num_nodes=num_nodes,
            embedding_dim=embedding_dim,
        )

    def build(self, input_shape):
        """Initialize static adjacency as a non-trainable weight."""
        if self._static_adj is not None:
            self.static_adj = self.add_weight(
                name="static_adj",
                shape=(self.num_nodes, self.num_nodes),
                initializer=tf.constant_initializer(self._static_adj),
                trainable=False,
            )
        else:
            # Default to identity if no static adjacency provided
            self.static_adj = self.add_weight(
                name="static_adj",
                shape=(self.num_nodes, self.num_nodes),
                initializer="identity",
                trainable=False,
            )
        
        # Learnable weights for combining static and adaptive
        self.alpha = self.add_weight(
            name="alpha",
            shape=(1,),
            initializer=tf.constant_initializer(0.5),
            trainable=True,
            constraint=tf.keras.constraints.MinMaxNorm(min_value=0.0, max_value=1.0),
        )
        
        super(CombinedAdjacencyLayer, self).build(input_shape)

    def call(self, inputs, training=None):
        """
        Compute combined adjacency matrix.
        
        Returns:
            Weighted combination of static and adaptive adjacency
        """
        # Get adaptive adjacency
        adaptive_adj = self.adaptive_layer(inputs, training=training)
        
        # Combine with learned weight
        alpha = tf.sigmoid(self.alpha)  # Ensure in [0, 1]
        combined = alpha * self.static_adj + (1 - alpha) * adaptive_adj
        
        return combined

    def get_config(self):
        config = super(CombinedAdjacencyLayer, self).get_config()
        config.update({
            "num_nodes": self.num_nodes,
            "embedding_dim": self.embedding_dim,
        })
        return config
