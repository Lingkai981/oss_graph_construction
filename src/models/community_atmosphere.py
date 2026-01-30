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
    
    # # 情感传播指标
    # average_emotion: float = 0.0
    # """平均情绪值，范围通常在-1到1之间"""
    
    # emotion_propagation_steps: int = 5
    # """传播步数"""
    
    # emotion_damping_factor: float = 0.85
    # """阻尼系数"""
    
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
    
    # 毒性指标（ToxiCR）
    # 来源：预计算的 toxicity.json 缓存文件，按仓库+月份聚合
    toxicity_mean: float = 0.0
    """平均毒性分数，范围 [0, 1]"""
    
    toxicity_p95: float = 0.0
    """毒性分数的95分位数，用于识别极端毒性行为"""
    
    toxic_rate_0_5: float = 0.0
    """毒性概率 >= 0.5 的评论占比"""
    
    toxic_comment_count_0_5: int = 0
    """毒性概率 >= 0.5 的评论数量"""
    
    comment_analyzed_count: int = 0
    """被分析的评论总数"""
    
    # ========================================
    # CHAOSS 指标（从 GraphML 提取）
    # 参考 CHAOSS 社区健康指标体系
    # https://chaoss.community/kb/metric-change-request-closure-ratio/
    # https://chaoss.community/kb/metric-time-to-first-response/
    # ========================================
    
    # 变更请求关闭率（Change Request Closure Ratio）
    # 定义：一段时间内关闭的变更请求（PR/Issue）数量与新打开的变更请求数量之比
    # 计算公式：closed_change_requests / opened_change_requests
    # 意义：衡量社区处理贡献的能力，> 1 表示消化能力强，< 1 表示积压
    change_request_closure_ratio: float = 0.0
    """变更请求关闭率，closed / opened，> 1 表示消化能力强"""
    
    opened_prs: int = 0
    """当月打开的 PR 数量"""
    
    closed_prs: int = 0
    """当月关闭（合并或拒绝）的 PR 数量"""
    
    opened_issues: int = 0
    """当月打开的 Issue 数量"""
    
    closed_issues: int = 0
    """当月关闭的 Issue 数量"""
    
    # 首次响应时间（Time to First Response）
    # 定义：从 Issue/PR 创建到第一条评论/Review 的时间间隔
    # 意义：反映社区活跃度和响应速度，时间越短表示社区越活跃
    time_to_first_response_median: float = 0.0
    """首次响应时间中位数（小时），反映典型响应速度"""
    
    time_to_first_response_mean: float = 0.0
    """首次响应时间均值（小时）"""
    
    time_to_first_response_p95: float = 0.0
    """首次响应时间95分位数（小时），反映最慢响应情况"""
    
    items_with_response: int = 0
    """有响应的 Issue/PR 数量"""
    
    items_without_response: int = 0
    """无响应的 Issue/PR 数量"""
    
    # ========================================
    # LLM 评分（由 DeepSeek 大模型生成）
    # ========================================
    
    llm_score: int = 0
    """综合评分，范围 0-100"""
    
    llm_toxicity_score: int = 0
    """毒性评分，范围 0-40"""
    
    llm_response_score: int = 0
    """响应效率评分，范围 0-60"""
    
    llm_toxicity_reason: str = ""
    """毒性评分理由"""
    
    llm_response_reason: str = ""
    """响应效率评分理由"""
    
    llm_overall_reason: str = ""
    """综合评价"""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于 JSON 序列化和结果保存"""
        return {
            "month": self.month,
            "repo_name": self.repo_name,
            # # 情感指标（已弃用，保留兼容性）
            # "average_emotion": self.average_emotion,
            # "emotion_propagation_steps": self.emotion_propagation_steps,
            # "emotion_damping_factor": self.emotion_damping_factor,
            # 网络结构指标
            "global_clustering_coefficient": self.global_clustering_coefficient,
            "average_local_clustering": self.average_local_clustering,
            "actor_graph_nodes": self.actor_graph_nodes,
            "actor_graph_edges": self.actor_graph_edges,
            "diameter": self.diameter,
            "average_path_length": self.average_path_length,
            "is_connected": self.is_connected,
            "num_connected_components": self.num_connected_components,
            "largest_component_size": self.largest_component_size,
            # 毒性指标（ToxiCR）
            "toxicity_mean": self.toxicity_mean,
            "toxicity_p95": self.toxicity_p95,
            "toxic_rate_0_5": self.toxic_rate_0_5,
            "toxic_comment_count_0_5": self.toxic_comment_count_0_5,
            "comment_analyzed_count": self.comment_analyzed_count,
            # CHAOSS 指标 - 变更请求关闭率
            "change_request_closure_ratio": self.change_request_closure_ratio,
            "opened_prs": self.opened_prs,
            "closed_prs": self.closed_prs,
            "opened_issues": self.opened_issues,
            "closed_issues": self.closed_issues,
            # CHAOSS 指标 - 首次响应时间
            "time_to_first_response_median": self.time_to_first_response_median,
            "time_to_first_response_mean": self.time_to_first_response_mean,
            "time_to_first_response_p95": self.time_to_first_response_p95,
            "items_with_response": self.items_with_response,
            "items_without_response": self.items_without_response,
            # LLM 评分
            "llm_score": self.llm_score,
            "llm_toxicity_score": self.llm_toxicity_score,
            "llm_response_score": self.llm_response_score,
            "llm_toxicity_reason": self.llm_toxicity_reason,
            "llm_response_reason": self.llm_response_reason,
            "llm_overall_reason": self.llm_overall_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MonthlyAtmosphereMetrics":
        """
        从字典构建对象（用于断点续传/增量读取）
        
        Args:
            data: 包含指标数据的字典
            
        Returns:
            MonthlyAtmosphereMetrics 对象
        """
        return cls(
            month=str(data.get("month") or ""),
            repo_name=str(data.get("repo_name") or ""),
            # # 情感指标（已弃用，保留兼容性）
            # average_emotion=float(data.get("average_emotion") or 0.0),
            # emotion_propagation_steps=int(data.get("emotion_propagation_steps") or 5),
            # emotion_damping_factor=float(data.get("emotion_damping_factor") or 0.85),
            # 网络结构指标
            global_clustering_coefficient=float(data.get("global_clustering_coefficient") or 0.0),
            average_local_clustering=float(data.get("average_local_clustering") or 0.0),
            actor_graph_nodes=int(data.get("actor_graph_nodes") or 0),
            actor_graph_edges=int(data.get("actor_graph_edges") or 0),
            diameter=int(data.get("diameter") or 0),
            average_path_length=float(data.get("average_path_length") or 0.0),
            is_connected=bool(data.get("is_connected") or False),
            num_connected_components=int(data.get("num_connected_components") or 0),
            largest_component_size=int(data.get("largest_component_size") or 0),
            # 毒性指标（ToxiCR）
            toxicity_mean=float(data.get("toxicity_mean") or 0.0),
            toxicity_p95=float(data.get("toxicity_p95") or 0.0),
            toxic_rate_0_5=float(data.get("toxic_rate_0_5") or 0.0),
            toxic_comment_count_0_5=int(data.get("toxic_comment_count_0_5") or 0),
            comment_analyzed_count=int(data.get("comment_analyzed_count") or 0),
            # CHAOSS 指标 - 变更请求关闭率
            change_request_closure_ratio=float(data.get("change_request_closure_ratio") or 0.0),
            opened_prs=int(data.get("opened_prs") or 0),
            closed_prs=int(data.get("closed_prs") or 0),
            opened_issues=int(data.get("opened_issues") or 0),
            closed_issues=int(data.get("closed_issues") or 0),
            # CHAOSS 指标 - 首次响应时间
            time_to_first_response_median=float(data.get("time_to_first_response_median") or 0.0),
            time_to_first_response_mean=float(data.get("time_to_first_response_mean") or 0.0),
            time_to_first_response_p95=float(data.get("time_to_first_response_p95") or 0.0),
            items_with_response=int(data.get("items_with_response") or 0),
            items_without_response=int(data.get("items_without_response") or 0),
            # LLM 评分
            llm_score=int(data.get("llm_score") or 0),
            llm_toxicity_score=int(data.get("llm_toxicity_score") or 0),
            llm_response_score=int(data.get("llm_response_score") or 0),
            llm_toxicity_reason=str(data.get("llm_toxicity_reason") or ""),
            llm_response_reason=str(data.get("llm_response_reason") or ""),
            llm_overall_reason=str(data.get("llm_overall_reason") or ""),
        )