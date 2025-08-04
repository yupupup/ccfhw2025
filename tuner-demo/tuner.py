import json
import numpy as np
import subprocess
import re
import opentuner
from opentuner import ConfigurationManipulator
from opentuner import IntegerParameter
from opentuner import MeasurementInterface
from opentuner import Result
from typing import List, Tuple

config_file = 'config.json'
N = 5

def update_config(config_path, new_args):
    # 读取现有配置
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 修改 args
    config['args'] = new_args

    # 写回文件
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def run_node_and_parse_time():
    # 执行 node 命令
    cmd = ['node', 'web_page_driver.js']
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')

    time_ms = None
    for line in process.stdout:
        print(line, end='')  # 同时打印node输出，方便调试
        # 解析时间，例如 "time consumed: 292.50 ms"
        m = re.search(r'time consumed:\s*([\d.]+)\s*ms', line)
        if m:
            time_ms = float(m.group(1))

    process.wait()
    return time_ms

def filter_outliers_and_average(
    data: List[float], 
    threshold: float = 1.5
) -> Tuple[List[float], List[float], float]:
    """
    过滤异常值（基于IQR方法），并返回清洗后的数据、异常值及平均值（浮点数）

    参数:
        data: 浮点数列表（例如 [400.5, 389.2, 415.0, 395.8, 285.3]）
        threshold: IQR异常值检测的阈值（默认1.5）

    返回:
        Tuple[List[float], List[float], float]:
            - 清洗后的数据列表
            - 被剔除的异常值列表
            - 清洗后数据的平均值（保证为float）
    """
    if len(data) < 3:
        avg = sum(data) / len(data) if data else 0.0
        return data, [], avg

    # 计算四分位数（显式转换为float，避免整数操作）
    sorted_data = sorted(data)
    q1 = float(np.percentile(sorted_data, 25))
    q3 = float(np.percentile(sorted_data, 75))
    iqr = q3 - q1

    # 计算异常值边界
    lower = q1 - threshold * iqr
    upper = q3 + threshold * iqr

    # 分离正常值与异常值
    clean = [x for x in data if lower <= x <= upper]
    outliers = [x for x in data if x < lower or x > upper]

    # 计算平均值（确保浮点数除法）
    avg = sum(clean) / len(clean) if clean else 0.0

    return clean, outliers, avg

class V8Tuner(MeasurementInterface):

    def manipulator(self):
        manipulator = ConfigurationManipulator()
        manipulator.add_parameter(IntegerParameter('turbo-inlining', 0, 1))
        manipulator.add_parameter(IntegerParameter('use-osr', 0, 1))
        manipulator.add_parameter(IntegerParameter('compact-on-every-full-gc', 0, 1))
        manipulator.add_parameter(IntegerParameter('inline-new', 0, 1))
        manipulator.add_parameter(IntegerParameter('max-optimized-bytecode-size', 30720, 122880))
        manipulator.add_parameter(IntegerParameter('max-inlined-bytecode-size', 230, 920))
        manipulator.add_parameter(IntegerParameter('invocation-count-for-maglev', 100, 800))
        manipulator.add_parameter(IntegerParameter('invocation-count-for-turbofan', 1000, 5000))
        manipulator.add_parameter(IntegerParameter('min-semi-space-size', 0, 16))
        manipulator.add_parameter(IntegerParameter('stack-size', 492, 1968))
        manipulator.add_parameter(IntegerParameter('baseline-batch-compilation-threshold', 2048, 8192))

        return manipulator

    def run(self, desired_result, input, limit):
        cfg = desired_result.configuration.data

        args = "--js-flags=--expose-gc "
        if cfg['turbo-inlining'] == 0:
            args += '--no-turbo-inlining '
        if cfg['use-osr'] == 0:
            args += '--no-use-osr '
        if cfg['compact-on-every-full-gc'] == 1:
            args += '--compact-on-every-full-gc '
        if cfg['inline-new'] == 0:
            args += '--no-inline-new '
        args += '--max-optimized-bytecode-size=' + str(cfg['max-optimized-bytecode-size']) + ' '
        args += '--max-inlined-bytecode-size=' + str(cfg['max-inlined-bytecode-size']) + ' '
        args += '--invocation-count-for-maglev=' + str(cfg['invocation-count-for-maglev']) + ' '
        args += '--invocation-count-for-turbofan=' + str(cfg['invocation-count-for-turbofan']) + ' '
        args += '--min-semi-space-size=' + str(cfg['min-semi-space-size']) + ' '
        args += '--stack-size=' + str(cfg['stack-size']) + ' '
        args += '--baseline-batch-compilation-threshold=' + str(cfg['baseline-batch-compilation-threshold'])

        new_args = [args]
        update_config(config_path=config_file, new_args=new_args)

        data = []
        for i in range(N):
            data.append(run_node_and_parse_time())
        _, _, avg = filter_outliers_and_average(data=data)

        print("args:", args)
        print("time:", avg)
        return Result(time=avg)

    def save_final_config(self, configuration):
        self.manipulator().save_to_file(configuration.data, 'cfg.json')

if __name__ == '__main__':
    argparser = opentuner.default_argparser()
    V8Tuner.main(argparser.parse_args())
