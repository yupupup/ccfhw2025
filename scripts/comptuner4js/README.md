# V8CompTuner

**V8CompTuner** is an automated tuning tool for the V8 JavaScript engine, adapted from the CompTuner methodology. It uses **Active Learning** with a **Random Forest** surrogate model to efficiently explore the high-dimensional space of V8 compilation flags and parameters.

## Key Features

*   **Mixed Parameter Types**: Unlike the original CompTuner which only supported boolean flags, V8CompTuner supports:
    *   `Boolean`: e.g., `--turbo-splitting`
    *   `Integer`: e.g., `--max-inlined-bytecode-size`
    *   `Float`: e.g., probability thresholds
*   **Active Learning Loop**: Uses Expected Improvement (EI) to balance exploration (finding unknown regions) and exploitation (optimizing known good regions).
*   **Modular Design**: Built on top of shared utilities (`ParameterSpace`, `ConfigGenerator`, `OctaneRunner`) for easy integration with different benchmarks.

## Architecture

### 1. `V8CompTuner` Class
The core controller that manages the tuning loop.
*   **Input**: A `ParameterSpace` defining the search space and a `BenchmarkRunner` (e.g., `OctaneRunner`) to evaluate configurations.
*   **Model**: Uses `sklearn.ensemble.RandomForestRegressor` to predict the performance of untried configurations.
*   **Acquisition Function**: Uses **Expected Improvement (EI)** to select the next batch of configurations to evaluate.

### 2. The Tuning Loop
1.  **Initialization**: Randomly samples a small set of configurations (default 2) and evaluates them to initialize the model.
2.  **Candidate Generation**: In each iteration, generates a large pool (30,000) of random "neighbor" configurations.
3.  **Prediction**: The Random Forest model predicts the performance (mean and variance) of these candidates.
4.  **Selection**:
    *   Calculates EI for all candidates.
    *   Selects the candidate with the highest EI.
    *   *Adaptive Exploration*: If the model's prediction accuracy is low (error > 5%), it probabilistically selects additional candidates based on their EI distribution to improve model coverage.
5.  **Evaluation**: Runs the selected configuration(s) using the `BenchmarkRunner` to get the true score.
6.  **Update**: Adds the new data to the training set and retrains the Random Forest model.
7.  **Termination**: Stops when 50 samples are collected or model accuracy converges (error < 4%).

## Usage

```python
from scripts.comptuner4js.v8_tuner import V8CompTuner
from scripts.utils.parameters import ParameterSpace, Parameter
from scripts.utils.benchmark_runner import OctaneRunner

# 1. Define Parameter Space
params = [
    Parameter("turbo_splitting", "boolean", True),
    Parameter("max_inlined_bytecode_size", "integer", 500, min=100, max=1000)
]
space = ParameterSpace(params)

# 2. Initialize Runner
runner = OctaneRunner(d8_path="/path/to/d8", octane_dir="/path/to/octane")

# 3. Start Tuning
tuner = V8CompTuner(space, runner, log_file="tuner.log")
model, best_configs, best_scores = tuner.build_RF_model()
```

## Algorithm Details

### Expected Improvement (EI)
The tuner uses the standard EI formula for maximization:
$$ EI(x) = (\mu(x) - f_{best}) \Phi(Z) + \sigma(x) \phi(Z) $$
Where:
*   $Z = \frac{\mu(x) - f_{best}}{\sigma(x)}$
*   $\mu(x), \sigma(x)$ are the predicted mean and standard deviation.
*   $f_{best}$ is the current best observed score.
*   $\Phi$ and $\phi$ are the CDF and PDF of the standard normal distribution.

### Vector Representation
Configurations are converted to a numerical vector for the Random Forest:
*   `Boolean`: 0 or 1
*   `Integer/Float`: Normalized or raw numeric values (Random Forest handles raw scales well).
