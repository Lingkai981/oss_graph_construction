"""
图导出服务

提供图快照导出功能，支持 GraphML 和 JSON 格式。
同时为时序语义图提供符合 contracts 约定的导出函数。
"""

from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

import networkx as nx
import json
from src.utils.logger import get_logger

logger = get_logger()


def ensure_output_directory(output_dir: str = "output/") -> Path:
    """
    确保输出目录存在
    
    Args:
        output_dir: 输出目录路径
    
    Returns:
        Path对象
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


def generate_filename(date: str, format: str = "graphml") -> str:
    """
    生成包含日期的文件名
    
    Args:
        date: 日期字符串（YYYY-MM-DD格式）
        format: 文件格式（graphml或json）
    
    Returns:
        文件名（如snapshot_2024-01-01.graphml）
    """
    extension = "graphml" if format == "graphml" else "json"
    return f"snapshot_{date}.{extension}"


def export_graphml(graph: nx.DiGraph, output_path: str) -> None:
    """
    导出图为GraphML格式
    
    使用NetworkX的write_graphml()函数导出图
    
    Args:
        graph: NetworkX有向图对象
        output_path: 输出文件路径
    """
    try:
        nx.write_graphml(graph, output_path)
        logger.info(f"GraphML文件已导出: {output_path}")
    except Exception as e:
        logger.error(f"导出GraphML文件失败: {output_path}, 错误: {str(e)}")
        raise


def export_json(graph: nx.DiGraph, output_path: str) -> None:
    """
    导出图为JSON格式
    
    使用NetworkX的node_link_data()函数导出为JSON格式
    
    Args:
        graph: NetworkX有向图对象
        output_path: 输出文件路径
    """
    try:
        # 使用NetworkX的node_link_data生成JSON数据
        data = nx.node_link_data(graph)
        
        # 写入JSON文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"JSON文件已导出: {output_path}")
    except Exception as e:
        logger.error(f"导出JSON文件失败: {output_path}, 错误: {str(e)}")
        raise


def export_snapshot(graph: nx.DiGraph, date: str, output_dir: str = "output/", 
                   format: str = "graphml") -> str:
    """
    导出单个图快照
    
    Args:
        graph: NetworkX有向图对象
        date: 日期字符串（YYYY-MM-DD格式）
        output_dir: 输出目录
        format: 导出格式（graphml或json）
    
    Returns:
        导出文件的路径
    """
    # 确保输出目录存在
    output_path = ensure_output_directory(output_dir)
    
    # 生成文件名
    filename = generate_filename(date, format)
    file_path = output_path / filename
    
    # 根据格式导出
    if format == "graphml":
        export_graphml(graph, str(file_path))
    elif format == "json":
        export_json(graph, str(file_path))
    else:
        raise ValueError(f"不支持的导出格式: {format}")
    
    return str(file_path)


def export_all_snapshots(
    snapshots: List[nx.DiGraph],
    dates: List[str],
    output_dir: str = "output/",
    format: str = "graphml",
) -> List[str]:
    """
    为所有快照生成导出文件
    
    Args:
        snapshots: 图快照列表
        dates: 日期列表（与快照列表对应）
        output_dir: 输出目录
        format: 导出格式（graphml或json）
    
    Returns:
        导出文件路径列表
    """
    if len(snapshots) != len(dates):
        raise ValueError(f"快照数量({len(snapshots)})与日期数量({len(dates)})不匹配")
    
    exported_files = []
    
    for graph, date in zip(snapshots, dates):
        try:
            file_path = export_snapshot(graph, date, output_dir, format)
            exported_files.append(file_path)
        except Exception as e:
            logger.error(f"导出日期 {date} 的快照失败: {str(e)}")
            # 继续处理其他快照
    
    logger.info(f"批量导出完成: {len(exported_files)}/{len(snapshots)} 个文件")
    return exported_files


# ========== 时序语义图专用导出函数（002 特性） ==========


def _split_node_attributes(node_attrs: Dict[str, object]) -> Dict[str, object]:
    """
    将节点属性拆分为 type 与 attributes 两部分。
    """
    node_type = node_attrs.get("node_type")
    attrs = {k: v for k, v in node_attrs.items() if k != "node_type"}
    return {"type": node_type, "attributes": attrs}


def _split_edge_attributes(edge_attrs: Dict[str, object]) -> Dict[str, object]:
    """
    将边属性拆分为 type 与 attributes 两部分。
    """
    edge_type = edge_attrs.get("type")
    attrs = {k: v for k, v in edge_attrs.items() if k != "type"}
    return {"type": edge_type, "attributes": attrs}


def export_temporal_graph_to_json(
    graph: nx.DiGraph, output_path: str, source_file: str
) -> None:
    """
    按 contracts/README.md 约定，将时序语义图导出为 JSON 结构：

    {
      "meta": {...},
      "nodes": [...],
      "edges": [...]
    }
    """
    meta = {
        "source_file": source_file,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
    }

    nodes = []
    for node_id, data in graph.nodes(data=True):
        parts = _split_node_attributes(data)
        nodes.append(
            {
                "id": node_id,
                "type": parts["type"],
                "attributes": parts["attributes"],
            }
        )

    edges = []
    for u, v, data in graph.edges(data=True):
        parts = _split_edge_attributes(data)
        edges.append(
            {
                "id": f"{u}->{v}",
                "type": parts["type"],
                "source": u,
                "target": v,
                "attributes": parts["attributes"],
            }
        )

    payload = {"meta": meta, "nodes": nodes, "edges": edges}

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info(f"时序语义图 JSON 文件已导出: {output_path}")
    except Exception as e:
        logger.error(f"导出时序语义图 JSON 失败: {output_path}, 错误: {str(e)}")
        raise


def export_temporal_graph_to_graphml(graph: nx.DiGraph, output_path: str) -> None:
    """
    将时序语义图导出为 GraphML。

    直接复用 NetworkX 的 write_graphml，节点与边的属性将作为 data 元素输出。
    """
    try:
        nx.write_graphml(graph, output_path)
        logger.info(f"时序语义图 GraphML 文件已导出: {output_path}")
    except Exception as e:
        logger.error(f"导出时序语义图 GraphML 失败: {output_path}, 错误: {str(e)}")
        raise

