import argparse
import json
import torch
import numpy as np
import os
from scripts.mlp.model import MLPModel
from scripts.mlp.data_loader import DataProcessor
from scripts.mlp.utils import load_config, get_device

class Predictor:
    """Predictor class for MLP model."""

    def __init__(self, model_path, config_path):
        """
        Initialize Predictor.

        Args:
            model_path (str): Path to the trained model.
            config_path (str): Path to the configuration file.
        """
        self.config = load_config(config_path)
        self.device = get_device()
        self.processor = DataProcessor()
        
        # Initialize model
        self.model = MLPModel(
            input_size=self.config['input_size'],
            hidden_sizes=self.config['hidden_sizes'],
            num_classes=self.config.get('num_classes', 4),
            dropout_rate=self.config.get('dropout_rate', 0.2)
        ).to(self.device)
        
        # Load weights
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.eval()
        
        # Load Scaler
        scaler_path = os.path.join(os.path.dirname(model_path), 'scaler.pkl')
        if os.path.exists(scaler_path):
            self.processor.load_scaler(scaler_path)
            print(f"Loaded scaler from {scaler_path}")
        else:
            print("Warning: scaler.pkl not found. Prediction might be inaccurate.")

    def predict(self, config_sequences):
        """
        Predict performance class for given configuration sequences.

        Args:
            config_sequences (list): List of configuration sequences.

        Returns:
            list: Predicted class indices.
        """
        # Preprocess
        processed_configs = self.processor.preprocess(config_sequences)
        
        # Normalize
        if self.processor.is_fitted:
            processed_configs = self.processor.normalize(processed_configs, fit=False)
        else:
            print("Warning: Scaler not fitted. Using raw data.")
        
        input_tensor = torch.FloatTensor(processed_configs).to(self.device)
        
        with torch.no_grad():
            predictions = self.model.predict(input_tensor)
            
        return predictions.cpu().tolist()

def main():
    parser = argparse.ArgumentParser(description='MLP Performance Prediction')
    parser.add_argument('--model', type=str, default='scripts/mlp/model.pth', help='Path to trained model')
    parser.add_argument('--config', type=str, default='scripts/mlp/config.json', help='Path to config file')
    parser.add_argument('--input', type=str, help='Input configuration sequence (e.g., "[1, 2, 3]")')
    parser.add_argument('--eval', type=str, help='Path to CSV file for evaluation')
    args = parser.parse_args()

    if not args.input and not args.eval:
        parser.error("Either --input or --eval must be provided.")

    predictor = Predictor(args.model, args.config)
    
    try:
        if args.eval:
            # Evaluation Mode
            print(f"Evaluating model on {args.eval}...")
            configs, ratios = predictor.processor.load_data(args.eval)
            true_labels = predictor.processor.create_labels(ratios)
            
            # Predict
            predictions = predictor.predict(configs)
            
            # Metrics
            from scripts.mlp.utils import calculate_metrics
            metrics = calculate_metrics(true_labels, predictions)
            
            print(f"Evaluation Results:")
            print(json.dumps(metrics, indent=4))
            
            # Print first 10 results
            class_names = ["<0.8", "0.8-1.0", "1.0-1.2", ">1.2"]
            print("\nSample Predictions:")
            for i in range(len(predictions)):
                print(f"Sample {i+1}: True={class_names[true_labels[i]]} ({ratios[i]:.4f}), Pred={class_names[predictions[i]]}")

        elif args.input:
            # Single Input Prediction Mode
            input_seq = json.loads(args.input)
            if not isinstance(input_seq, list):
                 raise ValueError("Input must be a list")
            # Wrap in list if it's a single sequence
            if isinstance(input_seq[0], int):
                input_seq = [input_seq]
                
            predictions = predictor.predict(input_seq)
            
            class_names = ["<0.8", "0.8-1.0", "1.0-1.2", ">1.2"]
            for i, pred in enumerate(predictions):
                print(f"Sequence: {input_seq[i]}")
                print(f"Predicted Class: {pred} ({class_names[pred]})")
            
    except json.JSONDecodeError:
        print("Error: Invalid JSON input.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
