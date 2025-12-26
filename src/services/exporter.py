"""
图导出服务

提供图快照导出功能，支持GraphML和JSON格式
"""

from pathlib import Path
from typing import List, Optional
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


def export_all_snapshots(snapshots: List[nx.DiGraph], dates: List[str],
                        output_dir: str = "output/", format: str = "graphml") -> List[str]:
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

