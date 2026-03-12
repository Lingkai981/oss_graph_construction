#!/usr/bin/env python3
"""
方案A：替换缺图严重的 repo
  - 替换 4 个: qwenlm/Qwen→Qwen-Agent, THUDM/ChatGLM-6B→ChatGLM3,
    meta-llama/llama→llama-stack, mistralai/mistral-inference→client-python
  - 删除 1 个: deepseek-ai/DeepSeek-Coder (已有 DeepSeek-V3)
  - 保留 2 个: 01-ai/Yi, baichuan-inc/Baichuan2 (同组织无更好替代)
  
  最终 73 → 72 个 repo

Usage:
  python3 scripts/_replace_repos.py --download       # Step 1: 下载 4 个新 repo 数据
  python3 scripts/_replace_repos.py --build-graphs   # Step 2: 构建图
  python3 scripts/_replace_repos.py --update-index   # Step 3: 更新 index.json
  python3 scripts/_replace_repos.py --all            # 全部执行
"""

import os, sys, json, time, hashlib, argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict

try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

CLICKHOUSE_URL = "https://play.clickhouse.com/"
CLICKHOUSE_PARAMS = {"user": "play"}

DATA_DIR = os.path.join(BASE, "data", "filtered-replace")
GRAPHS_DIR = os.path.join(BASE, "output", "monthly-graphs")

# ===================== 4 NEW REPOS =====================
NEW_REPOS = {
    "QwenLM/Qwen-Agent":          ["QwenLM/Qwen-Agent"],
    "THUDM/ChatGLM3":             ["THUDM/ChatGLM3"],
    "meta-llama/llama-stack":     ["meta-llama/llama-stack"],
    "mistralai/client-python":    ["mistralai/client-python"],
}

# 5 repos to REMOVE from index
REPOS_TO_REMOVE = [
    "qwenlm/qwen",
    "thudm/chatglm-6b", 
    "meta-llama/llama",
    "mistralai/mistral-inference",
    "deepseek-ai/deepseek-coder",
]

# Build alias mapping
ALIAS_TO_CANONICAL = {}
ALL_REPO_NAMES = []
for canonical, aliases in NEW_REPOS.items():
    for alias in aliases:
        ALIAS_TO_CANONICAL[alias] = canonical
        ALL_REPO_NAMES.append(alias)

# ===================== UTILS =====================

def stable_hash_id(name: str) -> int:
    h = hashlib.md5(name.encode()).hexdigest()
    return int(h[:14], 16)

def query_clickhouse(sql: str, timeout: int = 600, retries: int = 3) -> str:
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                CLICKHOUSE_URL, params=CLICKHOUSE_PARAMS,
                data=sql.encode("utf-8"), timeout=timeout,
                headers={"Content-Type": "text/plain"},
            )
            if resp.status_code != 200:
                print(f"  ClickHouse error ({resp.status_code}): {resp.text[:500]}")
                resp.raise_for_status()
            return resp.text
        except Exception as e:
            if attempt < retries:
                wait = attempt * 15
                print(f"  Retry {attempt}/{retries} in {wait}s: {e}")
                time.sleep(wait)
            else:
                raise

