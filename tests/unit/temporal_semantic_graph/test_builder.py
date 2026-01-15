"""
builder 模块单元测试

主要验证：
- 事件、开发者、仓库、提交节点是否按预期创建；
- 关键关系边（开发者→事件、事件→仓库、事件→提交）是否存在；
- 事件按时间顺序被处理（通过时间戳属性体现）。
"""

import networkx as nx

from src.services.temporal_semantic_graph.builder import build_temporal_semantic_graph


def _make_sample_events():
    """
    构造一组最小样例事件，用于测试构图逻辑。
    """
    return [
        {
            "id": "e1",
            "type": "CreateEvent",
            "created_at": "2015-01-01T15:00:00Z",
            "actor": {"id": 1, "login": "user1"},
            "repo": {"id": 100, "name": "owner/repo1", "url": "https://api.github.com/repos/owner/repo1"},
            "payload": {},
        },
        {
            "id": "e2",
            "type": "PushEvent",
            "created_at": "2015-01-01T15:00:10Z",
            "actor": {"id": 2, "login": "user2"},
            "repo": {"id": 200, "name": "owner/repo2", "url": "https://api.github.com/repos/owner/repo2"},
            "payload": {
                "commits": [
                    {
                        "sha": "abc123",
                        "message": "test commit",
                        "author": {"name": "user2", "email": "user2@example.com"},
                        "distinct": True,
                        "url": "https://api.github.com/repos/owner/repo2/commits/abc123",
                    }
                ]
            },
        },
    ]


def test_build_temporal_semantic_graph_basic():
    events = _make_sample_events()

    # 构造简单的语义评分映射
    actor_influence = {1: 0.3, 2: 0.9}
    event_importance = {"e1": 0.4, "e2": 0.8}

    graph = build_temporal_semantic_graph(
        events,
        actor_influence=actor_influence,
        event_importance=event_importance,
    )
    assert isinstance(graph, nx.DiGraph)

    # 节点检查：事件、actor、repo、commit
    assert "event:e1" in graph.nodes
    assert "event:e2" in graph.nodes
    assert "actor:1" in graph.nodes
    assert "actor:2" in graph.nodes
    assert "repo:100" in graph.nodes
    assert "repo:200" in graph.nodes
    assert "commit:abc123" in graph.nodes

    # 节点类型属性
    assert graph.nodes["event:e1"]["node_type"] == "Event"
    assert graph.nodes["actor:1"]["node_type"] == "Actor"
    assert graph.nodes["repo:100"]["node_type"] == "Repository"
    assert graph.nodes["commit:abc123"]["node_type"] == "Commit"

    # 语义评分属性检查
    assert graph.nodes["actor:1"]["influence_score"] == 0.3
    assert graph.nodes["event:e2"]["importance_score"] == 0.8

    # 边检查：开发者→事件、事件→仓库、事件→提交
    assert graph.has_edge("actor:1", "event:e1")
    assert graph["actor:1"]["event:e1"]["type"] == "ACTOR_TRIGGERED_EVENT"

    assert graph.has_edge("event:e1", "repo:100")
    assert graph["event:e1"]["repo:100"]["type"] == "EVENT_TARGETS_REPOSITORY"

    assert graph.has_edge("actor:2", "event:e2")
    assert graph.has_edge("event:e2", "repo:200")
    assert graph.has_edge("event:e2", "commit:abc123")
    assert graph["event:e2"]["commit:abc123"]["type"] == "EVENT_CONTAINS_COMMIT"

    # 开发者→事件边的贡献强度应为两侧评分的乘积
    strength = graph["actor:2"]["event:e2"]["contribution_strength"]
    assert abs(strength - (0.9 * 0.8)) < 1e-6

    # 时间属性检查：created_at_ts 应按时间先后递增
    ts1 = graph.nodes["event:e1"]["created_at_ts"]
    ts2 = graph.nodes["event:e2"]["created_at_ts"]
    assert ts1 is not None and ts2 is not None and ts1 < ts2


def test_build_temporal_semantic_graph_with_scores():
    """
    测试新增的语义评分属性（仓库活跃度、提交重要性、边评分）。
    """
    events = _make_sample_events()
    # 模拟预计算的评分
    mock_actor_influence = {1: 0.8, 2: 0.5}
    mock_event_importance = {"e1": 0.9, "e2": 0.6}
    mock_repo_activity = {100: 0.7, 200: 0.4}
    mock_commit_significance = {"abc123": 0.55}

    graph = build_temporal_semantic_graph(
        events,
        actor_influence=mock_actor_influence,
        event_importance=mock_event_importance,
        repo_activity=mock_repo_activity,
        commit_significance=mock_commit_significance,
    )

    # 验证事件节点重要性
    assert graph.nodes["event:e1"]["importance_score"] == 0.9
    assert graph.nodes["event:e2"]["importance_score"] == 0.6

    # 验证开发者节点影响力
    assert graph.nodes["actor:1"]["influence_score"] == 0.8
    assert graph.nodes["actor:2"]["influence_score"] == 0.5

    # 验证仓库节点活跃度
    assert graph.nodes["repo:100"]["activity_score"] == 0.7
    assert graph.nodes["repo:200"]["activity_score"] == 0.4

    # 验证提交节点重要性
    assert graph.nodes["commit:abc123"]["significance_score"] == 0.55

    # 验证开发者→事件边贡献强度
    edge_e1_attrs = graph["actor:1"]["event:e1"]
    assert "contribution_strength" in edge_e1_attrs
    assert abs(edge_e1_attrs["contribution_strength"] - (0.8 * 0.9)) < 1e-6

    edge_e2_attrs = graph["actor:2"]["event:e2"]
    assert "contribution_strength" in edge_e2_attrs
    assert abs(edge_e2_attrs["contribution_strength"] - (0.5 * 0.6)) < 1e-6

    # 验证事件→仓库边影响评分（等于事件重要性）
    event_repo_edge = graph["event:e1"]["repo:100"]
    assert "impact_score" in event_repo_edge
    assert event_repo_edge["impact_score"] == 0.9

    event_repo_edge2 = graph["event:e2"]["repo:200"]
    assert "impact_score" in event_repo_edge2
    assert event_repo_edge2["impact_score"] == 0.6

    # 验证事件→提交边关联强度（事件重要性 × 提交重要性）
    event_commit_edge = graph["event:e2"]["commit:abc123"]
    assert "relevance_score" in event_commit_edge
    assert abs(event_commit_edge["relevance_score"] - (0.6 * 0.55)) < 1e-6


