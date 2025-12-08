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


def compare_multiple_csv(files, output_file="merged_comparison.csv"):
    # 读取所有文件
    all_data = {}
    for f in files:
        all_data[f] = load_csv(f)

    # 所有参数的全集
    all_flags = set()
    for d in all_data.values():
        all_flags.update(d.keys())

    # 写合并结果
    # 使用每个 CSV 的文件名作为模型名（保留扩展名），如需不带扩展名可改用 Path(f).stem
    model_names = [os.path.basename(f) for f in files]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # 写表头
        writer.writerow(["flag"] + model_names + ["same?", "final_category"])

        # 每个参数依次对比
        for flag in sorted(all_flags):
            categories = []
            for f in files:
                categories.append(all_data[f].get(flag, ""))

            # 判断是否一致
            non_empty_cats = [c for c in categories if c != ""]
            same = "yes" if len(set(non_empty_cats)) <= 1 else "no"

            # 一致 → 用统一分类
            # 不一致 → 输出每个分类拼接
            if same == "yes":
                final_cat = non_empty_cats[0] if non_empty_cats else ""
            else:
                final_cat = ", ".join(categories)

            writer.writerow([flag] + categories + [same, final_cat])

    print(f"对比完成，已生成文件：{output_file}")


# 使用方式（自动读取当前目录下所有 *.csv 文件）：
if __name__ == "__main__":
    files = glob.glob("*.csv")   # 也可以手动写列表，例如 ["m1.csv", "m2.csv"]
    compare_multiple_csv(files)
