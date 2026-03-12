#!/usr/bin/env python3
"""全面检查数据源完整性：从原始下载到图构建的全链路审计。"""
import json, glob, os
from collections import defaultdict
from pathlib import Path

ROOT = "/Users/milk/Documents/ali2025/oss_graph_construction"
os.chdir(ROOT)

print("=" * 70)
print("  第一部分：各数据目录概况")
print("=" * 70)

data_dirs = sorted(glob.glob("data/filtered*/"))
for d in data_dirs:
    files = glob.glob(os.path.join(d, "*.json"))
    jsonl_files = [f for f in files if "index" not in f and "progress" not in f and "repos" not in f]
    if not jsonl_files:
        print(f"\n  {d}: 0 个数据文件")
        continue
    # 月份范围
    months = set()
    for f in jsonl_files:
        base = os.path.basename(f)
        parts = base.split("-")
        if len(parts) >= 3:
            months.add(f"{parts[0]}-{parts[1]}")
    months = sorted(months)
    size_mb = sum(os.path.getsize(f) for f in jsonl_files) / 1024 / 1024
    print(f"\n  {d}")
    print(f"    文件数: {len(jsonl_files)}, 总大小: {size_mb:.0f} MB")
    print(f"    月份: {months[0]} ~ {months[-1]} ({len(months)} 个月)")
    # 检查每月文件数（应该是每天一个或每小时一个）
    files_per_month = defaultdict(int)
    for f in jsonl_files:
        base = os.path.basename(f)
        parts = base.split("-")
        if len(parts) >= 3:
            files_per_month[f"{parts[0]}-{parts[1]}"] += 1
    # 文件数分布
    counts = sorted(set(files_per_month.values()))
    print(f"    每月文件数分布: {counts}")

print("\n")
print("=" * 70)
print("  第二部分：73 个 repo 的数据来源追踪")
print("=" * 70)

# 加载 index.json 获取 73 个 repo
with open("output/monthly-graphs/index.json") as f:
    index = json.load(f)
repo_names = sorted(index.keys())
print(f"\n  index.json 中共 {len(repo_names)} 个 repo\n")

# 对每个 repo，检查在哪些数据目录中有数据
# 扫描所有数据目录，建立 repo -> {month: event_count} 的映射
repo_data_source = {}  # repo -> {dir_name: {month: count}}

for d in data_dirs:
    dir_name = os.path.basename(d.rstrip("/"))
    jsonl_files = sorted(glob.glob(os.path.join(d, "*-filtered.json")))
    if not jsonl_files:
        continue
    # 从文件中抽样读取 repo 列表（每个月读第一天）
    # 为效率起见，只读每月的第一个文件
    month_first_file = {}
    for f in jsonl_files:
        base = os.path.basename(f)
        parts = base.split("-")
        if len(parts) >= 3:
            m = f"{parts[0]}-{parts[1]}"
            if m not in month_first_file:
                month_first_file[m] = f
    
    print(f"  扫描 {dir_name} ({len(month_first_file)} 个月)...", flush=True)

# 用更高效的方法：直接扫描每个 repo 在全量数据中的月度事件
# 先收集所有 JSONL 文件按月分组
all_files_by_month = defaultdict(list)  # month -> [filepath, ...]
for d in data_dirs:
    for f in glob.glob(os.path.join(d, "*-filtered.json")):
        base = os.path.basename(f)
        parts = base.split("-")
        if len(parts) >= 3:
            m = f"{parts[0]}-{parts[1]}"
            all_files_by_month[m].append(f)

all_months = sorted(all_files_by_month.keys())
print(f"\n  全量数据月份范围: {all_months[0]} ~ {all_months[-1]} ({len(all_months)} 个月)")

# 对每个月，统计每个 repo 的事件数
print("\n  逐月扫描事件（这会比较慢）...", flush=True)
repo_month_events = defaultdict(lambda: defaultdict(int))  # repo -> {month: count}
repo_month_source = defaultdict(lambda: defaultdict(set))  # repo -> {month: {dir_name}}

for mi, month in enumerate(all_months):
    files = all_files_by_month[month]
    for f in files:
        dir_name = f.split("/data/")[1].split("/")[0] if "/data/" in f else "unknown"
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except:
                    continue
                repo = evt.get("repo", {}).get("name", "")
                if repo:
                    repo_lower = repo.lower()
                    # 匹配 index 中的 repo（大小写不敏感）
                    for rn in repo_names:
                        if rn.lower() == repo_lower:
                            repo_month_events[rn][month] += 1
                            repo_month_source[rn][month].add(dir_name)
                            break
    if (mi + 1) % 5 == 0:
        print(f"    已扫描 {mi+1}/{len(all_months)} 个月...", flush=True)

