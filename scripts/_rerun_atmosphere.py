#!/usr/bin/env python3
"""
仅重跑: community_atmosphere → atmosphere_report → comprehensive_report
清旧氛围数据后重跑
"""
import subprocess, sys, os, time

os.chdir("/Users/milk/Documents/ali2025/oss_graph_construction")

# Step 0: 清旧氛围数据
atmo_dir = "output/report/community-atmosphere-analysis"
if os.path.exists(atmo_dir):
    for f in os.listdir(atmo_dir):
        fp = os.path.join(atmo_dir, f)
        if os.path.isfile(fp):
            os.remove(fp)
            print(f"  删除: {f}")
print("✅ 旧氛围数据已清理\n", flush=True)

BASE_CMD = [
    sys.executable, "run_analysis.py",
    "--graphs-dir", "output/monthly-graphs",
    "--output-dir", "output/report",
    "--continue-on-error",
    "--verbose",
]

stages = [
    ("1/3 Community Atmosphere", ["--analyzers", "community_atmosphere"]),
    ("2/3 Atmosphere Report",    ["--reports", "atmosphere_report"]),
    ("3/3 Comprehensive Report", ["--reports", "comprehensive_report"]),
]

t0 = time.time()
for name, args in stages:
    print(f"\n{'='*60}")
    print(f"  [{name}] {time.strftime('%H:%M:%S')}")
    print(f"{'='*60}", flush=True)
    
    ts = time.time()
    cmd = BASE_CMD + args
    print(f"  $ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, capture_output=False)
    elapsed = time.time() - ts
    
    if result.returncode == 0:
        print(f"  ✅ {name} 完成 ({elapsed:.0f}s)", flush=True)
    else:
        print(f"  ❌ {name} 失败 (exit={result.returncode}, {elapsed:.0f}s)", flush=True)
        if "Community Atmosphere" in name:
            print("  ⛔ 氛围分析失败，停止", flush=True)
            sys.exit(1)

total = time.time() - t0
print(f"\n{'='*60}")
print(f"  完成! 总耗时: {total/60:.1f} 分钟 ({time.strftime('%H:%M:%S')})")
print(f"{'='*60}", flush=True)

# 验证
import json
with open("output/report/community-atmosphere-analysis/summary.json") as f:
    atmo = json.load(f)
print(f"\n验证: atmosphere summary 有 {len(atmo)} 个 repo")
repo_names = [r["repo_name"] for r in atmo]
for r in ["qwenlm/qwen-agent", "thudm/chatglm3", "meta-llama/llama-stack", "mistralai/client-python"]:
    print(f"  {r}: {'✅' if r in repo_names else '❌'}")
for r in ["qwenlm/qwen", "thudm/chatglm-6b", "deepseek-ai/deepseek-coder"]:
    print(f"  {r}: {'⚠️ 残留!' if r in repo_names else '✅ 已清除'}")
