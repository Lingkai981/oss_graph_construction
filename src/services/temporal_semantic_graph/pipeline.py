"""
时序语义图构建流水线

负责将加载、构图与导出串联起来，供 CLI 子命令调用。
支持四种图模式：
1. event-centric: 原始的以事件为中心的异构图
2. actor-repo: Actor-Repository 投影图
3. actor-actor: Actor-Actor 协作图
4. actor-discussion: Actor-Discussion 二部图（Issue/PR 讨论图）
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List
from collections import defaultdict
import math

import networkx as nx

from src.services.exporter import (
    ensure_output_directory,
    export_temporal_graph_to_json,
    export_temporal_graph_to_graphml,
    export_projection_graph_to_json,
    export_projection_graph_to_graphml,
)
from src.services.temporal_semantic_graph.loader import load_events_from_file
from src.services.temporal_semantic_graph.builder import build_temporal_semantic_graph
from src.services.temporal_semantic_graph.projection_builder import (
    build_actor_repo_graph,
    build_actor_actor_graph,
    build_actor_discussion_graph,
)
from src.utils.date_utils import parse_timestamp
from src.utils.logger import get_logger

logger = get_logger()


def run_temporal_graph_pipeline(
    input_path: str,
    output_dir: str = "output/temporal-semantic-graph/",
    export_formats: Iterable[str] = ("json", "graphml"),
) -> List[str]:
    """
    运行完整的一小时时序语义图构建流水线。

    步骤：
    1. 从 JSON 行文件中加载事件；
    2. 构建时序语义图；
    3. 根据需要导出为 JSON / GraphML。

    Args:
        input_path: GitHub 事件 JSON 行文件路径
        output_dir: 导出文件目录
        export_formats: 需要导出的格式集合（如 ["json", "graphml"]）

    Returns:
        实际生成的导出文件路径列表
    """
    export_formats = list(export_formats)
    logger.info("=" * 60)
    logger.info("开始构建一小时时序语义图")
    logger.info(f"输入文件: {input_path}")
    logger.info(f"输出目录: {output_dir}")
    logger.info(f"导出格式: {', '.join(export_formats)}")

    # 1. 加载事件
    events = load_events_from_file(input_path)
    if not events:
        logger.warning("未从输入文件中解析到任何事件，本次不会生成任何快照图")

    # 2. 基于整小时事件预计算语义评分
    event_importance_raw: Dict[str, float] = {}
    actor_influence_raw: Dict[int, float] = defaultdict(float)
    actor_repo_set: Dict[int, set] = defaultdict(set)
    repo_activity_raw: Dict[int, float] = defaultdict(float)
    repo_actor_set: Dict[int, set] = defaultdict(set)
    commit_significance_raw: Dict[str, float] = {}

    type_weights: Dict[str, float] = {
        "PushEvent": 3.0,
        "CreateEvent": 2.0,
        "PullRequestEvent": 2.0,
        "IssuesEvent": 1.5,
        "IssueCommentEvent": 1.5,
        "WatchEvent": 1.0,
    }

    for ev in events:
        event_id = ev.get("id")
        if not event_id:
            continue
        event_type = ev.get("type") or ""
        base = type_weights.get(event_type, 1.0)

        payload = ev.get("payload") or {}
        commits = payload.get("commits") or []
        if event_type == "PushEvent" and commits:
            commit_factor = math.log1p(len(commits))
        else:
            commit_factor = 1.0

        raw_imp = base * commit_factor
        event_importance_raw[event_id] = raw_imp

        actor = ev.get("actor") or {}
        actor_id = actor.get("id")
        repo = ev.get("repo") or {}
        repo_id = repo.get("id")

        if repo_id is not None:
            repo_activity_raw[repo_id] += raw_imp
            if actor_id is not None:
                repo_actor_set[repo_id].add(actor_id)

        if actor_id is not None:
            actor_influence_raw[actor_id] += raw_imp
            if repo_id is not None:
                actor_repo_set[actor_id].add(repo_id)

        if event_type == "PushEvent" and commits:
            for commit in commits:
                sha = commit.get("sha")
                if not sha:
                    continue
                message = commit.get("message") or ""
                message_length = len(message)
                message_factor = 1.0 + 0.1 * math.log1p(message_length)
                commit_significance_raw[sha] = max(
                    commit_significance_raw.get(sha, 0.0), raw_imp * message_factor
                )

    cross_repo_alpha = 0.5
    for actor_id, repos in actor_repo_set.items():
        repo_count = len(repos)
        if repo_count > 0:
            actor_influence_raw[actor_id] += cross_repo_alpha * math.log1p(repo_count)

    participation_alpha = 0.3
    for repo_id, actors in repo_actor_set.items():
        actor_count = len(actors)
        if actor_count > 0:
            repo_activity_raw[repo_id] += participation_alpha * math.log1p(actor_count)

    def _min_max_normalize(scores: Dict) -> Dict:
        if not scores:
            return {}
        values = list(scores.values())
        min_v = min(values)
        max_v = max(values)
        if max_v <= 0:
            return {k: 0.0 for k in scores}
        if max_v == min_v:
            return {k: 1.0 for k in scores}
        scale = max_v - min_v
        return {k: float(v - min_v) / float(scale) for k, v in scores.items()}

    event_importance = _min_max_normalize(event_importance_raw)
    actor_influence = _min_max_normalize(actor_influence_raw)
    repo_activity = _min_max_normalize(repo_activity_raw)
    commit_significance = _min_max_normalize(commit_significance_raw)

    # 3. 按分钟分组
    groups: dict[str, list[dict]] = {}
    for ev in events:
        created_at = ev.get("created_at")
        dt = parse_timestamp(created_at) if created_at else None
        if dt is None:
            logger.warning(f"事件缺少可解析的 created_at 字段，已跳过: {ev!r}")
            continue
        minute_key = dt.strftime("%Y-%m-%d-%H-%M")
        groups.setdefault(minute_key, []).append(ev)

    logger.info(f"按分钟划分后，共有 {len(groups)} 个时间窗口将构建图快照")

    # 4. 导出
    output_path = ensure_output_directory(output_dir)
    generated_files: List[str] = []

    for minute_key, minute_events in sorted(groups.items()):
        graph: nx.DiGraph = build_temporal_semantic_graph(
            minute_events,
            actor_influence=actor_influence,
            event_importance=event_importance,
            repo_activity=repo_activity,
            commit_significance=commit_significance,
        )

        for fmt in export_formats:
            fmt_lower = fmt.lower()
            if fmt_lower not in ("json", "graphml"):
                logger.warning(f"忽略不支持的导出格式: {fmt}")
                continue

            if fmt_lower == "json":
                file_path = output_path / f"temporal-graph-{minute_key}.json"
                export_temporal_graph_to_json(
                    graph, str(file_path), source_file=str(input_path)
                )
            else:
                file_path = output_path / f"temporal-graph-{minute_key}.graphml"
                export_temporal_graph_to_graphml(graph, str(file_path))

            generated_files.append(str(file_path))

    logger.info(f"时序语义图构建与导出完成，共生成 {len(generated_files)} 个文件")
    for fp in generated_files:
        logger.info(f"生成文件: {fp}")

    logger.info("=" * 60)
    return generated_files


def run_projection_graph_pipeline(
    input_path: str,
    output_dir: str = "output/projection-graphs/",
    export_formats: Iterable[str] = ("json", "graphml"),
    graph_mode: str = "all",
    include_watch_events: bool = False,
    include_fork_events: bool = True,
    include_shared_repo_edges: bool = True,
    min_shared_repos: int = 1,
) -> List[str]:
    """
    运行投影图构建流水线。
    
    构建 Actor-Repository / Actor-Actor / Actor-Discussion 投影图，
    将事件作为边属性而非独立节点，更适合社区分析算法。
    
    Args:
        input_path: GitHub 事件 JSON 行文件路径
        output_dir: 导出文件目录
        export_formats: 需要导出的格式集合
        graph_mode: 图模式 (actor-repo / actor-actor / actor-discussion / all)
        include_watch_events: Actor-Repo 图是否包含 WatchEvent
        include_fork_events: Actor-Repo 图是否包含 ForkEvent
        include_shared_repo_edges: Actor-Actor 图是否包含共同仓库边
        min_shared_repos: 共同仓库边的最小仓库数阈值
    
    Returns:
        实际生成的导出文件路径列表
    """
    export_formats = list(export_formats)
    logger.info("=" * 60)
    logger.info("开始构建投影图")
    logger.info(f"输入文件: {input_path}")
    logger.info(f"输出目录: {output_dir}")
    logger.info(f"导出格式: {', '.join(export_formats)}")
    logger.info(f"图模式: {graph_mode}")
    
    # 1. 加载事件
    events = load_events_from_file(input_path)
    if not events:
        logger.warning("未从输入文件中解析到任何事件，本次不会生成任何图")
        return []
    
    logger.info(f"已加载 {len(events)} 条事件")
    
    # 2. 根据时间窗口提取标识
    first_event_time = None
    for ev in events:
        created_at = ev.get("created_at")
        if created_at:
            dt = parse_timestamp(created_at)
            if dt:
                first_event_time = dt.strftime("%Y-%m-%d-%H")
                break
    
    time_label = first_event_time or "unknown"
    
    # 3. 构建图
    graphs_to_export = {}
    
    if graph_mode in ("actor-repo", "all"):
        logger.info("构建 Actor-Repository 投影图...")
        actor_repo_graph = build_actor_repo_graph(
            events,
            include_watch_events=include_watch_events,
            include_fork_events=include_fork_events,
        )
        graphs_to_export["actor-repo"] = actor_repo_graph
    
    if graph_mode in ("actor-actor", "all"):
        logger.info("构建 Actor-Actor 协作图...")
        actor_actor_graph = build_actor_actor_graph(
            events,
            include_shared_repo_edges=include_shared_repo_edges,
            min_shared_repos=min_shared_repos,
        )
        graphs_to_export["actor-actor"] = actor_actor_graph
    
    if graph_mode in ("actor-discussion", "all"):
        logger.info("构建 Actor-Discussion 二部图（Issue/PR 讨论图）...")
        actor_discussion_graph = build_actor_discussion_graph(events)
        graphs_to_export["actor-discussion"] = actor_discussion_graph
    
    # 4. 导出
    output_path = ensure_output_directory(output_dir)
    generated_files: List[str] = []
    
    for graph_name, graph in graphs_to_export.items():
        for fmt in export_formats:
            fmt_lower = fmt.lower()
            if fmt_lower not in ("json", "graphml"):
                logger.warning(f"忽略不支持的导出格式: {fmt}")
                continue
            
            filename = f"{graph_name}-{time_label}.{fmt_lower}"
            file_path = output_path / filename
            
            if fmt_lower == "json":
                export_projection_graph_to_json(
                    graph,
                    str(file_path),
                    source_file=str(input_path),
                    graph_type=graph_name,
                )
            else:
                export_projection_graph_to_graphml(graph, str(file_path))
            
            generated_files.append(str(file_path))
    
    logger.info(f"投影图构建与导出完成，共生成 {len(generated_files)} 个文件")
    for fp in generated_files:
        logger.info(f"生成文件: {fp}")
    
    logger.info("=" * 60)
    return generated_files
