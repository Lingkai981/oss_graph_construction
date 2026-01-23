"""
情感传播算法单元测试
"""

import pytest
import networkx as nx

from src.algorithms.emotion_propagation import analyze_emotion_propagation


def test_emotion_propagation_empty_graph():
    """测试空图"""
    graph = nx.MultiDiGraph()
    result = analyze_emotion_propagation(graph)
    
    assert result["final_emotions"] == {}
    assert result["average_emotion"] == 0.0
    assert len(result["propagation_history"]) == 0


def test_emotion_propagation_single_node():
    """测试单节点图"""
    graph = nx.MultiDiGraph()
    graph.add_node("actor1", node_type="Actor")
    
    result = analyze_emotion_propagation(graph)
    
    assert "actor1" in result["final_emotions"]
    assert result["average_emotion"] == 0.0


def test_emotion_propagation_with_sentiment():
    """测试带情感分数的传播"""
    graph = nx.MultiDiGraph()
    graph.add_node("actor1", node_type="Actor")
    graph.add_node("issue1", node_type="Issue")
    graph.add_edge("actor1", "issue1", comment_body="Great work! Thanks!")
    
    result = analyze_emotion_propagation(graph)
    
    assert len(result["final_emotions"]) > 0
    assert result["propagation_steps"] == 5
    assert result["damping_factor"] == 0.85


def test_emotion_propagation_custom_params():
    """测试自定义参数"""
    graph = nx.MultiDiGraph()
    graph.add_node("actor1", node_type="Actor")
    graph.add_node("issue1", node_type="Issue")
    graph.add_edge("actor1", "issue1", comment_body="Good job")
    
    result = analyze_emotion_propagation(
        graph,
        propagation_steps=3,
        damping_factor=0.9,
    )
    
    assert result["propagation_steps"] == 3
    assert result["damping_factor"] == 0.9
    assert len(result["propagation_history"]) == 3

