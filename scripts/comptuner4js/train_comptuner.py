import sys
import os
import numpy as np
import argparse

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from scripts.comptuner4js.v8_tuner import V8CompTuner
from scripts.utils.parameters import ParameterSpace, Parameter
from scripts.utils.benchmark_runner import OctaneRunner
from scripts.utils.config_generator import ConfigGenerator

parameters = [
    Parameter("turbo-inlining", "boolean", True),
    Parameter("use-osr", "boolean", True),
    Parameter("compact-on-every-full-gc", "boolean", False),
    Parameter("inline-new", "boolean", True),
    Parameter("max-optimized-bytecode-size", "integer", 61440, 30000, 120000),
    Parameter("max-inlined-bytecode-size", "integer", 460, 230, 920),
    Parameter("invocation-count-for-maglev", "integer", 400, 200, 800),
    Parameter("invocation-count-for-turbofan", "integer", 3000, 1500, 6000),
    Parameter("min-semi-space-size", "integer", 0, 0, 8),
    Parameter("stack-size", "integer", 984, 492, 1968),
    Parameter("baseline-batch-compilation-threshold", "integer", 4096, 2048, 8192),
]
parameter_space = ParameterSpace(parameters)

def build_model():
    parser = argparse.ArgumentParser(description="Generate dataset for V8 tuning")
    parser.add_argument("--d8-path", required=True, help="Path to d8 executable")
    parser.add_argument("--octane-path", required=True, help="Path to octane directory")

    args = parser.parse_args()
    octane_dir = os.path.join(args.octane_path)
    if not os.path.isdir(octane_dir):
        print(f"Error: Octane directory not found at {octane_dir}")
        return
    
    runner = OctaneRunner(args.d8_path, octane_dir)
    tuner = V8CompTuner(parameter_space, runner, "test_log.txt")
    model, _, _ = tuner.build_RF_model()
    
    import joblib
    model_path = "rf_model.pkl"
    joblib.dump(model, model_path)
    print(f"Model saved to {model_path}")

    test_samples = []
    cg = ConfigGenerator(parameter_space)
    all_loss = []
    while len(test_samples) < 30:
        config, vector = cg.generate_random_config()
        # Check for duplicates (simple list check)
        if not any(np.array_equal(vector, x) for x in test_samples):
            test_samples.append(vector)
        
        loss, true_score = tuner.getPrecision(model, vector)
        print(f'config: {config}, loss: {loss}, true_score: {true_score}')
        all_loss.append(loss)
    
    print(f"Average loss: {np.mean(all_loss)}")

if __name__ == "__main__":
    build_model()
