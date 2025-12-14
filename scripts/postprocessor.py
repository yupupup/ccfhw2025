#!/usr/bin/env python3
"""
日志特征向量整理脚本
用于处理 JSTuner 特征提取日志，生成网页级特征向量
"""

import json
import re
import os
import sys
from typing import Dict, List, Tuple
from pathlib import Path

class LogFeatureProcessor:
    """特征日志处理器"""
    
    def __init__(self, log_path: str, output_path: str):
        """
        初始化处理器
        
        Args:
            log_path: 日志文件路径
            output_path: 输出JSON文件路径
        """
        self.log_path = Path(log_path)
        self.output_path = Path(output_path)
        
        # 初始化特征变量
        self.features = {
            # 取最大值的特征
            "max_ast_depth": 0,
            "max_iteration_depth": 0,
            "max_cyclomatic_complexity": 0,
            "max_branches": 0,
            
            # 累加的特征
            "total_functions": 0,
            "total_symbols": 0,
            "total_nodes": 0,
            "total_cyclomatic_complexity": 0,
            "total_parameters": 0,
            "total_branches": 0,
            "total_comparations": 0,
            "total_operators": 0,
        }
        
        # 特征映射：日志键 -> 特征键，处理函数
        self.feature_patterns = {
            # 取最大值的特征
            "Max AST Depth:": ("max_ast_depth", self._process_max),
            "Max Iteration Depth:": ("max_iteration_depth", self._process_max),
            "Max Cyclomatic Complexity:": ("max_cyclomatic_complexity", self._process_max),
            "Max Branches:": ("max_branches", self._process_max),
            
            # 累加的特征
            "Number of Functions:": ("total_functions", self._process_sum),
            "Total Symbols:": ("total_symbols", self._process_sum),
            "Total Nodes:": ("total_nodes", self._process_sum),
            "Total Cyclomatic Complexity:": ("total_cyclomatic_complexity", self._process_sum),
            "Total Parameters:": ("total_parameters", self._process_sum),
            "Total Branches:": ("total_branches", self._process_sum),
            "Total Comparations:": ("total_comparations", self._process_sum),
            "Total Operators:": ("total_operators", self._process_sum),
        }
        
        # 编译正则表达式以提高性能
        self.pattern_cache = {}
        for pattern in self.feature_patterns.keys():
            # 创建匹配 "特征名: 数值" 的正则表达式
            self.pattern_cache[pattern] = re.compile(
                rf"^\s*{re.escape(pattern)}\s*(\d+)\s*$"
            )
    
    def _process_max(self, feature_key: str, value: int) -> None:
        """处理取最大值的特征"""
        self.features[feature_key] = max(self.features[feature_key], value)
    
    def _process_sum(self, feature_key: str, value: int) -> None:
        """处理累加的特征"""
        self.features[feature_key] += value
    
    def parse_log_line(self, line: str) -> Tuple[str, int, bool]:
        """
        解析日志行，提取特征名和数值
        
        Args:
            line: 日志行
            
        Returns:
            (特征键, 数值, 是否成功匹配)
        """
        line = line.strip()
        
        for pattern, regex in self.pattern_cache.items():
            match = regex.match(line)
            if match:
                feature_key, processor = self.feature_patterns[pattern]
                value = int(match.group(1))
                return feature_key, value, True
        
        return "", 0, False
    
    def process_log(self) -> bool:
        """
        处理日志文件
        
        Returns:
            是否成功处理
        """
        if not self.log_path.exists():
            print(f"错误: 日志文件不存在 - {self.log_path}")
            return False
        
        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            print(f"正在处理日志文件: {self.log_path}")
            print(f"日志行数: {len(lines)}")
            
            # 统计处理的行数
            processed_count = 0
            
            for i, line in enumerate(lines, 1):
                feature_key, value, matched = self.parse_log_line(line)
                if matched:
                    # 获取对应的处理函数
                    _, processor = self.feature_patterns[self._get_pattern_by_key(feature_key)]
                    # 更新特征值
                    processor(feature_key, value)
                    processed_count += 1
            
            print(f"成功处理 {processed_count} 个特征记录")
            
            # 保存结果
            self.save_features()
            
            # 清空原日志
            # self.clear_log()
            
            return True
            
        except Exception as e:
            print(f"处理日志时发生错误: {e}")
            return False
    
    def _get_pattern_by_key(self, feature_key: str) -> str:
        """根据特征键找到对应的日志模式"""
        for pattern, (key, _) in self.feature_patterns.items():
            if key == feature_key:
                return pattern
        return ""
    
    def save_features(self) -> None:
        """保存特征向量到JSON文件"""
        try:
            # 确保输出目录存在
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 添加元数据
            feature_data = {
                "metadata": {
                    "source_log": str(self.log_path),
                    "processed_at": self._get_current_timestamp(),
                    "feature_count": len(self.features)
                },
                "features": self.features
            }
            
            with open(self.output_path, 'w', encoding='utf-8') as f:
                json.dump(feature_data, f, indent=2, ensure_ascii=False)
            
            print(f"特征向量已保存到: {self.output_path}")
            
            # 打印汇总信息
            print("\n特征向量汇总:")
            print("=" * 40)
            for key, value in self.features.items():
                print(f"{key.replace('_', ' ').title():30} : {value}")
            print("=" * 40)
            
        except Exception as e:
            print(f"保存特征向量时发生错误: {e}")
            raise
    
    def clear_log(self) -> None:
        """清空日志文件"""
        try:
            # 使用写入模式打开文件，这会清空文件内容
            with open(self.log_path, 'w', encoding='utf-8') as f:
                f.write("")
            print(f"日志文件已清空: {self.log_path}")
        except Exception as e:
            print(f"清空日志文件时发生错误: {e}")
    
    def _get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def get_feature_summary(self) -> Dict:
        """获取特征汇总信息"""
        summary = {
            "total_features": len(self.features),
            "max_features": {},
            "sum_features": {}
        }
        
        # 分类统计
        for key, value in self.features.items():
            if key.startswith("max_"):
                summary["max_features"][key] = value
            elif key.startswith("total_"):
                summary["sum_features"][key] = value
        
        return summary

