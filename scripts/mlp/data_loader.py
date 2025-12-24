import json
import pandas as pd
import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

class DataProcessor:
    """Data Processor for MLP model."""

    def __init__(self):
        """Initialize DataProcessor."""
        self.scaler = StandardScaler()
        self.is_fitted = False

    def save_scaler(self, path):
        import pickle
        with open(path, 'wb') as f:
            pickle.dump(self.scaler, f)
            
    def load_scaler(self, path):
        import pickle
        with open(path, 'rb') as f:
            self.scaler = pickle.load(f)
        self.is_fitted = True

    def save_scaler(self, path):
        import pickle
        with open(path, 'wb') as f:
            pickle.dump(self.scaler, f)
            
    def load_scaler(self, path):
        import pickle
        with open(path, 'rb') as f:
            self.scaler = pickle.load(f)
        self.is_fitted = True

    def load_data(self, data_path):
        """
        Load data from CSV or JSON file.

        Args:
            data_path (str): Path to the data file.

        Returns:
            tuple: (configurations, performance_ratios)
        """
        if data_path.endswith('.csv'):
            data = pd.read_csv(data_path)
        elif data_path.endswith('.json'):
            data = pd.read_json(data_path)
        else:
            raise ValueError("Unsupported file format. Please provide CSV or JSON file.")

        # Check for expected columns
        if 'config_sequence' in data.columns and 'performance_ratio' in data.columns:
            # Handle string representation of lists if necessary
            if isinstance(data['config_sequence'].iloc[0], str):
                 configurations = data['config_sequence'].apply(eval).tolist()
            else:
                 configurations = data['config_sequence'].tolist()
            performance_ratios = data['performance_ratio'].tolist()
        else:
            # Fallback: assume last column is target, rest are features
            configurations = data.iloc[:, :-1].values.tolist()
            performance_ratios = data.iloc[:, -1].tolist()

        return configurations, performance_ratios

    def preprocess(self, config_sequences):
        """
        Preprocess configuration sequences (padding).

        Args:
            config_sequences (list): List of configuration sequences.

        Returns:
            np.array: Padded configuration sequences.
        """
        if not config_sequences:
            return np.array([])

        # Ensure sequences are lists
        if isinstance(config_sequences[0], str):
             config_sequences = [eval(seq) for seq in config_sequences]

        max_length = max(len(seq) for seq in config_sequences) if config_sequences else 0
        processed_sequences = []

        for seq in config_sequences:
            # Pad with 0s
            if len(seq) < max_length:
                padded_seq = seq + [0] * (max_length - len(seq))
            else:
                padded_seq = seq[:max_length]
            processed_sequences.append(padded_seq)

        return np.array(processed_sequences)

    def normalize(self, data, fit=True):
        """
        Normalize data using StandardScaler.

        Args:
            data (np.array): Input data.
            fit (bool): Whether to fit the scaler.

        Returns:
            np.array: Normalized data.
        """
        if data.shape[0] == 0:
            return data
        
        if fit:
            normalized_data = self.scaler.fit_transform(data)
            self.is_fitted = True
        else:
            if not self.is_fitted:
                raise ValueError("Scaler is not fitted. Call normalize with fit=True first.")
            normalized_data = self.scaler.transform(data)

        return normalized_data

    def create_labels(self, performance_ratios):
        """
        Create classification labels from performance ratios.

        Args:
            performance_ratios (list): List of performance ratios.

        Returns:
            np.array: Array of labels (0-3).
        """
        labels = []
        for ratio in performance_ratios:
            if ratio < 0.8:
                labels.append(0)
            elif ratio < 1.0:
                labels.append(1)
            elif ratio < 1.2:
                labels.append(2)
            else:
                labels.append(3)

        return np.array(labels)

    def split_dataset(self, data, labels, train_ratio=0.7, val_ratio=0.15, random_state=42):
        """
        Split dataset into train, validation, and test sets.

        Args:
            data (np.array): Input features.
            labels (np.array): Target labels.
            train_ratio (float): Ratio of training data.
            val_ratio (float): Ratio of validation data.
            random_state (int): Random seed.

        Returns:
            tuple: (X_train, X_val, X_test, y_train, y_val, y_test)
        """
        test_ratio = 1.0 - train_ratio - val_ratio
        
        # First split: Train vs (Val + Test)
        X_train, X_temp, y_train, y_temp = train_test_split(
            data, labels, test_size=(val_ratio + test_ratio), random_state=random_state
        )

        if val_ratio + test_ratio > 0:
            # Second split: Val vs Test
            # Calculate relative test size for the second split
            relative_test_size = test_ratio / (val_ratio + test_ratio)
            if relative_test_size > 0 and relative_test_size < 1:
                X_val, X_test, y_val, y_test = train_test_split(
                    X_temp, y_temp, test_size=relative_test_size, random_state=random_state
                )
            elif relative_test_size == 0:
                 X_val, y_val = X_temp, y_temp
                 X_test, y_test = np.array([]), np.array([])
            else: # relative_test_size == 1
                 X_val, y_val = np.array([]), np.array([])
                 X_test, y_test = X_temp, y_temp
        else:
            X_val, X_test = np.array([]), np.array([])
            y_val, y_test = np.array([]), np.array([])

        return X_train, X_val, X_test, y_train, y_val, y_test

    def create_dataloader(self, data, labels, batch_size=32, shuffle=True):
        """
        Create PyTorch DataLoader.

        Args:
            data (np.array): Input features.
            labels (np.array): Target labels.
            batch_size (int): Batch size.
            shuffle (bool): Whether to shuffle the data.

        Returns:
            DataLoader: PyTorch DataLoader.
        """
        if len(data) == 0:
            return None
        
        data_tensor = torch.FloatTensor(data)
        labels_tensor = torch.LongTensor(labels)
        
        dataset = TensorDataset(data_tensor, labels_tensor)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)
        
        return dataloader
