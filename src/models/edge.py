"""
边类型定义

定义Edge基类和边类型常量
"""

from typing import Dict, Any, Optional
from datetime import datetime


# 边类型常量
CONTRIBUTES = "contributes"


class Edge:
    """
    边基类
    
    表示图中节点之间的关系
    """
    
    def __init__(self, source: str, target: str, edge_type: str, **attributes):
        """
        初始化边
        
        Args:
            source: 源节点ID
            target: 目标节点ID
            edge_type: 边类型（contributes）
            **attributes: 边属性
        """
        self.source = source
        self.target = target
        self.edge_type = edge_type
        self.attributes = attributes
    
    def to_dict(self) -> Dict[str, Any]:
        """
        将边转换为字典
        
        Returns:
            边字典
        """
        result = {
            'source': self.source,
            'target': self.target,
            'edge_type': self.edge_type
        }
        result.update(self.attributes)
        return result
    
    def __repr__(self) -> str:
        return f"Edge(source={self.source}, target={self.target}, type={self.edge_type})"


def create_contribution_edge(contributor_id: int, commit_sha: str,
                            created_at: Optional[datetime] = None,
                            project_id: Optional[int] = None) -> Edge:
    """
    创建贡献关系边
    
    连接贡献者节点和提交节点，表示某个贡献者在某个时间点进行了代码提交
    
    Args:
        contributor_id: 贡献者用户ID
        commit_sha: 提交SHA
        created_at: 关系创建时间（提交时间，必需）
        project_id: 关联的项目ID（可选）
    
    Returns:
        贡献关系边对象
    """
    source = f"contributor_{contributor_id}"
    target = f"commit_{commit_sha}"
    attributes = {}
    
    if created_at:
        attributes['created_at'] = created_at.isoformat() if isinstance(created_at, datetime) else created_at
    if project_id:
        attributes['project_id'] = project_id
    
    return Edge(source, target, CONTRIBUTES, **attributes)

