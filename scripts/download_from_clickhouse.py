#!/usr/bin/env python3
"""
从 ClickHouse playground 下载 GH Archive 数据 —— 带宽最优方案

相比直接下载 GH Archive .gz 文件 (~178GB), 此方案只下载匹配事件 (~50MB)
节省 99.97% 带宽！

原理：
  - play.clickhouse.com 已经导入了全量 GH Archive 数据
  - 我们通过 SQL 查询只获取 11 个目标仓库的事件
  - 重建 GH Archive JSON 格式，兼容 monthly_graph_builder

用法：
  python scripts/download_from_clickhouse.py [--output-dir data/filtered-new11]
"""

import os
import sys
import json
import time
import hashlib
import argparse
from datetime import datetime
from collections import defaultdict

try:
    import requests
except ImportError:
    print("请先安装 requests: pip install requests")
    sys.exit(1)

# ===================== 配置 =====================

CLICKHOUSE_URL = "https://play.clickhouse.com/"
CLICKHOUSE_PARAMS = {"user": "play"}

# 11 个目标仓库 → 包含所有历史别名
# 格式: {当前名: [当前名, 旧名1, 旧名2, ...]}
REPO_ALIASES = {
    "ggerganov/llama.cpp": ["ggerganov/llama.cpp"],
    "ollama/ollama": ["ollama/ollama"],
    "vllm-project/vllm": ["vllm-project/vllm"],
    "Significant-Gravitas/AutoGPT": [
        "Significant-Gravitas/AutoGPT",
        "Significant-Gravitas/Auto-GPT",
    ],
    "comfyanonymous/ComfyUI": ["comfyanonymous/ComfyUI"],
    "open-webui/open-webui": [
        "open-webui/open-webui",
        "ollama-webui/ollama-webui",
    ],
    "meta-llama/llama": [
        "meta-llama/llama",
        "meta-llama/llama3",
    ],
    "run-llama/llama_index": [
        "run-llama/llama_index",
        "jerryjliu/llama_index",
        "jerryjliu/gpt_index",
    ],
    "microsoft/autogen": ["microsoft/autogen"],
    "langgenius/dify": ["langgenius/dify"],
    "openclaw/openclaw": ["openclaw/openclaw"],
}

# 构建反向映射: 旧名 → 当前名
ALIAS_TO_CANONICAL = {}
ALL_REPO_NAMES = []
for canonical, aliases in REPO_ALIASES.items():
    for alias in aliases:
        ALIAS_TO_CANONICAL[alias] = canonical
        ALL_REPO_NAMES.append(alias)

DEFAULT_OUTPUT_DIR = "data/filtered-new11"

# ===================== 工具函数 =====================


def stable_hash_id(name: str) -> int:
    """从字符串生成稳定的数字 ID（用于替代 GitHub numeric ID）"""
    h = hashlib.md5(name.encode()).hexdigest()
    return int(h[:14], 16)  # 14 hex digits → ~56 bit int, 避免溢出


def query_clickhouse(sql: str, timeout: int = 600) -> str:
    """执行 ClickHouse 查询"""
    resp = requests.post(
        CLICKHOUSE_URL,
        params=CLICKHOUSE_PARAMS,
        data=sql.encode("utf-8"),
        timeout=timeout,
        headers={"Content-Type": "text/plain"},
    )
    if resp.status_code != 200:
        print(f"  ClickHouse error ({resp.status_code}): {resp.text[:500]}")
        resp.raise_for_status()
    return resp.text


# ===================== 事件重建 =====================


