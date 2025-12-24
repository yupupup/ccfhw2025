import torch
import torch.nn as nn
import torch.nn.functional as F

class MLPModel(nn.Module):
    """Multi-Layer Perceptron Model for classification."""

    def __init__(self, input_size, hidden_sizes, num_classes=4, dropout_rate=0.2):
        """
        Initialize the MLP model.

        Args:
            input_size (int): Dimension of input features.
            hidden_sizes (list): List of hidden layer sizes.
            num_classes (int): Number of output classes.
            dropout_rate (float): Dropout probability.
        """
        super(MLPModel, self).__init__()

        self.input_size = input_size
        self.hidden_sizes = hidden_sizes
        self.num_classes = num_classes
        self.dropout_rate = dropout_rate

        layers = []
        prev_size = input_size

        # Add hidden layers
        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(prev_size, hidden_size))
            layers.append(nn.BatchNorm1d(hidden_size))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout_rate))
            prev_size = hidden_size

        # Add output layer
        layers.append(nn.Linear(prev_size, num_classes))

        self.network = nn.Sequential(*layers)

    def forward(self, x):
        """
        Forward pass.

        Args:
            x (torch.Tensor): Input tensor.

        Returns:
            torch.Tensor: Output logits.
        """
        return self.network(x)

    def predict_proba(self, x):
        """
        Predict class probabilities.

        Args:
            x (torch.Tensor): Input tensor.

        Returns:
            torch.Tensor: Class probabilities.
        """
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            probabilities = F.softmax(logits, dim=1)
        return probabilities

    def predict(self, x):
        """
        Predict class labels.

        Args:
            x (torch.Tensor): Input tensor.

        Returns:
            torch.Tensor: Predicted class indices.
        """
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            predictions = torch.argmax(logits, dim=1)
        return predictions
