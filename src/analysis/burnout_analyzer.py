"""
维护者倦怠分析器

分析指标：
1. 度中心性变化：核心维护者的活跃度是否下降
2. 响应时间变化：Issue/PR 响应是否变慢
3. 活跃度变化：事件数量是否下降
4. 核心成员流失：top-k 成员是否仍然活跃

输出：
- 每个项目的月度指标时间序列
- 倦怠风险评分
- 预警列表
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from src.utils.logger import get_logger

logger = get_logger()

# ==================== 边权重配置 ====================

# 默认权重配置（可在配置文件中自定义）
# 权重反映不同类型贡献的价值，用于核心成员识别中的加权度数计算
#
# 权重设计原则：
# 1. PR_MERGE (3.0): 最高权重，合并 PR 是核心维护者的关键职责
# 2. PR_REVIEW (1.5): 中等权重，代码审查体现技术贡献和协作
# 3. ISSUE_INTERACTION (0.5): 较低权重，Issue 评论主要是参与讨论
# 4. ISSUE_CO_PARTICIPANT (0.5): 较低权重，共同参与体现社区参与度
#
# 权重合理性评估：
# - PR_MERGE 从 5.0 降至 3.0 是合理的：
#   * 3.0 仍然是最高权重，体现其重要性
#   * 避免过度依赖单一指标（PR 合并）
#   * 与其他权重（1.5, 0.5）的比例更均衡
# - 权重比例：3.0 : 1.5 : 0.5 = 6 : 3 : 1，体现了清晰的贡献价值层次
EDGE_WEIGHTS = {
    # Actor-Actor 图边类型权重
    "PR_MERGE": 3.0,              # 合并的 PR（高价值贡献）
    "PR_REVIEW": 1.5,             # PR 代码审查（中等价值）
    "ISSUE_INTERACTION": 0.5,     # Issue 评论（参与度）
    "ISSUE_CO_PARTICIPANT": 0.5,  # 共同参与 Issue（参与度）
    
    # 默认权重（如果边类型未在配置中）
    "default": 1.0,
}


@dataclass
class MonthlyMetrics:
    """单个月的指标"""
    month: str
    repo_name: str
    
    # 基础网络指标
    node_count: int = 0
    edge_count: int = 0
    density: float = 0.0
    
    # 活跃度指标
    total_events: int = 0
    unique_actors: int = 0
    
    # 核心成员指标（动态计算，贡献了 80% 交互的人）
    core_actors: List[Tuple[str, float]] = field(default_factory=list)  # [(login, degree)]
    core_actor_ids: List[int] = field(default_factory=list)
    core_actor_count: int = 0  # 核心成员数量
    core_contribution_ratio: float = 0.8  # 核心成员贡献占比阈值
    
    # 兼容旧代码
    top_actors: List[Tuple[str, float]] = field(default_factory=list)
    top_actor_ids: List[int] = field(default_factory=list)
    
    # 度中心性分布
    degree_mean: float = 0.0
    degree_std: float = 0.0
    degree_max: float = 0.0
    
    # 边类型分布
    edge_type_counts: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "month": self.month,
            "repo_name": self.repo_name,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "density": self.density,
            "total_events": self.total_events,
            "unique_actors": self.unique_actors,
            "core_actors": self.core_actors,
            "core_actor_count": self.core_actor_count,
            "degree_mean": self.degree_mean,
            "degree_std": self.degree_std,
            "degree_max": self.degree_max,
            "edge_type_counts": self.edge_type_counts,
        }


@dataclass
class BurnoutAlert:
    """倦怠预警"""
    repo_name: str
    month: str
    alert_type: str
    severity: str  # low, medium, high
    description: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_name": self.repo_name,
            "month": self.month,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "description": self.description,
            "metrics": self.metrics,
        }


class BurnoutAnalyzer:
    """维护者倦怠分析器"""
    
    def __init__(
        self,
        graphs_dir: str = "output/monthly-graphs/",
        output_dir: str = "output/burnout-analysis/",
    ):
        self.graphs_dir = Path(graphs_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 存储分析结果
        self.repo_metrics: Dict[str, List[MonthlyMetrics]] = defaultdict(list)
        self.alerts: List[BurnoutAlert] = []
    
    def load_graph(self, graph_path: str) -> Optional[nx.MultiDiGraph]:
        """加载图"""
        try:
            graph = nx.read_graphml(graph_path)
            # 确保返回 MultiDiGraph
            if isinstance(graph, nx.MultiDiGraph):
                return graph
            elif isinstance(graph, nx.DiGraph):
                # 转换为 MultiDiGraph
                multi_graph = nx.MultiDiGraph()
                multi_graph.add_nodes_from(graph.nodes(data=True))
                multi_graph.add_edges_from(graph.edges(data=True))
                multi_graph.graph.update(graph.graph)
                return multi_graph
            elif isinstance(graph, (nx.Graph, nx.MultiGraph)):
                # 如果是无向图，先转为有向图再转为 MultiDiGraph
                di_graph = graph.to_directed()
                multi_graph = nx.MultiDiGraph()
                multi_graph.add_nodes_from(di_graph.nodes(data=True))
                multi_graph.add_edges_from(di_graph.edges(data=True))
                multi_graph.graph.update(di_graph.graph)
                return multi_graph
            else:
                logger.warning(f"未知的图类型: {type(graph)}, 路径: {graph_path}")
                return None
        except Exception as e:
            logger.warning(f"加载图失败: {graph_path}, 错误: {e}")
            return None
    
    def compute_monthly_metrics(
        self,
        graph: nx.MultiDiGraph,
        repo_name: str,
        month: str,
    ) -> MonthlyMetrics:
        """计算单个月的指标"""
        metrics = MonthlyMetrics(month=month, repo_name=repo_name)
        
        # 基础指标
        metrics.node_count = graph.number_of_nodes()
        metrics.edge_count = graph.number_of_edges()
        
        if metrics.node_count > 1:
            max_edges = metrics.node_count * (metrics.node_count - 1)
            metrics.density = metrics.edge_count / max_edges if max_edges > 0 else 0
        
        # 从图元数据获取
        metrics.total_events = graph.graph.get("total_events", 0)
        metrics.unique_actors = graph.graph.get("actor_count", metrics.node_count)
        
        # 计算度中心性
        if metrics.node_count > 0:
            # 使用总度数（入度+出度）
            degrees = dict(graph.degree())
            degree_values = list(degrees.values())
            
            if degree_values:
                metrics.degree_mean = sum(degree_values) / len(degree_values)
                metrics.degree_max = max(degree_values)
                
                if len(degree_values) > 1:
                    variance = sum((d - metrics.degree_mean) ** 2 for d in degree_values) / len(degree_values)
                    metrics.degree_std = math.sqrt(variance)
                
                # ========== 智能核心成员识别（多信号融合 + 边权重）==========
                total_actors = len(degrees)
                
                # 1. 计算加权度数（考虑边类型权重）
                weighted_degrees = {}
                is_multigraph = isinstance(graph, (nx.MultiGraph, nx.MultiDiGraph))
                
                for node_id in graph.nodes():
                    weighted_degree = 0.0
                    # 遍历节点的所有出边
                    if is_multigraph:
                        for _, _, key, data in graph.out_edges(node_id, keys=True, data=True):
                            edge_type = data.get("edge_type", "default")
                            weight = EDGE_WEIGHTS.get(edge_type, EDGE_WEIGHTS["default"])
                            weighted_degree += weight
                    else:
                        for _, _, data in graph.out_edges(node_id, data=True):
                            edge_type = data.get("edge_type", "default")
                            weight = EDGE_WEIGHTS.get(edge_type, EDGE_WEIGHTS["default"])
                            weighted_degree += weight
                    # 遍历节点的所有入边
                    if is_multigraph:
                        for _, _, key, data in graph.in_edges(node_id, keys=True, data=True):
                            edge_type = data.get("edge_type", "default")
                            weight = EDGE_WEIGHTS.get(edge_type, EDGE_WEIGHTS["default"])
                            weighted_degree += weight
                    else:
                        for _, _, data in graph.in_edges(node_id, data=True):
                            edge_type = data.get("edge_type", "default")
                            weight = EDGE_WEIGHTS.get(edge_type, EDGE_WEIGHTS["default"])
                            weighted_degree += weight
                    weighted_degrees[node_id] = weighted_degree
                
                weighted_degree_values = list(weighted_degrees.values())
                total_weighted_degree = sum(weighted_degree_values)
                max_weighted_degree = max(weighted_degree_values) if weighted_degree_values else 1
                
                # 2. 计算 k-core 分解（网络结构核心）
                try:
                    # 转换为无向图进行 k-core 分解
                    undirected = graph.to_undirected()
                    core_numbers = nx.core_number(undirected)
                    max_k = max(core_numbers.values()) if core_numbers else 0
                except:
                    core_numbers = {n: 1 for n in graph.nodes()}
                    max_k = 1
                
                # 3. 计算综合得分：加权贡献量（50%）+ 网络位置（50%）
                actor_scores = {}
                for node_id in graph.nodes():
                    weighted_degree = weighted_degrees.get(node_id, 0.0)
                    raw_degree = degrees.get(node_id, 0)  # 保留原始度数为兼容性
                    kcore = core_numbers.get(node_id, 0)
                    
                    # 归一化
                    weighted_degree_norm = weighted_degree / max(max_weighted_degree, 1)
                    kcore_norm = kcore / max(max_k, 1)
                    
                    # 综合得分（使用加权度数）
                    score = 0.5 * weighted_degree_norm + 0.5 * kcore_norm
                    actor_scores[node_id] = {
                        "score": score,
                        "weighted_degree": weighted_degree,
                        "degree": raw_degree,  # 保留原始度数
                        "kcore": kcore,
                    }
                
                # 3. 按综合得分排序
                sorted_actors = sorted(
                    actor_scores.items(), 
                    key=lambda x: x[1]["score"], 
                    reverse=True
                )
                
                # 4. 动态确定核心成员数量（双重约束）
                #    - 贡献阈值：累计加权贡献 >= 50%
                #    - 得分阈值：得分 >= 平均得分（且已有至少 3 人）
                contribution_threshold = total_weighted_degree * 0.5
                avg_score = sum(s["score"] for s in actor_scores.values()) / len(actor_scores) if actor_scores else 0
                
                cumsum = 0.0  # 使用加权度数的累计值
                for node_id, score_data in sorted_actors:
                    login = graph.nodes[node_id].get("login", node_id)
                    actor_id = graph.nodes[node_id].get("actor_id", 0)
                    weighted_degree = score_data["weighted_degree"]
                    raw_degree = score_data["degree"]  # 保留原始度数为显示
                    
                    # 兼容旧代码：top_actors 保留前 10 个（使用原始度数）
                    if len(metrics.top_actors) < 10:
                        metrics.top_actors.append((login, raw_degree))
                        metrics.top_actor_ids.append(actor_id)
                    
                    # 核心成员：满足以下条件之一时停止
                    # 1. 已达到 50% 加权贡献阈值
                    # 2. 得分低于平均值（且已有至少 3 人）
                    should_stop = (
                        cumsum >= contribution_threshold or
                        (score_data["score"] < avg_score and len(metrics.core_actors) >= 3)
                    )
                    
                    if not should_stop:
                        metrics.core_actors.append((login, raw_degree))  # 显示用原始度数
                        metrics.core_actor_ids.append(actor_id)
                        cumsum += weighted_degree  # 累计使用加权度数
                
                # 确保至少有 2 个核心成员
                if len(metrics.core_actors) < 2 and len(sorted_actors) >= 2:
                    for node_id, score_data in sorted_actors[:2]:
                        login = graph.nodes[node_id].get("login", node_id)
                        actor_id = graph.nodes[node_id].get("actor_id", 0)
                        if actor_id not in metrics.core_actor_ids:
                            metrics.core_actors.append((login, score_data["degree"]))
                            metrics.core_actor_ids.append(actor_id)
                
                metrics.core_actor_count = len(metrics.core_actors)
        
        # 边类型分布
        edge_types = defaultdict(int)
        for u, v, data in graph.edges(data=True):
            edge_type = data.get("edge_type", "UNKNOWN")
            edge_types[edge_type] += 1
        metrics.edge_type_counts = dict(edge_types)
        
        return metrics
    
    def analyze_burnout_signals(
        self,
        repo_name: str,
        metrics_series: List[MonthlyMetrics],
    ) -> List[BurnoutAlert]:
        """分析倦怠信号"""
        alerts = []
        
        if len(metrics_series) < 2:
            return alerts
        
        # 按月份排序
        sorted_metrics = sorted(metrics_series, key=lambda m: m.month)
        
        for i in range(1, len(sorted_metrics)):
            prev = sorted_metrics[i - 1]
            curr = sorted_metrics[i]
            
            # 1. 活跃度大幅下降
            if prev.total_events > 0:
                event_change = (curr.total_events - prev.total_events) / prev.total_events
                if event_change < -0.5:  # 下降超过 50%
                    alerts.append(BurnoutAlert(
                        repo_name=repo_name,
                        month=curr.month,
                        alert_type="ACTIVITY_DROP",
                        severity="high" if event_change < -0.7 else "medium",
                        description=f"事件数量下降 {abs(event_change)*100:.1f}%",
                        metrics={
                            "prev_events": prev.total_events,
                            "curr_events": curr.total_events,
                            "change_rate": event_change,
                        },
                    ))
            
            # 2. 核心成员流失（使用动态计算的核心成员）
            prev_core = set(prev.core_actor_ids) if prev.core_actor_ids else set(prev.top_actor_ids[:5])
            curr_core = set(curr.core_actor_ids) if curr.core_actor_ids else set(curr.top_actor_ids[:5])
            
            if prev_core and curr_core:
                lost = prev_core - curr_core
                # 计算流失比例
                loss_ratio = len(lost) / len(prev_core) if prev_core else 0
                
                # 流失超过 30% 或者绝对数量 >= 2 人触发预警
                if loss_ratio >= 0.3 or len(lost) >= 2:
                    alerts.append(BurnoutAlert(
                        repo_name=repo_name,
                        month=curr.month,
                        alert_type="CORE_MEMBER_LOSS",
                        severity="high" if loss_ratio >= 0.5 or len(lost) >= 3 else "medium",
                        description=f"核心成员流失 {len(lost)}/{len(prev_core)} 人 ({loss_ratio*100:.0f}%)",
                        metrics={
                            "lost_count": len(lost),
                            "loss_ratio": loss_ratio,
                            "prev_core_count": len(prev_core),
                            "curr_core_count": len(curr_core),
                            "prev_core": list(prev_core),
                            "curr_core": list(curr_core),
                        },
                    ))
            
            # 3. 网络密度下降（协作减少）
            if prev.density > 0:
                density_change = (curr.density - prev.density) / prev.density
                if density_change < -0.3:  # 下降超过 30%
                    alerts.append(BurnoutAlert(
                        repo_name=repo_name,
                        month=curr.month,
                        alert_type="COLLABORATION_DECLINE",
                        severity="medium",
                        description=f"网络密度下降 {abs(density_change)*100:.1f}%",
                        metrics={
                            "prev_density": prev.density,
                            "curr_density": curr.density,
                            "change_rate": density_change,
                        },
                    ))
            
            # 4. 参与者数量下降
            if prev.unique_actors > 0:
                actor_change = (curr.unique_actors - prev.unique_actors) / prev.unique_actors
                if actor_change < -0.4:  # 下降超过 40%
                    alerts.append(BurnoutAlert(
                        repo_name=repo_name,
                        month=curr.month,
                        alert_type="CONTRIBUTOR_DROP",
                        severity="medium",
                        description=f"活跃贡献者下降 {abs(actor_change)*100:.1f}%",
                        metrics={
                            "prev_actors": prev.unique_actors,
                            "curr_actors": curr.unique_actors,
                            "change_rate": actor_change,
                        },
                    ))
        
        # 5. 长期趋势分析（需要至少 3 个月数据）
        if len(sorted_metrics) >= 3:
            # 检查连续下降
            events_trend = [m.total_events for m in sorted_metrics[-3:]]
            if all(events_trend[i] > events_trend[i+1] for i in range(len(events_trend)-1)):
                if events_trend[0] > 0:
                    total_decline = (events_trend[-1] - events_trend[0]) / events_trend[0]
                    if total_decline < -0.3:
                        alerts.append(BurnoutAlert(
                            repo_name=repo_name,
                            month=sorted_metrics[-1].month,
                            alert_type="SUSTAINED_DECLINE",
                            severity="high",
                            description=f"连续 3 个月活跃度下降，累计下降 {abs(total_decline)*100:.1f}%",
                            metrics={
                                "trend": events_trend,
                                "total_decline": total_decline,
                            },
                        ))
        
        return alerts
    
    def _linear_regression_slope(self, values: List[float]) -> float:
        """计算线性回归斜率（最小二乘法）"""
        n = len(values)
        if n < 2:
            return 0.0
        
        # x = [0, 1, 2, ..., n-1]
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0.0
        
        return numerator / denominator
    
    def _compute_volatility(self, values: List[float]) -> float:
        """计算月度变化率的波动性（标准差）"""
        if len(values) < 2:
            return 0.0
        
        # 计算环比变化率
        changes = []
        for i in range(1, len(values)):
            if values[i - 1] > 0:
                change = (values[i] - values[i - 1]) / values[i - 1]
                changes.append(change)
        
        if not changes:
            return 0.0
        
        mean_change = sum(changes) / len(changes)
        variance = sum((c - mean_change) ** 2 for c in changes) / len(changes)
        return math.sqrt(variance)
    
    def _compute_dimension_score(
        self,
        values: List[float],
        dimension_name: str,
        max_score: float = 25.0,
    ) -> Dict[str, Any]:
        """
        计算单个维度的倦怠得分（三层分析）
        
        架构：
        - 长期趋势 (40%): 线性回归斜率
        - 近期状态 (40%): 最近3个月 vs 最早3个月
        - 稳定性 (20%): 波动率惩罚
        """
        n = len(values)
        if n < 2 or all(v == 0 for v in values):
            return {
                "score": 0,
                "long_term_trend": {"slope": 0, "score": 0},
                "recent_state": {"early_avg": 0, "recent_avg": 0, "change": 0, "score": 0},
                "stability": {"volatility": 0, "score": 0},
            }
        
        # 归一化值（相对于第一个非零值）
        first_nonzero = next((v for v in values if v > 0), 1)
        normalized = [v / first_nonzero for v in values]
        
        # ========== 1. 长期趋势 (40%) ==========
        # 线性回归斜率，负斜率表示下降
        slope = self._linear_regression_slope(normalized)
        # 假设 -0.1/月（每月下降10%）为极端情况
        trend_score = max(0, min(max_score * 0.4, -slope * max_score * 4))
        
        # ========== 2. 近期状态 (40%) ==========
        # 对比最近3个月和最早3个月的均值
        window = min(3, n // 2) if n >= 4 else 1
        early_avg = sum(values[:window]) / window
        recent_avg = sum(values[-window:]) / window
        
        if early_avg > 0:
            recent_change = (recent_avg - early_avg) / early_avg
        else:
            recent_change = 0
        
        recent_score = max(0, min(max_score * 0.4, -recent_change * max_score * 0.4))
        
        # ========== 3. 稳定性惩罚 (20%) ==========
        # 波动率 > 0.3 开始扣分
        volatility = self._compute_volatility(values)
        stability_score = max(0, min(max_score * 0.2, (volatility - 0.3) * max_score))
        
        # 综合得分
        total = trend_score + recent_score + stability_score
        
        return {
            "score": round(total, 2),
            "long_term_trend": {
                "slope": round(slope, 4),
                "slope_percent_per_month": round(slope * 100, 2),
                "score": round(trend_score, 2),
            },
            "recent_state": {
                "early_avg": round(early_avg, 2),
                "recent_avg": round(recent_avg, 2),
                "change": round(recent_change, 4),
                "change_percent": round(recent_change * 100, 2),
                "score": round(recent_score, 2),
            },
            "stability": {
                "volatility": round(volatility, 4),
                "volatility_percent": round(volatility * 100, 2),
                "score": round(stability_score, 2),
            },
        }
    
    def compute_burnout_score(
        self,
        repo_name: str,
        metrics_series: List[MonthlyMetrics],
    ) -> Dict[str, Any]:
        """
        计算综合倦怠风险评分（三层分析架构）
        
        每个维度都使用：
        - 长期趋势 (40%): 线性回归
        - 近期状态 (40%): 最近3月 vs 最早3月
        - 稳定性 (20%): 波动率惩罚
        
        四个维度：
        - 活跃度 (0-25分)
        - 贡献者 (0-25分)
        - 核心成员 (0-25分)
        - 协作密度 (0-25分)
        """
        if len(metrics_series) < 2:
            return {"score": 0, "level": "unknown", "factors": {}}
        
        sorted_metrics = sorted(metrics_series, key=lambda m: m.month)
        n = len(sorted_metrics)
        
        factors = {}
        
        # ========== 1. 活跃度维度 (0-25分) ==========
        event_values = [m.total_events for m in sorted_metrics]
        factors["activity"] = self._compute_dimension_score(
            event_values, "activity", max_score=25
        )
        
        # ========== 2. 贡献者维度 (0-25分) ==========
        actor_values = [m.unique_actors for m in sorted_metrics]
        factors["contributors"] = self._compute_dimension_score(
            actor_values, "contributors", max_score=25
        )
        
        # ========== 3. 核心成员稳定性 (0-25分) ==========
        # 核心成员需要特殊处理：计算累积留存率
        core_ids_series = [
            set(m.core_actor_ids) if m.core_actor_ids else set(m.top_actor_ids[:5])
            for m in sorted_metrics
        ]
        
        # 计算每个月相对于第一个月的留存率
        if core_ids_series[0]:
            initial_core = core_ids_series[0]
            retention_values = [
                len(initial_core & core_ids_series[i]) / len(initial_core)
                for i in range(n)
            ]
        else:
            retention_values = [1.0] * n
        
        # 留存率下降 = 倦怠风险上升，所以用 1 - retention
        churn_values = [1 - r for r in retention_values]
        
        # 核心成员流失分析
        core_detail = self._compute_dimension_score(
            churn_values, "core_churn", max_score=25
        )
        
        # 添加额外的核心成员信息
        earliest = sorted_metrics[0]
        latest = sorted_metrics[-1]
        early_core = core_ids_series[0]
        latest_core = core_ids_series[-1]
        
        core_detail["early_core_count"] = len(early_core)
        core_detail["latest_core_count"] = len(latest_core)
        core_detail["final_retention"] = round(retention_values[-1], 4) if retention_values else 1
        core_detail["retained_count"] = len(early_core & latest_core) if early_core else 0
        
        factors["core_stability"] = core_detail
        
        # ========== 4. 协作密度 (0-25分) ==========
        density_values = [m.density for m in sorted_metrics]
        factors["collaboration"] = self._compute_dimension_score(
            density_values, "collaboration", max_score=25
        )
        
        # ========== 综合评分 ==========
        total_score = (
            factors["activity"]["score"] +
            factors["contributors"]["score"] +
            factors["core_stability"]["score"] +
            factors["collaboration"]["score"]
        )
        
        # 风险等级
        if total_score >= 60:
            level = "high"
        elif total_score >= 40:
            level = "medium"
        elif total_score >= 20:
            level = "low"
        else:
            level = "healthy"
        
        return {
            "score": round(total_score, 2),
            "level": level,
            "factors": factors,
            "months_analyzed": n,
            "period": f"{earliest.month} to {latest.month}",
            "analysis_method": "three_layer",  # 标记使用新算法
        }
    
    def analyze_all_repos(self) -> Dict[str, Any]:
        """分析所有项目"""
        # 加载索引
        index_file = self.graphs_dir / "index.json"
        if not index_file.exists():
            logger.error(f"索引文件不存在: {index_file}")
            logger.info("请先运行 monthly_graph_builder.py 构建图")
            return {}
        
        with open(index_file, "r") as f:
            index = json.load(f)
        
        total_repos = len(index)
        logger.info(f"开始分析 {total_repos} 个项目...")
        
        all_results = {}
        
        for repo_idx, (repo_name, graph_types_data) in enumerate(index.items(), 1):
            # 新格式: {repo: {graph_type: {month: path}}}
            # 旧格式: {repo: {month: path}}
            # 检测格式
            first_value = next(iter(graph_types_data.values()), {})
            if isinstance(first_value, dict) and not first_value.get("node_type"):
                # 新格式，取 actor-actor 类型
                months = graph_types_data.get("actor-actor", {})
            else:
                # 旧格式
                months = graph_types_data
            
            logger.info(f"[{repo_idx}/{total_repos}] 分析: {repo_name} ({len(months)} 个月)")
            
            # 加载所有月份的图并计算指标
            metrics_series = []
            for month, graph_path in sorted(months.items()):
                graph = self.load_graph(graph_path)
                if graph is not None:
                    metrics = self.compute_monthly_metrics(graph, repo_name, month)
                    metrics_series.append(metrics)
                    self.repo_metrics[repo_name].append(metrics)
            
            if not metrics_series:
                continue
            
            # 分析倦怠信号
            alerts = self.analyze_burnout_signals(repo_name, metrics_series)
            self.alerts.extend(alerts)
            
            # 计算综合评分
            burnout_score = self.compute_burnout_score(repo_name, metrics_series)
            
            all_results[repo_name] = {
                "metrics": [m.to_dict() for m in metrics_series],
                "alerts": [a.to_dict() for a in alerts],
                "burnout_score": burnout_score,
            }
        
        return all_results
    
    def save_results(self, results: Dict[str, Any]):
        """保存分析结果"""
        # 保存完整结果
        full_result_file = self.output_dir / "full_analysis.json"
        with open(full_result_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"完整分析结果已保存: {full_result_file}")
        
        # 保存摘要（按风险排序）
        summary = []
        for repo_name, data in results.items():
            summary.append({
                "repo_name": repo_name,
                "burnout_score": data["burnout_score"]["score"],
                "risk_level": data["burnout_score"]["level"],
                "months_analyzed": data["burnout_score"]["months_analyzed"],
                "alert_count": len(data["alerts"]),
                "high_alerts": len([a for a in data["alerts"] if a["severity"] == "high"]),
            })
        
        # 按风险评分排序
        summary.sort(key=lambda x: x["burnout_score"], reverse=True)
        
        summary_file = self.output_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info(f"摘要已保存: {summary_file}")
        
        # 保存所有预警
        alerts_file = self.output_dir / "all_alerts.json"
        all_alerts = [a.to_dict() for a in self.alerts]
        # 按严重程度和时间排序
        all_alerts.sort(key=lambda x: (
            {"high": 0, "medium": 1, "low": 2}.get(x["severity"], 3),
            x["month"]
        ))
        with open(alerts_file, "w", encoding="utf-8") as f:
            json.dump(all_alerts, f, indent=2, ensure_ascii=False)
        logger.info(f"预警列表已保存: {alerts_file}")
        
        # 打印高风险项目
        high_risk = [s for s in summary if s["risk_level"] in ("high", "medium")]
        if high_risk:
            logger.info("=" * 60)
            logger.info("高/中风险项目:")
            for item in high_risk[:20]:
                logger.info(
                    f"  {item['repo_name']}: "
                    f"评分={item['burnout_score']:.1f}, "
                    f"等级={item['risk_level']}, "
                    f"高危预警={item['high_alerts']}"
                )
            logger.info("=" * 60)
    
    def run(self) -> Dict[str, Any]:
        """运行完整分析"""
        logger.info("=" * 60)
        logger.info("开始维护者倦怠分析")
        logger.info("=" * 60)
        
        results = self.analyze_all_repos()
        
        if results:
            self.save_results(results)
        
        logger.info("=" * 60)
        logger.info("分析完成!")
        logger.info(f"分析项目数: {len(results)}")
        logger.info(f"总预警数: {len(self.alerts)}")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info("=" * 60)
        
        return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="维护者倦怠分析")
    parser.add_argument(
        "--graphs-dir",
        type=str,
        default="output/monthly-graphs/",
        help="月度图目录"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/burnout-analysis/",
        help="输出目录"
    )
    
    args = parser.parse_args()
    
    analyzer = BurnoutAnalyzer(
        graphs_dir=args.graphs_dir,
        output_dir=args.output_dir,
    )
    analyzer.run()