def reconstruct_event(row: dict, row_idx: int) -> dict:
    """
    将 ClickHouse 行数据重建为 GH Archive JSON 格式
    
    ClickHouse github_events 表没有 actor_id/repo_id 数字字段,
    因此我们用 stable_hash_id 生成稳定的数字 ID
    """
    event_type = row.get("event_type", "")
    actor_login = row.get("actor_login", "")
    repo_name_raw = row.get("repo_name", "")
    
    # 规范化仓库名
    repo_name = ALIAS_TO_CANONICAL.get(repo_name_raw, repo_name_raw)
    
    actor_id = stable_hash_id(f"actor:{actor_login}")
    repo_id = stable_hash_id(f"repo:{repo_name}")
    
    created_at = row.get("created_at", "")
    # ClickHouse 返回 "2023-01-01 12:00:00" 格式, 转为 ISO 格式
    if created_at and "T" not in created_at:
        created_at = created_at.replace(" ", "T") + "Z"
    
    # 基础事件结构
    event = {
        "id": str(row_idx),
        "type": event_type,
        "actor": {
            "id": actor_id,
            "login": actor_login,
            "display_login": actor_login,
            "gravatar_id": "",
            "url": f"https://api.github.com/users/{actor_login}",
            "avatar_url": "",
        },
        "repo": {
            "id": repo_id,
            "name": repo_name,
            "url": f"https://api.github.com/repos/{repo_name}",
        },
        "public": True,
        "created_at": created_at,
    }
    
    # 解析 payload 字段
    action = row.get("action", "none")
    if action == "none":
        action = None
    
    number = row.get("number", 0) or 0
    title = row.get("title", "") or ""
    state = row.get("state", "") or ""
    body = row.get("body", "") or ""
    comment_id = row.get("comment_id", 0) or 0
    creator_login = row.get("creator_user_login", "") or ""
    creator_id = stable_hash_id(f"actor:{creator_login}") if creator_login else 0
    merged = row.get("merged", 0) or 0
    push_size = row.get("push_size", 0) or 0
    push_distinct = row.get("push_distinct_size", 0) or 0
    
    payload = {}
    if action:
        payload["action"] = action
    
    if event_type in ("IssuesEvent", "IssueCommentEvent"):
        issue_user = {"id": creator_id, "login": creator_login} if creator_login else {"id": 0, "login": ""}
        issue = {
            "number": number,
            "title": title,
            "state": state,
            "created_at": created_at,
            "user": issue_user,
            "labels": [],
            "comments": 0,
        }
        payload["issue"] = issue
        
        if event_type == "IssueCommentEvent":
            payload["comment"] = {
                "id": comment_id,
                "body": body,
                "user": {
                    "id": actor_id,
                    "login": actor_login,
                },
                "created_at": created_at,
                "updated_at": row.get("updated_at", created_at),
            }
    
    elif event_type in ("PullRequestEvent", "PullRequestReviewCommentEvent", "PullRequestReviewEvent"):
        pr_user = {"id": creator_id, "login": creator_login} if creator_login else {"id": 0, "login": ""}
        pr = {
            "number": number,
            "title": title,
            "state": state,
            "merged": bool(merged),
            "user": pr_user,
        }
        payload["pull_request"] = pr
        
        if event_type == "PullRequestReviewCommentEvent":
            payload["comment"] = {
                "id": comment_id,
                "body": body,
                "user": {
                    "id": actor_id,
                    "login": actor_login,
                },
                "created_at": created_at,
            }
    
    elif event_type == "PushEvent":
        # 创建合成 commits 列表来匹配 push_size
        commits = []
        for i in range(min(push_size, 20)):
            commits.append({
                "sha": f"synthetic_{row_idx}_{i}",
                "message": "",
                "distinct": True,
                "author": {"name": actor_login, "email": ""},
            })
        payload["commits"] = commits
        payload["size"] = push_size
        payload["distinct_size"] = push_distinct
        payload["ref"] = row.get("ref", "") or ""
    
    elif event_type == "WatchEvent":
        payload["action"] = "started"
    
    elif event_type == "ForkEvent":
        pass  # 最简 payload
    
    elif event_type == "CreateEvent":
        ref = row.get("ref", "") or ""
        ref_type = row.get("ref_type", "") or ""
        if ref_type and ref_type != "none":
            payload["ref_type"] = ref_type
        if ref:
            payload["ref"] = ref
    
    elif event_type == "DeleteEvent":
        ref = row.get("ref", "") or ""
        ref_type = row.get("ref_type", "") or ""
        if ref_type and ref_type != "none":
            payload["ref_type"] = ref_type
        if ref:
            payload["ref"] = ref
    
    elif event_type == "ReleaseEvent":
        payload["action"] = action or "published"
        payload["release"] = {
            "tag_name": row.get("release_tag_name", "") or "",
            "name": row.get("release_name", "") or "",
        }
    
    elif event_type == "MemberEvent":
        payload["action"] = action or "added"
        member_login = row.get("member_login", "") or ""
        if member_login:
            payload["member"] = {
                "id": stable_hash_id(f"actor:{member_login}"),
                "login": member_login,
            }
    
    event["payload"] = payload
    return event


# ===================== 下载逻辑 =====================


