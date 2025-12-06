#!/usr/bin/env python3
import configparser
import json
import random
import sys
from collections import Counter
from datetime import datetime
import numpy as np

# 导入我们创建的模块
import db_manager
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

def get_test_values(param):
    """根据参数类型和默认值生成测试值列表。"""
    param_type = param['type']
    default_val_str = param['default']

    if param_type == 'boolean':
        return ['true', 'false']
    
    if param_type == 'integer':
        try:
            v = int(default_val_str)
            if v == 0:
                return [0, 1, 2, 4]
            else:
                # 确保值不为负，且是整数
                return sorted(list(set([
                    max(0, int(v / 2)), 
                    v, 
                    int(v * 1.5), 
                    v * 2
                ])))
        except (ValueError, TypeError):
            print(f"Warning: Could not parse integer default value '{default_val_str}' for param '{param['name']}'. Skipping.")
            return []
            
    return []

def build_v8_args(config: dict) -> list:
    """将参数名和值的字典转换为v8启动参数列表。"""
    args = []
    for name, value in config.items():
        if isinstance(value, bool):
            # 处理布尔标志
            prefix = '' if value else '--no-'
            args.append(f"{prefix}{name}")
        else:
            # 处理键值对标志
            args.append(f"--{name}={value}")
    return args

def generate_random_background_configs(all_params, current_param, num_configs):
    """为当前参数生成指定数量的随机背景配置。"""
    other_params = [p for p in all_params if p['id'] != current_param['id']]
    background_configs = []

    for _ in range(num_configs):
        config = {}
        # 从其他参数中随机选择一部分（例如50%）来构建背景
        sample_size = min(len(other_params), max(1, int(len(other_params) * 0.5)))
        params_to_use = random.sample(other_params, sample_size)
        
        for p in params_to_use:
            test_values = get_test_values(p)
            if test_values:
                # 从测试值中随机选一个作为背景值
                config[p['name']] = random.choice(test_values)
        background_configs.append(config)
        
    return background_configs

def analyze_parameter(param, all_params, scenes, config):
    """对单个参数进行完整的性能分析。"""
    print(f"\n{'='*20}\nAnalyzing parameter: {param['name']}\n{'='*20}")
    
    test_values = get_test_values(param)
    if not test_values:
        return None

    num_runs = config.getint('analysis', 'test_runs')
    num_backgrounds = config.getint('analysis', 'random_configs_per_param')

    background_configs = generate_random_background_configs(all_params, param, num_backgrounds)
    
    # 用于存储每个场景和背景下的性能数据
    # perf_data[scene][background_idx][value] = time
    perf_data = {s: [{} for _ in range(num_backgrounds)] for s in scenes}
    
    # 1. 数据收集
    for scene in scenes:
        for i, bg_config in enumerate(background_configs):
            for value in test_values:
                # 结合背景参数和当前测试参数
                current_config = bg_config.copy()
                current_config[param['name']] = value
                
                v8_args = build_v8_args(current_config)
                param_config_for_tester = {
                    'name': f"{param['name']}={value}_bg{i}",
                    'args': v8_args
                }
                
                avg_time = performance_tester.run_test(param_config_for_tester, scene, num_runs)
                if avg_time < 0:
                    print(f"Test failed for {param['name']}={value} on {scene} with background {i}. Skipping this background.")
                    # 标记失败，以便后续跳过此背景的计算
                    perf_data[scene][i] = None 
                    break 
                perf_data[scene][i][value] = avg_time
            
            if perf_data[scene][i] is None:
                continue

    # 2. 指标计算
    scene_impacts = []
    scene_best_values = []

    for scene in scenes:
        background_impacts = []
        background_best_values = []

        for i in range(num_backgrounds):
            if perf_data[scene][i] is None: continue

            results = perf_data[scene][i]
            default_value_str = str(param['default'])
            
            # 确保默认值在测试结果中
            if default_value_str not in results:
                print(f"Warning: Default value '{default_value_str}' not in test results for {param['name']}. Using first value as baseline.")
                baseline_perf = next(iter(results.values()))
            else:
                baseline_perf = results[default_value_str]

            if baseline_perf == 0: continue

            max_impact = 0
            for value, perf in results.items():
                impact = abs((perf - baseline_perf) / baseline_perf)
                if impact > max_impact:
                    max_impact = impact
            background_impacts.append(max_impact)

            # 找到当前背景下的最优值
            best_value = min(results, key=results.get)
            background_best_values.append(best_value)

        if background_impacts:
            scene_impacts.append(np.mean(background_impacts))
        if background_best_values:
            # 场景主导最优值
            scene_best_values.append(Counter(background_best_values).most_common(1)[0][0])

    if not scene_impacts:
        return None # 如果所有测试都失败了

    # 综合影响值
    overall_impact = np.mean(scene_impacts)
    
    # 方向稳定性
    if not scene_best_values:
        stability = 0
        dominant_value = None
    else:
        dominant_value, count = Counter(scene_best_values).most_common(1)[0]
        stability = count / len(scenes)

    # 3. 分类
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
        'parameter_id': param['id'],
        'impact_value': overall_impact,
        'stability_value': stability,
        'category': category,
        'dominant_value': dominant_value
    }

