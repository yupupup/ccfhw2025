import os
import random
import subprocess
import argparse
import re
import csv
import json
import time
import multiprocessing
import sys
import math

try:
    import opentuner
    from opentuner import ConfigurationManipulator
    from opentuner.search.manipulator import IntegerParameter, BooleanParameter
    from opentuner import MeasurementInterface
    from opentuner import Result
except ImportError as e:
    print(f"Warning: Failed to import opentuner: {e}")
    opentuner = None

# Define parameter space
PARAMETERS = [
    {"name": "turbo-inlining", "type": "bool", "default": True},
    {"name": "use-osr", "type": "bool", "default": True},
    {"name": "compact-on-every-full-gc", "type": "bool", "default": False},
    {"name": "inline-new", "type": "bool", "default": True},
    {"name": "max-optimized-bytecode-size", "type": "int", "default": 61440, "min": 30000, "max": 120000},
    {"name": "max-inlined-bytecode-size", "type": "int", "default": 460, "min": 230, "max": 920},
    {"name": "invocation-count-for-maglev", "type": "int", "default": 400, "min": 200, "max": 800},
    {"name": "invocation-count-for-turbofan", "type": "int", "default": 3000, "min": 1500, "max": 6000},
    {"name": "min-semi-space-size", "type": "int", "default": 0, "min": 0, "max": 8},
    {"name": "stack-size", "type": "int", "default": 984, "min": 492, "max": 1968},
    {"name": "baseline-batch-compilation-threshold", "type": "int", "default": 4096, "min": 2048, "max": 8192},
]

def generate_random_config():
    config = {}
    config_vector = []
    
    for param in PARAMETERS:
        val = None
        if param["type"] == "bool":
            # Random boolean
            val = random.choice([True, False])
        elif param["type"] == "int":
            # Random int in range [min, max]
            val = random.randint(param["min"], param["max"])
        
        config[param["name"]] = val
        
        # Vector representation: True=1, False=0, Int=Int
        if param["type"] == "bool":
            config_vector.append(1 if val else 0)
        else:
            config_vector.append(val)
            
    return config, config_vector

def get_default_config_vector():
    config_vector = []
    for param in PARAMETERS:
        val = param["default"]
        if param["type"] == "bool":
            config_vector.append(1 if val else 0)
        else:
            config_vector.append(val)
    return config_vector

def get_config_vector_from_dict(config):
    config_vector = []
    for param in PARAMETERS:
        val = config.get(param["name"], param["default"])
        if param["type"] == "bool":
            config_vector.append(1 if val else 0)
        else:
            config_vector.append(val)
    return config_vector

def build_cmd(d8_path, octane_dir, config, benchmark=None):
    cmd = [d8_path]
    for key, val in config.items():
        if val is True:
            cmd.append(f"--{key}")
        elif val is False:
            cmd.append(f"--no-{key}")
        else:
            cmd.append(f"--{key}={val}")
    
    if benchmark:
        cmd.append("base.js")
        cmd.append(f"{benchmark}.js")
        cmd.append("-e")
        js_code = (
            "function PrintResult(name, result) { print(name + ': ' + result); }; "
            "function PrintScore(score) { print('Score: ' + score); }; "
            "BenchmarkSuite.RunSuites({NotifyResult: PrintResult, NotifyScore: PrintScore});"
        )
        cmd.append(js_code)
    else:
        cmd.append("run.js") 
        
    return cmd

def run_benchmark_single(d8_path, octane_dir, config, benchmark=None):
    cmd = build_cmd(d8_path, octane_dir, config, benchmark)
    
    try:
        result = subprocess.run(
            cmd, 
            cwd=octane_dir,
            capture_output=True, 
            text=True, 
            timeout=120
        )
        
        if result.returncode != 0:
            return None
        
        match = re.search(r"Score \(version \d+\): (\d+)", result.stdout)
        if not match:
             match = re.search(r"Score: (\d+)", result.stdout)
             
        if match:
            return float(match.group(1))
        else:
            return None

    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f"Exception: {e}")
        return None

def run_benchmark(d8_path, octane_dir, config, benchmark=None, repeats=1):
    scores = []
    for _ in range(repeats):
        score = run_benchmark_single(d8_path, octane_dir, config, benchmark)
        if score is not None:
            scores.append(score)
    
    if not scores:
        return None
        
    return sum(scores) / len(scores)

def worker(args):
    """
    Worker function for parallel execution.
    args: (d8_path, octane_dir, config, config_vector, default_score, benchmark, repeats)
    """
    d8_path, octane_dir, config, config_vector, default_score, benchmark, repeats = args
    
    score = run_benchmark(d8_path, octane_dir, config, benchmark, repeats)
    
    if score is not None:
        ratio = score / default_score
        return (config_vector, ratio, score)
    else:
        return None

# Global helper for OpenTuner to write to CSV
_csv_writer = None
_csv_file = None
_d8_path = None
_octane_dir = None
_default_score = None
_benchmark = None
_repeats = 1