def download_all_events(output_dir: str):
    """从 ClickHouse 下载所有目标仓库的 daily-mode 事件"""
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 构建 IN 子句
    repo_list = ", ".join(f"'{r}'" for r in ALL_REPO_NAMES)
    
    # 先预览数据量
    print("=" * 60)
    print("预览数据量...")
    count_sql = f"""
    SELECT count() FROM github_events
    WHERE repo_name IN ({repo_list})
      AND toHour(file_time) = 12
    FORMAT TabSeparated
    """
    total_count = int(query_clickhouse(count_sql, timeout=60).strip())
    print(f"  Daily-mode 事件总数: {total_count:,}")
    print(f"  预估数据量: ~{total_count * 500 // 1024 // 1024} MB (JSON)")
    
    # 因为数据量不大(~72K行), 可以一次性查询
    # 但为安全起见分仓库查询
    all_events_by_date = defaultdict(list)
    global_row_idx = 0
    
    for canonical_name, aliases in REPO_ALIASES.items():
        alias_list = ", ".join(f"'{a}'" for a in aliases)
        
        print(f"\n{'─' * 50}")
        print(f"📦 {canonical_name}")
        if len(aliases) > 1:
            print(f"   (含别名: {', '.join(aliases[1:])})")
        
        sql = f"""
        SELECT
            event_type,
            actor_login,
            repo_name,
            toString(created_at) AS created_at,
            toString(updated_at) AS updated_at,
            action,
            comment_id,
            body,
            number,
            title,
            state,
            creator_user_login,
            merged,
            push_size,
            push_distinct_size,
            ref,
            ref_type,
            release_tag_name,
            release_name,
            review_state,
            member_login,
            toString(file_time) AS file_time_str
        FROM github_events
        WHERE repo_name IN ({alias_list})
          AND toHour(file_time) = 12
        ORDER BY file_time, created_at
        FORMAT JSONEachRow
        """
        
        start_time = time.time()
        try:
            result = query_clickhouse(sql, timeout=600)
        except Exception as e:
            print(f"   ❌ 查询失败: {e}")
            continue
        elapsed = time.time() - start_time
        
        # 解析结果
        repo_count = 0
        repo_dates = set()
        
        for line in result.strip().split("\n"):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            # 提取日期
            file_time = row.get("file_time_str", "")
            date_str = file_time[:10] if file_time else row.get("created_at", "")[:10]
            
            if not date_str or date_str < "2020":
                continue
            
            event = reconstruct_event(row, global_row_idx)
            global_row_idx += 1
            all_events_by_date[date_str].append(event)
            repo_count += 1
            repo_dates.add(date_str)
        
        print(f"   ✅ {repo_count:,} 事件, {len(repo_dates)} 天, 耗时 {elapsed:.1f}s")
    
    # 写入日文件
    print(f"\n{'=' * 60}")
    print(f"📝 写入 daily JSON 文件到 {output_dir}/")
    
    total_events = 0
    total_files = 0
    
    for date_str in sorted(all_events_by_date.keys()):
        events = all_events_by_date[date_str]
        if not events:
            continue
        
        filename = f"{date_str}-12-filtered.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        
        total_events += len(events)
        total_files += 1
    
    print(f"   ✅ {total_files} 文件, {total_events:,} 事件")
    
    # 统计
    total_size = sum(
        os.path.getsize(os.path.join(output_dir, f))
        for f in os.listdir(output_dir)
        if f.endswith(".json")
    )
    print(f"   💾 总大小: {total_size / 1024 / 1024:.1f} MB")
    
    # 按仓库统计
    print(f"\n📊 按仓库统计:")
    repo_stats = defaultdict(int)
    for events in all_events_by_date.values():
        for e in events:
            rname = e.get("repo", {}).get("name", "")
            repo_stats[rname] += 1
    
    for repo, count in sorted(repo_stats.items(), key=lambda x: -x[1]):
        print(f"   {repo}: {count:,}")
    
    print(f"\n🎉 下载完成! 可以运行 run_new_repos.py --build-graphs 构建图谱")
    return total_files, total_events


def test_connection():
    """测试 ClickHouse 连接"""
    print("🔗 测试 ClickHouse 连接...")
    try:
        result = query_clickhouse("SELECT 1 FORMAT TabSeparated", timeout=15)
        if result.strip() == "1":
            print("   ✅ 连接成功")
            return True
    except Exception as e:
        print(f"   ❌ 连接失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="从 ClickHouse playground 下载 GH Archive 数据 (节省 99.97%% 带宽)"
    )
    parser.add_argument(
        "--output-dir", default=DEFAULT_OUTPUT_DIR,
        help=f"输出目录 (默认: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="仅测试连接"
    )
    args = parser.parse_args()
    
    if not test_connection():
        print("\n请检查网络连接。需要访问 https://play.clickhouse.com/")
        sys.exit(1)
    
    if args.test:
        return
    
    download_all_events(args.output_dir)


if __name__ == "__main__":
    main()
