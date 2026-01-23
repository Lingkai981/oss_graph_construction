"""
聚类系数算法单元测试
"""

import pytest
import networkx as nx

from src.algorithms.clustering_coefficient import compute_clustering_coefficient


def test_clustering_coefficient_empty_graph():
    """测试空图"""
    graph = nx.MultiDiGraph()
    result = compute_clustering_coefficient(graph)
    
    assert result["global_clustering_coefficient"] == 0.0
    assert result["average_local_clustering"] == 0.0
    assert result["actor_graph_nodes"] == 0


def test_clustering_coefficient_single_actor():
    """测试单actor节点"""
    graph = nx.MultiDiGraph()
    graph.add_node("actor1", node_type="Actor")
    
    result = compute_clustering_coefficient(graph)
    
    assert result["actor_graph_nodes"] == 0  # 没有discussion，无法构建投影图


def test_clustering_coefficient_with_discussion():
    """测试带discussion的图"""
    graph = nx.MultiDiGraph()
    graph.add_node("actor1", node_type="Actor")
    graph.add_node("actor2", node_type="Actor")
    graph.add_node("issue1", node_type="Issue")
    
    # 两个actor都连接到同一个issue
    graph.add_edge("actor1", "issue1", comment_body="Comment 1")
    graph.add_edge("actor2", "issue1", comment_body="Comment 2")
    
    result = compute_clustering_coefficient(graph)
    
    assert result["actor_graph_nodes"] == 2
    assert 0.0 <= result["global_clustering_coefficient"] <= 1.0
    assert 0.0 <= result["average_local_clustering"] <= 1.0


def test_clustering_coefficient_triangle():
    """测试三角形结构（高聚类系数）"""
    graph = nx.MultiDiGraph()
    graph.add_node("actor1", node_type="Actor")
    graph.add_node("actor2", node_type="Actor")
    graph.add_node("actor3", node_type="Actor")
    graph.add_node("issue1", node_type="Issue")
    graph.add_node("issue2", node_type="Issue")
    graph.add_node("issue3", node_type="Issue")
    
    # 构建三角形：每个actor连接到两个issue
    graph.add_edge("actor1", "issue1")
    graph.add_edge("actor1", "issue2")
    graph.add_edge("actor2", "issue2")
    graph.add_edge("actor2", "issue3")
    graph.add_edge("actor3", "issue3")
    graph.add_edge("actor3", "issue1")
    
    result = compute_clustering_coefficient(graph)
    
    assert result["actor_graph_nodes"] == 3
    assert result["actor_graph_edges"] >= 3  # 至少3条边形成三角形