def generate_report(results):
    """生成Markdown格式的分析报告。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    report = f"# V8 Parameter Analysis Report\n\n"
    report += f"*Generated on: {timestamp}*\n\n"
    
    # 按分类组织结果
    categorized_results = {'stable': [], 'sensitive': [], 'none': []}
    for r in results:
        categorized_results[r['category']].append(r)
        
    for category, items in categorized_results.items():
        report += f"## {category.title()} Impact Parameters ({len(items)})\n\n"
        if not items:
            report += "None\n\n"
            continue
            
        report += "| Parameter ID | Impact Value | Stability | Dominant Value |\n"
        report += "|--------------|--------------|-----------|----------------|\n"
        # 按影响值降序排序
        for item in sorted(items, key=lambda x: x['impact_value'], reverse=True):
            report += f"| {item['parameter_id']} | {item['impact_value']:.4f} | {item['stability_value']:.2%} | {item['dominant_value']} |\n"
        report += "\n"
        
    try:
        with open('scripts/parameter-analyzer/analysis_results.md', 'w', encoding='utf-8') as f:
            f.write(report)
        print("\nAnalysis report generated at 'scripts/parameter-analyzer/analysis_results.md'")
    except IOError as e:
        print(f"Error writing report file: {e}", file=sys.stderr)

def main():
    """主函数，执行完整的分析流程。"""
    print("Starting V8 Parameter Analysis...")
    
    # 1. 加载配置
    config = load_config()
    dataset_path = config.get('files', 'dataset_path')
    
    try:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            scenes = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading scenes from {dataset_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. 数据库连接和设置
    conn = db_manager.get_connection()
    if not conn:
        sys.exit(1)
    db_manager.setup_database(conn)
    
    # 3. 获取待分析参数
    all_params = db_manager.get_parameters_to_analyze(conn)
    if not all_params:
        print("No parameters found in the database to analyze.")
        conn.close()
        sys.exit(0)

    # 4. 执行分析
    analysis_results = []
    for param in all_params:
        result = analyze_parameter(param, all_params, scenes, config)
        if result:
            analysis_results.append(result)
            print(f"Analysis complete for {param['name']}: Impact={result['impact_value']:.4f}, Stability={result['stability_value']:.2%}, Category='{result['category']}'")

    # 5. 保存结果和生成报告
    if analysis_results:
        # 清空旧数据
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE parameter_analysis RESTART IDENTITY;")
        db_manager.save_analysis_results(conn, analysis_results)
        generate_report(analysis_results)
    else:
        print("No analysis was completed.")

    # 6. 关闭连接
    conn.close()
    print("\nAnalysis finished. Database connection closed.")

if __name__ == '__main__':
    main()