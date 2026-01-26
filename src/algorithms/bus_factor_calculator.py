"""
Bus Factor 计算算法

实现 Bus Factor 计算和贡献量聚合的核心算法。
"""

from __future__ import annotations

import math
from typing import Dict, List

import networkx as nx
import numpy as np

from src.models.bus_factor import ContributorContribution
from src.utils.logger import get_logger

logger = get_logger()

# 默认权重配置（可在配置文件中自定义）
DEFAULT_WEIGHTS = {
    "commit_count": 1.0,      # 提交次数
    "pr_merged": 3.0,         # 合并的 PR（高价值）
    "pr_opened": 2.0,         # 打开的 PR
    "pr_closed": 1.0,         # 关闭的 PR
    "issue_opened": 1.5,      # 打开的 Issue
    "issue_closed": 2.0,      # 关闭的 Issue
    "is_comment": 0.5,        # 评论（参与度）
}


def is_bot_account(login: str) -> bool:
    """
    判断是否为 Bot 账号
    
    Args:
        login: 用户登录名
    
    Returns:
        如果是 Bot 账号返回 True，否则返回 False
    """
    if not login:
        return False
    login_lower = login.lower()
    return (
        "[bot]" in login_lower or
        login_lower.endswith("-bot") or
        login_lower.endswith("_bot") or
        login_lower.startswith("bot-") or
        login_lower.startswith("bot_")
    )


def calculate_bus_factor(
    contributions: Dict[int, float],
    threshold: float = 0.5,
) -> int:
    """
    计算 Bus Factor（达到阈值所需的最少贡献者数量）
    
    Args:
        contributions: {contributor_id: contribution_value} 贡献量字典
        threshold: 阈值（默认0.5，即50%）
    
    Returns:
        Bus Factor 值（达到阈值所需的最少贡献者数量）
    
    Raises:
        ValueError: 如果 contributions 为空或 threshold 不在 [0, 1] 范围内
    """
    if not contributions:
        return None
    
    if not (0.0 <= threshold <= 1.0):
        raise ValueError(f"阈值必须在 [0, 1] 范围内，当前值: {threshold}")
    
    total = sum(contributions.values())
    
    # 如果总贡献量为0，返回None
    if math.isclose(total, 0.0, abs_tol=1e-9):
        return None
    
    target = total * threshold
    
    # 按贡献量降序排序
    sorted_contributors = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
    
    cumulative = 0.0
    count = 0
    
    for contributor_id, contribution in sorted_contributors:
        cumulative += contribution
        count += 1
        # 使用 math.isclose 处理浮点数精度问题
        if math.isclose(cumulative, target, abs_tol=1e-9) or cumulative >= target:
            return count
    
    # 如果所有贡献者加起来都不够阈值，返回总数
    return count