def reconstruct_event(row: dict, row_idx: int) -> dict:
    """Reconstruct GH Archive-format event from ClickHouse row."""
    event_type = row.get("event_type", "")
    actor_login = row.get("actor_login", "")
    repo_name_raw = row.get("repo_name", "")
    repo_name = ALIAS_TO_CANONICAL.get(repo_name_raw, repo_name_raw)
    
    actor_id = stable_hash_id(f"actor:{actor_login}")
    repo_id = stable_hash_id(f"repo:{repo_name}")
    created_at = row.get("created_at", "")
    if created_at and "T" not in created_at:
        created_at = created_at.replace(" ", "T") + "Z"
    
    event = {
        "id": str(row_idx),
        "type": event_type,
        "actor": {"id": actor_id, "login": actor_login, "display_login": actor_login,
                  "gravatar_id": "", "url": f"https://api.github.com/users/{actor_login}", "avatar_url": ""},
        "repo": {"id": repo_id, "name": repo_name, "url": f"https://api.github.com/repos/{repo_name}"},
        "public": True, "created_at": created_at,
    }
    
    action = row.get("action", "none")
    if action == "none": action = None
    number = row.get("number", 0) or 0
    title = row.get("title", "") or ""
    state = row.get("state", "") or ""
    body = row.get("body", "") or ""
    comment_id = row.get("comment_id", 0) or 0
    creator_login = row.get("creator_user_login", "") or ""
    creator_id = stable_hash_id(f"actor:{creator_login}") if creator_login else 0
    merged = row.get("merged", 0) or 0
    
    payload = {}
    if action: payload["action"] = action
    
    if event_type in ("IssuesEvent", "IssueCommentEvent"):
        issue = {"number": number, "title": title, "state": state, "created_at": created_at,
                 "user": {"id": creator_id, "login": creator_login} if creator_login else {"id": 0, "login": ""},
                 "labels": [], "comments": 0}
        payload["issue"] = issue
        if event_type == "IssueCommentEvent":
            payload["comment"] = {"id": comment_id, "body": body,
                                  "user": {"id": actor_id, "login": actor_login}, "created_at": created_at}
    elif event_type in ("PullRequestEvent", "PullRequestReviewCommentEvent", "PullRequestReviewEvent"):
        pr = {"number": number, "title": title, "state": state, "merged": bool(merged),
              "user": {"id": creator_id, "login": creator_login} if creator_login else {"id": 0, "login": ""}}
        payload["pull_request"] = pr
        if event_type == "PullRequestReviewCommentEvent":
            payload["comment"] = {"id": comment_id, "body": body,
                                  "user": {"id": actor_id, "login": actor_login}, "created_at": created_at}
    elif event_type == "PushEvent":
        payload["size"] = row.get("push_size", 0) or 0
        payload["distinct_size"] = row.get("push_distinct_size", 0) or 0
    elif event_type == "ForkEvent":
        payload["forkee"] = {"full_name": f"{actor_login}/{repo_name.split('/')[-1]}"}
    elif event_type == "CreateEvent":
        payload["ref_type"] = row.get("ref_type", "") or ""
    elif event_type == "DeleteEvent":
        payload["ref_type"] = row.get("ref_type", "") or ""
    elif event_type == "ReleaseEvent":
        payload["release"] = {"tag_name": title}
    
    event["payload"] = payload
    return event

# ===================== DOWNLOAD =====================

def download_data():
    os.makedirs(DATA_DIR, exist_ok=True)
    repo_list = ", ".join(f"'{r}'" for r in ALL_REPO_NAMES)
    
    # Generate month list: 2021-01 to 2026-03
    months = []
    for year in range(2021, 2027):
        for month in range(1, 13):
            ym = f"{year}-{month:02d}"
            if ym <= "2026-03":
                months.append(ym)
    
    progress_file = os.path.join(DATA_DIR, ".progress")
    done_months = set()
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            done_months = set(line.strip() for line in f if line.strip())
    
    remaining = [m for m in months if m not in done_months]
    print(f"\n📥 下载 {len(NEW_REPOS)} 个新 repo: {', '.join(NEW_REPOS.keys())}")
    print(f"   总月份: {len(months)}, 已下载: {len(done_months)}, 剩余: {len(remaining)}")
    
    global_event_id = 0
    total_events = 0
    
    for i, month in enumerate(remaining, 1):
        year, mo = month.split("-")
        if int(mo) == 12:
            next_month = f"{int(year)+1}-01-01"
        else:
            next_month = f"{year}-{int(mo)+1:02d}-01"
        
        sql = f"""
        SELECT
            event_type, actor_login, repo_name, created_at,
            action, number, title, state, body, comment_id,
            creator_user_login, merged, push_size, push_distinct_size,
            ref_type, updated_at
        FROM github_events
        WHERE repo_name IN ({repo_list})
          AND created_at >= '{year}-{mo}-01'
          AND created_at < '{next_month}'
        ORDER BY created_at
        FORMAT JSONEachRow
        """
        
        print(f"  [{i}/{len(remaining)}] {month}...", end=" ", flush=True)
        t0 = time.time()
        
        try:
            raw = query_clickhouse(sql, timeout=300)
        except Exception as e:
            print(f"ERROR: {e}")
            continue
        
        day_hour_events = defaultdict(list)
        for line in raw.strip().split("\n"):
            if not line.strip(): continue
            try:
                row = json.loads(line)
                global_event_id += 1
                event = reconstruct_event(row, global_event_id)
                ts = event.get("created_at", "")
                if len(ts) >= 13:
                    day = ts[:10]
                    hour = ts[11:13]
                    day_hour_events[f"{day}-{hour}"].append(event)
            except:
                continue
        
        month_events = 0
        for day_hour, events in sorted(day_hour_events.items()):
            filepath = os.path.join(DATA_DIR, f"{day_hour}-filtered.json")
            with open(filepath, "w", encoding="utf-8") as f:
                for ev in events:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            month_events += len(events)
        
        total_events += month_events
        elapsed = time.time() - t0
        print(f"{month_events:,} events, {elapsed:.1f}s")
        
        with open(progress_file, "a") as f:
            f.write(month + "\n")
    
    print(f"\n✅ 下载完成: {total_events:,} events")
    all_files = list(Path(DATA_DIR).glob("*-filtered.json"))
    total_size = sum(f.stat().st_size for f in all_files)
    print(f"   文件数: {len(all_files)}, 大小: {total_size/1024/1024:.1f} MB")

