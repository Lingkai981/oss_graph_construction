"""
时序语义图构建流水线

负责将加载、构图与导出串联起来，供 CLI 子命令调用。
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
)
from src.services.temporal_semantic_graph.loader import load_events_from_file
from src.services.temporal_semantic_graph.builder import build_temporal_semantic_graph
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

    # 2. 基于整小时事件预计算语义评分（事件重要性与开发者影响力）
    event_importance_raw: Dict[str, float] = {}
    actor_influence_raw: Dict[int, float] = defaultdict(float)
    actor_repo_set: Dict[int, set] = defaultdict(set)

    # 事件类型权重（可根据研究需要调整）
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
        commit_factor = math.log1p(len(commits)) if commits else 1.0

        raw_imp = base * commit_factor
        event_importance_raw[event_id] = event_importance_raw.get(event_id, 0.0) + raw_imp

        actor = ev.get("actor") or {}
        actor_id = actor.get("id")
        if actor_id is not None:
            actor_influence_raw[actor_id] += raw_imp
            repo = ev.get("repo") or {}
            repo_id = repo.get("id")
            if repo_id is not None:
                actor_repo_set[actor_id].add(repo_id)

    # 为跨仓库活动增加一点加成
    for actor_id, repos in actor_repo_set.items():
        actor_influence_raw[actor_id] += 0.5 * len(repos)

    def _normalize(scores: Dict) -> Dict:
        if not scores:
            return {}
        max_v = max(scores.values())
        if max_v <= 0:
            return {k: 0.0 for k in scores}
        return {k: float(v) / float(max_v) for k, v in scores.items()}

    event_importance = _normalize(event_importance_raw)
    actor_influence = _normalize(actor_influence_raw)

    # 3. 按分钟分组并为每个分钟构建独立图
    # 键格式示例：2015-01-01-15-00
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
            minute_events, actor_influence=actor_influence, event_importance=event_importance
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


