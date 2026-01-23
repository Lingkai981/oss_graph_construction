"""
网络直径计算算法

计算网络直径，衡量社区沟通效率。
网络直径 = 所有节点对之间最短路径的最大值。
时间复杂度O(V·E)。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict

import networkx as nx

from src.utils.logger import get_logger

logger = get_logger()


def compute_network_diameter(
    graph: nx.MultiDiGraph,
) -> Dict[str, Any]:
    """
    计算网络直径，衡量社区沟通效率
    
    网络直径 = 所有节点对之间最短路径的最大值
    
    时间复杂度：O(V·E)
    
    Args:
        graph: actor-discussion图 或 actor-actor图
    
    Returns:
        包含直径、平均路径长度等指标的字典
    """
    # 准备actor无向图：actor-discussion -> 投影；actor-actor -> 无向化+去重
    print("  正在准备actor图用于网络直径计算...", flush=True)
    actor_graph = _prepare_actor_graph(graph)
    
    print(f"  投影图构建完成: 节点数={actor_graph.number_of_nodes()}, 边数={actor_graph.number_of_edges()}", flush=True)
    logger.debug(f"投影图构建完成: 节点数={actor_graph.number_of_nodes()}, 边数={actor_graph.number_of_edges()}")
    
    if actor_graph.number_of_nodes() == 0:
        logger.warning("没有actor节点，返回空的网络直径结果")
        return {
            "diameter": 0,
            "average_path_length": 0.0,
            "is_connected": False,
            "num_connected_components": 0,
            "largest_component_size": 0,
            "actor_graph_nodes": 0,
            "actor_graph_edges": 0,
        }
    
    if actor_graph.number_of_edges() == 0:
        logger.debug("投影图没有边，网络直径为0，每个节点都是独立的连通分量")
    
    # 检查连通性
    print("  正在检查图的连通性...", flush=True)
    is_connected = nx.is_connected(actor_graph)
    num_components = nx.number_connected_components(actor_graph)
    
    if is_connected:
        print("  图是连通的，正在计算直径和平均路径长度...", flush=True)
        # 图连通，直接计算直径和平均路径长度
        if actor_graph.number_of_nodes() > 1:
            diameter = nx.diameter(actor_graph)
            avg_path_length = nx.average_shortest_path_length(actor_graph)
            largest_component_size = actor_graph.number_of_nodes()
        else:
            diameter = 0
            avg_path_length = 0.0
            largest_component_size = 1
    else:
        print(f"  图不连通（{num_components}个连通分量），正在计算最大连通分量的直径...", flush=True)
        # 图不连通，计算最大连通分量的直径
        connected_components = list(nx.connected_components(actor_graph))
        largest_cc = max(connected_components, key=len)
        subgraph = actor_graph.subgraph(largest_cc)
        
        if len(largest_cc) > 1:
            diameter = nx.diameter(subgraph)
            avg_path_length = nx.average_shortest_path_length(subgraph)
        else:
            diameter = 0
            avg_path_length = 0.0
        
        largest_component_size = len(largest_cc)
    
    print(f"  网络直径计算完成: diameter={diameter}, avg_path_length={avg_path_length:.3f}, connected={is_connected}", flush=True)
    
    return {
        "diameter": diameter,
        "average_path_length": float(avg_path_length),
        "is_connected": is_connected,
        "num_connected_components": num_components,
        "largest_component_size": largest_component_size,
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
    if "Issue" in node_types or "PullRequest" in node_types or "Repository" in node_types:
        print("  输入为二部图，正在构建actor投影图...", flush=True)
        return _build_actor_projection_graph(graph)
    print("  输入为actor-actor图，正在无向化并去重...", flush=True)
    return _collapse_to_simple_undirected(graph)

def _collapse_to_simple_undirected(graph: nx.MultiDiGraph) -> nx.Graph:
    g = nx.Graph()
    for n, data in graph.nodes(data=True):
        g.add_node(n, **(data or {}))

    if isinstance(graph, nx.MultiDiGraph):
        for u, v, _k in graph.edges(keys=True):
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

