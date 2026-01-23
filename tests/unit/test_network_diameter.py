"""
网络直径算法单元测试
"""

import pytest
import networkx as nx

from src.algorithms.network_diameter import compute_network_diameter


def test_network_diameter_empty_graph():
    """测试空图"""
    graph = nx.MultiDiGraph()
    result = compute_network_diameter(graph)
    
    assert result["diameter"] == 0
    assert result["average_path_length"] == 0.0
    assert result["is_connected"] is False
    assert result["num_connected_components"] == 0


def test_network_diameter_single_node():
    """测试单节点图"""
    graph = nx.MultiDiGraph()
    graph.add_node("actor1", node_type="Actor")
    
    result = compute_network_diameter(graph)
    
    assert result["diameter"] == 0
    assert result["is_connected"] is False


def test_network_diameter_connected():
    """测试连通图"""
    graph = nx.MultiDiGraph()
    graph.add_node("actor1", node_type="Actor")
    graph.add_node("actor2", node_type="Actor")
    graph.add_node("issue1", node_type="Issue")
    
    # 两个actor都连接到同一个issue，形成连通
    graph.add_edge("actor1", "issue1")
    graph.add_edge("actor2", "issue1")
    
    result = compute_network_diameter(graph)
    
    assert result["actor_graph_nodes"] == 2
    assert result["diameter"] >= 0
    assert result["average_path_length"] >= 0.0


def test_network_diameter_disconnected():
    """测试非连通图"""
    graph = nx.MultiDiGraph()
    graph.add_node("actor1", node_type="Actor")
    graph.add_node("actor2", node_type="Actor")
    graph.add_node("issue1", node_type="Issue")
    graph.add_node("issue2", node_type="Issue")
    
    # 两个独立的连通分量
    graph.add_edge("actor1", "issue1")
    graph.add_edge("actor2", "issue2")
    
    result = compute_network_diameter(graph)
    
    assert result["num_connected_components"] == 2
    assert result["is_connected"] is False
    assert result["largest_component_size"] == 1  # 每个分量1个actor节点（投影图只包含actor节点）

