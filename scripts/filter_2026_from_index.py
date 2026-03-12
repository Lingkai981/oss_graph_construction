#!/usr/bin/env python3
"""
从 index.json 中，仅对跨度 >= 3 年的 repo 过滤 2026 及以后的月份数据。
跨度 < 3 年的 repo 保留 2026 数据。
"""
import json
import shutil
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / "output" / "monthly-graphs" / "index.json"
BACKUP = INDEX.with_name("index.json.bak-with-2026")

# 从备份恢复（确保从完整数据开始）
if BACKUP.exists():
    shutil.copy2(BACKUP, INDEX)
    print(f"已从备份恢复: {BACKUP}")
else:
    shutil.copy2(INDEX, BACKUP)
    print(f"已创建备份: {BACKUP}")

with open(INDEX) as f:
    idx = json.load(f)

MIN_SPAN_YEARS = 3
total_removed = 0
affected_repos = []
skipped_repos = []

for repo, graph_types in idx.items():
    # 收集所有月份
    all_months = set()
    for months in graph_types.values():
        all_months.update(months.keys())
    if not all_months:
        continue

    min_m = min(all_months)
    max_m = max(all_months)
    span = int(max_m[:4]) - int(min_m[:4])

    if span < MIN_SPAN_YEARS:
        has_2026 = any(m >= "2026-01" for m in all_months)
        if has_2026:
            skipped_repos.append((repo, len(all_months), min_m, max_m, span))
        continue

    # 跨度 >= 3 年: 过滤 2026
    repo_removed = 0
    for gtype, months in graph_types.items():
        to_remove = [m for m in months if m >= "2026-01"]
        for m in to_remove:
            del months[m]
            repo_removed += 1
    if repo_removed > 0:
        affected_repos.append((repo, repo_removed))
        total_removed += repo_removed

with open(INDEX, "w") as f:
    json.dump(idx, f, indent=2, ensure_ascii=False)

print(f"\n已过滤 {total_removed} 个 2026 月份条目，涉及 {len(affected_repos)} 个 repo（跨度 >= {MIN_SPAN_YEARS} 年）:")
for r, cnt in sorted(affected_repos):
    print(f"  {r}: 移除 {cnt} 条")

if skipped_repos:
    print(f"\n保留 2026 数据（跨度 < {MIN_SPAN_YEARS} 年）: {len(skipped_repos)} 个 repo:")
    for r, n, mn, mx, sp in sorted(skipped_repos):
        print(f"  {r}: {n} months ({mn}~{mx}), span={sp}y")

# 验证
with open(INDEX) as f:
    idx2 = json.load(f)
total_repos = len(idx2)
repos_with_data = sum(1 for r in idx2.values() if any(gt for gt in r.values()))
has_2026 = sum(1 for r in idx2.values() for gt in r.values() for m in gt if m >= "2026-01")
print(f"\n验证: {total_repos} 个 repo, 有效 repo: {repos_with_data}, 剩余 2026 条目: {has_2026}")
