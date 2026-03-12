#!/usr/bin/env python3
"""高效版全链路数据完整性审计：预构建小写映射、避免逐行 73 次比较。"""
import json, glob, os
from collections import defaultdict
from pathlib import Path

ROOT = "/Users/milk/Documents/ali2025/oss_graph_construction"
os.chdir(ROOT)

# 加载 index.json 获取 73 个 repo
with open("output/monthly-graphs/index.json") as f:
    index = json.load(f)
repo_names = sorted(index.keys())
# 建小写映射
repo_lower_map = {rn.lower(): rn for rn in repo_names}

print(f"index.json 中共 {len(repo_names)} 个 repo\n")

# 收集所有 JSONL 文件
data_dirs = sorted(glob.glob("data/filtered*/"))
all_files = []
for d in data_dirs:
    for f in glob.glob(os.path.join(d, "*-filtered.json")):
        all_files.append(f)
all_files.sort()
print(f"总共 {len(all_files)} 个 JSONL 文件\n")

# 逐文件扫描，统计 repo -> {month -> count} 和 repo -> {month -> {data_dir}}
repo_month_events = defaultdict(lambda: defaultdict(int))
repo_month_source = defaultdict(lambda: defaultdict(set))

for fi, f in enumerate(all_files):
    base = os.path.basename(f)
    parts = base.split("-")
    if len(parts) >= 3:
        month = f"{parts[0]}-{parts[1]}"
    else:
        continue
    dir_name = f.split("/data/")[1].split("/")[0] if "/data/" in f else "unknown"
    
    with open(f) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            # 快速提取 repo name 用字符串搜索，避免 json.loads 每行
            # "name": "owner/repo"
            idx = line.find('"name"', line.find('"repo"'))
            if idx == -1:
                continue
            colon = line.find(':', idx)
            if colon == -1:
                continue
            q1 = line.find('"', colon + 1)
            if q1 == -1:
                continue
            q2 = line.find('"', q1 + 1)
            if q2 == -1:
                continue
            repo_raw = line[q1+1:q2].lower()
            
            rn = repo_lower_map.get(repo_raw)
            if rn:
                repo_month_events[rn][month] += 1
                repo_month_source[rn][month].add(dir_name)
    
    if (fi + 1) % 2000 == 0:
        print(f"  已扫描 {fi+1}/{len(all_files)} 个文件...", flush=True)

print(f"  扫描完成！\n")

# 加载 actor-actor 图月份
repo_graph_months = {}
for rn in repo_names:
    aa = index.get(rn, {}).get("actor-actor", {})
    repo_graph_months[rn] = set(aa.keys())

# 各 repo 月份对比
print("=" * 70)
print("  逐 repo 数据完整性：原始事件 vs actor-actor 图")
print("=" * 70)

all_problem_repos = []
for rn in sorted(repo_names):
    events = repo_month_events.get(rn, {})
    event_months = sorted(events.keys())
    graph_months = repo_graph_months.get(rn, set())
    
    if not event_months:
        print(f"\n  ⚠️ {rn}: 所有数据目录中找不到任何事件!")
        all_problem_repos.append((rn, 0, len(graph_months), [], "NO_DATA"))
        continue
    
    # 有事件但无图的月份
    gaps = [(m, events[m]) for m in event_months if m not in graph_months]
    # 有图但无事件的月份（不应该）
    orphan = [m for m in sorted(graph_months) if m not in events]
    
    total_event_months = len(event_months)
    total_graph_months = len(graph_months)
    
    # 数据来源
    sources = set()
    for m in event_months:
        sources.update(repo_month_source[rn].get(m, set()))
    
    has_problem = len(gaps) >= 2 or (gaps and len(gaps) / total_event_months > 0.1)
    
    if has_problem:
        gap_pct = len(gaps) / total_event_months * 100
        all_problem_repos.append((rn, total_event_months, total_graph_months, gaps, "GAPS"))
        print(f"\n  ⚠️ {rn}")
        print(f"    数据来源: {', '.join(sorted(sources))}")
        print(f"    有事件月份: {total_event_months}, 有图月份: {total_graph_months}")
        print(f"    缺图月份: {len(gaps)} ({gap_pct:.0f}%)")
        # 显示前5个缺失月份
        for m, cnt in gaps[:8]:
            print(f"      {m}: {cnt} events")
        if len(gaps) > 8:
            print(f"      ... 共 {len(gaps)} 个月缺图")
    
    if orphan:
        print(f"\n  🔍 {rn}: 有图但数据目录中无事件的月份: {orphan}")

# 无事件的 repo (图数据可能来自旧管道)
no_data_repos = [rn for rn in repo_names if rn not in repo_month_events]
if no_data_repos:
    print(f"\n\n{'='*70}")
    print(f"  ⚠️ 以下 {len(no_data_repos)} 个 repo 在所有 data/ 目录中找不到事件：")
    print(f"{'='*70}")
    for rn in no_data_repos:
        gm = repo_graph_months.get(rn, set())
        print(f"  {rn}: actor-actor 图 {len(gm)} 月")

# 月份连续性检查
print(f"\n\n{'='*70}")
print(f"  各数据目录月份连续性")
print(f"{'='*70}")
for d in data_dirs:
    dir_name = os.path.basename(d.rstrip("/"))
    files = glob.glob(os.path.join(d, "*-filtered.json"))
    if not files:
        continue
    months = set()
    for f in files:
        base = os.path.basename(f)
        parts = base.split("-")
        if len(parts) >= 3:
            months.add(f"{parts[0]}-{parts[1]}")
    months = sorted(months)
    if len(months) < 2:
        print(f"\n  {dir_name}: 只有 {len(months)} 个月")
        continue
    
    gaps = []
    for i in range(len(months) - 1):
        y1, m1 = map(int, months[i].split("-"))
        y2, m2 = map(int, months[i+1].split("-"))
        expected = y1 * 12 + m1 + 1
        actual = y2 * 12 + m2
        if actual != expected:
            gaps.append(f"{months[i]} -> {months[i+1]} (跳 {actual-expected-1} 月)")
    
    if gaps:
        print(f"\n  {dir_name}: ⚠️ {len(gaps)} 个月份缺口 ({months[0]}~{months[-1]})")
        for g in gaps:
            print(f"    {g}")
    else:
        print(f"\n  {dir_name}: ✅ 连续 ({months[0]}~{months[-1]}, {len(months)} 月)")

# 数据源 vs 图数据对比统计
print(f"\n\n{'='*70}")
print(f"  总结")
print(f"{'='*70}")
total_repos_with_data = len(repo_month_events)
total_repos_with_gaps = len([x for x in all_problem_repos if x[4] == "GAPS"])
total_repos_no_data = len(no_data_repos)
print(f"  73 个 repo 中:")
print(f"    有原始事件数据: {total_repos_with_data}")
print(f"    无原始事件数据: {total_repos_no_data} (图数据可能来自旧管道)")
print(f"    有显著缺图: {total_repos_with_gaps}")
print(f"    数据完整: {total_repos_with_data - total_repos_with_gaps}")

print("\n✅ 审计完毕")
