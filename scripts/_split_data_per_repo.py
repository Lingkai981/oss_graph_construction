"""
将 data/filtered*/ 下的 JSONL 数据按 repo 拆分，
输出到 filtered_union_2021_2025_fulldaily_per_repo/ (与之前合并)。

处理的目录:
  data/filtered/           (4.5GB, 1116 files)
  data/filtered-fullday/   (1.8GB, 38476 files)
  data/filtered-new11/     (53MB, 1164 files)
  data/filtered-cnllm/     (~0, 1224 files)
  data/filtered-llm-intl/  (~0, 1185 files)
  data/filtered-replace/   (~0, 13705 files)
  data/filtered-linux/     (~0, 1 file)
  data/filtered-qwen-code/ (~0, 1 file)
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DATA_DIR = Path("/Users/milk/Documents/ali2025/oss_graph_construction/data")
DST_DIR = Path("/Users/milk/test_data/ali2025/filtered_union_2021_2025_fulldaily_per_repo")

# All filtered-* dirs under data/
SRC_DIRS = sorted(DATA_DIR.glob("filtered*/"))

# 跳过日期后带小时后缀 -12 的文件 (如 2023-01-01-12-filtered.json)
# 也跳过 2026-03 开头的文件
SKIP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-12-filtered\.json$")
SKIP_PREFIX = "2026-03"


def process_dir(src_dir: Path):
    all_files = sorted(src_dir.glob("*-filtered.json"))
    src_files = [
        f for f in all_files
        if not SKIP_PATTERN.match(f.name) and not f.name.startswith(SKIP_PREFIX)
    ]
    skipped = len(all_files) - len(src_files)
    total = len(src_files)
    if total == 0:
        print(f"  跳过 {src_dir.name}: 无有效文件 (跳过 {skipped} 个)")
        return

    print(f"\n处理 {src_dir.name}: {total} 个文件 (跳过 {skipped} 个带-12或2026-03)")

    for idx, src_file in enumerate(src_files, 1):
        filename = src_file.name
        repo_lines: dict[str, list[str]] = defaultdict(list)

        with open(src_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    repo_name = obj["repo"]["name"]
                    repo_lines[repo_name].append(line)
                except (json.JSONDecodeError, KeyError):
                    continue

        for repo_name, lines in repo_lines.items():
            repo_dir = DST_DIR / repo_name
            repo_dir.mkdir(parents=True, exist_ok=True)
            dst_file = repo_dir / filename
            # 如果文件已存在（来自之前的 fulldaily 拆分），追加
            if dst_file.exists():
                with open(dst_file, "a", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                    f.write("\n")
            else:
                with open(dst_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                    f.write("\n")

        if idx % 200 == 0 or idx == total:
            print(f"  [{idx}/{total}] {filename} - {len(repo_lines)} repos")

    print(f"  {src_dir.name} 完成!")


def main():
    DST_DIR.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {DST_DIR}")
    print(f"源目录数: {len(SRC_DIRS)}")
    for d in SRC_DIRS:
        print(f"  {d.name}")

    for src_dir in SRC_DIRS:
        process_dir(src_dir)

    print("\n全部完成!")


if __name__ == "__main__":
    main()