def load_config(config_path="config.json"):
    """读取 JSON 配置文件"""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"配置文件不存在：{config_path}")
        return {}

def main():
    # 从配置文件读默认值
    config = load_config()

    LOG_PATH = config.get(
        "log_path",
        r"D:\v8\v8\out\x64.release\feature-vector.log"
    )
    OUTPUT_PATH = config.get(
        "output_path",
        r"C:\Users\11436\Desktop\webpage-feature-vector.json"
    )
    
    # 支持命令行参数
    if len(sys.argv) >= 2:
        LOG_PATH = sys.argv[1]
    if len(sys.argv) >= 3:
        OUTPUT_PATH = sys.argv[2]
    
    print("=" * 50)
    print("JSTuner 特征日志处理器")
    print("=" * 50)
    print(f"输入日志: {LOG_PATH}")
    print(f"输出JSON: {OUTPUT_PATH}")
    print()
    
    # 创建处理器
    processor = LogFeatureProcessor(LOG_PATH, OUTPUT_PATH)
    
    # 处理日志
    success = processor.process_log()
    
    if success:
        print("\n处理完成!")
        
        # 显示统计信息
        summary = processor.get_feature_summary()
        print(f"\n特征统计:")
        print(f"  特征总数: {summary['total_features']}")
        print(f"  最大值特征: {len(summary['max_features'])} 个")
        print(f"  累加特征: {len(summary['sum_features'])} 个")
    else:
        print("\n处理失败!")
        sys.exit(1)


def batch_process_logs():
    """批量处理多个日志文件"""
    # 示例：批量处理多个日志文件
    log_files = [
        r"path_to_log\feature-vector-1.log",
        r"path_to_log\feature-vector-2.log",
        r"path_to_log\feature-vector-3.log",
    ]
    
    for i, log_file in enumerate(log_files, 1):
        output_file = f"another_path\webpage-feature-vector-{i}.json"
        
        print(f"\n处理日志 {i}/{len(log_files)}: {log_file}")
        
        processor = LogFeatureProcessor(log_file, output_file)
        success = processor.process_log()
        
        if not success:
            print(f"警告: 处理失败 - {log_file}")


if __name__ == "__main__":
    # 运行主函数
    main()
    
    # 如果需要批量处理，取消注释下面这行
    # batch_process_logs()
    
