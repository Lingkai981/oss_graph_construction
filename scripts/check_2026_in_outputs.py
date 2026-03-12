#!/usr/bin/env python3
"""检查四维分析输出中是否含有 2026 数据。"""
import json

files = {
    "burnout": "output/burnout-analysis/full_analysis.json",
    "newcomer": "output/newcomer-analysis/full_analysis.json",
    "atmosphere": "output/community-atmosphere-analysis/full_analysis.json",
}

for name, path in files.items():
    with open(path) as f:
        d = json.load(f)
    count_2026 = 0
    repos_2026 = set()
    if isinstance(d, dict):
        for repo, data in d.items():
            metrics = data.get("metrics", data.get("monthly_metrics", []))
            if isinstance(metrics, list):
                for m in metrics:
                    month = m.get("month", "")
                    if month >= "2026-01":
                        count_2026 += 1
                        repos_2026.add(repo)
            elif isinstance(metrics, dict):
                for month_key in metrics:
                    if month_key >= "2026-01":
                        count_2026 += 1
                        repos_2026.add(repo)
    print(f"{name}: {count_2026} entries with 2026 in {len(repos_2026)} repos: {sorted(repos_2026)}")

# personnel flow
with open("output/personnel-flow-all/repo_yearly_status.txt") as f:
    lines_2026 = [l.strip() for l in f if "2026" in l]
print(f"personnel_flow: {len(lines_2026)} lines with 2026")
