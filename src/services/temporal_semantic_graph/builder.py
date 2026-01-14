"""
时序语义图构建器

根据 GitHub 事件列表构建包含事件、开发者、仓库、提交等节点的时序语义图，
并建立开发者→事件、事件→仓库、事件→提交等关系边。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

import networkx as nx

from src.models.temporal_semantic import (
    make_actor_attributes,
    make_commit_attributes,
    make_event_attributes,
    make_repo_attributes,
)
from src.utils.logger import get_logger

logger = get_logger()


def build_temporal_semantic_graph(
    events: Iterable[Dict[str, Any]],
    actor_influence: Optional[Dict[int, float]] = None,
    event_importance: Optional[Dict[str, float]] = None,
) -> nx.DiGraph:
    """
    从事件列表构建时序语义图（MVP 版本，结构正确为主）。

    当前实现重点：
    - 为每个事件创建事件节点，并附带基础时间属性；
    - 为每个 actor 创建开发者节点，为每个 repo 创建仓库节点；
    - 对 PushEvent 创建提交节点，并建立事件→提交关系；
    - 建立开发者→事件、事件→仓库、事件→提交三类关系边；
    - 使用 created_at 对事件进行排序，并作为时间语义的主要来源。

    Args:
        events: 事件字典可迭代对象
        actor_influence: 开发者影响力评分映射（actor_id -> influence_score，0～1），可选
        event_importance: 事件重要性评分映射（event_id -> importance_score，0～1），可选

    Returns:
        NetworkX 有向图对象
    """
    graph = nx.DiGraph()
    actor_influence = actor_influence or {}
    event_importance = event_importance or {}

    # 先将事件收集为列表并按时间排序
    normalized_events = []
    for ev in events:
        attrs = make_event_attributes(ev)
        ts = attrs.get("created_at_ts")
        normalized_events.append((ts, ev, attrs))

    # 以时间戳排序，None 的事件排在最后
    normalized_events.sort(key=lambda pair: (pair[0] is None, pair[0]))

    for ts, ev, event_attrs in normalized_events:
        event_id = ev.get("id")
        event_type = ev.get("type")
        created_at = ev.get("created_at")
        if not event_id or not event_type or not created_at:
            # 缺少关键字段的事件直接跳过
            logger.warning(f"跳过缺少关键字段的事件: {ev!r}")
            continue

        # -------- 事件节点 --------
        event_node_id = f"event:{event_id}"
        if event_node_id not in graph:
            # 写入事件重要性评分（如有）
            importance_score = float(event_importance.get(event_id, 0.0))
            event_attrs_with_score = dict(event_attrs)
            event_attrs_with_score["importance_score"] = importance_score
            graph.add_node(event_node_id, **event_attrs_with_score)

        # -------- 开发者节点与边 --------
        actor = ev.get("actor") or {}
        actor_id = actor.get("id")
        if actor_id is not None:
            actor_node_id = f"actor:{actor_id}"
            if actor_node_id not in graph:
                actor_attrs = make_actor_attributes(actor)
                influence_score = float(actor_influence.get(actor_id, 0.0))
                actor_attrs["influence_score"] = influence_score
                graph.add_node(actor_node_id, **actor_attrs)
            # 开发者 → 事件
            edge_id = (actor_node_id, event_node_id, "ACTOR_TRIGGERED_EVENT")
            if not graph.has_edge(actor_node_id, event_node_id):
                influence_score = float(actor_influence.get(actor_id, 0.0))
                importance_score = float(event_importance.get(event_id, 0.0))
                contribution_strength = influence_score * importance_score
                graph.add_edge(
                    actor_node_id,
                    event_node_id,
                    type="ACTOR_TRIGGERED_EVENT",
                    created_at=created_at,
                    contribution_strength=contribution_strength,
                )

        # -------- 仓库节点与边 --------
        repo = ev.get("repo") or {}
        repo_id = repo.get("id")
        if repo_id is not None:
            repo_node_id = f"repo:{repo_id}"
            if repo_node_id not in graph:
                graph.add_node(repo_node_id, **make_repo_attributes(repo))
            # 事件 → 仓库
            if not graph.has_edge(event_node_id, repo_node_id):
                graph.add_edge(
                    event_node_id,
                    repo_node_id,
                    type="EVENT_TARGETS_REPOSITORY",
                    created_at=created_at,
                    event_type=event_type,
                )

        # -------- 提交节点与边（PushEvent） --------
        if event_type == "PushEvent":
            payload = ev.get("payload") or {}
            commits = payload.get("commits") or []
            for commit in commits:
                sha = commit.get("sha")
                if not sha:
                    continue
                commit_node_id = f"commit:{sha}"
                if commit_node_id not in graph:
                    graph.add_node(commit_node_id, **make_commit_attributes(commit))
                # 事件 → 提交
                if not graph.has_edge(event_node_id, commit_node_id):
                    graph.add_edge(
                        event_node_id,
                        commit_node_id,
                        type="EVENT_CONTAINS_COMMIT",
                        created_at=created_at,
                        distinct=commit.get("distinct"),
                    )

    logger.info(
        f"时序语义图构建完成: 节点数={graph.number_of_nodes()}，边数={graph.number_of_edges()}"
    )
    return graph


