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

# --- Path Setup ---
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)
# --- End Path Setup ---

# 导入我们创建的模块
from utils import db_manager
import performance_tester

def load_config(filename='scripts/parameter-analyzer/config.ini'):
    """加载并返回配置文件解析器对象。"""
    parser = configparser.ConfigParser()
    try:
        if not parser.read(filename):
            raise FileNotFoundError(f"Config file not found at {filename}")
        return parser
    except configparser.Error as e:
        print(f"Error reading config file: {e}", file=sys.stderr)
        sys.exit(1)

def generate_random_background_configs(all_params, current_param, num_configs):
    """为当前参数生成指定数量的随机背景配置。"""
    other_params = [p for p in all_params if p.name != current_param.name]
    background_configs = []

    for _ in range(num_configs):
        config = {}
        # 从其他参数中随机选择一部分（例如50%）来构建背景
        sample_size = min(len(other_params), max(1, int(len(other_params) * 0.5)))
        params_to_use = random.sample(other_params, sample_size)
        
        for p in params_to_use:
            test_values = p.get_test_values()
            if test_values:
                # 从测试值中随机选一个作为背景值
                config[p.name] = random.choice(test_values)
        background_configs.append(config)
        
    return background_configs

def worker_func(args):
    """
    Worker function for parallel execution.
    args: (runner, config, benchmark, repeats)
    """
    runner, config, benchmark, repeats = args
    scores = []
    for _ in range(repeats):
        score = runner.run(config, benchmark=benchmark)
        if score is not None:
            scores.append(score)
    
    if not scores:
        return None
    return sum(scores) / len(scores)

def run_test_parallel(runner, config, benchmark, repeats, pool):
    """
    Executes a test using the process pool.
    For simplicity in this refactoring, we might not parallelize *within* a single test run here,
    but rather parallelize the *set* of tests for a parameter.
    However, since `runner.run` is synchronous, we can just call it directly if we parallelize at the parameter level.
    
    Wait, the user wants parallelization.
    Let's parallelize the execution of different configurations for a parameter.
    """
    # This helper is just a wrapper for now if we use pool.map at a higher level
    pass

def analyze_parameter_deep(runner, param, all_params, scenes, config, pool):
    """
    Deep analysis for a parameter using random backgrounds.
    """
    print(f"Deep analyzing parameter: {param.name}")
    
    test_values = param.get_test_values()
    if not test_values:
        return None

    num_runs = config.getint('analysis', 'test_runs')
    num_backgrounds = config.getint('analysis', 'random_configs_per_param')

    background_configs = generate_random_background_configs(all_params, param, num_backgrounds)
    
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
    # We need a wrapper for pool.map that returns metadata
    def task_wrapper(args):
        runner, cfg, bnch, rpts, scn, bg_idx, val = args
        score = worker_func((runner, cfg, bnch, rpts))
        return (scn, bg_idx, val, score)

    results = pool.map(task_wrapper, tasks)

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
            
            # For simplicity, let's use the first available value as baseline if default not found
            # But ideally we should test default.
            
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
        'parameter_id': param.name, # Using name as ID for now or need to map back
        'impact_value': overall_impact,
        'stability_value': stability,
        'category': category,
        'dominant_value': str(dominant_value)
    }

