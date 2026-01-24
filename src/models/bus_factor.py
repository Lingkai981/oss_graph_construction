"""
Bus Factor 分析数据模型

定义 Bus Factor 分析所需的所有数据模型类。
参考社区氛围分析和维护者倦怠分析的结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ContributorContribution:
    """单个贡献者的贡献量信息"""
    
    contributor_id: int
    """贡献者 ID（Actor ID）"""
    
    login: str
    """贡献者登录名"""
    
    total_contribution: float
    """总贡献量（加权后的值）"""
    
    contribution_ratio: float
    """贡献占比（0.0-1.0）"""
    
    # 详细贡献统计（可选）
    commit_count: int = 0
    pr_merged: int = 0
    pr_opened: int = 0
    pr_closed: int = 0
    issue_opened: int = 0
    issue_closed: int = 0
    comment_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "contributor_id": self.contributor_id,
            "login": self.login,
            "total_contribution": round(self.total_contribution, 2),
            "contribution_ratio": round(self.contribution_ratio, 4),
            "commit_count": self.commit_count,
            "pr_merged": self.pr_merged,
            "pr_opened": self.pr_opened,
            "pr_closed": self.pr_closed,
            "issue_opened": self.issue_opened,
            "issue_closed": self.issue_closed,
            "comment_count": self.comment_count,
        }


@dataclass
class MonthlyRiskMetrics:
    """单个月份的风险指标"""
    
    month: str
    """月份，格式 "YYYY-MM"，如 "2023-01" """
    
    repo_name: str
    """项目名称，如 "angular/angular" """
    
    bus_factor: int
    """Bus Factor 值（达到50%贡献所需的最少贡献者数量）"""
    
    total_contribution: float
    """总贡献量"""
    
    contributor_count: int
    """贡献者总数"""
    
    contributors: List[ContributorContribution] = field(default_factory=list)
    """贡献者贡献量列表（按贡献量降序排序）"""
    
    # 图统计信息（可选）
    node_count: int = 0
    """图节点数"""
    
    edge_count: int = 0
    """图边数"""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        # 处理 contributors：如果已经是字典则直接使用，否则转换为字典
        contributors_dict = []
        for c in self.contributors:
            if isinstance(c, dict):
                contributors_dict.append(c)
            else:
                contributors_dict.append(c.to_dict())
        
        return {
            "month": self.month,
            "repo_name": self.repo_name,
            "bus_factor": self.bus_factor,
            "total_contribution": round(self.total_contribution, 2),
            "contributor_count": self.contributor_count,
            "contributors": contributors_dict,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
        }


@dataclass
class TrendAnalysis:
    """趋势分析结果"""
    
    repo_name: str
    """项目名称"""
    
    bus_factor_trend: Dict[str, Any]
    """Bus Factor 趋势"""
    # {
    #     "direction": "上升" | "下降" | "稳定" | "数据不足",
    #     "slope": float,  # 斜率
    #     "change_rate": float,  # 变化率（百分比）
    #     "values": List[float],  # 时间序列值
    # }
    
    months: List[str]
    """月份列表（按时间顺序）"""
    
    bus_factor_values: List[int]
    """Bus Factor 值列表（按时间顺序）"""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "repo_name": self.repo_name,
            "bus_factor_trend": self.bus_factor_trend,
            "months": self.months,
            "bus_factor_values": self.bus_factor_values,
        }


@dataclass
class RiskScore:
    """综合风险评分"""
    
    repo_name: str
    """项目名称"""
    
    total_score: float
    """总分（0-100，分数越高风险越高）"""
    
    current_score: float
    """当前值得分（0-50）"""
    
    trend_score: float
    """趋势得分（0-50）"""
    
    risk_level: str
    """风险等级（"低" | "中" | "高"）"""
    
    current_bus_factor: int
    """当前 Bus Factor 值"""
    
    trend_direction: str
    """趋势方向"""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "repo_name": self.repo_name,
            "total_score": round(self.total_score, 2),
            "current_score": round(self.current_score, 2),
            "trend_score": round(self.trend_score, 2),
            "risk_level": self.risk_level,
            "current_bus_factor": self.current_bus_factor,
            "trend_direction": self.trend_direction,
        }

