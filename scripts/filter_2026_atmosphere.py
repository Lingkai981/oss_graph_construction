#!/usr/bin/env python3
"""
从 atmosphere full_analysis.json 中过滤掉 >=3 年跨度 repo 的 2026 月份数据。
同时重新计算 summary。
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ATMO_FULL = BASE / "output" / "community-atmosphere-analysis" / "full_analysis.json"
ATMO_SUMMARY = BASE / "output" / "community-atmosphere-analysis" / "summary.json"

MIN_SPAN_YEARS = 3

with open(ATMO_FULL) as f:
    data = json.load(f)

total_removed = 0
affected = []

for repo, repo_data in data.items():
    metrics = repo_data.get("metrics", [])
    if not metrics:
        continue

    # Get all months
    all_months = [m.get("month", "") for m in metrics if m.get("month")]
    if not all_months:
        continue

    min_m = min(all_months)
    max_m = max(all_months)
    span = int(max_m[:4]) - int(min_m[:4])

    if span < MIN_SPAN_YEARS:
        continue

    # Filter out 2026
    before = len(metrics)
    metrics_filtered = [m for m in metrics if m.get("month", "") < "2026-01"]
    after = len(metrics_filtered)
    removed = before - after

    if removed > 0:
        repo_data["metrics"] = metrics_filtered
        total_removed += removed
        affected.append((repo, removed))

with open(ATMO_FULL, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"Atmosphere: 过滤 {total_removed} 条 2026 数据，涉及 {len(affected)} 个 repo")
for r, cnt in sorted(affected):
    print(f"  {r}: -{cnt}")

# Regenerate summary from full_analysis
summary = {}
for repo, repo_data in data.items():
    metrics = repo_data.get("metrics", [])
    if metrics:
        scores = [m.get("composite_score", 0) for m in metrics if m.get("composite_score") is not None]
        avg_score = sum(scores) / len(scores) if scores else 0
        summary[repo] = {
            "repo": repo,
            "months_analyzed": len(metrics),
            "average_composite_score": round(avg_score, 2),
            "latest_month": metrics[-1].get("month", "") if metrics else "",
        }

with open(ATMO_SUMMARY, "w") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print(f"Summary 已更新: {len(summary)} 个 repo")
