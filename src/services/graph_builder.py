"""
图构建服务

提供时间快照图构建功能，使用NetworkX创建图结构
"""

from typing import Dict, Any, List, Optional
import networkx as nx
from src.models.node import (
    create_project_node, create_contributor_node, create_commit_node
)
from src.models.edge import create_contribution_edge
from src.utils.logger import get_logger
from src.utils.date_utils import parse_timestamp

logger = get_logger()


def remove_isolated_nodes(graph: nx.DiGraph) -> nx.DiGraph:
    """
    移除孤立节点（没有边的节点）
    
    Args:
        graph: NetworkX有向图对象
    
    Returns:
        移除孤立节点后的图对象
    """
    isolated = list(nx.isolates(graph))
    if isolated:
        graph.remove_nodes_from(isolated)
        logger.info(f"移除了 {len(isolated)} 个孤立节点")
    return graph


def add_nodes(graph: nx.DiGraph, nodes: List[Dict[str, Any]], node_type: str) -> None:
    """
    将节点添加到图中，包含所有节点属性
    
    Args:
        graph: NetworkX有向图对象
        nodes: 节点数据列表
        node_type: 节点类型（project/contributor/commit）
    """
    for node_data in nodes:
        try:
            if node_type == 'project':
                if 'id' not in node_data:
                    logger.warning(f"项目数据缺少id字段: {node_data}，跳过")
                    continue
                # 处理updated_at，过滤无效值
                updated_at_value = node_data.get('updated_at')
                updated_at = None
                if updated_at_value and str(updated_at_value).strip() and str(updated_at_value) != '0':
                    parsed = parse_timestamp(str(updated_at_value))
                    # 只有解析成功且不是1970-01-01才使用
                    if parsed and parsed.year > 1970:
                        updated_at = parsed
                
                node = create_project_node(
                    project_id=node_data['id'],
                    name=node_data.get('name'),
                    created_at=parse_timestamp(str(node_data.get('created_at'))) if node_data.get('created_at') else None,
                    updated_at=updated_at
                )
            elif node_type == 'contributor':
                if 'id' not in node_data:
                    logger.warning(f"贡献者数据缺少id字段: {node_data}，跳过")
                    continue
                node = create_contributor_node(
                    user_id=node_data['id'],
                    login=node_data.get('login'),
                    name=node_data.get('name'),
                    created_at=parse_timestamp(str(node_data.get('created_at'))) if node_data.get('created_at') else None
                )
            elif node_type == 'commit':
                commit_sha = node_data.get('sha') or str(node_data.get('id', ''))
                if not commit_sha:
                    logger.warning(f"提交数据缺少sha或id字段: {node_data}，跳过")
                    continue
                node = create_commit_node(
                    commit_sha=commit_sha,
                    sha=node_data.get('sha'),
                    message=node_data.get('message'),
                    created_at=parse_timestamp(str(node_data.get('created_at'))) if node_data.get('created_at') else None
                )
            else:
                logger.warning(f"未知的节点类型: {node_type}，跳过")
                continue
            
            # 为节点添加统一的label属性，便于可视化
            # 优先使用name，其次使用login，最后使用node_id
            label = None
            if node_type == 'project':
                label = node.attributes.get('name') or node.node_id
            elif node_type == 'contributor':
                label = node.attributes.get('name') or node.attributes.get('login') or node.node_id
            elif node_type == 'commit':
                # 提交节点使用message的前50个字符或sha
                label = (node.attributes.get('message', '')[:50] if node.attributes.get('message') 
                        else node.attributes.get('sha') or node.node_id)
            
            # 添加label属性
            node.attributes['label'] = label
            
            # 添加节点到图（如果节点已存在，更新属性）
            graph.add_node(node.node_id, **node.attributes)
        except Exception as e:
            logger.warning(f"添加节点失败: {node_data}, 错误: {str(e)}，跳过该节点")


def add_edges(graph: nx.DiGraph, edges: List[Dict[str, Any]]) -> None:
    """
    将边添加到图中，包含所有边属性
    
    Args:
        graph: NetworkX有向图对象
        edges: 边数据列表
    """
    for edge_data in edges:
        try:
            contributor_id = edge_data.get('contributor_id')
            commit_sha = edge_data.get('commit_sha') or str(edge_data.get('commit_id', ''))
            created_at = parse_timestamp(str(edge_data.get('created_at'))) if edge_data.get('created_at') else None
            project_id = edge_data.get('project_id')
            
            if not contributor_id or not commit_sha:
                logger.warning(f"边数据缺少必需字段: {edge_data}，跳过")
                continue
            
            edge = create_contribution_edge(
                contributor_id=contributor_id,
                commit_sha=commit_sha,
                created_at=created_at,
                project_id=project_id
            )
            
            # 检查源节点和目标节点是否存在
            if edge.source not in graph:
                logger.warning(f"源节点不存在: {edge.source}，跳过该边")
                continue
            if edge.target not in graph:
                logger.warning(f"目标节点不存在: {edge.target}，跳过该边")
                continue
            
            # 添加边到图
            graph.add_edge(edge.source, edge.target, **edge.attributes)
        except Exception as e:
            logger.warning(f"添加边失败: {edge_data}, 错误: {str(e)}，跳过该边")


