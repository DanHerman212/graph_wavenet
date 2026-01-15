"""
Temporal Convolution Layers for Graph WaveNet

Implements dilated causal convolutions with gated activation units
for capturing long-range temporal dependencies in headway data.
"""

import tensorflow as tf
from tensorflow.keras.layers import Layer, Conv1D, Dense


class GatedTemporalConvolution(Layer):
    """
    Gated Temporal Convolution Layer with dilated causal convolution.
    
    Uses the WaveNet-style gated activation:
        z = tanh(W_f * x) ⊙ σ(W_g * x)
    
    Where:
        - W_f: Filter weights (feature extraction)
        - W_g: Gate weights (information control)
        - tanh extracts features
        - σ (sigmoid) gates information flow
    
    Args:
        filters: Number of output filters
        kernel_size: Size of convolution kernel
        dilation_rate: Dilation rate for receptive field expansion
    """
    
    def __init__(
        self,
        filters: int,
        kernel_size: int = 2,
        dilation_rate: int = 1,
        **kwargs
    ):
        super(GatedTemporalConvolution, self).__init__(**kwargs)
        self.filters = filters
        self.kernel_size = kernel_size
        self.dilation_rate = dilation_rate

    def build(self, input_shape):
        """Build filter and gate convolutions."""
        # Filter convolution (tanh branch)
        self.filter_conv = Conv1D(
            filters=self.filters,
            kernel_size=self.kernel_size,
            dilation_rate=self.dilation_rate,
            padding="causal",
            activation=None,
            name="filter_conv"
        )
        
        # Gate convolution (sigmoid branch)
        self.gate_conv = Conv1D(
            filters=self.filters,
            kernel_size=self.kernel_size,
            dilation_rate=self.dilation_rate,
            padding="causal",
            activation=None,
            name="gate_conv"
        )
        
        super(GatedTemporalConvolution, self).build(input_shape)

    def call(self, inputs, training=None):
        """
        Apply gated temporal convolution.
        
        Args:
            inputs: Tensor of shape (batch, time, features)
            training: Whether in training mode
            
        Returns:
            Gated output of shape (batch, time, filters)
        """
        # Filter branch
        filter_output = tf.nn.tanh(self.filter_conv(inputs))
        
        # Gate branch
        gate_output = tf.nn.sigmoid(self.gate_conv(inputs))
        
        # Element-wise multiplication (gating)
        output = filter_output * gate_output
        
        return output

    def get_config(self):
        config = super(GatedTemporalConvolution, self).get_config()
        config.update({
            "filters": self.filters,
            "kernel_size": self.kernel_size,
            "dilation_rate": self.dilation_rate,
        })
        return config


