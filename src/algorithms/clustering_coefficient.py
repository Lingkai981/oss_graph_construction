"""
聚类系数计算算法

计算聚类系数，衡量社区紧密度。
对于 actor-discussion 二部图，需要先构建 actor 之间的投影图，然后计算聚类系数。
对于 actor-actor 协作图，直接在“去重+无向化”的 actor 图上计算。
时间复杂度O(V·d²)，其中d是平均度。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict

import networkx as nx
import numpy as np

from src.utils.logger import get_logger

logger = get_logger()


def compute_clustering_coefficient(
    graph: nx.MultiDiGraph,
) -> Dict[str, Any]:
    """
    计算聚类系数，衡量社区紧密度
    
    对于有向图，计算局部聚类系数：
    - 对于每个节点，计算其邻居之间实际连接的边数 / 可能的最大边数
    
    时间复杂度：O(V·d²)，其中d是平均度
    
    Args:
        graph: actor-discussion图 或 actor-actor图
    
    Returns:
        包含全局聚类系数、局部聚类系数分布的字典
    """
    # 如果图已经是 actor-actor（只含Actor节点），则直接无向化+去重
    print("  正在准备actor图用于聚类系数计算...", flush=True)
    actor_graph = _prepare_actor_graph(graph)
    
    print(f"  投影图构建完成: 节点数={actor_graph.number_of_nodes()}, 边数={actor_graph.number_of_edges()}", flush=True)
    logger.debug(f"投影图构建完成: 节点数={actor_graph.number_of_nodes()}, 边数={actor_graph.number_of_edges()}")
    
    if actor_graph.number_of_nodes() == 0:
        logger.warning("没有actor节点，返回空的聚类系数结果")
        return {
            "global_clustering_coefficient": 0.0,
            "local_clustering_coefficients": {},
            "average_local_clustering": 0.0,
            "actor_graph_nodes": 0,
            "actor_graph_edges": 0,
        }
    
    if actor_graph.number_of_edges() == 0:
        logger.debug("投影图没有边，所有聚类系数为0")
    
    # 计算全局聚类系数（传递性）
    print("  正在计算全局聚类系数...", flush=True)
    global_clustering = nx.transitivity(actor_graph) if actor_graph.number_of_nodes() > 1 else 0.0
    
    # 计算局部聚类系数
    print("  正在计算局部聚类系数...", flush=True)
    local_clustering = nx.clustering(actor_graph)
    
    # 计算平均局部聚类系数
    if local_clustering:
        average_local_clustering = np.mean(list(local_clustering.values()))
    else:
        average_local_clustering = 0.0
    
    print(f"  聚类系数计算完成: global={global_clustering:.3f}, average_local={average_local_clustering:.3f}", flush=True)
    
    return {
        "global_clustering_coefficient": float(global_clustering),
        "local_clustering_coefficients": {str(k): float(v) for k, v in local_clustering.items()},
        "average_local_clustering": float(average_local_clustering),
        "actor_graph_nodes": actor_graph.number_of_nodes(),
        "actor_graph_edges": actor_graph.number_of_edges(),
    }

def _prepare_actor_graph(graph: nx.MultiDiGraph) -> nx.Graph:
    """
    将输入图转换为用于结构指标计算的actor无向图（简单图）。
    - 若输入为 actor-discussion：投影为 actor-actor（共同参与同一discussion）
    - 若输入为 actor-actor：将多重/有向边折叠为无向简单边
    """
    node_types = {data.get("node_type") for _, data in graph.nodes(data=True)}
    # actor-discussion 通常包含 Issue / PullRequest
    if "Issue" in node_types or "PullRequest" in node_types or "Repository" in node_types:
        print("  输入为二部图，正在构建actor投影图...", flush=True)
        return _build_actor_projection_graph(graph)
    print("  输入为actor-actor图，正在无向化并去重...", flush=True)
    return _collapse_to_simple_undirected(graph)

def _collapse_to_simple_undirected(graph: nx.MultiDiGraph) -> nx.Graph:
    """
    将 MultiDiGraph/DiGraph 折叠为无向简单图：
    - 保留节点
    - 忽略边方向
    - 多重边去重（同一对节点只保留一条边）
    - 忽略自环
    """
    g = nx.Graph()
    for n, data in graph.nodes(data=True):
        g.add_node(n, **(data or {}))

    if isinstance(graph, nx.MultiDiGraph):
        edges_iter = graph.edges(keys=True)
        for u, v, _k in edges_iter:
            if u == v:
                continue
            g.add_edge(u, v)
    else:
        for u, v in graph.edges():
            if u == v:
                continue
            g.add_edge(u, v)
    return g


def _build_actor_projection_graph(graph: nx.MultiDiGraph) -> nx.Graph:
    """
    构建actor节点之间的投影图
    
    如果两个actor都连接到同一个discussion，则它们之间有连接。
    
    Args:
        graph: actor-discussion图
    
    Returns:
        actor之间的无向图
    """
    actor_graph = nx.Graph()
    
    # 首先从节点属性中收集所有Actor节点（即使没有边也要包含）
    all_actors = set()
    for node, data in graph.nodes(data=True):
        if data.get('node_type') == 'Actor':
            all_actors.add(node)
    
    # 收集连接到每个discussion的actor节点（用于构建边）
    discussion_to_actors = defaultdict(set)
    
    # 根据图类型处理边：MultiDiGraph支持keys，DiGraph不支持
    if isinstance(graph, nx.MultiDiGraph):
        for u, v, key, data in graph.edges(keys=True, data=True):
            u_type = graph.nodes[u].get('node_type', '')
            v_type = graph.nodes[v].get('node_type', '')
            
            # 检查是否是actor到discussion的边
            if u_type == 'Actor' and (v_type == 'Issue' or v_type == 'PullRequest'):
                discussion_to_actors[v].add(u)
            elif v_type == 'Actor' and (u_type == 'Issue' or u_type == 'PullRequest'):
                discussion_to_actors[u].add(v)
    else:
        for u, v, data in graph.edges(data=True):
            u_type = graph.nodes[u].get('node_type', '')
            v_type = graph.nodes[v].get('node_type', '')
            
            # 检查是否是actor到discussion的边
            if u_type == 'Actor' and (v_type == 'Issue' or v_type == 'PullRequest'):
                discussion_to_actors[v].add(u)
            elif v_type == 'Actor' and (u_type == 'Issue' or u_type == 'PullRequest'):
                discussion_to_actors[u].add(v)
    
    # 先添加所有actor节点（即使没有边，也要确保节点存在）
    for actor in all_actors:
        actor_graph.add_node(actor)
    
    # 构建actor之间的连接
    for discussion, actors in discussion_to_actors.items():
        actors_list = list(actors)
        # 对于每个discussion，将其连接的actor节点两两之间建立边
        for i in range(len(actors_list)):
            for j in range(i + 1, len(actors_list)):
                actor_graph.add_edge(actors_list[i], actors_list[j])
    
    return actor_graph

