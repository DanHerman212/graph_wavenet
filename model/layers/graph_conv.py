"""
Graph Convolution Layers for Graph WaveNet

Implements diffusion convolution on the graph structure,
allowing information to propagate through the subway network.
"""

import tensorflow as tf
from tensorflow.keras.layers import Layer, Dense


class DiffusionConvolution(Layer):
    """
    Diffusion convolution layer for graph neural networks.
    
    Implements K-hop diffusion using the transition matrix of the graph.
    For bidirectional diffusion, uses both forward and backward transitions:
    
        Z = sum_{k=0}^{K-1} (P_f^k * X * W_k^f + P_b^k * X * W_k^b)
    
    Where:
        - P_f: Forward transition matrix (random walk)
        - P_b: Backward transition matrix
        - X: Input features
        - W: Learnable weights
    
    Args:
        output_dim: Number of output channels
        num_diffusion_steps: Number of diffusion steps K (default: 2)
        use_bias: Whether to use bias in dense layers
    """
    
    def __init__(
        self,
        output_dim: int,
        num_diffusion_steps: int = 2,
        use_bias: bool = True,
        **kwargs
    ):
        super(DiffusionConvolution, self).__init__(**kwargs)
        self.output_dim = output_dim
        self.num_diffusion_steps = num_diffusion_steps
        self.use_bias = use_bias
        
        # Create dense layers for each diffusion step
        self.forward_layers = []
        self.backward_layers = []

    def build(self, input_shape):
        """Build dense layers for each diffusion step."""
        input_dim = input_shape[-1]
        
        for k in range(self.num_diffusion_steps):
            self.forward_layers.append(
                Dense(
                    self.output_dim,
                    use_bias=False,
                    kernel_initializer="glorot_uniform",
                    name=f"forward_step_{k}"
                )
            )
            self.backward_layers.append(
                Dense(
                    self.output_dim,
                    use_bias=False,
                    kernel_initializer="glorot_uniform",
                    name=f"backward_step_{k}"
                )
            )
        
        if self.use_bias:
            self.bias = self.add_weight(
                name="bias",
                shape=(self.output_dim,),
                initializer="zeros",
                trainable=True,
            )
        
        super(DiffusionConvolution, self).build(input_shape)

    def call(self, inputs, adj_matrix, training=None):
        """
        Apply diffusion convolution.
        
        Args:
            inputs: Node features of shape (batch, nodes, features)
            adj_matrix: Adjacency matrix of shape (nodes, nodes)
            training: Whether in training mode
            
        Returns:
            Convolved features of shape (batch, nodes, output_dim)
        """
        # Compute transition matrices
        P_forward = self._compute_transition_matrix(adj_matrix)
        P_backward = self._compute_transition_matrix(tf.transpose(adj_matrix))
        
        # Initialize output
        outputs = []
        
        # Forward diffusion
        x_forward = inputs
        for k in range(self.num_diffusion_steps):
            if k > 0:
                # Apply k-hop diffusion: P^k * X
                x_forward = tf.matmul(P_forward, x_forward)
            
            # Apply learnable transformation
            outputs.append(self.forward_layers[k](x_forward))
        
        # Backward diffusion
        x_backward = inputs
        for k in range(self.num_diffusion_steps):
            if k > 0:
                x_backward = tf.matmul(P_backward, x_backward)
            
            outputs.append(self.backward_layers[k](x_backward))
        
        # Sum all diffusion steps
        output = tf.add_n(outputs)
        
        if self.use_bias:
            output = output + self.bias
        
        return output

    def _compute_transition_matrix(self, adj_matrix):
        """
        Compute random walk transition matrix.
        
        P = D^{-1} * A (row-normalized adjacency)
        """
        # Add self-loops
        adj_with_self = adj_matrix + tf.eye(tf.shape(adj_matrix)[0])
        
        # Compute degree (row sum)
        degree = tf.reduce_sum(adj_with_self, axis=-1, keepdims=True)
        
        # Row normalize
        transition = adj_with_self / (degree + 1e-8)
        
        return transition

    def get_config(self):
        config = super(DiffusionConvolution, self).get_config()
        config.update({
            "output_dim": self.output_dim,
            "num_diffusion_steps": self.num_diffusion_steps,
            "use_bias": self.use_bias,
        })
        return config


class GraphConvBlock(Layer):
    """
    Graph convolution block combining diffusion convolution with
    batch normalization and activation.
    
    Args:
        output_dim: Number of output channels
        num_diffusion_steps: Number of diffusion steps
        activation: Activation function
        dropout_rate: Dropout rate for regularization
    """
    
    def __init__(
        self,
        output_dim: int,
        num_diffusion_steps: int = 2,
        activation: str = "relu",
        dropout_rate: float = 0.1,
        **kwargs
    ):
        super(GraphConvBlock, self).__init__(**kwargs)
        self.output_dim = output_dim
        self.num_diffusion_steps = num_diffusion_steps
        self.activation_name = activation
        self.dropout_rate = dropout_rate
        
        self.diff_conv = DiffusionConvolution(
            output_dim=output_dim,
            num_diffusion_steps=num_diffusion_steps,
        )
        self.batch_norm = tf.keras.layers.BatchNormalization()
        self.activation = tf.keras.layers.Activation(activation)
        self.dropout = tf.keras.layers.Dropout(dropout_rate)

    def call(self, inputs, adj_matrix, training=None):
        """Apply graph convolution block."""
        x = self.diff_conv(inputs, adj_matrix, training=training)
        x = self.batch_norm(x, training=training)
        x = self.activation(x)
        x = self.dropout(x, training=training)
        return x

    def get_config(self):
        config = super(GraphConvBlock, self).get_config()
        config.update({
            "output_dim": self.output_dim,
            "num_diffusion_steps": self.num_diffusion_steps,
            "activation": self.activation_name,
            "dropout_rate": self.dropout_rate,
        })
        return config
