"""
社区氛围分析数据模型

定义社区氛围分析所需的所有数据模型类。
参考维护者倦怠分析的结构，使用时间序列分析。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class MonthlyAtmosphereMetrics:
    """单个月的社区氛围指标"""
    
    month: str
    """月份，格式 "YYYY-MM"，如 "2023-01" """
    
    repo_name: str
    """项目名称，如 "angular/angular" """
    
    # 情感传播指标
    average_emotion: float = 0.0
    """平均情绪值，范围通常在-1到1之间"""
    
    emotion_propagation_steps: int = 5
    """传播步数"""
    
    emotion_damping_factor: float = 0.85
    """阻尼系数"""
    
    # 聚类系数指标
    global_clustering_coefficient: float = 0.0
    """全局聚类系数，范围0到1"""
    
    average_local_clustering: float = 0.0
    """平均局部聚类系数"""
    
    actor_graph_nodes: int = 0
    """actor图节点数"""
    
    actor_graph_edges: int = 0
    """actor图边数"""
    
    # 网络直径指标
    diameter: int = 0
    """网络直径，如果图不连通则为最大连通分量的直径"""
    
    average_path_length: float = 0.0
    """平均路径长度"""
    
    is_connected: bool = False
    """图是否连通"""
    
    num_connected_components: int = 0
    """连通分量数量"""
    
    largest_component_size: int = 0
    """最大连通分量的大小"""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "month": self.month,
            "repo_name": self.repo_name,
            "average_emotion": self.average_emotion,
            "emotion_propagation_steps": self.emotion_propagation_steps,
            "emotion_damping_factor": self.emotion_damping_factor,
            "global_clustering_coefficient": self.global_clustering_coefficient,
            "average_local_clustering": self.average_local_clustering,
            "actor_graph_nodes": self.actor_graph_nodes,
            "actor_graph_edges": self.actor_graph_edges,
            "diameter": self.diameter,
            "average_path_length": self.average_path_length,
            "is_connected": self.is_connected,
            "num_connected_components": self.num_connected_components,
            "largest_component_size": self.largest_component_size,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MonthlyAtmosphereMetrics":
        """从字典构建对象（用于断点续传/增量读取）"""
        return cls(
            month=str(data.get("month") or ""),
            repo_name=str(data.get("repo_name") or ""),
            average_emotion=float(data.get("average_emotion") or 0.0),
            emotion_propagation_steps=int(data.get("emotion_propagation_steps") or 5),
            emotion_damping_factor=float(data.get("emotion_damping_factor") or 0.85),
            global_clustering_coefficient=float(data.get("global_clustering_coefficient") or 0.0),
            average_local_clustering=float(data.get("average_local_clustering") or 0.0),
            actor_graph_nodes=int(data.get("actor_graph_nodes") or 0),
            actor_graph_edges=int(data.get("actor_graph_edges") or 0),
            diameter=int(data.get("diameter") or 0),
            average_path_length=float(data.get("average_path_length") or 0.0),
            is_connected=bool(data.get("is_connected") or False),
            num_connected_components=int(data.get("num_connected_components") or 0),
            largest_component_size=int(data.get("largest_component_size") or 0),
        )