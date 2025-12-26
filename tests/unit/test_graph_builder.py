"""
图构建服务单元测试
"""

import pytest
import networkx as nx
from src.services.graph_builder import build_snapshot, add_nodes, add_edges


def test_build_snapshot_empty():
    """测试构建空快照"""
    data = {
        'date': '2024-01-01',
        'projects': [],
        'contributors': [],
        'commits': [],
        'edges': []
    }
    graph = build_snapshot(data)
    assert isinstance(graph, nx.DiGraph)
    assert graph.graph['date'] == '2024-01-01'
    assert len(graph.nodes()) == 0
    assert len(graph.edges()) == 0


def test_build_snapshot_with_data():
    """测试构建包含数据的快照"""
    data = {
        'date': '2024-01-01',
        'projects': [{'id': 1, 'name': 'test'}],
        'contributors': [{'id': 1, 'login': 'user1'}],
        'commits': [{'id': 1, 'sha': 'abc123', 'created_at': '2024-01-01 10:00:00'}],
        'edges': [{'contributor_id': 1, 'commit_sha': 'abc123', 'created_at': '2024-01-01 10:00:00'}]
    }
    graph = build_snapshot(data)
    assert isinstance(graph, nx.DiGraph)
    assert len(graph.nodes()) > 0


def test_add_nodes():
    """测试添加节点"""
    graph = nx.DiGraph()
    nodes = [{'id': 1, 'name': 'test'}]
    add_nodes(graph, nodes, 'project')
    assert len(graph.nodes()) > 0

