"""
Newcomer / Core-evolution analyzer (v2 - Kuzu 版)

数据源：Kuzu 图数据库（替代 GraphML 文件）
计算逻辑：与 v4（GraphML 版）完全一致

核心改动：
- load_graph_from_kuzu()：从 Kuzu 查询边数据，重建 NetworkX MultiDiGraph
- PreparedMonth：恢复 graph / g_simple 字段（与 v4 一致）
- identify_core_members / compute_* / save_results：与 v4 完全相同
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

import kuzu
import networkx as nx

from src.utils.logger import get_logger

logger = get_logger()


# =========================
# 数据结构
# =========================

@dataclass
class MonthlyCore:
    month: str
    repo_name: str
    core_node_ids: List[str] = field(default_factory=list)
    core_actor_ids: List[int] = field(default_factory=list)
    core_logins: List[str] = field(default_factory=list)


@dataclass
class PreparedMonth:
    month: str
    repo_name: str
    graph: nx.MultiDiGraph        # 有向多重图（原始）
    g_simple: nx.Graph            # 无向简单图（用于最短路径）
    core_node_ids: List[str]
    actor_nodes: List[str]        # 当月所有 Actor 节点 ID（去重）


@dataclass
class NewcomerDistanceRecord:
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
    分母为当月所有 Actor 总数（total_actor_count），与 v4 一致。
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
# 工具函数（与 v4 完全相同）
# =========================

def _parse_actor_id(value: Any) -> int:
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
    s = _month_to_dt(start_month)
    e = _month_to_dt(end_month)
    return (e.year - s.year) * 12 + (e.month - s.month)


def _to_undirected_simple(graph: nx.MultiDiGraph) -> nx.Graph:
    return nx.Graph(graph.to_undirected())


def _linear_regression_slope(values: List[float]) -> float:
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
    与 v4 逻辑完全相同，仅数据来源从 GraphML 改为 Kuzu 数据库。
    步骤：
      1. load_graph_from_kuzu()  → 查询 Kuzu 边，重建 nx.MultiDiGraph
      2. prepare_monthly_data()  → 预计算 core、g_simple、actor_nodes（与 v4 相同）
      3. compute_*()             → 三个指标计算（与 v4 完全相同）
      4. save_results()          → 三层分析 + health_score（与 v4 完全相同）
    """

    def __init__(
        self,
        kuzu_db_path: str = "output/kuzu_db",
        output_dir: str = "output/newcomer-analysis/",
    ):
        self.kuzu_db_path = kuzu_db_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db = kuzu.Database(str(self.kuzu_db_path))
        self.conn = kuzu.Connection(self.db)

    # ---------- 数据加载（唯一与 v4 不同之处） ----------

    def load_graph_from_kuzu(self, repo_name: str, month: str) -> Optional[nx.MultiDiGraph]:
        """
        从 Kuzu 查询 Actor-Actor 边，重建 nx.MultiDiGraph。
        节点属性：node_type="Actor", actor_id, login
        边属性与 v4 一致（只需有向边存在即可）。
        """
        query = f"""
        MATCH (a:Actor)-[r:ActorToActor]->(b:Actor)
        WHERE r.repo_name = "{repo_name}" AND r.month = "{month}"
        RETURN a.id, a.actor_id, a.login, b.id, b.actor_id, b.login
        """
        try:
            result = self.conn.execute(query)
            G = nx.MultiDiGraph()
            while result.has_next():
                row = result.get_next()
                a_id, a_actor_id, a_login, b_id, b_actor_id, b_login = row

                # 添加节点（若已存在则跳过，避免覆盖已有属性）
                if not G.has_node(str(a_id)):
                    G.add_node(str(a_id),
                               node_type="Actor",
                               actor_id=_parse_actor_id(a_actor_id),
                               login=str(a_login) if a_login else str(a_id))
                if not G.has_node(str(b_id)):
                    G.add_node(str(b_id),
                               node_type="Actor",
                               actor_id=_parse_actor_id(b_actor_id),
                               login=str(b_login) if b_login else str(b_id))

                G.add_edge(str(a_id), str(b_id))

            if G.number_of_nodes() == 0:
                return None
            return G

        except Exception as e:
            logger.warning(f"从 Kuzu 加载图数据失败: {repo_name} {month}, 错误: {e}")
            return None

    def _load_index(self) -> Dict[str, Any]:
        index_file = Path("output/monthly-graphs/index.json")
        if not index_file.exists():
            logger.error(f"索引文件不存在: {index_file}")
            return {}
        with open(index_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _get_actor_actor_months(self, graph_types_data: Any) -> Dict[str, str]:
        """
        解析 index.json 获取月份列表（仅需 month key，path 不再使用）。
        兼容新旧两种 index.json 结构。
        """
        if not isinstance(graph_types_data, dict) or not graph_types_data:
            return {}

        def _looks_like_month(s: str) -> bool:
            return isinstance(s, str) and len(s) == 7 and s[4] == "-" \
                   and s[:4].isdigit() and s[5:7].isdigit()

        # 结构B：直接 month->path
        if all(_looks_like_month(k) for k in graph_types_data.keys()):
            return {k: v for k, v in graph_types_data.items() if isinstance(v, (str, bytes))}

        # 结构A：graph_type -> {month: path}，优先 actor-actor
        preferred_types = [
            "actor-actor", "actor-discussion", "actor-comment",
            "actor-issue", "actor-pr", "actor-review",
        ]
        for t in preferred_types:
            v = graph_types_data.get(t)
            if isinstance(v, dict) and v:
                return {k: p for k, p in v.items() if _looks_like_month(k) and isinstance(p, (str, bytes))}

        # fallback
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

    def prepare_monthly_data(
        self,
        repo_name: str,
        month_to_graph_path: Dict[str, str],
    ) -> List[PreparedMonth]:
        """
        每个月份：从 Kuzu 加载图 → 预计算 core、g_simple、actor_nodes。
        PreparedMonth 结构与 v4 完全一致，后续计算方法零修改。
        """
        prepared: List[PreparedMonth] = []
        for month in sorted(month_to_graph_path.keys()):
            # 从 Kuzu 重建 NetworkX 图（替代 v4 的 nx.read_graphml）
            graph = self.load_graph_from_kuzu(repo_name, month)
            if graph is None or graph.number_of_nodes() == 0:
                continue

            core_node_ids, _, _ = self.identify_core_members(graph)
            g_simple = _to_undirected_simple(graph)
            actor_nodes = [
                n for n, a in graph.nodes(data=True)
                if str(a.get("node_type", "Actor")) == "Actor"
            ]

            prepared.append(PreparedMonth(
                month=month,
                repo_name=repo_name,
                graph=graph,
                g_simple=g_simple,
                core_node_ids=core_node_ids,
                actor_nodes=actor_nodes,
            ))
        return prepared

    # ---------- 核心成员识别（与 v4 完全相同） ----------

    def identify_core_members(self, graph: nx.MultiDiGraph) -> Tuple[List[str], List[int], List[str]]:
        """
        核心成员识别规则：

        1. 对每个 Actor 节点计算两个结构指标：
        - degree：节点度数，表示其连接活跃程度
        - k-core number：节点所在 k-core 层级，表示其处于网络核心区的深度

        2. 对两个指标做归一化后加权求综合分：
        score = 0.6 * normalized_degree + 0.4 * normalized_kcore

        3. 按 score 降序排序（若分数相同则按 node_id 升序）。

        4. 依次选取排序靠前的成员作为 core，直到满足任一停止条件：
        - 已覆盖全图总度数的 70%（累计 degree 贡献）
        - core 数量达到总人数的 30%（至少按 3 计算上限）
        - 当前候选分数低于全体平均分，且已经选出至少 3 名 core

        5. 为避免极端情况，若最终 core 少于 2 人，则补齐排序前 2 名。

        返回：
        - core_node_ids：核心成员节点 ID
        - core_actor_ids：核心成员 actor_id
        - core_logins：核心成员 login
        """
        if graph.number_of_nodes() == 0:
            return [], [], []

        degrees = dict(graph.degree())
        # 获取degree列表
        if not degrees:
            return [], [], []

        degree_values = list(degrees.values())
        degree_max = max(degree_values) if degree_values else 0
        total_degree = sum(degree_values)
        total_actors = len(degrees)

        try:
            undirected = graph.to_undirected()
            core_numbers = nx.core_number(undirected)
            # K核分解，获取每个成员的k值列表
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
            # 得分加权求和
            actor_scores[node_id] = {"score": score, "degree": deg, "kcore": kcore}

        # sorted_actors = sorted(actor_scores.items(), key=lambda x: x[1]["score"], reverse=True)
        sorted_actors = sorted(
            actor_scores.items(),
            key=lambda x: (-x[1]["score"], x[0]),  # score 降序，node_id 升序
        )

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
            '''
            选出尽可能少的成员满足以下规则
            规则1: 合计贡献度数超过总度数的70%
            规则2: 核心贡献者至少选取三个，且人数要大于总人数的30%
            规则3: 核心贡献者的得分不应小于平均分
            '''
            if should_stop:
                continue

            node_attr = graph.nodes[node_id]
            login = node_attr.get("login", node_id)
            actor_id = _parse_actor_id(node_attr.get("actor_id", 0))

            core_node_ids.append(node_id)
            core_actor_ids.append(actor_id)
            core_logins.append(str(login))
            cumsum += float(sdata.get("degree", 0))

        # 至少补齐 2 个核心成员
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

    # ---------- 指标1：新人到核心平均路径（与 v4 完全相同） ----------

    def compute_newcomer_distances_for_repo(
        self,
        repo_name: str,
        prepared_months: List[PreparedMonth],
    ) -> Tuple[List[NewcomerDistanceRecord], List[Dict[str, Any]]]:
        """
        新人成员判定规则：

        - 维护 first_seen[node_id]，记录每个 Actor 节点第一次出现的月份。
        - 按月份顺序扫描图中的 Actor 节点。
        - 若某节点此前从未出现过，则将当前月记为其 first_seen_month，
        并把该节点视为“本月 newcomer（新人）”。

        注意：
        这里的 newcomer 是“在分析时间窗口内首次出现的成员”，
        不一定代表其在项目全历史中的绝对首次参与者。
        """
        newcomer_records: List[NewcomerDistanceRecord] = []
        monthly_summary: List[Dict[str, Any]] = []
        first_seen: Dict[str, str] = {}

        for pm in prepared_months:
            month = pm.month
            graph = pm.graph
            if graph is None or graph.number_of_nodes() == 0:
                continue

            core_node_ids = pm.core_node_ids
            g_simple = pm.g_simple
            newcomers_this_month: List[NewcomerDistanceRecord] = []

            for node_id, attr in graph.nodes(data=True):
                if str(attr.get("node_type", "Actor")) != "Actor":
                    continue
                if node_id not in first_seen:
                    first_seen[node_id] = month
                    newcomer_login = str(attr.get("login", node_id))
                    newcomer_actor_id = _parse_actor_id(attr.get("actor_id", 0))

                    core_targets = [c for c in core_node_ids if c != node_id]
                    # 获取核心成员列表，排除该成员自己
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
                    avg_len: Optional[float] = (
                        None if reachable_count == 0
                        else round(sum(reachable) / reachable_count, 4)
                    ) # 平均路径长度 = 总路径长度 / 可达核心节点数量

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
            month_avg = round(sum(vals) / len(vals), 4) if vals else None # 月度指标
            monthly_summary.append({
                "repo_name": repo_name,
                "month": month,
                "newcomers": len(newcomers_this_month),
                "newcomers_with_reachable_core": len(vals),
                "avg_shortest_path_to_core": month_avg,
                "core_member_count": len(core_node_ids),
            })

        return newcomer_records, monthly_summary

    # ---------- 指标2：外围→核心耗时（与 v4 完全相同，含首月过滤） ----------

    def compute_periphery_to_core_for_repo(
        self,
        repo_name: str,
        prepared_months: List[PreparedMonth],
    ) -> Tuple[List[PeripheryToCoreRecord], Optional[float], List[Dict[str, Any]]]:
        first_seen: Dict[str, str] = {}
        first_core: Dict[str, str] = {}
        actor_info: Dict[str, Tuple[int, str]] = {}

        months_sorted = [pm.month for pm in prepared_months]
        if not months_sorted:
            return [], None, []
        first_month = months_sorted[0]

        for pm in prepared_months:
            graph = pm.graph
            month = pm.month
            if graph is None or graph.number_of_nodes() == 0:
                continue

            for node_id, attr in graph.nodes(data=True):
                if str(attr.get("node_type", "Actor")) != "Actor":
                    continue
                if node_id not in first_seen:
                    first_seen[node_id] = month # 每个成员第一次出现的月份
                if node_id not in actor_info:
                    actor_info[node_id] = (
                        _parse_actor_id(attr.get("actor_id", 0)),
                        str(attr.get("login", node_id)),
                    )

            for c in pm.core_node_ids:
                if c not in first_core:
                    first_core[c] = month

        records_all: List[PeripheryToCoreRecord] = []
        for node_id, core_month in first_core.items():
            seen_month = first_seen.get(node_id)
            if not seen_month:
                continue
            actor_id, login = actor_info.get(node_id, (0, node_id))
            months_to_core = _months_diff(seen_month, core_month) # 计算月份差
            records_all.append(PeripheryToCoreRecord(
                repo_name=repo_name,
                actor_node_id=node_id,
                actor_id=actor_id,
                login=login,
                first_seen_month=seen_month,
                first_core_month=core_month,
                months_to_core=months_to_core,
            ))

        # v4 改动：排除"分析窗口首月即为核心"的成员
        records = [
            r for r in records_all
            if not (r.first_seen_month == first_month and r.first_core_month == first_month)
        ]
        # 排除掉最开始就是核心成员、或者最早出现时间是第一个月的这部分人，因为不知道具体成为核心成员或者具体加入项目是哪天，会对统计结果产生影响

        overall_avg = round(sum(r.months_to_core for r in records) / len(records), 4) if records else None

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

    # ---------- 指标3：非核心→核心可达性（与 v4 完全相同） ----------

    def compute_core_reachability_for_repo(
        self,
        repo_name: str,
        prepared_months: List[PreparedMonth],
    ) -> Tuple[List[CoreReachabilityMonthlySummary], Dict[str, Any]]:
        monthly: List[CoreReachabilityMonthlySummary] = []
        total_actor_sum = 0
        total_unreach_all = 0
        total_unreach_any = 0
        # 部分不可达和完全不可达
        for pm in prepared_months:
            graph = pm.graph
            month = pm.month
            if graph is None or graph.number_of_nodes() == 0:
                continue

            actor_nodes = pm.actor_nodes
            total_actor_count = len(actor_nodes)
            core_node_ids = pm.core_node_ids
            core_targets = list(core_node_ids)
            total_core = len(core_targets)

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
            g_simple = pm.g_simple
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

    # ---------- 总流程（与 v4 完全相同） ----------

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

            prepared_months = self.prepare_monthly_data(repo_name, months)
            if not prepared_months:
                continue

            newcomer_records, newcomer_monthly = self.compute_newcomer_distances_for_repo(repo_name, prepared_months)
            periphery_records, avg_months_to_core, p2c_monthly = self.compute_periphery_to_core_for_repo(repo_name, prepared_months)
            reach_monthly, reach_overall = self.compute_core_reachability_for_repo(repo_name, prepared_months)

            newcomer_vals = [r.avg_shortest_path_to_core for r in newcomer_records if r.avg_shortest_path_to_core is not None]
            overall_newcomer_avg = round(sum(newcomer_vals) / len(newcomer_vals), 4) if newcomer_vals else None

            # 三层分析（三个指标均为"越大越差"）
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
                "graph_type_used": "actor-actor (kuzu)",
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
                    "monthly_summary": reach_monthly_dicts,
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

            risk_scores = [
                (three.get("newcomer_distance", {}) or {}).get("total_score", 0),
                (three.get("periphery_to_core_monthly", {}) or {}).get("total_score", 0),
                (three.get("unreachable_to_all_core_rate", {}) or {}).get("total_score", 0),
                (three.get("unreachable_to_any_core_rate", {}) or {}).get("total_score", 0),
            ]
            total_risk = sum(risk_scores)
            health_score = max(0.0, 100.0 - total_risk)

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
                "three_layer_newcomer_distance_score": risk_scores[0],
                "three_layer_periphery_to_core_monthly_score": risk_scores[1],
                "three_layer_unreachable_to_all_core_rate_score": risk_scores[2],
                "three_layer_unreachable_to_any_core_rate_score": risk_scores[3],
                "total_risk_score": total_risk,
                "health_score": health_score,
            })

        summary.sort(key=lambda x: x["health_score"], reverse=True)

        summary_file = self.output_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info(f"摘要已保存: {summary_file}")

    def run(self) -> Dict[str, Any]:
        logger.info("=" * 60)
        logger.info("开始 Newcomer / Core-evolution 分析 (v2-Kuzu)")
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

    parser = argparse.ArgumentParser(description="Newcomer / Core-evolution 分析 (v2-Kuzu)")
    parser.add_argument("--kuzu-db", type=str, default="output/kuzu_db", help="Kuzu 数据库目录路径")
    parser.add_argument("--output-dir", type=str, default="output/newcomer-analysis/", help="输出目录")

    args = parser.parse_args()

    analyzer = NewcomerAnalyzer(
        kuzu_db_path=args.kuzu_db,
        output_dir=args.output_dir,
    )
    analyzer.run()