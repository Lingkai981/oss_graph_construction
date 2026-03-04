"""将 monthly-graphs2 里的 GraphML 导出为可供 Kuzu 批量导入的 CSV。

遍历 monthly-graphs2 下的 actor-actor、actor-discussion、actor-repo 所有 GraphML，产出：
    - actors.csv
    - repos.csv
    - discussions.csv
    - actor_actor_edges.csv
    - actor_discussion_edges.csv
    - actor_repo_edges.csv

Schema 采用“单表 + edge_type 字段”策略。

用法（在仓库根目录执行）：
        python scripts/graphml_to_kuzu_csv.py \
                --input-dir output/monthly-graphs2 \
                --output-dir output/kuzu_csv

脚本不虚构字段；缺失值保持为空。
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional

import networkx as nx


ActorNode = Dict[str, str]
RepoNode = Dict[str, str]
DiscussionNode = Dict[str, str]
EdgeRow = Dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 GraphML 导出为 Kuzu 用的 CSV")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("output/monthly-graphs2"),
        help="按仓库存放 GraphML 的目录",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/kuzu_csv"),
        help="CSV 输出目录",
    )
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_graphml(path: Path) -> nx.DiGraph:
    # networkx.read_graphml 返回 MultiGraph，这里直接拿到有向图对象使用
    graph = nx.read_graphml(path)
    return graph


def update_if_empty(dst: Dict[str, str], key: str, value: Optional[str]) -> None:
    if key not in dst and value is not None:
        dst[key] = value


def collect_from_graph(
    graph_path: Path,
    repo_name: str,
    graph_kind: str,
    actors: Dict[str, ActorNode],
    repos: Dict[str, RepoNode],
    discussions: Dict[str, DiscussionNode],
    actor_actor_edges: List[EdgeRow],
    actor_discussion_edges: List[EdgeRow],
    actor_repo_edges: List[EdgeRow],
) -> None:
    g = read_graphml(graph_path)
    graph_month = str(g.graph.get("month", graph_path.stem))
    meta_repo = g.graph.get("repo_name")
    repo_name = str(meta_repo) if meta_repo else repo_name

    for node_id, data in g.nodes(data=True):
        node_type = data.get("node_type")
        if node_type == "Actor":
            # Keep first seen values; do not invent missing fields
            if node_id not in actors:
                actors[node_id] = {
                    "id": node_id,
                    "actor_id": str(data.get("actor_id", "")),
                    "login": str(data.get("login", "")),
                    "event_count": str(data.get("event_count", "")),
                    "event_types": str(data.get("event_types", "")),
                }
        elif node_type in {"Issue", "PullRequest"}:
            if node_id not in discussions:
                discussions[node_id] = {
                    "id": node_id,
                    "node_type": node_type,
                    "repo_id": _parse_repo_id_from_discussion(node_id),
                    "number": str(data.get("number", "")),
                    "title": str(data.get("title", "")),
                    "state": str(data.get("state", "")),
                    "creator_id": str(data.get("creator_id", "")),
                    "creator_login": str(data.get("creator_login", "")),
                    "comment_count": str(data.get("comment_count", "")),
                    "participants_count": str(data.get("participants_count", "")),
                    "created_at": str(data.get("created_at", "")),
                }
        elif node_type in {"Repo", "Repository"}:
            if node_id not in repos:
                repos[node_id] = {
                    "id": node_id,
                    "repo_id": str(data.get("repo_id", "")),
                    "name": str(data.get("name", repo_name)),
                    "event_count": str(data.get("event_count", "")),
                    "event_types": str(data.get("event_types", "")),
                }
        else:
            # 未知节点类型，跳过以避免编造
            continue

    # 多重边图使用 edge key 作为 GraphML 边 ID；若缺失则回退自定义 ID
    if g.is_multigraph():
        edge_iter = g.edges(keys=True, data=True)
    else:
        edge_iter = ((u, v, None, data) for u, v, data in g.edges(data=True))

    for edge_idx, (u, v, edge_key, data) in enumerate(edge_iter, 1):
        graphml_edge_id = data.get("id")
        if not graphml_edge_id and edge_key is not None:
            graphml_edge_id = str(edge_key)
        if not graphml_edge_id:
            graphml_edge_id = f"{u}_{v}_{edge_idx}"

        edge_type = str(data.get("edge_type", ""))
        created_at = str(data.get("created_at", ""))
        comment_body = str(data.get("comment_body", ""))
        # 附加图级元数据（保证不丢失数据）
        total_events = str(g.graph.get("total_events", ""))
        row = {
            "id": str(graphml_edge_id),
            "src": u,
            "dst": v,
            "edge_type": edge_type,
            "created_at": created_at,
            "comment_body": comment_body,
            "total_events": total_events,  # ✅ 添加图级元数据
            "repo_name": repo_name,
            "month": graph_month,
        }

        if graph_kind == "actor-actor":
            actor_actor_edges.append(row)
        elif graph_kind == "actor-discussion":
            actor_discussion_edges.append(row)
        elif graph_kind == "actor-repo":
            actor_repo_edges.append(row)


def _parse_repo_id_from_discussion(node_id: str) -> str:
    # 格式: issue:{repo_id}:{number} 或 pr:{repo_id}:{number}
    parts = node_id.split(":")
    if len(parts) >= 3:
        return parts[1]
    return ""


def write_csv(path: Path, fieldnames: List[str], rows: List[Dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def export_all(input_dir: Path, output_dir: Path) -> None:
    ensure_dir(output_dir)

    actors: Dict[str, ActorNode] = {}
    repos: Dict[str, RepoNode] = {}
    discussions: Dict[str, DiscussionNode] = {}
    actor_actor_edges: List[EdgeRow] = []
    actor_discussion_edges: List[EdgeRow] = []
    actor_repo_edges: List[EdgeRow] = []

    # 预扫描文件总数，方便输出进度
    all_graphml_files = []
    for repo_dir in sorted(input_dir.iterdir()):
        if repo_dir.is_dir() and repo_dir.name != "index.json":
            for kind in ("actor-actor", "actor-discussion", "actor-repo"):
                graph_dir = repo_dir / kind
                if graph_dir.exists():
                    all_graphml_files.extend(sorted(graph_dir.glob("*.graphml")))
    total_files = len(all_graphml_files)
    print(f"待处理 GraphML 文件数: {total_files}")

    processed = 0

    for repo_dir in sorted(input_dir.iterdir()):
        if not repo_dir.is_dir():
            continue
        if repo_dir.name == "index.json":
            continue

        repo_name = repo_dir.name.replace("-", "/", 1) if "/" not in repo_dir.name else repo_dir.name

        for kind in ("actor-actor", "actor-discussion", "actor-repo"):
            graph_dir = repo_dir / kind
            if not graph_dir.exists():
                continue
            for graphml_file in sorted(graph_dir.glob("*.graphml")):
                processed += 1
                if processed % 50 == 0 or processed == total_files:
                    print(f"[进度] {processed}/{total_files} {graphml_file}")
                collect_from_graph(
                    graphml_file,
                    repo_name=repo_name,
                    graph_kind=kind,
                    actors=actors,
                    repos=repos,
                    discussions=discussions,
                    actor_actor_edges=actor_actor_edges,
                    actor_discussion_edges=actor_discussion_edges,
                    actor_repo_edges=actor_repo_edges,
                )

    write_csv(output_dir / "actors.csv", [
        "id",
        "actor_id",
        "login",
        "event_count",
        "event_types",
    ], list(actors.values()))

    write_csv(output_dir / "repos.csv", [
        "id",
        "repo_id",
        "name",
        "event_count",
        "event_types",
    ], list(repos.values()))

    write_csv(output_dir / "discussions.csv", [
        "id",
        "node_type",
        "repo_id",
        "number",
        "title",
        "state",
        "creator_id",
        "creator_login",
        "comment_count",
        "participants_count",
        "created_at",
    ], list(discussions.values()))

    write_csv(output_dir / "actor_actor_edges.csv", [
        "src",#边的起始节点
        "dst",#边的目标节点
        "id",
        "edge_type",
        "created_at",
        "comment_body",
        "total_events",  # ✅ 添加图级元数据
        "repo_name",
        "month",
    ], actor_actor_edges)

    write_csv(output_dir / "actor_discussion_edges.csv", [
        "src",
        "dst",
        "id",
        "edge_type",
        "created_at",
        "comment_body",
        "total_events",  # ✅ 添加图级元数据
        "repo_name",
        "month",
    ], actor_discussion_edges)

    write_csv(output_dir / "actor_repo_edges.csv", [
        "src",
        "dst",
        "id",
        "edge_type",
        "created_at",
        "comment_body",
        "total_events",  # ✅ 添加图级元数据
        "repo_name",
        "month",
    ], actor_repo_edges)


def main() -> None:
    args = parse_args()
    if not args.input_dir.exists():
        print(f"Input directory not found: {args.input_dir}", file=sys.stderr)
        sys.exit(1)
    export_all(args.input_dir, args.output_dir)
    print(f"CSV export completed: {args.output_dir}")


if __name__ == "__main__":
    main()