def calculate_contribution(edge_data: Dict, weights: Dict[str, float] = None) -> float:
    """
    计算单条边的贡献量
    
    Args:
        edge_data: 边的数据字典，包含统计字段
        weights: 权重配置（如果为 None，使用默认权重）
    
    Returns:
        贡献量值
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS
    
    contribution = 0.0
    for field, weight in weights.items():
        value = edge_data.get(field, 0)
        if isinstance(value, (int, float)):
            contribution += value * weight
    
    return contribution


def aggregate_contributions(
    graph: nx.Graph,
    weights: Dict[str, float] = None,
    filter_bots: bool = True,
) -> Dict[int, ContributorContribution]:
    """
    从图中聚合贡献量
    
    Args:
        graph: actor-repo 图（可以是 DiGraph 或 MultiDiGraph）
        weights: 权重配置（如果为 None，使用默认权重）
        filter_bots: 是否过滤 Bot 账号（默认 True）
    
    Returns:
        {contributor_id: ContributorContribution} 贡献量字典
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS
    
    # 聚合每个贡献者的贡献量
    contributor_contributions: Dict[int, Dict] = {}
    
    # 检查图类型：MultiDiGraph 支持 keys=True，DiGraph 不支持
    is_multigraph = isinstance(graph, (nx.MultiGraph, nx.MultiDiGraph))
    graph_type = type(graph).__name__
    logger.debug(f"聚合贡献量: 图类型={graph_type}, 是否为多重图={is_multigraph}")
    
    # 遍历所有边
    if is_multigraph:
        # MultiDiGraph: 使用 keys=True
        for source, target, key, edge_data in graph.edges(keys=True, data=True):
            # 只处理从 actor 到 repo 的边
            if not source.startswith("actor:") or not target.startswith("repo:"):
                continue
            
            # 提取 actor_id
            try:
                actor_id = int(source.split(":")[1])
            except (ValueError, IndexError):
                logger.warning(f"无法解析 actor_id: {source}")
                continue
            
            # 从节点获取登录名（用于 Bot 过滤）
            actor_node = graph.nodes.get(source, {})
            login = actor_node.get("login", f"actor_{actor_id}")
            
            # 过滤 Bot 账号
            if filter_bots and is_bot_account(login):
                continue  # 跳过 Bot 账号，不计算其贡献量
            
            # 计算这条边的贡献量
            edge_contribution = calculate_contribution(edge_data, weights)
            
            # 初始化贡献者记录
            if actor_id not in contributor_contributions:
                contributor_contributions[actor_id] = {
                    "contributor_id": actor_id,
                    "login": login,
                    "total_contribution": 0.0,
                    "commit_count": 0,
                    "pr_merged": 0,
                    "pr_opened": 0,
                    "pr_closed": 0,
                    "issue_opened": 0,
                    "issue_closed": 0,
                    "comment_count": 0,
                }
            
            # 累加贡献量
            contributor_contributions[actor_id]["total_contribution"] += edge_contribution
            
            # 累加详细统计
            contributor_contributions[actor_id]["commit_count"] += edge_data.get("commit_count", 0)
            contributor_contributions[actor_id]["pr_merged"] += edge_data.get("pr_merged", 0)
            contributor_contributions[actor_id]["pr_opened"] += edge_data.get("pr_opened", 0)
            contributor_contributions[actor_id]["pr_closed"] += edge_data.get("pr_closed", 0)
            contributor_contributions[actor_id]["issue_opened"] += edge_data.get("issue_opened", 0)
            contributor_contributions[actor_id]["issue_closed"] += edge_data.get("issue_closed", 0)
            contributor_contributions[actor_id]["comment_count"] += edge_data.get("is_comment", 0)
    else:
        # DiGraph: 不使用 keys=True
        for source, target, edge_data in graph.edges(data=True):
            # 只处理从 actor 到 repo 的边
            if not source.startswith("actor:") or not target.startswith("repo:"):
                continue
            
            # 提取 actor_id
            try:
                actor_id = int(source.split(":")[1])
            except (ValueError, IndexError):
                logger.warning(f"无法解析 actor_id: {source}")
                continue
            
            # 从节点获取登录名（用于 Bot 过滤）
            actor_node = graph.nodes.get(source, {})
            login = actor_node.get("login", f"actor_{actor_id}")
            
            # 过滤 Bot 账号
            if filter_bots and is_bot_account(login):
                continue  # 跳过 Bot 账号，不计算其贡献量
            
            # 计算这条边的贡献量
            edge_contribution = calculate_contribution(edge_data, weights)
            
            # 初始化贡献者记录
            if actor_id not in contributor_contributions:
                contributor_contributions[actor_id] = {
                    "contributor_id": actor_id,
                    "login": login,
                    "total_contribution": 0.0,
                    "commit_count": 0,
                    "pr_merged": 0,
                    "pr_opened": 0,
                    "pr_closed": 0,
                    "issue_opened": 0,
                    "issue_closed": 0,
                    "comment_count": 0,
                }
            
            # 累加贡献量
            contributor_contributions[actor_id]["total_contribution"] += edge_contribution
            
            # 累加详细统计
            contributor_contributions[actor_id]["commit_count"] += edge_data.get("commit_count", 0)
            contributor_contributions[actor_id]["pr_merged"] += edge_data.get("pr_merged", 0)
            contributor_contributions[actor_id]["pr_opened"] += edge_data.get("pr_opened", 0)
            contributor_contributions[actor_id]["pr_closed"] += edge_data.get("pr_closed", 0)
            contributor_contributions[actor_id]["issue_opened"] += edge_data.get("issue_opened", 0)
            contributor_contributions[actor_id]["issue_closed"] += edge_data.get("issue_closed", 0)
            contributor_contributions[actor_id]["comment_count"] += edge_data.get("is_comment", 0)
    
    # 计算总贡献量
    total_contribution = sum(
        data["total_contribution"] for data in contributor_contributions.values()
    )
    logger.debug(f"聚合完成: {len(contributor_contributions)} 个贡献者, 总贡献量={total_contribution:.2f}")
    
    # 创建 ContributorContribution 对象并计算贡献占比
    result: Dict[int, ContributorContribution] = {}
    for actor_id, data in contributor_contributions.items():
        contribution_ratio = (
            data["total_contribution"] / total_contribution
            if not math.isclose(total_contribution, 0.0, abs_tol=1e-9)
            else 0.0
        )
        
        result[actor_id] = ContributorContribution(
            contributor_id=data["contributor_id"],
            login=data["login"],
            total_contribution=data["total_contribution"],
            contribution_ratio=contribution_ratio,
            commit_count=data["commit_count"],
            pr_merged=data["pr_merged"],
            pr_opened=data["pr_opened"],
            pr_closed=data["pr_closed"],
            issue_opened=data["issue_opened"],
            issue_closed=data["issue_closed"],
            comment_count=data["comment_count"],
        )
    
    return result

