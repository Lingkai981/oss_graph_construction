#!/usr/bin/env python3
"""检查各维度分析结果中的 repo 数量和残留旧 repo"""
import json, os

os.chdir("/Users/milk/Documents/ali2025/oss_graph_construction")

# 1. index.json
with open("output/monthly-graphs/index.json") as f:
    idx = json.load(f)
print(f"index.json: {len(idx)} repos")

# 应该被删除的 5 个 repo
removed = {"qwenlm/qwen", "thudm/chatglm-6b", "meta-llama/llama", "mistralai/mistral-inference", "deepseek-ai/deepseek-coder"}
# 新增的 4 个 repo
added = {"qwenlm/qwen-agent", "thudm/chatglm3", "meta-llama/llama-stack", "mistralai/client-python"}

# 2. Burnout
burnout_dir = "output/report/burnout-analysis"
burnout_files = [f for f in os.listdir(burnout_dir) if f.endswith(".json") and f != "all_alerts.json"]
burnout_repos = set()
for f in burnout_files:
    with open(os.path.join(burnout_dir, f)) as fh:
        d = json.load(fh)
    if isinstance(d, dict) and "repo" in d:
        burnout_repos.add(d["repo"])
    else:
        burnout_repos.add(f.replace(".json", ""))
print(f"\nburnout: {len(burnout_files)} files")
for r in removed:
    rkey = r.replace("/", "-")
    matches = [f for f in burnout_files if rkey in f.lower() or r.split("/")[1] in f.lower()]
    if matches:
        print(f"  ⚠️ 残留旧 repo: {r} -> {matches}")
for r in added:
    rkey = r.replace("/", "-")
    matches = [f for f in burnout_files if rkey in f.lower()]
    if matches:
        print(f"  ✅ 有新 repo: {r} -> {matches}")
    else:
        print(f"  ❌ 缺新 repo: {r}")

# 3. Newcomer
newcomer_dir = "output/report/newcomer-analysis"
newcomer_files = [f for f in os.listdir(newcomer_dir) if f.endswith(".json")]
print(f"\nnewcomer: {len(newcomer_files)} files")
for r in removed:
    rkey = r.replace("/", "-")
    matches = [f for f in newcomer_files if rkey in f.lower() or r.split("/")[1] in f.lower()]
    if matches:
        print(f"  ⚠️ 残留旧 repo: {r} -> {matches}")
for r in added:
    rkey = r.replace("/", "-")
    matches = [f for f in newcomer_files if rkey in f.lower()]
    if matches:
        print(f"  ✅ 有新 repo: {r} -> {matches}")
    else:
        print(f"  ❌ 缺新 repo: {r}")

# 4. Personnel Flow
pf_dir = "output/report/personnel-flow-all"
pf_files = [f for f in os.listdir(pf_dir) if f.endswith(".json") and f != "summary.json"]
print(f"\npersonnel-flow: {len(pf_files)} files")
for r in removed:
    rkey = r.replace("/", "-")
    matches = [f for f in pf_files if rkey in f.lower() or r.split("/")[1] in f.lower()]
    if matches:
        print(f"  ⚠️ 残留旧 repo: {r} -> {matches}")
for r in added:
    rkey = r.replace("/", "-")
    matches = [f for f in pf_files if rkey in f.lower()]
    if matches:
        print(f"  ✅ 有新 repo: {r} -> {matches}")
    else:
        print(f"  ❌ 缺新 repo: {r}")

# 5. Atmosphere
with open("output/report/community-atmosphere-analysis/summary.json") as f:
    atmo = json.load(f)
atmo_repos = set(r["repo_name"] for r in atmo)
print(f"\natmosphere: {len(atmo_repos)} repos")
for r in removed:
    if r in atmo_repos:
        print(f"  ⚠️ 残留旧 repo: {r}")
for r in added:
    if r in atmo_repos:
        print(f"  ✅ 有新 repo: {r}")
    else:
        print(f"  ❌ 缺新 repo: {r}")

# Summary
print(f"\n{'='*50}")
print("综合：报告中 N=77 的原因是旧 repo 的分析结果文件没被清理")
print("需要：删旧结果 → 重跑全部分析")
