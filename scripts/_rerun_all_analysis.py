#!/usr/bin/env python3
"""
替换 repo 后重跑全部 4 维分析 + 报告生成
72 repos: burnout → newcomer → personnel_flow → community_atmosphere → 所有报告
"""
import subprocess, sys, os, time

os.chdir("/Users/milk/Documents/ali2025/oss_graph_construction")

BASE_CMD = [
    sys.executable, "run_analysis.py",
    "--graphs-dir", "output/monthly-graphs",
    "--output-dir", "output/report",
    "--continue-on-error",
    "--verbose",
]

stages = [
    ("1/6 Burnout 分析",         ["--analyzers", "burnout"]),
    ("2/6 Newcomer 分析",        ["--analyzers", "newcomer"]),
    ("3/6 Personnel Flow 分析",  ["--analyzers", "personnel_flow"]),
    ("4/6 Community Atmosphere", ["--analyzers", "community_atmosphere"]),
    ("5/6 Atmosphere Report",    ["--reports", "atmosphere_report"]),
    ("6/6 Comprehensive Report", ["--reports", "comprehensive_report"]),
]

print(f"{'='*60}")
print(f"  开始全量分析 (72 repos)")
print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}", flush=True)

t0 = time.time()
for i, (name, args) in enumerate(stages):
    print(f"\n{'='*60}")
    print(f"  [{name}]")
    print(f"  开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}", flush=True)
    
    ts = time.time()
    cmd = BASE_CMD + args
    print(f"  命令: {' '.join(cmd)}", flush=True)
    
    result = subprocess.run(cmd, capture_output=False)
    
    elapsed = time.time() - ts
    if result.returncode == 0:
        print(f"  ✅ {name} 完成 ({elapsed:.0f}s)", flush=True)
    else:
        print(f"  ❌ {name} 失败 (exit={result.returncode}, {elapsed:.0f}s)", flush=True)
        # continue-on-error: don't stop

total = time.time() - t0
print(f"\n{'='*60}")
print(f"  全部完成! 总耗时: {total/60:.1f} 分钟")
print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}", flush=True)