if opentuner:
    class V8TunerGen(MeasurementInterface):
        def manipulator(self):
            manipulator = ConfigurationManipulator()
            for param in PARAMETERS:
                if param["type"] == "bool":
                    manipulator.add_parameter(BooleanParameter(param["name"]))
                elif param["type"] == "int":
                    manipulator.add_parameter(IntegerParameter(param["name"], param["min"], param["max"]))
            return manipulator

        def run(self, desired_result, input, limit):
            cfg = desired_result.configuration.data
            
            # Convert OpenTuner 'True'/'False' string sometimes to bool if needed, but BooleanParameter handles it
            # Just ensure types are correct
            config = {}
            for param in PARAMETERS:
                val = cfg[param["name"]]
                # OpenTuner BooleanParameter uses True/False
                config[param["name"]] = val

            score = run_benchmark(_d8_path, _octane_dir, config, _benchmark, _repeats)
            
            if score is None:
                return Result(time=float('inf')) # Penalize failure

            # Calculate ratio
            ratio = score / _default_score
            config_vector = get_config_vector_from_dict(config)
            
            # Write to CSV
            # Note: This might have concurrency issues if OpenTuner runs in parallel, 
            # but standard opentuner run is sequential in the main loop usually, 
            # unless using parallel technique. For safety, we should lock or open/close.
            # But simple print to file might be atomic enough for lines.
            if _csv_writer:
                _csv_writer.writerow([config_vector, ratio, score])
                if _csv_file:
                    _csv_file.flush()
            
            print(f"OpenTuner Sample: Ratio={ratio:.4f} (Score={score})")

            # OpenTuner minimizes time. We maximize score.
            # So return -score or 1/score. 
            # Let's use -score.
            return Result(time=-score)

        def save_final_config(self, configuration):
            # Optional: save best config
            pass

def main():
    parser = argparse.ArgumentParser(description="Generate dataset for V8 tuning")
    parser.add_argument("--d8-path", required=True, help="Path to d8 executable")
    parser.add_argument("--octane-path", required=True, help="Path to octane directory")
    parser.add_argument("--benchmark", help="Specific benchmark to run (e.g., richards). If not set, runs all.")
    parser.add_argument("--output", default="dataset.csv", help="Output CSV file")
    parser.add_argument("--samples", type=int, default=100, help="Number of samples to generate")
    parser.add_argument("--jobs", "-j", type=int, default=1, help="Number of parallel jobs (default: 1)")
    parser.add_argument("--repeats", type=int, default=3, help="Number of repeats per config (default: 3)")
    parser.add_argument("--mode", choices=["random", "opentuner"], default="random", help="Generation mode")
    
    # Parse known args, leaving others for opentuner if needed
    args, unknown = parser.parse_known_args()
    
    octane_dir = os.path.join(args.octane_path)
    if not os.path.isdir(octane_dir):
        print(f"Error: Octane directory not found at {octane_dir}")
        return

    # Verify d8
    if not os.path.isfile(args.d8_path):
        print(f"Error: d8 not found at {args.d8_path}")
        return

    print("Measuring default performance...")
    default_config = {p["name"]: p["default"] for p in PARAMETERS}
    default_score = run_benchmark(args.d8_path, octane_dir, default_config, args.benchmark, args.repeats)
    
    if default_score is None:
        print("Failed to run default configuration. Aborting.")
        return
        
    print(f"Default Score: {default_score}")
    
    # Globals for OpenTuner
    global _d8_path, _octane_dir, _default_score, _benchmark, _repeats, _csv_writer, _csv_file
    _d8_path = args.d8_path
    _octane_dir = octane_dir
    _default_score = default_score
    _benchmark = args.benchmark
    _repeats = args.repeats

    # Append mode if file exists, else 'w'
    file_mode = 'a' if os.path.exists(args.output) else 'w'
    
    with open(args.output, file_mode, newline='') as f:
        _csv_file = f
        writer = csv.writer(f)
        _csv_writer = writer
        
        # If new file, write header and default
        if file_mode == 'w':
            writer.writerow(["config_sequence", "performance_ratio", "score"])
            writer.writerow([get_default_config_vector(), 1.0, default_score])
        
        if args.mode == "opentuner":
            if not opentuner:
                print("Error: opentuner not installed.")
                return
            
            print(f"Starting OpenTuner for {args.samples} samples (approx)...")
            # OpenTuner arguments
            # We construct a fake argv for OpenTuner
            # We want to run for 'samples' iterations potentially.
            # OpenTuner runs by time or no-improvement. 
            # We can use --test-limit to limit number of evaluations? 
            # measurement_interface.py has --test-limit arg.
            
            ot_args = opentuner.default_argparser().parse_args(unknown)
            ot_args.test_limit = args.samples
            ot_args.no_dups = True 
            
            # Enable parallelism if jobs > 1
            if args.jobs > 1:
                ot_args.parallelism = args.jobs
            
            V8TunerGen.main(ot_args)
            
        else:
            # Random Mode
            valid_samples = 0
            tried = 0
            
            print(f"Generating {args.samples} samples with {args.jobs} jobs (Random Mode)...")
            
            pool = multiprocessing.Pool(processes=args.jobs)
            
            while valid_samples < args.samples:
                remaining = args.samples - valid_samples
                batch_size = min(remaining * 2 + 10, 100) 
                
                tasks = []
                for _ in range(batch_size):
                    config, config_vector = generate_random_config()
                    tasks.append((args.d8_path, octane_dir, config, config_vector, default_score, args.benchmark, args.repeats))
                
                results = pool.map(worker, tasks)
                
                for res in results:
                    tried += 1
                    if res:
                        writer.writerow(res)
                        valid_samples += 1
                        print(f"Sample {valid_samples}/{args.samples}: Ratio={res[1]:.4f} (Score={res[2]})")
                    else:
                         pass
                         
                    if valid_samples >= args.samples:
                        break
                
                f.flush()
                
            pool.close()
            pool.join()
                
    print(f"Done. Dataset saved to {args.output}")

if __name__ == "__main__":
    main()
