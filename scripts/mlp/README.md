# MLP Performance Prediction Model

This directory contains the implementation of a Multi-Layer Perceptron (MLP) model for predicting performance speedup ratios based on parameter configuration sequences.

## Directory Structure

- `model.py`: Defines the `MLPModel` architecture using PyTorch.
- `data_loader.py`: Handles data loading, preprocessing (padding), and splitting.
- `train.py`: Script for training the model.
- `predict.py`: Script for making predictions using a trained model.
- `utils.py`: Utility functions for metrics and configuration management.
- `DESIGN.md`: Design document detailing requirements and implementation details.
- `config.json`: Configuration file for model hyperparameters (generated during training if not present).

## Usage

### 1. Data Preparation

The model accepts data in CSV or JSON format.
- **CSV**: Should contain columns `config_sequence` (string representation of list or list) and `performance_ratio` (float).
- **JSON**: List of objects with `config_sequence` and `performance_ratio` keys.

Example `data.csv`:
```csv
config_sequence,performance_ratio
"[10, 20, 30]",1.1
"[5, 15, 25]",0.7
...
```

### 2. Training

To train the model, run `train.py`. You must specify the data path.

```bash
python3 scripts/mlp/train.py --data /path/to/your/data.csv --output scripts/mlp/model.pth
```

Optional arguments:
- `--config`: Path to a JSON config file (default: `scripts/mlp/config.json`).
- `--output`: Path to save the trained model (default: `scripts/mlp/model.pth`).

The training script will automatically split the data into Train/Validation/Test sets, normalize features, and save the best model.

### 3. Prediction

To predict the performance class for a new configuration sequence:

```bash
python3 scripts/mlp/predict.py --model scripts/mlp/model.pth --input "[10, 20, 30]"
```

Arguments:
- `--model`: Path to the trained model file.
- `--config`: Path to the config file used during training (to ensure correct model architecture).
- `--input`: The configuration sequence as a JSON string (e.g., `"[1, 2, 3]"`).

**Output Classes:**
- **0**: Speedup < 0.8
- **1**: 0.8 <= Speedup < 1.0
- **2**: 1.0 <= Speedup < 1.2
- **3**: Speedup >= 1.2

### 4. Dataset Generation

To generate training data using Octane benchmarks:

```bash
python3 scripts/mlp/generate_dataset.py \
    --d8-path /path/to/d8 \
    --octane-path /path/to/v8/test/benchmarks/data/octane \
    --output scripts/mlp/dataset.csv \
    --samples 100 \
    --benchmark richards \
    --jobs 4  # Optional: run with 4 parallel jobs
```

### 5. Docker Usage

If you don't have PyTorch installed locally, you can use the provided Docker setup.

**Build the image:**
```bash
./scripts/mlp/docker_build.sh
```

**Run scripts inside Docker:**
```bash
# Train
./scripts/mlp/docker_run.sh scripts/mlp/train.py --data scripts/mlp/dataset.csv --output scripts/mlp/model.pth

# Predict
./scripts/mlp/docker_run.sh scripts/mlp/predict.py --model scripts/mlp/model.pth --input "[10, 20, 30]"
```

## Requirements

- Python 3.x
- PyTorch
- Pandas
- NumPy
- Scikit-learn
- Docker (optional)

### 6. Current Progress

1. 测试目标程序。针对octane数据集中的richards.js测试程序进行
2. 因为只针对单个程序做复现，当前模型的输入只包含参数配置序列而不包含特征向量
3. 模型输出为预测当前配置序列在上述测试程序中能达到的加速比，加速比分为4类。
4. 参数配置序列的选择：为了降低工作量，目前仅选用了10个参数作为调优目标参数，具体见代码。
5. 测试数据集的生成：使用随机的方式生成500条配置序列，使用opentuner搜索的方式生成200条配置序列。
6. 模型效果的评估：使用随机的方式生成70条数据作为测试数据集。在测试数据集上的评估模型准确率达到了80%

### 7. Results

The results of the model on the test set are as follows:

```bash
python3 scripts/mlp/predict.py --eval scripts/mlp/dataset_test.csv --model scripts/mlp/model.pth
```

Evaluation Results:

```json
{
    "accuracy": 0.8028169014084507,
    "precision": 0.8146526216120251,
    "recall": 0.8028169014084507,
    "f1": 0.8061890404007623
}
```
