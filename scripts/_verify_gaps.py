#!/usr/bin/env python3
"""从原始 JSONL 数据验证缺失月份是否真的没有开发者协作。"""
import json, glob, os
from collections import defaultdict

ROOT = "/Users/milk/Documents/ali2025/oss_graph_construction"
os.chdir(ROOT)

# 要验证的 repo 及其缺失/存在的月份
checks = {
    "qwenlm/qwen": {
        "present": ["2024-10", "2025-02"],
        "missing": ["2024-11", "2024-12", "2025-01", "2025-06", "2025-07"],
    },
    "THUDM/ChatGLM3": {
        "present": ["2023-10", "2024-01"],
        "missing": ["2024-02", "2024-03", "2024-04", "2024-05"],
    },
    "deepseek-ai/DeepSeek-Coder": {
        "present": ["2023-11", "2024-02"],
        "missing": ["2024-03", "2024-04", "2024-05", "2024-06"],
    },
    "meta-llama/llama": {
        "present": ["2023-07", "2024-04"],
        "missing": ["2023-10", "2023-11", "2024-01", "2024-02"],
    },
    "baichuan-inc/Baichuan2": {
        "present": ["2023-09", "2024-01"],
        "missing": ["2024-02", "2024-03", "2024-04"],
    },
}

data_dirs = ["data/filtered", "data/filtered-fullday"]

def check_month(target_repo, month):
    year, mon = month.split("-")
    events_by_type = defaultdict(int)
    actors = set()
    interactions = []
    total = 0

    for data_dir in data_dirs:
        pattern = os.path.join(data_dir, f"{year}-{mon}-*-filtered.json")
        files = sorted(glob.glob(pattern))
        for f in files:
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
                    if repo.lower() != target_repo.lower():
                        continue
                    total += 1
                    etype = evt.get("type", "Unknown")
                    events_by_type[etype] += 1
                    actor = evt.get("actor", {}).get("login", "")
                    actors.add(actor)

                    payload = evt.get("payload", {})
                    if etype == "IssueCommentEvent":
                        issue = payload.get("issue", {})
                        issue_user = issue.get("user", {}).get("login", "")
                        if actor and issue_user and actor != issue_user:
                            interactions.append(f"  {actor} -> {issue_user} (评论他人issue)")
                    elif etype == "PullRequestReviewCommentEvent":
                        pr = payload.get("pull_request", {})
                        pr_user = pr.get("user", {}).get("login", "")
                        if actor and pr_user and actor != pr_user:
                            interactions.append(f"  {actor} -> {pr_user} (PR审查评论)")
                    elif etype == "PullRequestReviewEvent":
                        pr = payload.get("pull_request", {})
                        pr_user = pr.get("user", {}).get("login", "")
                        if actor and pr_user and actor != pr_user:
                            interactions.append(f"  {actor} -> {pr_user} (PR审查)")
                    elif etype == "PullRequestEvent":
                        pr = payload.get("pull_request", {})
                        if payload.get("action") == "closed" and pr.get("merged"):
                            merger = pr.get("merged_by", {})
                            merger_login = merger.get("login", "") if merger else ""
                            pr_user = pr.get("user", {}).get("login", "")
                            if merger_login and pr_user and merger_login != pr_user:
                                interactions.append(f"  {merger_login} -> {pr_user} (合并PR)")

    return total, len(actors), dict(events_by_type), interactions


for repo, months_info in checks.items():
    print(f"\n{'='*60}")
    print(f"  {repo}")
    print(f"{'='*60}")

    all_months = sorted(set(months_info["present"] + months_info["missing"]))
    for month in all_months:
        is_present = month in months_info["present"]
        status = "✅ 有图" if is_present else "❌ 缺失"
        total, n_actors, etypes, interactions = check_month(repo, month)

        # 计算"被动"事件占比
        passive = etypes.get("WatchEvent", 0) + etypes.get("ForkEvent", 0)
        passive_pct = f"{passive/total*100:.0f}%" if total > 0 else "-"

        print(f"\n  {month} [{status}]  事件={total}  用户={n_actors}  被动(star+fork)={passive}({passive_pct})")
        top3 = sorted(etypes.items(), key=lambda x: -x[1])[:5]
        for et, cnt in top3:
            print(f"    {et}: {cnt}")
        print(f"  ➜ 跨用户协作交互: {len(interactions)} 条")
        for i in interactions[:5]:
            print(f"    {i}")
        if len(interactions) > 5:
            print(f"    ... 共 {len(interactions)} 条")

print("\n\n✅ 验证完毕")
