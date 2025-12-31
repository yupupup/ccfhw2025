#!/usr/bin/env python3
import configparser
import json
import random
import sys
import multiprocessing
import numpy as np
from collections import Counter
from datetime import datetime
import os
import argparse

# --- Path Setup ---
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)
# --- End Path Setup ---

from utils import benchmark_runner
from utils.parameters import Parameter, ParameterSpace, ParameterRelationship

# 导入我们创建的模块
from utils import db_manager
import performance_tester

def load_config(filename='config.ini'):
    """加载并返回配置文件解析器对象。"""
    parser = configparser.ConfigParser()
    try:
        if not parser.read(filename):
            raise FileNotFoundError(f"Config file not found at {filename}")
        return parser
    except configparser.Error as e:
        print(f"Error reading config file: {e}", file=sys.stderr)
        sys.exit(1)

def generate_random_background_configs(parameter_space : ParameterSpace, current_param, num_configs):
    """
    Generates random background configurations respecting dependencies.
    """
    all_params = parameter_space.get_parameters()
    other_params = [p for p in all_params if p.name != current_param.name]
    background_configs = [{}] # 包含一个默认配置

    for _ in range(num_configs-1):
        config = {}
        # Start with default values for all parameters
        for p in all_params:
            config[p.name] = p.default

        # Randomly select a subset of other parameters to modify
        sample_size = min(len(other_params), max(1, int(len(other_params) * 0.5)))
        params_to_modify = random.sample(other_params, sample_size)
        
        for p in params_to_modify:
            test_values = p.get_test_values()
            if test_values:
                new_val = random.choice(test_values)
                
                if parameter_space.check_src_dependencies(p.name):
                    config[p.name] = new_val
                else:
                    continue

                # Check target dependencies before applying
                if parameter_space.check_target_dependencies(p.name, new_val, config):
                    config[p.name] = new_val
                # Else: keep default (do not modify)
        
        # Remove current_param from config so it doesn't interfere with the test loop
        # (The test loop will set current_param to specific test values)
        if current_param.name in config:
            del config[current_param.name]
            
        background_configs.append(config)
        
    return background_configs

def get_parameters_to_analyze(conn, param_types=['boolean', 'integer']):
    """
    从数据库获取待分析的参数列表。
    返回 Parameter 对象列表。
    """
    classification = [
        "GC/Memory",
        "Optimization",
        "Compiler/Tier Manager",
        "Ignition",
        "Sparkplug",
        "Turboshaft",
        "Turbolev",
        "Turbofan",
        "Maglev"
    ]

    query = """
        SELECT parameter_id, parameter_name, data_type, default_value 
        FROM parameter 
        WHERE data_type IN %s and category IN %s and tuning_target IS NULL and readonly IS NULL;
    """
    
    params = []
    try:
        with conn.cursor() as cur:
            cur.execute(query, (tuple(param_types), tuple(classification)))
            rows = cur.fetchall()
            for row in rows:
                # Create Parameter object
                # Need to parse default value carefully
                default_val = row[3]
                if row[2] == 'boolean':
                    default_val = (str(default_val).lower() == 'true')
                elif row[2] == 'integer':
                    try:
                        default_val = int(default_val)
                    except:
                        default_val = 0
                elif row[2] == 'float':
                    try:
                        default_val = float(default_val)
                    except:
                        default_val = 0.0
                
                p = Parameter(row[1], row[2], default_val, id=row[0])
                params.append(p)
            print(f"Fetched {len(params)} parameters to analyze.")
    except Exception as error:
        print(f"Error fetching parameters: {error}", file=sys.stderr)
    
    return params

def worker_func(runner : benchmark_runner.BenchmarkRunner, config : dict, benchmark : str, repeats : int):
    """
    Worker function for parallel execution.
    args: (runner, config, benchmark, repeats)
    """
    scores = []
    for _ in range(repeats):
        score = runner.run(config, benchmark=benchmark)
        if score is not None:
            scores.append(score)
    
    if not scores:
        return None
    return sum(scores) / len(scores)

def analyze_task_wrapper(args):
    runner, cfg, bnch, rpts, scn, bg_idx, val = args
    score = worker_func(runner, cfg, bnch, rpts)
    return (scn, bg_idx, val, score)

