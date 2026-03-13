import random
import sys
import os
import numpy as np
import argparse

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from scripts.comptuner4js.v8_tuner import V8CompTuner
from scripts.comptuner4js.js2embedding import JSEmbedding
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
    BENCHMARK_FILES = [
        "richards",
        "deltablue",
        "crypto",
        "raytrace",
        "earley-boyer",
        "regexp",
        "splay",
        "navier-stokes",
        "pdfjs",
        "mandreel",
        "gbemu",
        "code-load",
        "box2d",
        "zlib",
        "typescript",
    ]
    parser = argparse.ArgumentParser(description="Generate dataset for V8 tuning")
    parser.add_argument("--d8-path", required=True, help="Path to d8 executable")
    parser.add_argument("--octane-path", required=True, help="Path to octane directory")
    parser.add_argument("--js-dir", required=True, help="Path to the directory containing JavaScript files.")

    args = parser.parse_args()

    # 1. 读取JS文件并生成代码嵌入
    js_dir = args.js_dir
    if not os.path.isdir(js_dir):
        print(f"Error: JavaScript directory not found at {js_dir}")
        return

    print("正在为JS文件生成代码嵌入...")
    embedder = JSEmbedding()
    code_embeddings = {}
    for benchmark_name in BENCHMARK_FILES:
        js_code = ""
        if benchmark_name == "gbemu":
            part1_path = os.path.join(js_dir, "gbemu-part1.js")
            part2_path = os.path.join(js_dir, "gbemu-part2.js")
            if os.path.exists(part1_path) and os.path.exists(part2_path):
                with open(part1_path, 'r') as f:
                    js_code += f.read() + "\n"
                with open(part2_path, 'r') as f:
                    js_code += f.read()
            else:
                print(f"Warning: gbemu parts not found, skipping.")
                continue
        else:
            file_path = os.path.join(js_dir, f"{benchmark_name}.js")
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    js_code = f.read()
            else:
                print(f"Warning: Benchmark file not found, skipping: {file_path}")
                continue
        
        try:
            embedding = embedder.get_embedding(js_code)
            code_embeddings[benchmark_name] = embedding.cpu().numpy()
        except Exception as e:
            print(f"Could not process benchmark {benchmark_name}: {e}")

    if not code_embeddings:
        print("No JavaScript files found or processed in the directory.")
        return

    # 2. 初始化 Runner 和 Tuner，并传入代码嵌入
    octane_dir = os.path.join(args.octane_path)
    if not os.path.isdir(octane_dir):
        print(f"Error: Octane directory not found at {octane_dir}")
        return
    
    runner = OctaneRunner(args.d8_path, octane_dir)
    tuner = V8CompTuner(parameter_space, runner, "test_log.txt", code_embeddings=code_embeddings)
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
        
        benchmark_name, embedding = random.choice(list(code_embeddings.items()))
        loss, true_score = tuner.getPrecision(model, vector, embedding, benchmark_name)
        print(f'embedding:{embedding},\nconfig: {config}, \nloss: {loss}, true_score: {true_score},benchmark_name:{benchmark_name}')
        all_loss.append(loss)
    
    print(f"Average loss: {np.mean(all_loss)}")

if __name__ == "__main__":
    build_model()
