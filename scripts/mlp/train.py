import argparse
import json
import os
import torch
import torch.nn as nn
import torch.optim as optim
from scripts.mlp.data_loader import DataProcessor
from scripts.mlp.model import MLPModel
from scripts.mlp.utils import load_config, calculate_metrics, get_device

def train_model(config, data_path, output_path):
    """
    Train the MLP model.

    Args:
        config (dict): Configuration dictionary.
        data_path (str): Path to training data.
        output_path (str): Path to save the model.
    """
    # 1. Load and Process Data
    print("Loading data...")
    processor = DataProcessor()
    configs, ratios = processor.load_data(data_path)
    
    print("Preprocessing data...")
    processed_configs = processor.preprocess(configs)
    
    # Split data first to avoid leakage, then fit scaler on training data
    # Note: For simplicity in this version, we split indices or data first
    labels = processor.create_labels(ratios)
    
    # We use the split_dataset method from processor
    # But we need to handle normalization carefully. 
    # Let's split raw data first? 
    # The processor.split_dataset takes numpy arrays.
    
    # Let's normalize everything for now as in the reference, 
    # but strictly we should fit on train only.
    # To do it correctly:
    # 1. Split raw processed_configs and labels
    # 2. Fit scaler on X_train
    # 3. Transform X_train, X_val, X_test
    
    # However, processor.split_dataset does the splitting. 
    # Let's use a slightly different approach to be correct.
    
    X_train, X_val, X_test, y_train, y_val, y_test = processor.split_dataset(
        processed_configs, labels,
        train_ratio=config.get('train_ratio', 0.7),
        val_ratio=config.get('val_ratio', 0.15)
    )
    
    # Normalize
    print("Normalizing data...")
    if len(X_train) > 0:
        X_train = processor.normalize(X_train, fit=True)
    if len(X_val) > 0:
        X_val = processor.normalize(X_val, fit=False)
    if len(X_test) > 0:
        X_test = processor.normalize(X_test, fit=False)
        
    # Create DataLoaders
    batch_size = config.get('batch_size', 32)
    train_loader = processor.create_dataloader(X_train, y_train, batch_size=batch_size)
    val_loader = processor.create_dataloader(X_val, y_val, batch_size=batch_size, shuffle=False)
    test_loader = processor.create_dataloader(X_test, y_test, batch_size=batch_size, shuffle=False)
    
    # 2. Initialize Model
    input_size = processed_configs.shape[1] if processed_configs.size > 0 else 0
    # Update config with actual input size
    config['input_size'] = input_size
    
    print(f"Initializing model with input_size={input_size}...")
    device = get_device()
    model = MLPModel(
        input_size=input_size,
        hidden_sizes=config.get('hidden_sizes', [128]),
        num_classes=config.get('num_classes', 4),
        dropout_rate=config.get('dropout_rate', 0.2)
    ).to(device)
    
    # 3. Setup Training
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=config.get('learning_rate', 0.001))
    
    epochs = config.get('epochs', 100)
    best_val_loss = float('inf')
    patience = config.get('patience', 10)
    patience_counter = 0
    
    history = {'train_loss': [], 'val_loss': [], 'val_acc': []}
    
    print("Starting training...")
    for epoch in range(epochs):
        # Training Phase
        model.train()
        train_loss = 0.0
        if train_loader:
            for inputs, targets in train_loader:
                inputs, targets = inputs.to(device), targets.to(device)
                
                optimizer.zero_grad()
                outputs = model(inputs)
                loss = criterion(outputs, targets)
                loss.backward()
                optimizer.step()
                
                train_loss += loss.item() * inputs.size(0)
            train_loss /= len(train_loader.dataset)
        
        # Validation Phase
        val_loss = 0.0
        val_preds = []
        val_targets = []
        model.eval()
        
        if val_loader:
            with torch.no_grad():
                for inputs, targets in val_loader:
                    inputs, targets = inputs.to(device), targets.to(device)
                    outputs = model(inputs)
                    loss = criterion(outputs, targets)
                    val_loss += loss.item() * inputs.size(0)
                    
                    _, preds = torch.max(outputs, 1)
                    val_preds.extend(preds.cpu().numpy())
                    val_targets.extend(targets.cpu().numpy())
            
            val_loss /= len(val_loader.dataset)
            val_metrics = calculate_metrics(val_targets, val_preds)
            val_acc = val_metrics['accuracy']
        else:
            val_loss = 0.0
            val_acc = 0.0
            
        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        history['val_acc'].append(val_acc)
        
        print(f"Epoch {epoch+1}/{epochs}: Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}, Val Acc: {val_acc:.4f}")
        
        # Early Stopping & Model Saving
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            torch.save(model.state_dict(), output_path)
            
            # Save scaler
            scaler_path = os.path.join(os.path.dirname(output_path), 'scaler.pkl')
            try:
                # We need to access the processor instance. 
                # In current scope, 'processor' is available.
                processor.save_scaler(scaler_path)
            except Exception as e:
                print(f"Warning: Failed to save scaler: {e}")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print("Early stopping triggered.")
                break
                
    print("Training completed.")
    
    # 4. Final Evaluation
    if test_loader:
        print("Evaluating on test set...")
        model.load_state_dict(torch.load(output_path))
        model.eval()
        test_preds = []
        test_targets = []
        with torch.no_grad():
            for inputs, targets in test_loader:
                inputs, targets = inputs.to(device), targets.to(device)
                outputs = model(inputs)
                _, preds = torch.max(outputs, 1)
                test_preds.extend(preds.cpu().numpy())
                test_targets.extend(targets.cpu().numpy())
        
        test_metrics = calculate_metrics(test_targets, test_preds)
        print(f"Test Metrics: {json.dumps(test_metrics, indent=4)}")

    # Save training history
    history_path = os.path.join(os.path.dirname(output_path), 'history.json')
    with open(history_path, 'w') as f:
        json.dump(history, f, indent=4)

def main():
    parser = argparse.ArgumentParser(description='Train MLP Performance Prediction Model')
    parser.add_argument('--config', type=str, default='scripts/mlp/config.json', help='Path to config file')
    parser.add_argument('--data', type=str, required=True, help='Path to training data')
    parser.add_argument('--output', type=str, default='scripts/mlp/model.pth', help='Path to save trained model')
    args = parser.parse_args()
    
    if os.path.exists(args.config):
        config = load_config(args.config)
    else:
        # Default config if file doesn't exist
        config = {
            "hidden_sizes": [128],
            "num_classes": 4,
            "dropout_rate": 0.2,
            "train_ratio": 0.7,
            "val_ratio": 0.15,
            "batch_size": 32,
            "epochs": 100,
            "learning_rate": 0.001,
            "patience": 10
        }
        # Save default config
        os.makedirs(os.path.dirname(args.config), exist_ok=True)
        with open(args.config, 'w') as f:
            json.dump(config, f, indent=4)

    # Process data to get input size
    print("Loading data...")
    processor = DataProcessor()
    configs, ratios = processor.load_data(args.data)
    processed_configs = processor.preprocess(configs)
    
    input_size = processed_configs.shape[1] if processed_configs.size > 0 else 0
    config['input_size'] = input_size
    
    # Save config with input_size
    with open(args.config, 'w') as f:
        json.dump(config, f, indent=4)
        
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    train_model(config, args.data, args.output)

if __name__ == '__main__':
    main()