def analyze_parameter_deep(runner: benchmark_runner.BenchmarkRunner, param: Parameter, parameter_space, scenes, config, pool):
    """
    Deep analysis for a parameter using random backgrounds.
    """
    print(f"Deep analyzing parameter: {param.name}")
    
    test_values = param.get_test_values()
    if not test_values:
        return None

    num_runs = config.getint('analysis', 'test_runs')
    num_backgrounds = config.getint('analysis', 'random_configs_per_param')

    background_configs = generate_random_background_configs(parameter_space, param, num_backgrounds)
    
    # perf_data[scene][background_idx][value] = score
    perf_data = {s: [{} for _ in range(num_backgrounds)] for s in scenes}
    
    tasks = []
    # Prepare all tasks
    for scene in scenes:
        for i, bg_config in enumerate(background_configs):
            for value in test_values:
                current_config = bg_config.copy()
                current_config[param.name] = value
                tasks.append((runner, current_config, scene, num_runs, scene, i, value))

    # Execute tasks in parallel
    results = pool.map(analyze_task_wrapper, tasks)

    # Save task inputs and results to a JSON file
    log_entries = [{"config": t[1], "benchmark": t[2], "value": t[6], "score": r[3]} for t, r in zip(tasks, results)]
    os.makedirs("analysis_results", exist_ok=True)
    with open(f"analysis_results/{param.name}_results.json", "w") as f:
        json.dump(log_entries, f, indent=4)

    # Process results
    for scn, bg_idx, val, score in results:
        if score is not None:
            perf_data[scn][bg_idx][val] = score

    # Calculate metrics
    scene_impacts = []
    scene_best_values = []

    for scene in scenes:
        background_impacts = []
        background_best_values = []

        for i in range(num_backgrounds):
            results = perf_data[scene][i]
            if not results: continue

            # Baseline is default value
            # Note: default value might not be in test_values if get_test_values logic changed,
            # but usually it is. If not, we pick one.
            # Actually get_test_values includes default-derived values.
            # Let's assume default is close to one of them or we use the first one.
            
            # Let's check if default is in results
            default_val = param.default
            # Type conversion might be needed for keys
            # keys in results are values from get_test_values
            
            baseline_score = None
            # Try to find default or equivalent
            for k, v in results.items():
                if k == default_val:
                    baseline_score = v
                    break
            
            if baseline_score is None:
                 baseline_score = next(iter(results.values()))

            if baseline_score == 0: continue

            max_impact = 0
            for value, score in results.items():
                impact = abs((score - baseline_score) / baseline_score)
                if impact > max_impact:
                    max_impact = impact
            background_impacts.append(max_impact)

            # Find best value
            # Metric direction: Octane is higher-better
            if runner.metric_direction == 'higher-better':
                best_value = max(results, key=results.get)
            else:
                best_value = min(results, key=results.get)
            background_best_values.append(best_value)

        if background_impacts:
            scene_impacts.append(np.mean(background_impacts))
        if background_best_values:
            # Most common best value
            # Convert to string for Counter if needed (e.g. bools)
            scene_best_values.append(Counter(background_best_values).most_common(1)[0][0])

    if not scene_impacts:
        return None

    overall_impact = np.mean(scene_impacts)
    
    if not scene_best_values:
        stability = 0
        dominant_value = None
    else:
        dominant_value, count = Counter(scene_best_values).most_common(1)[0]
        stability = count / len(scenes)

    # Classification
    impact_threshold = config.getfloat('analysis', 'impact_threshold')
    stability_threshold = config.getfloat('analysis', 'stability_threshold')
    
    category = ''
    if overall_impact < impact_threshold:
        category = 'none'
    elif stability >= stability_threshold:
        category = 'stable'
    else:
        category = 'sensitive'
        
    return {
        'parameter_name': param.name, # Using name as ID for now or need to map back
        'impact_value': overall_impact,
        'stability_value': stability,
        'category': category,
        'dominant_value': str(dominant_value)
    }

