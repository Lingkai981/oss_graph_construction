"""
Newcomer / Core-evolution analyzer (v4)

本版本相对 v3 的关键改动（按你的反馈）：
1) 指标2（Periphery→Core）：排除“分析窗口第一个月就已经是核心成员”的 actor（避免 months_to_core=0 拉低均值）。
2) 指标3（core reachability）：不可达比例的分母改为“当月所有成员数（Actor 总数）”，而不是非核心人数。
   - 分子仍然统计“非核心成员”到 core 的不可达情况（更符合‘外围与核心的断裂’信号，同时避免 core 自身稀释信号）
3) 三层分析方向统一为：三个指标都是“越小越好”（increase_is_bad=True）。
   - 均值步长 / 晋核耗时 / 不可达比例：上升代表变差，评分应更低（或惩罚更高）
   - 这里我们输出的是“惩罚分/风险分”风格：越高表示越糟（用于排序），与 burnout 的用法一致

输入：
- 默认读取 output/monthly-graphs/index.json（新格式时仅使用 actor-actor 图）

输出（output/newcomer-analysis/）：
- full_analysis.json
- summary.json

"""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from src.utils.logger import get_logger

logger = get_logger()


# =========================
# 数据结构
# =========================

@dataclass
class MonthlyCore:
    """单月核心成员识别结果（沿用原算法输出的核心集合）"""
    month: str
    repo_name: str
    core_node_ids: List[str] = field(default_factory=list)  # graphml node_id, e.g. "actor:123"
    core_actor_ids: List[int] = field(default_factory=list)  # numeric actor_id
    core_logins: List[str] = field(default_factory=list)     # login strings


@dataclass
class NewcomerDistanceRecord:
    """新人加入时到核心成员的平均最短路径长度"""
    repo_name: str
    join_month: str
    newcomer_node_id: str
    newcomer_actor_id: int
    newcomer_login: str
    avg_shortest_path_to_core: Optional[float]
    reachable_core_count: int
    total_core_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_name": self.repo_name,
            "join_month": self.join_month,
            "newcomer_node_id": self.newcomer_node_id,
            "newcomer_actor_id": self.newcomer_actor_id,
            "newcomer_login": self.newcomer_login,
            "avg_shortest_path_to_core": self.avg_shortest_path_to_core,
            "reachable_core_count": self.reachable_core_count,
            "total_core_count": self.total_core_count,
        }


@dataclass
class PeripheryToCoreRecord:
    """核心成员从首次出现到首次成为 core 的耗时（月）"""
    repo_name: str
    actor_node_id: str
    actor_id: int
    login: str
    first_seen_month: str
    first_core_month: str
    months_to_core: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_name": self.repo_name,
            "actor_node_id": self.actor_node_id,
            "actor_id": self.actor_id,
            "login": self.login,
            "first_seen_month": self.first_seen_month,
            "first_core_month": self.first_core_month,
            "months_to_core": self.months_to_core,
        }


@dataclass
class CoreReachabilityMonthlySummary:
    """
    非核心成员到核心成员的可达性统计（按月）

    注意：不可达“比例”的分母是当月所有 Actor 总数（total_actor_count），而不是 non_core_count。
    """
    repo_name: str
    month: str
    total_actor_count: int
    non_core_count: int
    unreachable_to_all_core_count: int
    unreachable_to_any_core_count: int
    total_core_count: int

    def to_dict(self) -> Dict[str, Any]:
        denom = self.total_actor_count
        return {
            "repo_name": self.repo_name,
            "month": self.month,
            "total_actor_count": self.total_actor_count,
            "non_core_count": self.non_core_count,
            "unreachable_to_all_core_count": self.unreachable_to_all_core_count,
            "unreachable_to_any_core_count": self.unreachable_to_any_core_count,
            "total_core_count": self.total_core_count,
            "unreachable_to_all_core_rate": round(self.unreachable_to_all_core_count / denom, 6) if denom else None,
            "unreachable_to_any_core_rate": round(self.unreachable_to_any_core_count / denom, 6) if denom else None,
        }


