import os
import argparse
import csv
import multiprocessing
import sys

# Add scripts directory to path to allow imports from utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from scripts.utils.benchmark_runner import OctaneRunner
from scripts.utils.config_generator import ConfigGenerator
from scripts.utils.tuner_utils import V8TunerGen, opentuner
from scripts.utils.parameters import Parameter, ParameterSpace

# Define parameter space
parameters = [
    Parameter("turbo-inlining", "bool", True),
    Parameter("use-osr", "bool", True),
    Parameter("compact-on-every-full-gc", "bool", False),
    Parameter("inline-new", "bool", True),
    Parameter("max-optimized-bytecode-size", "int", 61440, 30000, 120000),
    Parameter("max-inlined-bytecode-size", "int", 460, 230, 920),
    Parameter("invocation-count-for-maglev", "int", 400, 200, 800),
    Parameter("invocation-count-for-turbofan", "int", 3000, 1500, 6000),
    Parameter("min-semi-space-size", "int", 0, 0, 8),
    Parameter("stack-size", "int", 984, 492, 1968),
    Parameter("baseline-batch-compilation-threshold", "int", 4096, 2048, 8192),
]
parameter_space = ParameterSpace(parameters)

def worker(args):
    """
    Worker function for parallel execution.
    args: (runner, config_generator, default_score, benchmark, repeats)
    """
    runner, config_generator, default_score, benchmark, repeats = args
    
    # Generate random config
    config, config_vector = config_generator.generate_random_config()
    
    scores = []
    for _ in range(repeats):
        score = runner.run(config, benchmark=benchmark)
        if score is not None:
            scores.append(score)
            
    if not scores:
        return None
        
    avg_score = sum(scores) / len(scores)
    ratio = avg_score / default_score
    
    return (config_vector, ratio, avg_score)

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

    # Initialize utilities
    config_generator = ConfigGenerator(parameter_space)
    runner = OctaneRunner(args.d8_path, octane_dir)

    print("Measuring default performance...")
    default_config = {p.name: p.default for p in parameter_space}
    
    # Run default config
    default_scores = []
    for _ in range(args.repeats):
        s = runner.run(default_config, benchmark=args.benchmark)
        if s is not None:
            default_scores.append(s)
    
    if not default_scores:
        print("Failed to run default configuration. Aborting.")
        return
        
    default_score = sum(default_scores) / len(default_scores)
    print(f"Default Score: {default_score}")
    
    # Append mode if file exists, else 'w'
    file_mode = 'a' if os.path.exists(args.output) else 'w'
    
    with open(args.output, file_mode, newline='') as f:
        writer = csv.writer(f)
        
        # If new file, write header and default
        if file_mode == 'w':
            writer.writerow(["config_sequence", "performance_ratio", "score"])
            writer.writerow([config_generator.get_default_config_vector(), 1.0, default_score])
        
        if args.mode == "opentuner":
            if not opentuner:
                print("Error: opentuner not installed.")
                return
            
            print(f"Starting OpenTuner for {args.samples} samples (approx)...")
            
            ot_args = opentuner.default_argparser().parse_args(unknown)
            ot_args.test_limit = args.samples
            ot_args.no_dups = True 
            
            if args.jobs > 1:
                ot_args.parallelism = args.jobs
            
            # Pass repeats via args to tuner if needed, or handle in tuner
            ot_args.repeats = args.repeats

            def result_callback(config_vector, ratio, score):
                writer.writerow([config_vector, ratio, score])
                f.flush()

            # Instantiate V8TunerGen
            interface = V8TunerGen(
                ot_args, 
                runner=runner, 
                config_generator=config_generator, 
                default_score=default_score,
                result_callback=result_callback
            )
            
            from opentuner.tuning.tuner import TuningRunManager
            TuningRunManager(interface, ot_args).minimize()
            
        else:
            # Random Mode
            valid_samples = 0
            
            print(f"Generating {args.samples} samples with {args.jobs} jobs (Random Mode)...")
            
            pool = multiprocessing.Pool(processes=args.jobs)
            
            while valid_samples < args.samples:
                remaining = args.samples - valid_samples
                batch_size = min(remaining * 2 + 10, 100) 
                
                tasks = []
                for _ in range(batch_size):
                    tasks.append((runner, config_generator, default_score, args.benchmark, args.repeats))
                
                results = pool.map(worker, tasks)
                
                for res in results:
                    if res:
                        writer.writerow(res)
                        valid_samples += 1
                        print(f"Sample {valid_samples}/{args.samples}: Ratio={res[1]:.4f} (Score={res[2]})")
                         
                    if valid_samples >= args.samples:
                        break
                
                f.flush()
                
            pool.close()
            pool.join()
                
    print(f"Done. Dataset saved to {args.output}")

if __name__ == "__main__":
    main()