def get_parameters_to_analyze(conn, param_types=['boolean', 'integer', 'float']) -> list[Parameter]:
    """
    从数据库获取待分析的参数列表。
    返回 Parameter 对象列表。
    """
    classification = [
        "GC/Memory",
        "Optimization",
        "Compiler/Tier Manager",
        "Ignition",
        "Sparkplug",
        "Turboshaft",
        "Turbolev",
        "Turbofan",
        "Maglev"
    ]

    query = """
        SELECT parameter_name, data_type, default_value 
        FROM parameter 
        WHERE data_type IN %s and category IN %s and tuning_target IS NULL and readonly IS NULL;
    """
    
    params = []
    try:
        with conn.cursor() as cur:
            cur.execute(query, (tuple(param_types), tuple(classification)))
            rows = cur.fetchall()
            for row in rows:
                # Create Parameter object
                # Need to parse default value carefully
                default_val = row[2]
                if row[1] == 'boolean':
                    default_val = (str(default_val).lower() == 'true')
                elif row[1] == 'integer':
                    try:
                        default_val = int(default_val)
                    except:
                        default_val = 0
                elif row[1] == 'float':
                    try:
                        default_val = float(default_val)
                    except:
                        default_val = 0.0
                
                p = Parameter(row[0], row[1], default_val)
                params.append(p)
            print(f"Fetched {len(params)} parameters to analyze.")
    except Exception as error:
        print(f"Error fetching parameters: {error}", file=sys.stderr)
    
    return params

def save_analysis_results(conn, results):
    """
    Update analysis results in the parameter table.
    """
    update_query = """
        UPDATE parameter 
        SET impact_value = %s, 
            stability_value = %s, 
            dominant_value = %s
        WHERE parameter_name = %s;
    """
    
    data_to_update = []
    for r in results:
        # Convert numpy types to standard Python types to avoid database driver errors
        data_to_update.append((
            float(r['impact_value']), 
            float(r['stability_value']), 
            str(r['dominant_value']),
            r['parameter_name']
        ))
    
    if not data_to_update:
        print("No results to save.")
        return

    try:
        with conn.cursor() as cur:
            cur.executemany(update_query, data_to_update)
            conn.commit()
            print(f"Successfully updated {len(data_to_update)} parameters in the database.")
    except Exception as error:
        print(f"Error updating analysis results: {error}", file=sys.stderr)
        conn.rollback()

def main():
    parser = argparse.ArgumentParser(description="V8 Parameter Analyzer")
    args = parser.parse_args()

    print("Starting V8 Parameter Analysis...")
    
    config = load_config()
    
    # Use Octane benchmarks as scenes
    scenes = ['richards', 'box2d', 'deltablue', 'crypto', 'pdfjs', 'typescript', 'zlib']
    # scenes = ['richards']
    
    conn = db_manager.get_connection()
    if not conn:
        sys.exit(1)
    
    all_params = get_parameters_to_analyze(conn)
    
    if not all_params:
        print("No parameters found.")
        if conn: conn.close()
        sys.exit(0)

    # Initialize ParameterSpace
    parameter_space = ParameterSpace(all_params)
    parameter_space.load_relationships_from_db(conn) # Load relationships here

    # Initialize Runner
    d8_path = config.get('v8', 'd8_path', fallback='/home/dby/chromium/v8/v8/out/x64-debug/d8')
    octane_path = config.get('v8', 'octane_path', fallback='/home/dby/chromium/v8/v8/test/benchmarks/data/octane')
    
    runner = benchmark_runner.OctaneRunner(d8_path, octane_path)
    
    # Parallel Pool
    jobs = config.getint('analysis', 'jobs', fallback=multiprocessing.cpu_count())
    pool = multiprocessing.Pool(processes=jobs)
    
    analysis_results = []
    
    try:
        # Deep Analysis (Directly, no screening)
        print(f"Starting deep analysis for {len(all_params)} parameters...")
        
        # We need to pass parameter_space to analyze_parameter_deep instead of all_params list?
        # analyze_parameter_deep currently takes all_params list.
        # But it calls generate_random_background_configs which now expects parameter_space.
        # So we should update analyze_parameter_deep signature or pass parameter_space.
        # Let's check analyze_parameter_deep signature.
        # It is: def analyze_parameter_deep(runner, param, all_params, scenes, config, pool):
        # I should update it to take parameter_space.
        
        for param in all_params:
            # Pass parameter_space instead of all_params
            result = analyze_parameter_deep(runner, param, parameter_space, scenes, config, pool)
            if result:
                result['parameter_name'] = param.name
                analysis_results.append(result)
                print(f"Analysis complete for {param.name}: Impact={result['impact_value']:.4f}, Stability={result['stability_value']:.2%}, dominant_value={result['dominant_value']}, Category='{result['category']}'")

        # Save Results
        if analysis_results:
            save_analysis_results(conn, analysis_results)
        else:
            print("No analysis results to save.")
            
    finally:
        pool.close()
        pool.join()
        if conn: conn.close()
        print("\nAnalysis finished.")

if __name__ == '__main__':
    main()