def screen_parameter(runner, param, scenes, config, pool):
    """
    Screening phase: Test parameter with default background.
    Returns True if impact > threshold, False otherwise.
    """
    print(f"Screening parameter: {param.name}")
    
    test_values = param.get_test_values()
    if not test_values:
        return False

    num_runs = config.getint('analysis', 'test_runs')
    # Default background is empty config (or default values)
    default_config = {} 
    
    tasks = []
    for scene in scenes:
        for value in test_values:
            current_config = default_config.copy()
            current_config[param.name] = value
            tasks.append((runner, current_config, scene, num_runs, scene, value))
            
    def task_wrapper(args):
        runner, cfg, bnch, rpts, scn, val = args
        score = worker_func((runner, cfg, bnch, rpts))
        return (scn, val, score)

    results = pool.map(task_wrapper, tasks)
    
    perf_data = {s: {} for s in scenes}
    for scn, val, score in results:
        if score is not None:
            perf_data[scn][val] = score
            
    scene_impacts = []
    for scene in scenes:
        results = perf_data[scene]
        if not results: continue
        
        # Baseline
        baseline_score = None
        # Try to find default
        # If default is not in test_values (e.g. 0 for int), we might miss it.
        # But get_test_values usually includes default.
        # If not, pick first.
        # Actually, for screening, we compare range.
        
        vals = list(results.values())
        if not vals: continue
        
        min_score = min(vals)
        max_score = max(vals)
        
        if min_score == 0: 
             if max_score > 0: impact = 1.0
             else: impact = 0.0
        else:
            impact = (max_score - min_score) / min_score
            
        scene_impacts.append(impact)
        
    if not scene_impacts:
        return False
        
    avg_impact = np.mean(scene_impacts)
    impact_threshold = config.getfloat('analysis', 'impact_threshold')
    
    return avg_impact >= impact_threshold

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
        WHERE data_type IN %s and category IN %s;
    """
    
    params = []
    # Note: db_manager imports psycopg2, need to handle if not available or mock
    # Assuming db_manager works as before
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
                
                p = Parameter(row[1], row[2], default_val)
                # Store ID separately if needed, or attach to object
                p.id = row[0] 
                params.append(p)
            print(f"Fetched {len(params)} parameters to analyze.")
    except Exception as error:
        print(f"Error fetching parameters: {error}", file=sys.stderr)
    
    return params

def save_analysis_results(conn, results):
    """
    将分析结果更新到 parameter 表中。
    """
    update_query = """
        UPDATE parameter 
        SET impact_value = %s, 
            stability_value = %s, 
            dominant_value = %s
        WHERE parameter_id = %s;
    """
    
    data_to_update = []
    for r in results:
        # Map back parameter name to ID if needed, but we stored ID in p.id
        # Wait, analyze_parameter_deep returns 'parameter_id' as name.
        # We need to pass the ID through.
        # Let's fix analyze_parameter_deep to use p.id
        
        # Assuming r['parameter_id'] is the actual ID now
        data_to_update.append((
            r['impact_value'], 
            r['stability_value'], 
            r['dominant_value'],
            r['parameter_id']
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
    parser.add_argument("--mock", action="store_true", help="Run in mock mode without database")
    args = parser.parse_args()

    print("Starting V8 Parameter Analysis...")
    
    config = load_config()
    
    # Use Octane benchmarks as scenes
    scenes = ['richards'] # Use only one benchmark for quick verification if mocking, or list from config
    
    if args.mock:
        print("Running in MOCK mode.")
        all_params = get_mock_parameters()
        conn = None
    else:
        if db_manager is None:
            print("Error: db_manager module not found (psycopg2 missing?). Cannot run without --mock.", file=sys.stderr)
            sys.exit(1)
            
        conn = db_manager.get_connection()
        if not conn:
            sys.exit(1)
        # db_manager.setup_database(conn)
        
        all_params = get_parameters_to_analyze(conn)
    
    if not all_params:
        print("No parameters found.")
        if conn: conn.close()
        sys.exit(0)

    # Initialize Runner
    d8_path = config.get('v8', 'd8_path', fallback='/home/dby/chromium/v8/v8/out/x64-debug/d8')
    octane_path = config.get('v8', 'octane_path', fallback='/home/dby/chromium/v8/v8/test/benchmarks/data/octane')
    
    runner = OctaneRunner(d8_path, octane_path)
    
    # Parallel Pool
    jobs = config.getint('analysis', 'jobs', fallback=multiprocessing.cpu_count())
    pool = multiprocessing.Pool(processes=jobs)
    
    analysis_results = []
    
    try:
        # 1. Screening
        impactful_params = []
        for param in all_params:
            if screen_parameter(runner, param, scenes, config, pool):
                impactful_params.append(param)
            else:
                analysis_results.append({
                    'parameter_id': getattr(param, 'id', param.name),
                    'impact_value': 0.0,
                    'stability_value': 0.0,
                    'category': 'none',
                    'dominant_value': 'default'
                })
        
        print(f"Screening complete. {len(impactful_params)} parameters passed for deep analysis.")
        
        # 2. Deep Analysis
        for param in impactful_params:
            result = analyze_parameter_deep(runner, param, all_params, scenes, config, pool)
            if result:
                result['parameter_id'] = getattr(param, 'id', param.name)
                analysis_results.append(result)
                print(f"Analysis complete for {param.name}: Impact={result['impact_value']:.4f}, Stability={result['stability_value']:.2%}, Category='{result['category']}'")

        # 3. Save Results
        if args.mock:
            print("Mock mode: Results not saved to DB.")
            print(analysis_results)
        elif analysis_results:
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