def build_snapshot(data: Dict[str, Any], previous_snapshot: Optional[nx.DiGraph] = None) -> nx.DiGraph:
    """
    根据日期数据构建图快照
    
    时间快照式构图逻辑：
    - 节点累积：节点一旦创建就存在于所有后续快照中
    - 边累积：边一旦创建就存在于所有后续快照中
    - 每个快照反映到该日期为止的完整图状态
    
    Args:
        data: 日期数据字典，包含projects、contributors、commits、edges
        previous_snapshot: 前一个快照（用于节点和边的累积）
    
    Returns:
        NetworkX有向图对象
    """
    date = data.get('date', 'unknown')
    
    # 创建新的有向图
    graph = nx.DiGraph()
    graph.graph['date'] = date
    
    # 如果有前一个快照，复制所有节点和边（累积机制）
    if previous_snapshot:
        # 复制所有节点
        for node_id, node_attrs in previous_snapshot.nodes(data=True):
            # 确保累积的节点也有label属性（如果没有的话）
            if 'label' not in node_attrs:
                # 根据节点ID推断label
                if node_id.startswith('project_'):
                    node_attrs['label'] = node_attrs.get('name') or node_id
                elif node_id.startswith('contributor_'):
                    node_attrs['label'] = node_attrs.get('name') or node_attrs.get('login') or node_id
                elif node_id.startswith('commit_'):
                    node_attrs['label'] = node_attrs.get('message', '')[:50] if node_attrs.get('message') else node_attrs.get('sha') or node_id
                else:
                    node_attrs['label'] = node_id
            graph.add_node(node_id, **node_attrs)
        
        # 复制所有边（边也累积）
        for source, target, edge_attrs in previous_snapshot.edges(data=True):
            graph.add_edge(source, target, **edge_attrs)
        
        logger.debug(f"从上一个快照累积了 {len(graph.nodes())} 个节点, {len(graph.edges())} 条边")
    
    # 添加项目节点
    projects = data.get('projects', [])
    add_nodes(graph, projects, 'project')
    
    # 添加贡献者节点
    contributors = data.get('contributors', [])
    add_nodes(graph, contributors, 'contributor')
    
    # 添加提交节点
    commits = data.get('commits', [])
    add_nodes(graph, commits, 'commit')
    
    # 添加贡献关系边（当天的边，会累积到后续快照）
    edges = data.get('edges', [])
    add_edges(graph, edges)
    
    logger.info(f"日期 {date} 快照构建完成: {len(graph.nodes())} 个节点, {len(graph.edges())} 条边")
    return graph


def build_all_snapshots(all_data: List[Dict[str, Any]], remove_isolated: bool = False) -> List[nx.DiGraph]:
    """
    为所有日期构建图快照
    
    Args:
        all_data: 所有日期的数据列表，按时间顺序排序
        remove_isolated: 是否移除孤立节点（没有边的节点）
    
    Returns:
        图快照列表，按时间顺序排序
    """
    snapshots = []
    previous_snapshot = None
    
    for data in all_data:
        date = data.get('date', 'unknown')
        
        # 如果某天没有数据，创建空图（但仍需累积之前的节点和边）
        if not data.get('commits') and not data.get('edges'):
            graph = nx.DiGraph()
            graph.graph['date'] = date
            # 如果有前一个快照，复制所有节点和边（累积机制）
            if previous_snapshot:
                for node_id, node_attrs in previous_snapshot.nodes(data=True):
                    # 确保累积的节点也有label属性（如果没有的话）
                    if 'label' not in node_attrs:
                        # 根据节点ID推断label
                        if node_id.startswith('project_'):
                            node_attrs['label'] = node_attrs.get('name') or node_id
                        elif node_id.startswith('contributor_'):
                            node_attrs['label'] = node_attrs.get('name') or node_attrs.get('login') or node_id
                        elif node_id.startswith('commit_'):
                            node_attrs['label'] = node_attrs.get('message', '')[:50] if node_attrs.get('message') else node_attrs.get('sha') or node_id
                        else:
                            node_attrs['label'] = node_id
                    graph.add_node(node_id, **node_attrs)
                for source, target, edge_attrs in previous_snapshot.edges(data=True):
                    graph.add_edge(source, target, **edge_attrs)
            
            # 如果启用移除孤立节点，则移除
            if remove_isolated:
                remove_isolated_nodes(graph)
            
            snapshots.append(graph)
            logger.info(f"日期 {date} 无数据，创建空图（{len(graph.nodes())} 个节点, {len(graph.edges())} 条边）")
        else:
            snapshot = build_snapshot(data, previous_snapshot)
            
            # 如果启用移除孤立节点，则移除
            if remove_isolated:
                remove_isolated_nodes(snapshot)
            
            snapshots.append(snapshot)
            previous_snapshot = snapshot
    
    logger.info(f"构建完成: {len(snapshots)} 个快照")
    return snapshots

