"""
将 filtered_union_2021_2025_fulldaily/ 按 repo 拆分到 per_repo 目录。

源: /Users/milk/test_data/ali2025/filtered_union_2021_2025_fulldaily/
     每个文件是 JSONL，每行含 repo.name 字段

目标: /Users/milk/test_data/ali2025/filtered_union_2021_2025_fulldaily_per_repo/
     <org>/<repo>/<date>-filtered.json  (保持 JSONL 格式)
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

SRC_DIR = Path("/Users/milk/test_data/ali2025/filtered_union_2021_2025_fulldaily")
DST_DIR = Path("/Users/milk/test_data/ali2025/filtered_union_2021_2025_fulldaily_per_repo")


def main():
    src_files = sorted(SRC_DIR.glob("*-filtered.json"))
    total = len(src_files)
    print(f"源文件数: {total}")
    print(f"输出目录: {DST_DIR}")

    DST_DIR.mkdir(parents=True, exist_ok=True)

    for idx, src_file in enumerate(src_files, 1):
        filename = src_file.name  # e.g. 2021-01-01-filtered.json

        # repo_name -> list of lines
        repo_lines: dict[str, list[str]] = defaultdict(list)

        with open(src_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    repo_name = obj["repo"]["name"]  # e.g. "huggingface/transformers"
                    repo_lines[repo_name].append(line)
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"  跳过无效行: {e}", file=sys.stderr)
                    continue

        # 写入各 repo 子目录
        for repo_name, lines in repo_lines.items():
            repo_dir = DST_DIR / repo_name  # org/repo 自然形成两级目录
            repo_dir.mkdir(parents=True, exist_ok=True)
            dst_file = repo_dir / filename
            with open(dst_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
                f.write("\n")

        if idx % 50 == 0 or idx == total:
            print(f"  [{idx}/{total}] {filename} - {len(repo_lines)} repos")

    print("完成!")


if __name__ == "__main__":
    main()
