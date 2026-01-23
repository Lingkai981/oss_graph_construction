"""
情感传播模型算法

实现情感传播模型，分析情绪如何在社区中传播。
使用类似PageRank的迭代传播算法，时间复杂度O(V+E) per step。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Optional

import networkx as nx
import numpy as np

from src.utils.logger import get_logger

logger = get_logger()


def analyze_emotion_propagation(
    graph: nx.Graph,
    sentiment_scores: Optional[Dict[str, float]] = None,
    propagation_steps: int = 5,
    damping_factor: float = 0.85,
) -> Dict[str, Any]:
    """
    分析情绪如何在社区中传播
    
    算法思路：
    - 从边的comment_body提取情感分数（正面/负面）
    - 使用类似PageRank的传播模型，情绪沿着边传播
    - 每个step更新节点的情绪状态
    
    时间复杂度：O(V+E) per step
    
    Args:
        graph: actor-discussion图
        sentiment_scores: 预计算的情感分数 {edge_id: sentiment_score}，如果为None则从边属性中提取
        propagation_steps: 传播步数，默认5
        damping_factor: 阻尼系数（0-1），默认0.85
    
    Returns:
        包含每个节点的情绪分数和传播过程的字典
    """
    if graph.number_of_nodes() == 0:
        logger.warning("图为空，返回空的情感传播结果")
        return {
            "final_emotions": {},
            "propagation_history": [],
            "average_emotion": 0.0,
            "propagation_steps": propagation_steps,
            "damping_factor": damping_factor,
        }
    
    # 如果没有提供情感分数，使用空字典（情感分数应该由调用者通过DeepSeek API预先计算）
    if sentiment_scores is None:
        sentiment_scores = {}
    
    # 初始化节点情绪状态
    node_emotions = defaultdict(float)
    
    # 从边的情感分数初始化源节点的情绪
    # 根据图类型处理边：MultiDiGraph支持keys，DiGraph不支持
    if isinstance(graph, nx.MultiDiGraph):
        for u, v, key, data in graph.edges(keys=True, data=True):
            edge_id = f"{u}_{v}_{key}"
            if edge_id in sentiment_scores:
                # 累加源节点的初始情绪（基于其发出的边的情感）
                node_emotions[u] += sentiment_scores[edge_id]
    else:
        # DiGraph类型，没有key参数
        for u, v, data in graph.edges(data=True):
            edge_id = f"{u}_{v}"
            if edge_id in sentiment_scores:
                # 累加源节点的初始情绪（基于其发出的边的情感）
                node_emotions[u] += sentiment_scores[edge_id]
    
    # 归一化初始情绪（避免初始值过大）
    if node_emotions:
        max_initial = max(abs(v) for v in node_emotions.values())
        if max_initial > 0:
            for node in node_emotions:
                node_emotions[node] /= max_initial
    
    # 传播过程
    propagation_history = []
    for step in range(propagation_steps):
        new_emotions = defaultdict(float)
        
        # 遍历所有边，情绪从源节点传播到目标节点
        # 根据图类型处理边：MultiDiGraph支持keys，DiGraph不支持
        if isinstance(graph, nx.MultiDiGraph):
            for u, v, key, data in graph.edges(keys=True, data=True):
                edge_id = f"{u}_{v}_{key}"
                if edge_id in sentiment_scores:
                    # 情绪传播：源节点的情绪 * 边的情感分数 * 阻尼系数
                    propagation = node_emotions[u] * sentiment_scores[edge_id] * damping_factor
                    new_emotions[v] += propagation
        else:
            # DiGraph类型，没有key参数
            for u, v, data in graph.edges(data=True):
                edge_id = f"{u}_{v}"
                if edge_id in sentiment_scores:
                    # 情绪传播：源节点的情绪 * 边的情感分数 * 阻尼系数
                    propagation = node_emotions[u] * sentiment_scores[edge_id] * damping_factor
                    new_emotions[v] += propagation
        
        # 更新节点情绪（保留一部分原有情绪）
        for node in graph.nodes():
            node_emotions[node] = (
                damping_factor * node_emotions[node] + 
                (1 - damping_factor) * new_emotions[node]
            )
        
        # 记录传播历史
        propagation_history.append(dict(node_emotions))
    
    # 计算平均情绪
    if node_emotions:
        average_emotion = np.mean(list(node_emotions.values()))
    else:
        average_emotion = 0.0
    
    return {
        "final_emotions": dict(node_emotions),
        "propagation_history": propagation_history,
        "average_emotion": float(average_emotion),
        "propagation_steps": propagation_steps,
        "damping_factor": damping_factor,
    }



