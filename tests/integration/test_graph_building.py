"""
图构建集成测试
"""

import pytest
import networkx as nx
from src.services.graph_builder import build_snapshot, build_all_snapshots


def test_integration_build_snapshot():
    """测试集成：构建图快照"""
    data = {
        'date': '2024-01-01',
        'projects': [{'id': 1, 'name': 'test-project'}],
        'contributors': [{'id': 1, 'login': 'user1'}],
        'commits': [{'id': 1, 'sha': 'abc123', 'created_at': '2024-01-01 10:00:00'}],
        'edges': [{'contributor_id': 1, 'commit_sha': 'abc123', 'created_at': '2024-01-01 10:00:00'}]
    }
    graph = build_snapshot(data)
    assert isinstance(graph, nx.DiGraph)
    assert len(graph.nodes()) > 0


def test_integration_build_all_snapshots():
    """测试集成：构建所有快照"""
    all_data = [
        {
            'date': '2024-01-01',
            'projects': [{'id': 1, 'name': 'test'}],
            'contributors': [],
            'commits': [{'id': 1, 'sha': 'abc123', 'created_at': '2024-01-01 10:00:00'}],
            'edges': []
        },
        {
            'date': '2024-01-02',
            'projects': [],
            'contributors': [],
            'commits': [{'id': 2, 'sha': 'def456', 'created_at': '2024-01-02 10:00:00'}],
            'edges': []
        }
    ]
    snapshots = build_all_snapshots(all_data)
    assert len(snapshots) == 2
    # 验证节点累积：第二个快照应该包含第一个快照的节点
    assert len(snapshots[1].nodes()) >= len(snapshots[0].nodes())

