#!/usr/bin/env python3
"""检查各分析结果中实际包含的 repo 列表"""
import json, os
os.chdir("/Users/milk/Documents/ali2025/oss_graph_construction")

removed = {"qwenlm/qwen", "thudm/chatglm-6b", "meta-llama/llama", "mistralai/mistral-inference", "deepseek-ai/deepseek-coder"}
added = {"qwenlm/qwen-agent", "thudm/chatglm3", "meta-llama/llama-stack", "mistralai/client-python"}

def check_json(path, label):
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        repos = set(data.keys())
    elif isinstance(data, list):
        # could be list of dicts with repo_name
        repos = set()
        for item in data:
            if isinstance(item, dict):
                for key in ["repo_name", "repo", "project"]:
                    if key in item:
                        repos.add(item[key])
                        break
    else:
        repos = set()
    
    print(f"\n{label}: {len(repos)} repos")
    
    stale = repos & removed
    if stale:
        print(f"  ⚠️ 残留旧 repo: {stale}")
    
    found_new = repos & added
    missing_new = added - repos
    lc_repos = {r.lower() for r in repos}
    for r in added:
        if r not in repos and r.lower() in lc_repos:
            found_new.add(r)
            missing_new.discard(r)
    
    if found_new:
        print(f"  ✅ 有新 repo: {found_new}")
    if missing_new:
        print(f"  ❌ 缺新 repo: {missing_new}")
    
    return repos

# Burnout
try:
    repos = check_json("output/report/burnout-analysis/summary.json", "burnout/summary")
except: pass
try:
    repos = check_json("output/report/burnout-analysis/full_analysis.json", "burnout/full")
except: pass

# Newcomer
try:
    repos = check_json("output/report/newcomer-analysis/summary.json", "newcomer/summary")
except: pass

# Personnel flow
try:
    repos = check_json("output/report/personnel-flow-all/personnel_flow.json", "personnel-flow")
except Exception as e:
    print(f"  personnel-flow 读取失败: {e}")

# Atmosphere
try:
    repos = check_json("output/report/community-atmosphere-analysis/summary.json", "atmosphere/summary")
except: pass
try:
    repos = check_json("output/report/community-atmosphere-analysis/full_analysis.json", "atmosphere/full")
except: pass
