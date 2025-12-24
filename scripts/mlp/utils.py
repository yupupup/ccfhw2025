import json
import torch
import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

def load_config(config_path):
    """Load configuration from a JSON file."""
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config

def save_config(config, config_path):
    """Save configuration to a JSON file."""
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

def calculate_metrics(y_true, y_pred):
    """
    Calculate evaluation metrics.
    
    Args:
        y_true (np.array): True labels.
        y_pred (np.array): Predicted labels.
        
    Returns:
        dict: Dictionary containing accuracy, precision, recall, and f1 score.
    """
    accuracy = accuracy_score(y_true, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average='weighted', zero_division=0)
    
    return {
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1': f1
    }

def get_device():
    """Get the available device (CUDA or CPU)."""
    return 'cuda' if torch.cuda.is_available() else 'cpu'