class TemporalConvBlock(Layer):
    """
    Temporal Convolution Block with residual connections.
    
    Combines gated temporal convolution with:
    - 1x1 convolution for channel mixing
    - Residual connection
    - Skip connection for gradient flow
    
    Args:
        dilation_channels: Channels for dilated convolution
        residual_channels: Channels for residual path
        skip_channels: Channels for skip connection output
        kernel_size: Convolution kernel size
        dilation_rate: Dilation rate
    """
    
    def __init__(
        self,
        dilation_channels: int = 32,
        residual_channels: int = 32,
        skip_channels: int = 256,
        kernel_size: int = 2,
        dilation_rate: int = 1,
        **kwargs
    ):
        super(TemporalConvBlock, self).__init__(**kwargs)
        self.dilation_channels = dilation_channels
        self.residual_channels = residual_channels
        self.skip_channels = skip_channels
        self.kernel_size = kernel_size
        self.dilation_rate = dilation_rate

    def build(self, input_shape):
        """Build layer components."""
        # Gated temporal convolution
        self.gated_conv = GatedTemporalConvolution(
            filters=self.dilation_channels,
            kernel_size=self.kernel_size,
            dilation_rate=self.dilation_rate,
        )
        
        # 1x1 convolution for residual connection
        self.residual_conv = Conv1D(
            filters=self.residual_channels,
            kernel_size=1,
            padding="same",
            activation=None,
            name="residual_conv"
        )
        
        # 1x1 convolution for skip connection
        self.skip_conv = Conv1D(
            filters=self.skip_channels,
            kernel_size=1,
            padding="same",
            activation=None,
            name="skip_conv"
        )
        
        # Project input if needed for residual
        input_channels = input_shape[-1]
        if input_channels != self.residual_channels:
            self.input_projection = Conv1D(
                filters=self.residual_channels,
                kernel_size=1,
                padding="same",
                activation=None,
                name="input_projection"
            )
        else:
            self.input_projection = None
        
        super(TemporalConvBlock, self).build(input_shape)

    def call(self, inputs, training=None):
        """
        Apply temporal convolution block.
        
        Args:
            inputs: Input tensor
            training: Whether in training mode
            
        Returns:
            Tuple of (residual_output, skip_output)
        """
        # Gated convolution
        x = self.gated_conv(inputs, training=training)
        
        # Skip connection output
        skip = self.skip_conv(x)
        
        # Residual path
        residual = self.residual_conv(x)
        
        # Add residual connection
        if self.input_projection is not None:
            inputs = self.input_projection(inputs)
        
        residual_output = inputs + residual
        
        return residual_output, skip

    def get_config(self):
        config = super(TemporalConvBlock, self).get_config()
        config.update({
            "dilation_channels": self.dilation_channels,
            "residual_channels": self.residual_channels,
            "skip_channels": self.skip_channels,
            "kernel_size": self.kernel_size,
            "dilation_rate": self.dilation_rate,
        })
        return config


class TemporalConvStack(Layer):
    """
    Stack of Temporal Convolution Blocks with exponentially increasing dilations.
    
    Creates a receptive field that grows exponentially with depth:
    - Layer 0: dilation = 1, receptive field = 2
    - Layer 1: dilation = 2, receptive field = 4
    - Layer 2: dilation = 4, receptive field = 8
    - ...
    
    Args:
        num_layers: Number of temporal conv blocks
        dilation_channels: Channels for dilated convolution
        residual_channels: Channels for residual path
        skip_channels: Channels for skip connections
        kernel_size: Convolution kernel size
    """
    
    def __init__(
        self,
        num_layers: int = 8,
        dilation_channels: int = 32,
        residual_channels: int = 32,
        skip_channels: int = 256,
        kernel_size: int = 2,
        **kwargs
    ):
        super(TemporalConvStack, self).__init__(**kwargs)
        self.num_layers = num_layers
        self.dilation_channels = dilation_channels
        self.residual_channels = residual_channels
        self.skip_channels = skip_channels
        self.kernel_size = kernel_size

    def build(self, input_shape):
        """Build stack of temporal convolution blocks."""
        self.blocks = []
        
        for i in range(self.num_layers):
            # Exponentially increasing dilation
            dilation_rate = 2 ** i
            
            block = TemporalConvBlock(
                dilation_channels=self.dilation_channels,
                residual_channels=self.residual_channels,
                skip_channels=self.skip_channels,
                kernel_size=self.kernel_size,
                dilation_rate=dilation_rate,
                name=f"temporal_block_{i}"
            )
            self.blocks.append(block)
        
        # Calculate receptive field
        self.receptive_field = sum(
            (self.kernel_size - 1) * (2 ** i) for i in range(self.num_layers)
        ) + 1
        
        super(TemporalConvStack, self).build(input_shape)

    def call(self, inputs, training=None):
        """
        Apply stack of temporal convolutions.
        
        Args:
            inputs: Input tensor of shape (batch, time, nodes, features)
            training: Whether in training mode
            
        Returns:
            Sum of all skip connections
        """
        x = inputs
        skip_connections = []
        
        for block in self.blocks:
            x, skip = block(x, training=training)
            skip_connections.append(skip)
        
        # Sum all skip connections
        output = tf.add_n(skip_connections)
        
        return output

    def get_config(self):
        config = super(TemporalConvStack, self).get_config()
        config.update({
            "num_layers": self.num_layers,
            "dilation_channels": self.dilation_channels,
            "residual_channels": self.residual_channels,
            "skip_channels": self.skip_channels,
            "kernel_size": self.kernel_size,
        })
        return config
