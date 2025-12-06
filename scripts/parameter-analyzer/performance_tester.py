#!/usr/bin/env python3
import json
import subprocess
import re
import os
import numpy as np
from typing import List, Tuple, Dict, Any

# 定义 runner.js 和相关配置文件的路径
# 我们假设此脚本从 ccfhw2025 根目录执行
RUNNER_SCRIPT_PATH = 'scripts/page-executor/runner.js'
PARAM_GROUP_PATH = 'scripts/page-executor/param_groups.json'
BASE_CONFIG_PATH = 'scripts/page-executor/config.json'

def _filter_outliers_and_average(data: List[float], threshold: float = 1.5) -> float:
    """
    使用IQR方法过滤异常值并计算平均值。
    """
    if not data:
        return 0.0
    if len(data) < 3:
        return np.mean(data)

    q1, q3 = np.percentile(data, [25, 75])
    iqr = q3 - q1
    lower_bound = q1 - (iqr * threshold)
    upper_bound = q3 + (iqr * threshold)
    
    clean_data = [x for x in data if lower_bound <= x <= upper_bound]
    
    if not clean_data:
        return np.mean(data) # 如果所有数据都被过滤，则返回原始平均值
        
    return np.mean(clean_data)

def _generate_param_group(param_config: Dict[str, Any]) -> None:
    """
    根据给定的参数配置生成 param_groups.json 文件。
    param_config 示例: {'name': 'test_config', 'args': ['--no-turbo-inlining']}
    """
    # runner.js 需要一个包含一个或多个组的列表
    param_groups = [param_config]
    try:
        with open(PARAM_GROUP_PATH, 'w', encoding='utf-8') as f:
            json.dump(param_groups, f, indent=2)
    except IOError as e:
        print(f"Error writing to {PARAM_GROUP_PATH}: {e}")
        raise

def _execute_runner(target_url: str) -> float:
    """
    执行 runner.js 脚本并从其输出中解析性能数据。
    """
    cmd = ['node', RUNNER_SCRIPT_PATH]
    
    # 确保 runner.js 知道要测试哪个 URL
    # 我们通过修改其依赖的 dataset.json 来实现
    try:
        dataset_path = 'scripts/page-executor/dataset.json'
        with open(dataset_path, 'w', encoding='utf-8') as f:
            json.dump([target_url], f)
    except IOError as e:
        print(f"Error writing to dataset.json: {e}")
        return -1.0

    time_ms = -1.0
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', cwd='.')
        
        for line in process.stdout:
            print(line, end='') # 实时打印输出，方便调试
            match = re.search(r'✔ 加载时间: ([\d.]+) ms', line)
            if match:
                time_ms = float(match.group(1))
        
        process.wait()
        if process.returncode != 0:
            print(f"Runner script exited with error code {process.returncode}")
            return -1.0

    except FileNotFoundError:
        print(f"Error: 'node' command not found. Please ensure Node.js is installed and in your PATH.")
        return -1.0
    except Exception as e:
        print(f"An error occurred while executing the runner script: {e}")
        return -1.0
        
    return time_ms

def run_test(param_config: Dict[str, Any], scene_url: str, num_runs: int) -> float:
    """
    针对单个参数配置和场景，执行指定次数的性能测试，并返回清洗后的平均性能值。

    Args:
        param_config: 描述V8参数的字典，如 {'name': 'p1', 'args': ['--flag1=val1']}
        scene_url: 待测试的目标页面URL。
        num_runs: 重复测试的次数。

    Returns:
        清洗后的平均加载时间（毫秒），如果测试失败则返回-1.0。
    """
    print(f"\n----- Running test for param config: {param_config['name']} on scene: {scene_url} -----")
    
    try:
        _generate_param_group(param_config)
    except IOError:
        return -1.0

    results = []
    for i in range(num_runs):
        print(f"--- Run {i+1}/{num_runs} ---")
        time_taken = _execute_runner(scene_url)
        if time_taken < 0:
            print(f"Test run {i+1} failed. Aborting for this configuration.")
            return -1.0 # 如果单次运行失败，则整个测试失败
        results.append(time_taken)
        
    if not results:
        return -1.0

    average_time = _filter_outliers_and_average(results)
    print(f"----- Test finished. Raw results: {results} -----")
    print(f"----- Cleaned average time: {average_time:.2f} ms -----")
    
    return average_time

if __name__ == '__main__':
    # 用于测试模块功能的代码
    print("Testing performance_tester module...")
    
    # 示例1: 测试默认配置
    default_config = {
        "name": "default",
        "args": [] 
    }
    
    # 示例2: 测试一个具体参数
    inlining_off_config = {
        "name": "no-turbo-inlining",
        "args": ["--no-turbo-inlining"]
    }
    
    # 假设的测试场景
    test_scene = "https://www.google.com"
    
    # 执行测试
    print("\n--- Testing with default config ---")
    avg_time_default = run_test(default_config, test_scene, num_runs=3)
    if avg_time_default >= 0:
        print(f"\nAverage time for default config: {avg_time_default:.2f} ms")

    print("\n--- Testing with inlining off ---")
    avg_time_no_inline = run_test(inlining_off_config, test_scene, num_runs=3)
    if avg_time_no_inline >= 0:
        print(f"\nAverage time with inlining off: {avg_time_no_inline:.2f} ms")