# =========================
# 工具函数
# =========================

def _parse_actor_id(value: Any) -> int:
    """GraphML 节点属性 actor_id 可能是 str/int/float，做一次稳健转换。"""
    try:
        if value is None:
            return 0
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        s = str(value).strip()
        if not s:
            return 0
        return int(float(s))
    except Exception:
        return 0


def _month_to_dt(month: str) -> datetime:
    return datetime.strptime(month, "%Y-%m")


def _months_diff(start_month: str, end_month: str) -> int:
    """end - start in months"""
    s = _month_to_dt(start_month)
    e = _month_to_dt(end_month)
    return (e.year - s.year) * 12 + (e.month - s.month)


def _to_undirected_simple(graph: nx.MultiDiGraph) -> nx.Graph:
    """将 MultiDiGraph 转为无向简单图：忽略方向、合并平行边。"""
    return nx.Graph(graph.to_undirected())


def _linear_regression_slope(values: List[float]) -> float:
    """简单线性回归斜率（x=0..n-1）。"""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = 0.0
    den = 0.0
    for i, y in enumerate(values):
        dx = i - x_mean
        dy = y - y_mean
        num += dx * dy
        den += dx * dx
    return num / den if den != 0 else 0.0


def _compute_volatility(values: List[float]) -> float:
    """环比变化率标准差；跳过 prev<=0。"""
    if len(values) < 3:
        return 0.0
    changes: List[float] = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        cur = values[i]
        if prev is None or cur is None:
            continue
        if prev <= 0:
            continue
        changes.append((cur - prev) / prev)
    if len(changes) < 2:
        return 0.0
    mean = sum(changes) / len(changes)
    var = sum((c - mean) ** 2 for c in changes) / len(changes)
    return math.sqrt(var)