# ===================== BUILD GRAPHS =====================

def build_graphs():
    print("\n" + "=" * 60)
    print("🔨 为 4 个新 repo 构建 monthly graphs")
    print("=" * 60)
    
    from src.analysis.monthly_graph_builder import build_monthly_graphs_streaming
    
    data_path = Path(DATA_DIR)
    if not data_path.exists():
        print("ERROR: 无数据。先运行 --download")
        return
    
    files = list(data_path.glob("*-filtered.json"))
    print(f"  数据文件: {len(files)}")
    
    build_monthly_graphs_streaming(
        data_dir=DATA_DIR,
        output_dir=GRAPHS_DIR,
        workers=8,
        skip_existing=False,
    )
    print("✅ 图构建完成")

# ===================== UPDATE INDEX =====================

def update_index():
    print("\n" + "=" * 60)
    print("📇 更新 index.json")
    print("=" * 60)
    
    idx_path = os.path.join(GRAPHS_DIR, "index.json")
    with open(idx_path) as f:
        idx = json.load(f)
    print(f"  当前 index: {len(idx)} 个 repo")
    
    # 1) Remove 5 old repos
    removed = []
    for repo_key in REPOS_TO_REMOVE:
        if repo_key in idx:
            del idx[repo_key]
            removed.append(repo_key)
    print(f"  移除 {len(removed)} 个旧 repo: {removed}")
    
    # 2) Add 4 new repos by scanning graph dirs
    graphs_path = Path(GRAPHS_DIR)
    added = []
    for canonical in NEW_REPOS:
        dir_name = canonical.lower().replace("/", "-")
        repo_dir = graphs_path / dir_name
        if not repo_dir.exists():
            # Try case-insensitive match
            for d in graphs_path.iterdir():
                if d.is_dir() and d.name.lower() == dir_name:
                    repo_dir = d
                    break
        
        if not repo_dir.exists():
            print(f"  ⚠️ 未找到图目录: {repo_dir}")
            continue
        
        repo_key = canonical.lower()
        months_data = {}
        for graphml in sorted(repo_dir.glob("*.graphml")):
            name = graphml.stem
            parts = name.split("_")
            if len(parts) >= 3:
                month = parts[-1]
                if len(month) == 7 and "-" in month:
                    graph_type = "_".join(parts[:-1])
                    if month not in months_data:
                        months_data[month] = {}
                    months_data[month][graph_type] = str(graphml.absolute())
        
        if months_data:
            idx[repo_key] = months_data
            added.append(f"{repo_key} ({len(months_data)} months)")
    
    print(f"  添加 {len(added)} 个新 repo: {added}")
    
    # 3) Save
    with open(idx_path, "w") as f:
        json.dump(idx, f, indent=2, ensure_ascii=False)
    
    print(f"  最终 index: {len(idx)} 个 repo")
    
    # 4) Also update oneHour index if it exists
    onehour_path = os.path.join(BASE, "output", "monthly-graphs-oneHour", "index.json")
    if os.path.exists(onehour_path):
        with open(onehour_path) as f:
            oh_idx = json.load(f)
        for rk in REPOS_TO_REMOVE:
            oh_idx.pop(rk, None)
        # Don't add new repos to oneHour (they use fullday data)
        with open(onehour_path, "w") as f:
            json.dump(oh_idx, f, indent=2, ensure_ascii=False)
        print(f"  oneHour index 也已更新: {len(oh_idx)} 个 repo")
    
    print("✅ Index 更新完成")

# ===================== MAIN =====================

def main():
    parser = argparse.ArgumentParser(description="替换缺图严重的 repos (方案A)")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--build-graphs", action="store_true")
    parser.add_argument("--update-index", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    
    if not any([args.download, args.build_graphs, args.update_index, args.all]):
        parser.print_help()
        return
    
    if args.download or args.all:
        download_data()
    if args.build_graphs or args.all:
        build_graphs()
    if args.update_index or args.all:
        update_index()

if __name__ == "__main__":
    main()
