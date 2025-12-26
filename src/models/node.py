"""
节点类型定义

定义Node基类和节点类型常量
"""

from typing import Dict, Any, Optional
from datetime import datetime


# 节点类型常量
PROJECT = "project"
CONTRIBUTOR = "contributor"
COMMIT = "commit"


class Node:
    """
    节点基类
    
    表示图中的实体节点
    """
    
    def __init__(self, node_id: str, node_type: str, **attributes):
        """
        初始化节点
        
        Args:
            node_id: 节点唯一标识符
            node_type: 节点类型（project/contributor/commit）
            **attributes: 节点属性
        """
        self.node_id = node_id
        self.node_type = node_type
        self.attributes = attributes
    
    def to_dict(self) -> Dict[str, Any]:
        """
        将节点转换为字典
        
        Returns:
            节点字典
        """
        result = {
            'node_id': self.node_id,
            'node_type': self.node_type
        }
        result.update(self.attributes)
        return result
    
    def __repr__(self) -> str:
        return f"Node(id={self.node_id}, type={self.node_type})"


def create_project_node(project_id: int, name: Optional[str] = None,
                       created_at: Optional[datetime] = None,
                       updated_at: Optional[datetime] = None) -> Node:
    """
    创建项目节点
    
    Args:
        project_id: 项目ID
        name: 项目名称
        created_at: 创建时间
        updated_at: 更新时间
    
    Returns:
        项目节点对象
    """
    node_id = f"project_{project_id}"
    attributes = {}
    
    if name:
        attributes['name'] = name
    if created_at:
        attributes['created_at'] = created_at.isoformat() if isinstance(created_at, datetime) else created_at
    if updated_at:
        attributes['updated_at'] = updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at
    
    return Node(node_id, PROJECT, **attributes)


def create_contributor_node(user_id: int, login: Optional[str] = None,
                           name: Optional[str] = None,
                           created_at: Optional[datetime] = None) -> Node:
    """
    创建贡献者节点
    
    Args:
        user_id: 用户ID
        login: 登录名
        name: 显示名称
        created_at: 账户创建时间
    
    Returns:
        贡献者节点对象
    """
    node_id = f"contributor_{user_id}"
    attributes = {}
    
    if login:
        attributes['login'] = login
    if name:
        attributes['name'] = name
    if created_at:
        attributes['created_at'] = created_at.isoformat() if isinstance(created_at, datetime) else created_at
    
    return Node(node_id, CONTRIBUTOR, **attributes)


def create_commit_node(commit_sha: str, sha: Optional[str] = None,
                       message: Optional[str] = None,
                       created_at: Optional[datetime] = None) -> Node:
    """
    创建提交节点
    
    Args:
        commit_sha: 提交SHA（用于节点ID）
        sha: 提交SHA哈希值（用于属性）
        message: 提交消息（截断到前200字符）
        created_at: 提交时间（必需，用于时间快照）
    
    Returns:
        提交节点对象
    """
    node_id = f"commit_{commit_sha}"
    attributes = {}
    
    if sha:
        attributes['sha'] = sha
    if message:
        # 截断消息到前200字符
        attributes['message'] = message[:200] if len(message) > 200 else message
    if created_at:
        attributes['created_at'] = created_at.isoformat() if isinstance(created_at, datetime) else created_at
    
    return Node(node_id, COMMIT, **attributes)