def compute_three_layer_analysis(
    values: List[Optional[float]],
    *,
    max_score: float = 25.0,
    recent_window: int = 3,
    volatility_threshold: float = 0.3,
    increase_is_bad: bool = True,
) -> Dict[str, Any]:
    """
    三层分析（长期趋势/近期状态/稳定性），返回可解释的“惩罚/风险分”。
    - increase_is_bad=True 表示“越大越差”（本项目的三个指标都满足这一点）
      - 趋势：slope 越大惩罚越大
      - 近期：change 越大惩罚越大
    - increase_is_bad=False 表示“越小越差”（保留扩展性）

    None 会被过滤；n_points 是有效数据点数。
    """
    clean = [v for v in values if v is not None]
    n = len(clean)
    if n < 2:
        return {
            "n_points": n,
            "trend": {"slope": 0.0, "score": 0.0},
            "recent": {"change": 0.0, "score": 0.0},
            "stability": {"volatility": 0.0, "score": 0.0},
            "total_score": 0.0,
        }

    # 归一化（与 burnout 一致）：以首个非零值为基准
    base = None
    for v in clean:
        if v != 0:
            base = v
            break
    normalized = clean[:] if base is None else [v / base for v in clean]

    slope = _linear_regression_slope(normalized)

    w = min(recent_window, max(1, n // 2))
    early_avg = sum(clean[:w]) / w
    recent_avg = sum(clean[-w:]) / w
    change = (recent_avg - early_avg) / early_avg if early_avg != 0 else 0.0

    volatility = _compute_volatility(clean)

    # 映射到“惩罚/风险分”：越高越差
    if increase_is_bad:
        trend_score = max(0.0, min(max_score * 0.4, slope * max_score * 4))
        recent_score = max(0.0, min(max_score * 0.4, change * max_score * 0.4))
    else:
        trend_score = max(0.0, min(max_score * 0.4, -slope * max_score * 4))
        recent_score = max(0.0, min(max_score * 0.4, -change * max_score * 0.4))

    stability_score = max(0.0, min(max_score * 0.2, (volatility - volatility_threshold) * max_score))

    total = round(trend_score + recent_score + stability_score, 4)
    return {
        "n_points": n,
        "trend": {"slope": round(slope, 6), "score": round(trend_score, 4)},
        "recent": {
            "window": w,
            "early_avg": early_avg,
            "recent_avg": recent_avg,
            "change": round(change, 6),
            "score": round(recent_score, 4),
        },
        "stability": {
            "volatility": round(volatility, 6),
            "threshold": volatility_threshold,
            "score": round(stability_score, 4),
        },
        "total_score": total,
    }


# =========================
# 主分析器
# =========================

class NewcomerAnalyzer:
    """
    计算三类指标：
    1) newcomer -> core 平均最短路径长度（加入当月）
    2) periphery -> core 平均耗时（月），并提供“每月新晋核心”的月度序列（方案A）
    3) non-core -> core 不可达统计（any/all），比例分母为当月 Actor 总数
    """

    def __init__(
        self,
        graphs_dir: str = "output/monthly-graphs/",
        output_dir: str = "output/newcomer-analysis/",
    ):
        self.graphs_dir = Path(graphs_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ---------- IO ----------

    def load_graph(self, graph_path: str) -> Optional[nx.MultiDiGraph]:
        try:
            return nx.read_graphml(graph_path)
        except Exception as e:
            logger.warning(f"加载图失败: {graph_path}, 错误: {e}")
            return None

    def _load_index(self) -> Dict[str, Any]:
        index_file = self.graphs_dir / "index.json"
        if not index_file.exists():
            logger.error(f"索引文件不存在: {index_file}")
            logger.info("请先运行 monthly_graph_builder.py 构建图")
            return {}
        with open(index_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _get_actor_actor_months(self, graph_types_data: Any) -> Dict[str, str]:
        """
        从 index.json 的 repo 记录中解析出“用于分析的 actor-actor 月度图 {month: path}”。

        你当前的 index.json 常见结构是：
        - 结构A（多图类型）: {repo: {graph_type: {month: path}}}
          例如 graph_type 可能是 "actor-discussion", "actor-actor", "actor-repo" 等
        - 结构B（单层旧格式）: {repo: {month: path}}

        本分析只适用于“节点全部是 Actor”的图（actor-actor 类）。
        因此优先选择下列类型（按优先级）：
        1) actor-actor
        2) actor-discussion
        3) actor-comment / actor-issue / actor-pr / actor-review（如果存在）
        若以上都没有，则会尝试从 graph_types_data 里找出“看起来像 month->path 的 dict”。
        """
        if not isinstance(graph_types_data, dict) or not graph_types_data:
            return {}

        # 如果 keys 看起来就是月份（YYYY-MM），则认为已经是 {month: path}
        def _looks_like_month(s: str) -> bool:
            return isinstance(s, str) and len(s) == 7 and s[4] == "-" and s[:4].isdigit() and s[5:7].isdigit()

        # 结构B：直接 month->path
        if all(_looks_like_month(k) for k in graph_types_data.keys()):
            return {k: v for k, v in graph_types_data.items() if isinstance(v, (str, bytes))}

        # 结构A：graph_type -> {month: path}
        preferred_types = [
            "actor-actor",
            "actor-discussion",
            "actor-comment",
            "actor-issue",
            "actor-pr",
            "actor-review",
        ]
        for t in preferred_types:
            v = graph_types_data.get(t)
            if isinstance(v, dict) and v:
                return {k: p for k, p in v.items() if _looks_like_month(k) and isinstance(p, (str, bytes))}

        # fallback：在所有子 dict 里找一个最像 month->path 的
        candidates = []
        for t, v in graph_types_data.items():
            if not isinstance(v, dict) or not v:
                continue
            month_keys = [k for k in v.keys() if _looks_like_month(k)]
            if month_keys:
                candidates.append((len(month_keys), t, v))
        if candidates:
            candidates.sort(reverse=True)
            _, t, v = candidates[0]
            logger.warning(f"未找到首选 actor-actor 图类型，fallback 使用: {t}")
            return {k: p for k, p in v.items() if _looks_like_month(k) and isinstance(p, (str, bytes))}

        return {}

    # ---------- 核心成员识别（沿用原算法） ----------

    def identify_core_members(self, graph: nx.MultiDiGraph) -> Tuple[List[str], List[int], List[str]]:
        """
        返回：(core_node_ids, core_actor_ids, core_logins)

        算法来自 burnout_analyzer.py：
        - k-core（无向）
        - score = 0.6*degree_norm + 0.4*kcore_norm
        - 三重约束：
          * 累计 degree >= 70% total_degree
          * 核心人数 <= max(3, 30% actors)
          * score < 平均分 且已有>=3 人则停止
        - 最少补到 2 人
        """
        if graph.number_of_nodes() == 0:
            return [], [], []

        degrees = dict(graph.degree())
        if not degrees:
            return [], [], []

        degree_values = list(degrees.values())
        degree_max = max(degree_values) if degree_values else 0
        total_degree = sum(degree_values)
        total_actors = len(degrees)

        # k-core 分解
        try:
            undirected = graph.to_undirected()
            core_numbers = nx.core_number(undirected)
            max_k = max(core_numbers.values()) if core_numbers else 0
        except Exception:
            core_numbers = {n: 1 for n in graph.nodes()}
            max_k = 1

        actor_scores: Dict[str, Dict[str, float]] = {}
        for node_id in graph.nodes():
            deg = degrees.get(node_id, 0)
            kcore = core_numbers.get(node_id, 0)
            degree_norm = deg / max(degree_max, 1)
            kcore_norm = kcore / max(max_k, 1)
            score = 0.6 * degree_norm + 0.4 * kcore_norm
            actor_scores[node_id] = {"score": score, "degree": deg, "kcore": kcore}

        sorted_actors = sorted(actor_scores.items(), key=lambda x: x[1]["score"], reverse=True)

        contribution_threshold = total_degree * 0.7
        max_core_count = max(3, int(total_actors * 0.3))
        avg_score = sum(s["score"] for s in actor_scores.values()) / len(actor_scores) if actor_scores else 0.0

        core_node_ids: List[str] = []
        core_actor_ids: List[int] = []
        core_logins: List[str] = []

        cumsum = 0.0
        for node_id, sdata in sorted_actors:
            should_stop = (
                cumsum >= contribution_threshold
                or len(core_node_ids) >= max_core_count
                or (sdata["score"] < avg_score and len(core_node_ids) >= 3)
            )
            if should_stop:
                continue

            node_attr = graph.nodes[node_id]
            login = node_attr.get("login", node_id)
            actor_id = _parse_actor_id(node_attr.get("actor_id", 0))

            core_node_ids.append(node_id)
            core_actor_ids.append(actor_id)
            core_logins.append(str(login))
            cumsum += float(sdata.get("degree", 0))

        # 至少 2 个核心成员（补齐）
        if len(core_node_ids) < 2 and len(sorted_actors) >= 2:
            for node_id, _ in sorted_actors[:2]:
                if node_id in core_node_ids:
                    continue
                node_attr = graph.nodes[node_id]
                login = node_attr.get("login", node_id)
                actor_id = _parse_actor_id(node_attr.get("actor_id", 0))
                core_node_ids.append(node_id)
                core_actor_ids.append(actor_id)
                core_logins.append(str(login))

        return core_node_ids, core_actor_ids, core_logins

    # ---------- 指标1：新人加入时到核心平均路径 ----------

    def compute_newcomer_distances_for_repo(
        self,
        repo_name: str,
        month_to_graph_path: Dict[str, str],
    ) -> Tuple[List[NewcomerDistanceRecord], List[Dict[str, Any]]]:
        """
        返回：
        - newcomer records（每个新人一条）
        - monthly summary（每月新人均值/数量）
        """
        newcomer_records: List[NewcomerDistanceRecord] = []
        monthly_summary: List[Dict[str, Any]] = []

        first_seen: Dict[str, str] = {}  # node_id -> first month

        for month in sorted(month_to_graph_path.keys()):
            graph = self.load_graph(month_to_graph_path[month])
            if graph is None or graph.number_of_nodes() == 0:
                continue

            core_node_ids, _, _ = self.identify_core_members(graph)
            g_simple = _to_undirected_simple(graph)

            newcomers_this_month: List[NewcomerDistanceRecord] = []
            for node_id, attr in graph.nodes(data=True):
                if str(attr.get("node_type", "Actor")) != "Actor":
                    continue

                if node_id not in first_seen:
                    first_seen[node_id] = month

                    newcomer_login = str(attr.get("login", node_id))
                    newcomer_actor_id = _parse_actor_id(attr.get("actor_id", 0))

                    core_targets = [c for c in core_node_ids if c != node_id]
                    total_core = len(core_targets)

                    if total_core == 0:
                        rec = NewcomerDistanceRecord(
                            repo_name=repo_name,
                            join_month=month,
                            newcomer_node_id=node_id,
                            newcomer_actor_id=newcomer_actor_id,
                            newcomer_login=newcomer_login,
                            avg_shortest_path_to_core=None,
                            reachable_core_count=0,
                            total_core_count=0,
                        )
                        newcomer_records.append(rec)
                        newcomers_this_month.append(rec)
                        continue

                    lengths = nx.single_source_shortest_path_length(g_simple, node_id)
                    reachable = [lengths[t] for t in core_targets if t in lengths]
                    reachable_count = len(reachable)

                    avg_len: Optional[float] = None if reachable_count == 0 else round(sum(reachable) / reachable_count, 4)

                    rec = NewcomerDistanceRecord(
                        repo_name=repo_name,
                        join_month=month,
                        newcomer_node_id=node_id,
                        newcomer_actor_id=newcomer_actor_id,
                        newcomer_login=newcomer_login,
                        avg_shortest_path_to_core=avg_len,
                        reachable_core_count=reachable_count,
                        total_core_count=total_core,
                    )
                    newcomer_records.append(rec)
                    newcomers_this_month.append(rec)

            vals = [r.avg_shortest_path_to_core for r in newcomers_this_month if r.avg_shortest_path_to_core is not None]
            month_avg = round(sum(vals) / len(vals), 4) if vals else None

            monthly_summary.append({
                "repo_name": repo_name,
                "month": month,
                "newcomers": len(newcomers_this_month),
                "newcomers_with_reachable_core": len(vals),
                "avg_shortest_path_to_core": month_avg,
                "core_member_count": len(core_node_ids),
            })

        return newcomer_records, monthly_summary

    # ---------- 指标2：periphery->core 平均耗时（排除首月即 core） ----------

    def compute_periphery_to_core_for_repo(
        self,
        repo_name: str,
        month_to_graph_path: Dict[str, str],
    ) -> Tuple[List[PeripheryToCoreRecord], Optional[float], List[Dict[str, Any]]]:
        """
        对“曾经成为核心成员”的 actor，计算其：
        months_to_core = first_core_month - first_seen_month

        v4 改动：排除“分析窗口第一个月就已经是核心成员”的 actor：
        - 条件：first_core_month == first_month AND first_seen_month == first_month
        """
        first_seen: Dict[str, str] = {}
        first_core: Dict[str, str] = {}
        actor_info: Dict[str, Tuple[int, str]] = {}

        months_sorted = sorted(month_to_graph_path.keys())
        if not months_sorted:
            return [], None, []
        first_month = months_sorted[0]

        for month in months_sorted:
            graph = self.load_graph(month_to_graph_path[month])
            if graph is None or graph.number_of_nodes() == 0:
                continue

            for node_id, attr in graph.nodes(data=True):
                if str(attr.get("node_type", "Actor")) != "Actor":
                    continue
                if node_id not in first_seen:
                    first_seen[node_id] = month
                if node_id not in actor_info:
                    actor_info[node_id] = (_parse_actor_id(attr.get("actor_id", 0)), str(attr.get("login", node_id)))

            core_node_ids, _, _ = self.identify_core_members(graph)
            for c in core_node_ids:
                if c not in first_core:
                    first_core[c] = month

        records_all: List[PeripheryToCoreRecord] = []
        for node_id, core_month in first_core.items():
            seen_month = first_seen.get(node_id)
            if not seen_month:
                continue
            actor_id, login = actor_info.get(node_id, (0, node_id))
            months_to_core = _months_diff(seen_month, core_month)
            records_all.append(PeripheryToCoreRecord(
                repo_name=repo_name,
                actor_node_id=node_id,
                actor_id=actor_id,
                login=login,
                first_seen_month=seen_month,
                first_core_month=core_month,
                months_to_core=months_to_core,
            ))

        # v4：过滤“首月即 core”
        records = [
            r for r in records_all
            if not (r.first_seen_month == first_month and r.first_core_month == first_month)
        ]

        overall_avg = round(sum(r.months_to_core for r in records) / len(records), 4) if records else None

        # 方案A：按“每月新晋核心成员（first_core_month == month）”构造月度序列（基于过滤后的 records）
        by_month: Dict[str, List[int]] = defaultdict(list)
        for r in records:
            by_month[r.first_core_month].append(r.months_to_core)

        monthly_summary: List[Dict[str, Any]] = []
        for month in months_sorted:
            vals = by_month.get(month, [])
            if not vals:
                monthly_summary.append({
                    "repo_name": repo_name,
                    "month": month,
                    "new_core_count": 0,
                    "avg_months_to_core": None,
                    "median_months_to_core": None,
                })
            else:
                monthly_summary.append({
                    "repo_name": repo_name,
                    "month": month,
                    "new_core_count": len(vals),
                    "avg_months_to_core": round(sum(vals) / len(vals), 4),
                    "median_months_to_core": float(statistics.median(vals)),
                })

        return records, overall_avg, monthly_summary

    # ---------- 指标3：非核心成员与核心成员可达性（比例分母为当月所有成员数） ----------

    def compute_core_reachability_for_repo(
        self,
        repo_name: str,
        month_to_graph_path: Dict[str, str],
    ) -> Tuple[List[CoreReachabilityMonthlySummary], Dict[str, Any]]:
        """
        统计“非核心成员到核心成员”的不可达情况（按月 + 全局汇总）

        对每个月：
        - total_actor_count：当月 Actor 总数（分母）
        - non_core_count：当月非核心 actor 数（分子统计对象集合）
        - unreachable_to_all_core_count：与所有 core 都不可达（reachable_core_count == 0）
        - unreachable_to_any_core_count：与至少一个 core 不可达（reachable_core_count < total_core_count）

        全局汇总：
        - 对所有月份做加权汇总（按月累加分子/分母）
        """
        monthly: List[CoreReachabilityMonthlySummary] = []

        total_actor_sum = 0
        total_unreach_all = 0
        total_unreach_any = 0

        for month in sorted(month_to_graph_path.keys()):
            graph = self.load_graph(month_to_graph_path[month])
            if graph is None or graph.number_of_nodes() == 0:
                continue

            # 当月 Actor 总数（分母）
            actor_nodes = [n for n, a in graph.nodes(data=True) if str(a.get("node_type", "Actor")) == "Actor"]
            total_actor_count = len(actor_nodes)

            core_node_ids, _, _ = self.identify_core_members(graph)
            core_targets = list(core_node_ids)
            total_core = len(core_targets)

            # 没有 core 时：不可达无定义（当月输出 None-rate 的占位）
            if total_core == 0:
                monthly.append(CoreReachabilityMonthlySummary(
                    repo_name=repo_name,
                    month=month,
                    total_actor_count=total_actor_count,
                    non_core_count=max(0, total_actor_count),
                    unreachable_to_all_core_count=0,
                    unreachable_to_any_core_count=0,
                    total_core_count=0,
                ))
                total_actor_sum += total_actor_count
                continue

            core_set = set(core_targets)
            g_simple = _to_undirected_simple(graph)

            non_core_nodes = [n for n in actor_nodes if n not in core_set]

            unreach_all = 0
            unreach_any = 0

            for node_id in non_core_nodes:
                lengths = nx.single_source_shortest_path_length(g_simple, node_id)
                reachable_core = sum(1 for c in core_targets if c in lengths)

                if reachable_core == 0:
                    unreach_all += 1
                    unreach_any += 1
                elif reachable_core < total_core:
                    unreach_any += 1

            monthly.append(CoreReachabilityMonthlySummary(
                repo_name=repo_name,
                month=month,
                total_actor_count=total_actor_count,
                non_core_count=len(non_core_nodes),
                unreachable_to_all_core_count=unreach_all,
                unreachable_to_any_core_count=unreach_any,
                total_core_count=total_core,
            ))

            total_actor_sum += total_actor_count
            total_unreach_all += unreach_all
            total_unreach_any += unreach_any

        overall = {
            "repo_name": repo_name,
            "total_actor_sum": total_actor_sum,
            "total_unreachable_to_all_core_count": total_unreach_all,
            "total_unreachable_to_any_core_count": total_unreach_any,
            "overall_unreachable_to_all_core_rate": round(total_unreach_all / total_actor_sum, 6) if total_actor_sum else None,
            "overall_unreachable_to_any_core_rate": round(total_unreach_any / total_actor_sum, 6) if total_actor_sum else None,
        }

        return monthly, overall

    # ---------- 总流程 ----------

    def analyze_all_repos(self) -> Dict[str, Any]:
        index = self._load_index()
        if not index:
            return {}

        total_repos = len(index)
        logger.info(f"开始分析 {total_repos} 个项目（newcomer/core 指标）...")

        results: Dict[str, Any] = {}

        for repo_idx, (repo_name, graph_types_data) in enumerate(index.items(), 1):
            months = self._get_actor_actor_months(graph_types_data)
            if not months:
                continue

            logger.info(f"[{repo_idx}/{total_repos}] 分析: {repo_name} ({len(months)} 个月)")

            newcomer_records, newcomer_monthly = self.compute_newcomer_distances_for_repo(repo_name, months)
            periphery_records, avg_months_to_core, p2c_monthly = self.compute_periphery_to_core_for_repo(repo_name, months)
            reach_monthly, reach_overall = self.compute_core_reachability_for_repo(repo_name, months)

            # overall newcomer avg（只对有值的）
            newcomer_vals = [r.avg_shortest_path_to_core for r in newcomer_records if r.avg_shortest_path_to_core is not None]
            overall_newcomer_avg = round(sum(newcomer_vals) / len(newcomer_vals), 4) if newcomer_vals else None

            # ===== 三层分析：三个指标都是“越小越好” => increase_is_bad=True =====
            newcomer_series = [m.get("avg_shortest_path_to_core") for m in newcomer_monthly]
            newcomer_three_layer = compute_three_layer_analysis(newcomer_series, max_score=25.0, increase_is_bad=True)

            reach_monthly_dicts = [m.to_dict() for m in reach_monthly]
            unreach_all_series = [m.get("unreachable_to_all_core_rate") for m in reach_monthly_dicts]
            unreach_any_series = [m.get("unreachable_to_any_core_rate") for m in reach_monthly_dicts]
            unreach_all_three_layer = compute_three_layer_analysis(unreach_all_series, max_score=25.0, increase_is_bad=True)
            unreach_any_three_layer = compute_three_layer_analysis(unreach_any_series, max_score=25.0, increase_is_bad=True)

            p2c_series = [m.get("avg_months_to_core") for m in p2c_monthly]
            p2c_three_layer = compute_three_layer_analysis(p2c_series, max_score=25.0, increase_is_bad=True)

            results[repo_name] = {
                "repo_name": repo_name,
                "graph_type_used": "actor-actor",
                "three_layer_analysis": {
                    "newcomer_distance": newcomer_three_layer,
                    "periphery_to_core_monthly": p2c_three_layer,
                    "unreachable_to_all_core_rate": unreach_all_three_layer,
                    "unreachable_to_any_core_rate": unreach_any_three_layer,
                },
                "newcomer_distance": {
                    "overall_avg_shortest_path_to_core": overall_newcomer_avg,
                    "records": [r.to_dict() for r in newcomer_records],
                    "monthly_summary": newcomer_monthly,
                },
                "periphery_to_core": {
                    "average_months_to_core": avg_months_to_core,
                    "records": [r.to_dict() for r in periphery_records],
                    "monthly_summary": p2c_monthly,
                },
                "core_reachability": {
                    "overall": reach_overall,
                    "monthly_summary": [m.to_dict() for m in reach_monthly],
                },
            }

        return results

    def save_results(self, results: Dict[str, Any]) -> None:
        full_result_file = self.output_dir / "full_analysis.json"
        with open(full_result_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"完整分析结果已保存: {full_result_file}")

        summary: List[Dict[str, Any]] = []
        for repo_name, data in results.items():
            newcomer = data.get("newcomer_distance", {}) or {}
            p2c = data.get("periphery_to_core", {}) or {}
            reach = data.get("core_reachability", {}) or {}
            three = data.get("three_layer_analysis", {}) or {}

            reach_overall = reach.get("overall", {}) or {}

            summary.append({
                "repo_name": repo_name,
                "overall_avg_shortest_path_to_core": newcomer.get("overall_avg_shortest_path_to_core"),
                "newcomer_count": len(newcomer.get("records", []) or []),
                "newcomer_with_reachable_core_count": sum(
                    1 for r in (newcomer.get("records", []) or []) if r.get("avg_shortest_path_to_core") is not None
                ),
                "average_months_to_core": p2c.get("average_months_to_core"),
                "core_member_count_ever": len(p2c.get("records", []) or []),
                "overall_unreachable_to_all_core_rate": reach_overall.get("overall_unreachable_to_all_core_rate"),
                "overall_unreachable_to_any_core_rate": reach_overall.get("overall_unreachable_to_any_core_rate"),

                "three_layer_newcomer_distance_score": (three.get("newcomer_distance", {}) or {}).get("total_score"),
                "three_layer_periphery_to_core_monthly_score": (three.get("periphery_to_core_monthly", {}) or {}).get("total_score"),
                "three_layer_unreachable_to_all_core_rate_score": (three.get("unreachable_to_all_core_rate", {}) or {}).get("total_score"),
                "three_layer_unreachable_to_any_core_rate_score": (three.get("unreachable_to_any_core_rate", {}) or {}).get("total_score"),
            })

        # 默认排序：四个三层总分之和（越高信号越强/越差）
        def _sort_key(x: Dict[str, Any]) -> float:
            keys = [
                "three_layer_newcomer_distance_score",
                "three_layer_periphery_to_core_monthly_score",
                "three_layer_unreachable_to_all_core_rate_score",
                "three_layer_unreachable_to_any_core_rate_score",
            ]
            return sum(float(x.get(k) or 0.0) for k in keys)

        summary.sort(key=_sort_key, reverse=True)

        summary_file = self.output_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info(f"摘要已保存: {summary_file}")

    def run(self) -> Dict[str, Any]:
        logger.info("=" * 60)
        logger.info("开始 Newcomer / Core-evolution 分析 (v4)")
        logger.info("=" * 60)

        results = self.analyze_all_repos()
        if results:
            self.save_results(results)

        logger.info("=" * 60)
        logger.info("分析完成!")
        logger.info(f"分析项目数: {len(results)}")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info("=" * 60)
        return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Newcomer / Core-evolution 分析 (v4)")
    parser.add_argument("--graphs-dir", type=str, default="output/monthly-graphs/", help="月度图目录")
    parser.add_argument("--output-dir", type=str, default="output/newcomer-analysis/", help="输出目录")

    args = parser.parse_args()

    analyzer = NewcomerAnalyzer(
        graphs_dir=args.graphs_dir,
        output_dir=args.output_dir,
    )
    analyzer.run()
