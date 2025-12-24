# AI Model Development Strategy Guide

This document provides guidance on feature engineering, data generation, and hyperparameter tuning for the MLP performance prediction model.

## 1. Feature Engineering & Evaluation

### How to evaluate if features are appropriate?
1.  **Correlation Analysis**: Calculate the correlation matrix (e.g., Pearson or Spearman) between your features and the target (performance speedup). Features with near-zero correlation might be irrelevant.
2.  **Feature Importance (Tree-based)**: Train a Random Forest or XGBoost model on your data. These models provide built-in "feature importance" scores. If a feature has a very low score, it contributes little to the prediction.
3.  **Ablation Study**:
    *   Train a baseline model with ALL features.
    *   Remove one feature (or a group of features) and retrain.
    *   If the accuracy drops significantly, that feature is important. If it stays the same or improves, the feature might be noise.

### Are there missing important features?
For code performance prediction, consider adding:
*   **Memory Access Patterns**: Number of load/store operations, cache miss rates (if available from profiling).
*   **Instruction Mix**: Ratio of floating-point vs. integer operations.
*   **Data Dependencies**: Depth of loop nests, array access strides.
*   **Graph Features**: If you can extract the Control Flow Graph (CFG) or Data Flow Graph (DFG), features like "longest path" or "number of back-edges" can be predictive.

### Are some features redundant?
*   Check for **Multicollinearity**: If Feature A and Feature B have a correlation of 0.99 (e.g., "Number of Lines" vs "Number of Statements"), you only need one of them. Keeping both can confuse the model training.

## 2. Parameter Configuration Encoding

### Handling Mixed Types (Bool vs. Large Int)
*   **Boolean**: Encoding as 0 and 1 is perfect.
*   **Large Integers (e.g., 16482)**:
    *   **Problem**: Neural networks struggle with large, unscaled numbers. They expect inputs roughly in the range of [-1, 1] or [0, 1].
    *   **Solution**: You MUST normalize or standardize these inputs.
        *   **Min-Max Scaling**: $x' = \frac{x - min}{max - min}$ (Maps to [0, 1])
        *   **Log Scaling**: If the range is huge (e.g., 10 to 1,000,000), apply $x' = \log(x + 1)$ first, then normalize.

### Sampling Strategy (0.5x to 2.0x)
*   **Is it okay?**: Yes, this is a standard "Local Search" or "Neighborhood Sampling" strategy. It focuses the model on the region around the default configuration, which is usually where the most practical gains are found.
*   **Risk**: You might miss a global optimum that lies far away (e.g., 10x the default value).
*   **Recommendation**:
    *   Start with your current [0.5x, 2.0x] strategy.
    *   If results are good, try a wider range (e.g., [0.1x, 10x]) on a small subset of parameters to see if there are surprises.

## 3. Data Generation & Quality

### How much data?
*   **Rule of Thumb**: 10x to 50x the number of model parameters.
*   **For your MLP**: With ~2,500 parameters, aim for **25,000 to 100,000 samples**.
*   **Start Small**: Generate 5,000 samples first to debug the pipeline.

### What is "High Quality" data?
1.  **Coverage**: The data should cover the input space well.
    *   *Bad*: Random sampling often clumps points together.
    *   *Good*: Use **Latin Hypercube Sampling (LHS)**. It ensures that each dimension is sampled uniformly across its range.
2.  **Balance**: Ensure your 4 output classes are roughly balanced.
    *   If "Speedup > 1.2" is very rare (e.g., 1%), the model will learn to ignore it.
    *   *Fix*: Over-sample the rare cases or use a weighted loss function.
3.  **Consistency**: Ensure the performance measurement is stable.
    *   If you run the same config twice and get 0.8 and 1.2, your data is "noisy".
    *   *Fix*: Run each config 3-5 times and take the average/median.

## 4. Hyperparameter Tuning

### Key Hyperparameters (in order of importance)
1.  **Learning Rate (LR)**: The most critical knob.
    *   *Too high*: Loss oscillates or explodes.
    *   *Too low*: Training is too slow or gets stuck.
    *   *Try*: 0.001, 0.0001, 0.0003.
2.  **Batch Size**:
    *   *Standard*: 32, 64, 128.
    *   Smaller batch size = more noise but better generalization.
    *   Larger batch size = faster training but requires more memory.
3.  **Hidden Layer Size**:
    *   Start with [128]. Try [256], [64], or [128, 64] (two layers).
4.  **Dropout Rate**:
    *   Controls overfitting.
    *   *Range*: 0.1 to 0.5. Increase if Train Acc >> Test Acc.

### How to tune?
*   **Manual**: "Grid Search" (try all combinations of a few values).
*   **Automated (Recommended)**: Use a library like **Optuna**.
    *   It automatically tries different combinations and "learns" which ones work best.
    *   It saves you hours of manual trial and error.

## Summary Checklist for Next Steps
1.  [ ] Implement **LHS sampling** for data generation.
2.  [ ] Add **Normalization** for integer parameters in `data_loader.py`.
3.  [ ] Collect **5,000 samples** and check Class Balance.
4.  [ ] Use **Optuna** to find the best Learning Rate and Hidden Size.
