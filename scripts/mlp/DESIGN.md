# MLP Performance Prediction Model Design Document

## 1. Requirement Analysis

### 1.1 Goal
Develop a Machine Learning model to predict the performance speedup ratio of a system based on its parameter configuration.

### 1.2 Input
- **Parameter Configuration Sequence**: A sequence of integers representing different configuration parameters.
- **Code Feature Vector**: (Reserved for future use, currently empty).

### 1.3 Output
Classification into 4 categories based on speedup ratio:
0. Speedup < 0.8
1. 0.8 <= Speedup < 1.0
2. 1.0 <= Speedup < 1.2
3. Speedup >= 1.2

### 1.4 Constraints
- Model: Multi-Layer Perceptron (MLP).
- Initial Architecture: 1 Hidden Layer (adjustable).
- Framework: PyTorch (implied by context and `mlp_qwen` reference).

## 2. Functional Module Division

### 2.1 Data Processing (`data_loader.py`)
- **Functionality**:
    - Load raw data (JSON/CSV).
    - Parse integer sequences.
    - Handle variable-length sequences (Padding).
    - Normalize data (StandardScaler).
    - Map speedup ratios to 4 classification labels.
    - Split into Train/Validation/Test sets.
    - Provide PyTorch DataLoaders.

### 2.2 Model Definition (`model.py`)
- **Functionality**:
    - Define `MLP` class inheriting from `torch.nn.Module`.
    - Configurable input size, hidden layer sizes, and output classes.
    - Forward pass implementation.

### 2.3 Training Engine (`train.py`)
- **Functionality**:
    - Initialize model, optimizer (Adam), and loss function (CrossEntropyLoss).
    - Training loop with batches.
    - Validation loop to monitor performance.
    - Save best model checkpoint.
    - Log training history.

### 2.4 Inference Interface (`predict.py`)
- **Functionality**:
    - Load trained model.
    - Preprocess single/batch input.
    - Return predicted class and probability.

### 2.5 Utilities (`utils.py`)
- **Functionality**:
    - Evaluation metrics (Accuracy, Precision, Recall, F1).
    - Plotting (optional).
    - Config loading.

### 2.6 Dataset Generation (`generate_dataset.py`)
- **Functionality**:
    - **Dual Modes**:
        - **Random Mode**: Uniformly samples parameters from defined ranges.
        - **OpenTuner Mode**: Uses OpenTuner's evolutionary algorithms (e.g., AUC Bandit) to actively search for high-performance configurations.
    - **Parallel Execution**: Supports multi-process execution (`--jobs`) to speed up data collection.
    - **Noise Reduction**: Supports repeating benchmarks (`--repeats`) and averaging scores to mitigate runtime variance.
    - **Output**: Generates a CSV file containing configuration vectors, performance ratios, and raw scores.

## 3. Implementation Steps
1.  **Data Loader**: Implement `DataProcessor` class.
2.  **Model**: Implement `MLPModel` class.
3.  **Training**: Implement `train_model` function and main script.
4.  **Prediction**: Implement `Predictor` class.
5.  **Testing**: Create dummy data to verify the pipeline.
