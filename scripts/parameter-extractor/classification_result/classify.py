import csv
import glob
import os
from collections import defaultdict

def load_csv(filename):
    mapping = {}
    with open(filename, encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)  # 跳过第1行表头（中英文都可以）
        for row in reader:
            if len(row) < 2:
                continue
            flag = row[0].strip()
            category = row[1].strip()
            mapping[flag] = category
    return mapping


def compare_multiple_csv(files, output_file="MERGE_RESULT.csv"):
    # 读取所有文件
    all_data = {}
    for f in files:
        all_data[f] = load_csv(f)

    # 所有参数的全集
    all_flags = set()
    for d in all_data.values():
        all_flags.update(d.keys())

    # 写合并结果
    # 使用每个 CSV 的文件名作为模型名
    model_names = [os.path.basename(f) for f in files]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # 写表头
        writer.writerow(["flag"] + model_names + ["voted_category", "confidence"])

        # 每个参数依次对比
        for flag in sorted(all_flags):
            categories = [all_data[f].get(flag, "") for f in files]
            
            # 过滤掉空分类
            non_empty_cats = [c for c in categories if c]

            if not non_empty_cats:
                voted_category = ""
                confidence = 0.0
            else:
                # 投票
                counts = defaultdict(int)
                for cat in non_empty_cats:
                    counts[cat] += 1

                # 找出票数最多和第二多的
                sorted_counts = sorted(counts.items(), key=lambda item: item[1], reverse=True)

                voted_category = sorted_counts[0][0]
                n_max = sorted_counts[0][1]
                n_second = sorted_counts[1][1] if len(sorted_counts) > 1 else 0
                
                # 总投票数 N
                N = len(non_empty_cats)

                # 计算置信度
                confidence = (n_max - n_second) / N if N > 0 else 0.0

            writer.writerow([flag] + categories + [voted_category, f"{confidence:.2f}"])

    print(f"对比完成，已生成文件：{output_file}")


# 使用方式（自动读取当前目录下所有 *.csv 文件，并排除 MERGE_RESULT.csv）：
if __name__ == "__main__":
    output_filename = "MERGE_RESULT.csv"
    # 排除 MERGE_RESULT.csv
    files = [f for f in glob.glob("*.csv") if os.path.basename(f) != output_filename]
    
    if not files:
        print("在当前目录下没有找到需要处理的 .csv 文件。")
    else:
        print(f"找到 {len(files)} 个输入文件: {', '.join(files)}")
        compare_multiple_csv(files, output_file=output_filename)