print(f"    扫描完成！共 {len(all_months)} 个月\n")

print("=" * 70)
print("  第三部分：逐 repo 数据完整性审计")
print("=" * 70)

# 加载 actor-actor 图月份
repo_graph_months = {}
for rn in repo_names:
    aa = index.get(rn, {}).get("actor-actor", {})
    repo_graph_months[rn] = sorted(aa.keys())

# 对比
problem_repos = []
for rn in sorted(repo_names):
    events = repo_month_events.get(rn, {})
    event_months = sorted(events.keys())
    graph_months = set(repo_graph_months.get(rn, []))
    
    if not event_months:
        continue
    
    # 找出有事件但没图的月份
    months_with_events_no_graph = []
    for m in event_months:
        if m not in graph_months and events[m] > 0:
            months_with_events_no_graph.append((m, events[m]))
    
    # 找出连续月份中的空洞（有事件但无图的）
    if months_with_events_no_graph:
        total_event_months = len(event_months)
        total_graph_months = len(graph_months)
        gap_pct = len(months_with_events_no_graph) / total_event_months * 100 if total_event_months else 0
        
        # 只报告有显著缺口的
        if len(months_with_events_no_graph) >= 2 or gap_pct > 10:
            problem_repos.append((rn, total_event_months, total_graph_months, months_with_events_no_graph))

print(f"\n  有显著数据缺口的 repo ({len(problem_repos)} 个):\n")
for rn, n_evt_months, n_graph_months, gaps in sorted(problem_repos, key=lambda x: -len(x[3])):
    gap_pct = len(gaps) / n_evt_months * 100
    sources = set()
    for m, _ in gaps:
        sources.update(repo_month_source[rn].get(m, set()))
    print(f"  {rn}")
    print(f"    有事件月份: {n_evt_months}, 有图月份: {n_graph_months}, 缺图月份: {len(gaps)} ({gap_pct:.0f}%)")
    print(f"    数据来源: {', '.join(sorted(sources))}")
    print(f"    缺图月份详情 (月份: 事件数):")
    for m, cnt in gaps:
        print(f"      {m}: {cnt} events")
    print()

print("=" * 70)
print("  第四部分：下载完整性检查")
print("=" * 70)

# 检查 filtered-fullday 中的 repo 列表与预期是否一致
# 读取下载配置
fullday_repos = set()
for f in glob.glob("data/filtered-fullday/*-filtered.json"):
    with open(f) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
                repo = evt.get("repo", {}).get("name", "")
                if repo:
                    fullday_repos.add(repo)
            except:
                continue
            break  # 只读第一行判断

# 检查每个 data dir 的月份连续性
print("\n  各数据目录的月份连续性检查:\n")
for d in data_dirs:
    dir_name = os.path.basename(d.rstrip("/"))
    jsonl_files = glob.glob(os.path.join(d, "*-filtered.json"))
    if not jsonl_files:
        continue
    months = set()
    for f in jsonl_files:
        base = os.path.basename(f)
        parts = base.split("-")
        if len(parts) >= 3:
            months.add(f"{parts[0]}-{parts[1]}")
    months = sorted(months)
    if len(months) < 2:
        print(f"  {dir_name}: 只有 {len(months)} 个月，跳过连续性检查")
        continue
    
    # 检查月份是否连续
    from datetime import datetime, timedelta
    gaps = []
    for i in range(len(months) - 1):
        y1, m1 = map(int, months[i].split("-"))
        y2, m2 = map(int, months[i+1].split("-"))
        expected_next = (y1 * 12 + m1) + 1
        actual_next = y2 * 12 + m2
        if actual_next != expected_next:
            gap_months = actual_next - expected_next - 1
            gaps.append(f"{months[i]} -> {months[i+1]} (跳过 {gap_months} 个月)")
    
    if gaps:
        print(f"  {dir_name}: ⚠️ 有 {len(gaps)} 个月份缺口")
        for g in gaps:
            print(f"    {g}")
    else:
        print(f"  {dir_name}: ✅ 月份连续 ({months[0]} ~ {months[-1]})")

print("\n\n✅ 全部检查完毕")
