"""
Quality / Permission-gaming risk analyzer (v3)

新增 / 修正：
1) “攻击者是否仍是核心成员”按【每个项目可用的最新月份】判断：
   - 优先使用 actor-actor 最新月图
   - 若无 actor-actor，则使用 actor-discussion 最新月图投影为 actor-actor
   - 若二者都无，则在 summary 中记录该项目缺失 core 判定图
2) 攻击者候选集筛选：满足任一条件即可纳入排序
   - 触达过高重要 repo（first_high_repo_touch_time 非空）
   - total_event_importance 位于 top 20%（>= p80）
   - distinct_repos_touched >= 5
   同时仍会剔除 total_event_importance 最低 5%（避免一次性路人主导）
3) 输出增加：
   - top_suspects.csv 增加 core_projects_recent, core_month_used, core_graph_type_used
   - attackers_core_recent.json：actor -> [{project, month, graph_type}, ...]
   - missing_core_projects.json：无法判断 core 的项目列表（原因+最新月）
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from src.utils.logger import get_logger

logger = get_logger()


EDGE_TYPE_WEIGHTS: Dict[str, float] = {
    "REVIEW": 5.0,
    "PR": 4.5,
    "ISSUE": 4.0,
    "COMMENT": 3.0,
    "PUSH": 2.0,
    "FORK": 1.5,
    "STAR": 1.0,
    "WATCH": 1.0,
    "OTHER": 1.0,
}
LOW_COST_EDGE_TYPES: Set[str] = {"STAR", "WATCH", "FORK"}


def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def _parse_datetime(s: Any) -> Optional[datetime]:
    if s is None:
        return None
    try:
        ss = str(s).strip()
        if not ss:
            return None
        ss = ss.replace("Z", "+00:00")
        return datetime.fromisoformat(ss)
    except Exception:
        return None


def event_importance(edge_attr: Dict[str, Any], *, alpha: float = 0.2) -> float:
    t = _safe_str(edge_attr.get("edge_type", "")).upper()
    w = EDGE_TYPE_WEIGHTS.get(t, EDGE_TYPE_WEIGHTS["OTHER"])
    body = _safe_str(edge_attr.get("comment_body", ""))
    l = len(body)
    bonus = 1.0 + alpha * math.log(1.0 + l)
    return float(w) * float(bonus)


def iter_edges(g):
    """兼容 MultiGraph/MultiDiGraph 与 Graph/DiGraph。"""
    if g.is_multigraph():
        for u, v, k, attr in g.edges(keys=True, data=True):
            yield u, v, k, attr
    else:
        for u, v, attr in g.edges(data=True):
            yield u, v, None, attr


def _looks_like_month(s: str) -> bool:
    return isinstance(s, str) and len(s) == 7 and s[4] == "-" and s[:4].isdigit() and s[5:7].isdigit()


def _load_index(graphs_dir: Path) -> Dict[str, Any]:
    idx = graphs_dir / "index.json"
    if not idx.exists():
        raise FileNotFoundError(f"index.json 不存在: {idx}")
    with open(idx, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_month_map(repo_graph_entry: Any, preferred_type: str) -> Dict[str, str]:
    """
    从 index.json 的一个 repo entry 里，取出 {month: path}。
    兼容旧格式（直接 month->path）与新格式（graph_type->{month:path}）。
    该函数会在找不到 preferred_type 时 fallback 并 warning（用于主分析流程）。
    """
    if not isinstance(repo_graph_entry, dict) or not repo_graph_entry:
        return {}

    if all(_looks_like_month(k) for k in repo_graph_entry.keys()):
        return {m: p for m, p in repo_graph_entry.items() if isinstance(p, (str, bytes))}

    v = repo_graph_entry.get(preferred_type)
    if isinstance(v, dict) and v:
        return {m: p for m, p in v.items() if _looks_like_month(m) and isinstance(p, (str, bytes))}

    candidates = []
    for t, sub in repo_graph_entry.items():
        if not isinstance(sub, dict) or not sub:
            continue
        month_keys = [k for k in sub.keys() if _looks_like_month(k)]
        if month_keys:
            candidates.append((len(month_keys), t, sub))
    if candidates:
        candidates.sort(reverse=True)
        _, t, sub = candidates[0]
        logger.warning(f"repo entry 未找到 {preferred_type}，fallback 使用: {t}")
        return {m: p for m, p in sub.items() if _looks_like_month(m) and isinstance(p, (str, bytes))}
    return {}


def _get_month_map_strict(repo_graph_entry: Any, graph_type: str) -> Dict[str, str]:
    """严格取 graph_type->{month:path}；不 fallback、不 warning（用于 core 判定避免刷屏）。"""
    if not isinstance(repo_graph_entry, dict) or not repo_graph_entry:
        return {}
    v = repo_graph_entry.get(graph_type)
    if isinstance(v, dict) and v:
        return {m: p for m, p in v.items() if _looks_like_month(m) and isinstance(p, (str, bytes))}
    return {}


def _entropy_from_distribution(dist: Dict[str, float]) -> float:
    total = sum(dist.values())
    if total <= 0:
        return 0.0
    ps = [v / total for v in dist.values() if v > 0]
    h = -sum(p * math.log(p) for p in ps)
    k = max(1, len(ps))
    return h / math.log(k) if k > 1 else 0.0


def _quantile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    if q <= 0:
        return vs[0]
    if q >= 1:
        return vs[-1]
    idx = int(round((len(vs) - 1) * q))
    idx = max(0, min(len(vs) - 1, idx))
    return vs[idx]


def _zscore_map(x: Dict[str, float]) -> Dict[str, float]:
    vals = list(x.values())
    if len(vals) < 2:
        return {k: 0.0 for k in x.keys()}
    mu = sum(vals) / len(vals)
    var = sum((v - mu) ** 2 for v in vals) / len(vals)
    sd = math.sqrt(var) if var > 1e-12 else 1.0
    return {k: (v - mu) / sd for k, v in x.items()}


@dataclass
class RepoComponents:
    activity: float
    coverage: float
    structure: float
    importance: float
    total_event_importance: float
    unique_actors: int


@dataclass
class DiscussionComponents:
    activity: float
    coverage: float
    structure: float
    importance: float
    total_event_importance: float
    unique_actors: int


def identify_core_members(graph: nx.MultiDiGraph) -> List[str]:
    if graph.number_of_nodes() == 0:
        return []
    degrees = dict(graph.degree())
    if not degrees:
        return []

    degree_values = list(degrees.values())
    degree_max = max(degree_values) if degree_values else 0
    total_degree = sum(degree_values)
    total_actors = len(degrees)

    try:
        undirected = graph.to_undirected()
        core_numbers = nx.core_number(undirected)
        max_k = max(core_numbers.values()) if core_numbers else 0
    except Exception:
        core_numbers = {n: 1 for n in graph.nodes()}
        max_k = 1

    scores: Dict[str, float] = {}
    for node_id in graph.nodes():
        deg = degrees.get(node_id, 0)
        k = core_numbers.get(node_id, 0)
        deg_norm = (deg / degree_max) if degree_max > 0 else 0.0
        k_norm = (k / max_k) if max_k > 0 else 0.0
        scores[node_id] = 0.6 * deg_norm + 0.4 * k_norm

    avg_score = sum(scores.values()) / len(scores) if scores else 0.0
    sorted_nodes = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    core_nodes: List[str] = []
    accumulated_degree = 0.0
    max_core_size = max(3, int(math.ceil(0.3 * total_actors)))

    for node_id, score in sorted_nodes:
        if len(core_nodes) >= max_core_size:
            break
        core_nodes.append(node_id)
        accumulated_degree += degrees.get(node_id, 0)

        if total_degree > 0 and (accumulated_degree / total_degree) >= 0.7:
            if score < avg_score and len(core_nodes) >= 3:
                break

    if len(core_nodes) < 2:
        for node_id, _ in sorted_nodes:
            if node_id not in core_nodes:
                core_nodes.append(node_id)
            if len(core_nodes) >= 2:
                break

    return core_nodes


def project_actor_discussion_to_actor_graph(g: nx.Graph) -> nx.Graph:
    node_type = nx.get_node_attributes(g, "node_type")
    actors = [n for n, t in node_type.items() if str(t) == "Actor"]
    discussions = [n for n, t in node_type.items() if str(t) in {"Discussion", "Issue", "PullRequest"}]

    actor_set = set(actors)
    disc_set = set(discussions)

    disc_to_actors: Dict[str, List[str]] = defaultdict(list)
    for u, v in g.edges():
        if u in actor_set and v in disc_set:
            disc_to_actors[v].append(u)
        elif v in actor_set and u in disc_set:
            disc_to_actors[u].append(v)

    proj = nx.Graph()
    proj.add_nodes_from(actors)

    for disc, alist in disc_to_actors.items():
        uniq = list(dict.fromkeys(alist))
        if len(uniq) < 2:
            continue
        if len(uniq) > 200:
            for i in range(len(uniq) - 1):
                a1, a2 = uniq[i], uniq[i + 1]
                w = proj.get_edge_data(a1, a2, {}).get("weight", 0) + 1
                proj.add_edge(a1, a2, weight=w)
            continue

        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                a1, a2 = uniq[i], uniq[j]
                w = proj.get_edge_data(a1, a2, {}).get("weight", 0) + 1
                proj.add_edge(a1, a2, weight=w)

    return proj


class QualityRiskAnalyzer:
    def __init__(
        self,
        graphs_dir: str = "output/monthly-graphs/",
        output_dir: str = "output/quality-risk/",
        alpha: float = 0.2,
        low_quantile: float = 0.3,
        high_quantile: float = 0.9,
        top_n: int = 50,
        high_tei_quantile: float = 0.8,
        min_distinct_repos: int = 5,
    ):
        self.graphs_dir = Path(graphs_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.alpha = alpha
        self.low_quantile = low_quantile
        self.high_quantile = high_quantile
        self.top_n = top_n

        self.high_tei_quantile = high_tei_quantile
        self.min_distinct_repos = min_distinct_repos

    def _load_graph(self, path: str) -> Optional[nx.MultiDiGraph]:
        try:
            return nx.read_graphml(path, force_multigraph=True)
        except Exception as e:
            logger.warning(f"加载图失败: {path}, 错误: {e}")
            return None

    def compute_repo_importance(self, index: Dict[str, Any]) -> Dict[str, RepoComponents]:
        repo_sum_ie: Dict[str, float] = defaultdict(float)
        repo_type_ie: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        repo_actors: Dict[str, Set[str]] = defaultdict(set)

        for _, entry in index.items():
            months = _get_month_map(entry, preferred_type="actor-repo")
            for _, p in months.items():
                g = self._load_graph(p)
                if g is None or g.number_of_edges() == 0:
                    continue

                node_type = nx.get_node_attributes(g, "node_type")
                actors = {n for n, t in node_type.items() if str(t) == "Actor"}
                repos = {n for n, t in node_type.items() if str(t) in {"Repo", "Repository"}}

                for u, v, _, attr in iter_edges(g):
                    t = str(attr.get("edge_type", "OTHER")).upper()
                    ie = event_importance(attr, alpha=self.alpha)

                    if u in actors and v in repos:
                        a, r = u, v
                    elif v in actors and u in repos:
                        a, r = v, u
                    else:
                        continue

                    repo_sum_ie[r] += ie
                    repo_type_ie[r][t] += ie
                    repo_actors[r].add(a)

        activity_raw = {r: math.log(1.0 + s) for r, s in repo_sum_ie.items()}
        coverage_raw = {r: math.log(1.0 + len(repo_actors[r])) for r in repo_sum_ie.keys()}

        max_act = max(activity_raw.values()) if activity_raw else 1.0
        max_cov = max(coverage_raw.values()) if coverage_raw else 1.0

        out: Dict[str, RepoComponents] = {}
        for r in repo_sum_ie.keys():
            a = (activity_raw.get(r, 0.0) / max_act) if max_act > 0 else 0.0
            c = (coverage_raw.get(r, 0.0) / max_cov) if max_cov > 0 else 0.0
            s = _entropy_from_distribution(repo_type_ie[r])
            imp = a * c * (0.1 + 0.9 * s)
            out[r] = RepoComponents(
                activity=round(a, 6),
                coverage=round(c, 6),
                structure=round(s, 6),
                importance=round(imp, 6),
                total_event_importance=round(repo_sum_ie[r], 6),
                unique_actors=len(repo_actors[r]),
            )
        return out

    def compute_discussion_importance(self, index: Dict[str, Any]) -> Dict[str, DiscussionComponents]:
        dis_sum_ie: Dict[str, float] = defaultdict(float)
        dis_type_ie: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        dis_actors: Dict[str, Set[str]] = defaultdict(set)

        for _, entry in index.items():
            months = _get_month_map(entry, preferred_type="actor-discussion")
            if not months:
                continue
            for _, p in months.items():
                g = self._load_graph(p)
                if g is None or g.number_of_edges() == 0:
                    continue

                node_type = nx.get_node_attributes(g, "node_type")
                actors = {n for n, t in node_type.items() if str(t) == "Actor"}
                discussions = {n for n, t in node_type.items() if str(t) in {"Discussion", "Issue", "PullRequest"}}

                for u, v, _, attr in iter_edges(g):
                    t = str(attr.get("edge_type", "OTHER")).upper()
                    ie = event_importance(attr, alpha=self.alpha)

                    if u in actors and v in discussions:
                        a, d = u, v
                    elif v in actors and u in discussions:
                        a, d = v, u
                    else:
                        continue

                    dis_sum_ie[d] += ie
                    dis_type_ie[d][t] += ie
                    dis_actors[d].add(a)

        activity_raw = {d: math.log(1.0 + s) for d, s in dis_sum_ie.items()}
        coverage_raw = {d: math.log(1.0 + len(dis_actors[d])) for d in dis_sum_ie.keys()}

        max_act = max(activity_raw.values()) if activity_raw else 1.0
        max_cov = max(coverage_raw.values()) if coverage_raw else 1.0

        out: Dict[str, DiscussionComponents] = {}
        for d in dis_sum_ie.keys():
            a = (activity_raw.get(d, 0.0) / max_act) if max_act > 0 else 0.0
            c = (coverage_raw.get(d, 0.0) / max_cov) if max_cov > 0 else 0.0
            s = _entropy_from_distribution(dis_type_ie[d])
            imp = a * c * (0.1 + 0.9 * s)
            out[d] = DiscussionComponents(
                activity=round(a, 6),
                coverage=round(c, 6),
                structure=round(s, 6),
                importance=round(imp, 6),
                total_event_importance=round(dis_sum_ie[d], 6),
                unique_actors=len(dis_actors[d]),
            )
        return out

    def _build_thresholds(self, obj_imp_map: Dict[str, float]) -> Tuple[Set[str], Set[str], float, float]:
        vals = list(obj_imp_map.values())
        low_th = _quantile(vals, self.low_quantile)
        high_th = _quantile(vals, self.high_quantile)
        low = {k for k, v in obj_imp_map.items() if v <= low_th}
        high = {k for k, v in obj_imp_map.items() if v >= high_th}
        return low, high, low_th, high_th

    def _first_high_repo_touch_time(self, index: Dict[str, Any], high_repos: Set[str]) -> Dict[str, Optional[datetime]]:
        t_star: Dict[str, Optional[datetime]] = defaultdict(lambda: None)

        for _, entry in index.items():
            months = _get_month_map(entry, preferred_type="actor-repo")
            for _, p in months.items():
                g = self._load_graph(p)
                if g is None or g.number_of_edges() == 0:
                    continue

                node_type = nx.get_node_attributes(g, "node_type")
                actors = {n for n, t in node_type.items() if str(t) == "Actor"}
                repos = {n for n, t in node_type.items() if str(t) in {"Repo", "Repository"}}

                for u, v, _, attr in iter_edges(g):
                    if u in actors and v in repos:
                        a, r = u, v
                    elif v in actors and u in repos:
                        a, r = v, u
                    else:
                        continue

                    if r not in high_repos:
                        continue

                    dt = _parse_datetime(attr.get("created_at"))
                    if dt is None:
                        continue

                    cur = t_star[a]
                    if cur is None or dt < cur:
                        t_star[a] = dt

        return dict(t_star)

    def compute_actor_features(
        self,
        index: Dict[str, Any],
        repo_imp: Dict[str, RepoComponents],
        dis_imp: Dict[str, DiscussionComponents],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        repo_imp_map = {r: float(c.importance) for r, c in repo_imp.items()}
        dis_imp_map = {d: float(c.importance) for d, c in dis_imp.items()}

        low_repos, high_repos, low_repo_th, high_repo_th = self._build_thresholds(repo_imp_map)
        low_dis, high_dis, low_dis_th, high_dis_th = self._build_thresholds(dis_imp_map)

        t_star = self._first_high_repo_touch_time(index, high_repos)

        actor_total_ie: Dict[str, float] = defaultdict(float)
        actor_low_obj_ie: Dict[str, float] = defaultdict(float)
        actor_low_cost_ie: Dict[str, float] = defaultdict(float)
        actor_type_ie: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

        actor_high_value_contrib: Dict[str, float] = defaultdict(float)
        actor_all_value_contrib: Dict[str, float] = defaultdict(float)

        actor_pre_low_repo_ie: Dict[str, float] = defaultdict(float)
        actor_distinct_repos: Dict[str, Set[str]] = defaultdict(set)

        for _, entry in index.items():
            months = _get_month_map(entry, preferred_type="actor-repo")
            for _, p in months.items():
                g = self._load_graph(p)
                if g is None or g.number_of_edges() == 0:
                    continue

                node_type = nx.get_node_attributes(g, "node_type")
                actors = {n for n, t in node_type.items() if str(t) == "Actor"}
                repos = {n for n, t in node_type.items() if str(t) in {"Repo", "Repository"}}

                for u, v, _, attr in iter_edges(g):
                    t = str(attr.get("edge_type", "OTHER")).upper()
                    ie = event_importance(attr, alpha=self.alpha)

                    if u in actors and v in repos:
                        a, r = u, v
                    elif v in actors and u in repos:
                        a, r = v, u
                    else:
                        continue

                    actor_distinct_repos[a].add(r)

                    actor_total_ie[a] += ie
                    actor_type_ie[a][t] += ie
                    if t in LOW_COST_EDGE_TYPES:
                        actor_low_cost_ie[a] += ie

                    if r in low_repos:
                        actor_low_obj_ie[a] += ie

                    obj_imp = repo_imp_map.get(r, 0.0)
                    actor_all_value_contrib[a] += ie * obj_imp
                    if r in high_repos:
                        actor_high_value_contrib[a] += ie * obj_imp

                    dt = _parse_datetime(attr.get("created_at"))
                    if dt is not None and t_star.get(a) is not None:
                        if dt < t_star[a] and r in low_repos:
                            actor_pre_low_repo_ie[a] += ie

        for _, entry in index.items():
            months = _get_month_map(entry, preferred_type="actor-discussion")
            if not months:
                continue
            for _, p in months.items():
                g = self._load_graph(p)
                if g is None or g.number_of_edges() == 0:
                    continue

                node_type = nx.get_node_attributes(g, "node_type")
                actors = {n for n, t in node_type.items() if str(t) == "Actor"}
                discussions = {n for n, t in node_type.items() if str(t) in {"Discussion", "Issue", "PullRequest"}}

                for u, v, _, attr in iter_edges(g):
                    t = str(attr.get("edge_type", "OTHER")).upper()
                    ie = event_importance(attr, alpha=self.alpha)

                    if u in actors and v in discussions:
                        a, d = u, v
                    elif v in actors and u in discussions:
                        a, d = v, u
                    else:
                        continue

                    actor_total_ie[a] += ie
                    actor_type_ie[a][t] += ie
                    if t in LOW_COST_EDGE_TYPES:
                        actor_low_cost_ie[a] += ie

                    if d in low_dis:
                        actor_low_obj_ie[a] += ie

                    obj_imp = dis_imp_map.get(d, 0.0)
                    actor_all_value_contrib[a] += ie * obj_imp
                    if d in high_dis:
                        actor_high_value_contrib[a] += ie * obj_imp

        actor_low_ratio: Dict[str, float] = {}
        actor_low_cost_ratio: Dict[str, float] = {}
        actor_entropy: Dict[str, float] = {}
        actor_jumpiness: Dict[str, float] = {}
        actor_high_contrib_log: Dict[str, float] = {}

        for a, total_ie in actor_total_ie.items():
            actor_low_ratio[a] = (actor_low_obj_ie[a] / total_ie) if total_ie > 0 else 0.0
            actor_low_cost_ratio[a] = (actor_low_cost_ie[a] / total_ie) if total_ie > 0 else 0.0
            actor_entropy[a] = _entropy_from_distribution(actor_type_ie[a])

            pre_low = float(actor_pre_low_repo_ie.get(a, 0.0))
            high_contrib = float(actor_high_value_contrib.get(a, 0.0))
            actor_jumpiness[a] = math.log1p(pre_low) - math.log1p(high_contrib)
            actor_high_contrib_log[a] = math.log1p(high_contrib)

        z_low_ratio = _zscore_map(actor_low_ratio)
        z_low_cost = _zscore_map(actor_low_cost_ratio)
        z_jump = _zscore_map(actor_jumpiness)
        z_high_contrib = _zscore_map(actor_high_contrib_log)

        suspicion: Dict[str, float] = {}
        for a in actor_total_ie.keys():
            suspicion[a] = z_low_ratio.get(a, 0.0) + z_low_cost.get(a, 0.0) + z_jump.get(a, 0.0) - z_high_contrib.get(a, 0.0)

        actor_out: Dict[str, Dict[str, Any]] = {}
        for a in actor_total_ie.keys():
            actor_out[a] = {
                "actor_node_id": a,
                "total_event_importance": round(actor_total_ie[a], 6),
                "distinct_repos_touched": len(actor_distinct_repos.get(a, set())),
                "low_value_event_ratio": round(actor_low_ratio.get(a, 0.0), 6),
                "low_cost_event_ratio": round(actor_low_cost_ratio.get(a, 0.0), 6),
                "type_entropy": round(actor_entropy.get(a, 0.0), 6),
                "jumpiness": round(actor_jumpiness.get(a, 0.0), 6),
                "high_value_contrib": round(actor_high_value_contrib.get(a, 0.0), 6),
                "all_value_contrib": round(actor_all_value_contrib.get(a, 0.0), 6),
                "first_high_repo_touch_time": t_star.get(a).isoformat() if t_star.get(a) else None,
                "suspicion_score": round(suspicion.get(a, 0.0), 6),
            }

        summary = {
            "alpha": self.alpha,
            "low_quantile": self.low_quantile,
            "high_quantile": self.high_quantile,
            "actors_count": len(actor_out),
        }
        return actor_out, summary

    def _write_json(self, filename: str, obj: Any) -> Path:
        p = self.output_dir / filename
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return p

    def _write_csv(self, filename: str, rows: List[Dict[str, Any]]) -> Path:
        p = self.output_dir / filename
        if not rows:
            with open(p, "w", encoding="utf-8") as f:
                f.write("")
            return p
        with open(p, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return p

    def _latest_month_path(self, month_map: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
        if not month_map:
            return None, None
        latest_m = max(month_map.keys())
        return latest_m, month_map[latest_m]

    def _core_in_latest_month_for_project(
        self, entry: Dict[str, Any]
    ) -> Tuple[Optional[Set[str]], Optional[str], Optional[str], Optional[str]]:
        """返回 (core_nodes, month, graph_type_used, reason_if_missing)"""
        aa = _get_month_map_strict(entry, "actor-actor")
        ad = _get_month_map_strict(entry, "actor-discussion")

        if aa:
            month, path = self._latest_month_path(aa)
            g = self._load_graph(path)
            if g is None or g.number_of_edges() == 0:
                return None, month, "actor-actor", "latest_actor-actor_graph_empty_or_failed"
            node_type = nx.get_node_attributes(g, "node_type")
            actors = {n for n, t in node_type.items() if str(t) == "Actor"}
            ug = nx.Graph()
            ug.add_nodes_from(actors)
            for u, v, _, _attr in iter_edges(g):
                if u in actors and v in actors and u != v:
                    w = ug.get_edge_data(u, v, {}).get("weight", 0) + 1
                    ug.add_edge(u, v, weight=w)

            mg = nx.MultiDiGraph()
            mg.add_nodes_from(ug.nodes())
            for u, v, attr in ug.edges(data=True):
                mg.add_edge(u, v, weight=attr.get("weight", 1))
            return set(identify_core_members(mg)), month, "actor-actor", None

        if ad:
            month, path = self._latest_month_path(ad)
            g = self._load_graph(path)
            if g is None or g.number_of_edges() == 0:
                return None, month, "actor-discussion", "latest_actor-discussion_graph_empty_or_failed"
            proj = project_actor_discussion_to_actor_graph(g)

            mg = nx.MultiDiGraph()
            mg.add_nodes_from(proj.nodes())
            for u, v, attr in proj.edges(data=True):
                mg.add_edge(u, v, weight=attr.get("weight", 1))
            return set(identify_core_members(mg)), month, "actor-discussion", None

        return None, None, None, "no_actor-actor_or_actor-discussion_graph"

    def run(self) -> None:
        logger.info("=" * 60)
        logger.info("开始 Quality / Permission-gaming risk 分析 (v3)")
        logger.info("=" * 60)

        index = _load_index(self.graphs_dir)

        logger.info("Pass 1/3: 计算 repo 重要性（actor-repo）")
        repo_imp = self.compute_repo_importance(index)
        self._write_json(
            "repo_importance.json",
            {r: vars(c) for r, c in repo_imp.items()},
        )

        logger.info("Pass 2/3: 计算 discussion 重要性（actor-discussion）")
        dis_imp = self.compute_discussion_importance(index)
        self._write_json(
            "discussion_importance.json",
            {d: vars(c) for d, c in dis_imp.items()},
        )

        logger.info("Pass 3/3: 聚合 actor 特征并计算可疑分")
        actor_out, summary = self.compute_actor_features(index, repo_imp, dis_imp)

        tei_values = [float(v.get("total_event_importance", 0.0)) for v in actor_out.values()]
        tei_cutoff_bottom5 = _quantile(tei_values, 0.05)
        eligible_base = {a: v for a, v in actor_out.items() if float(v.get("total_event_importance", 0.0)) > tei_cutoff_bottom5}

        tei_cutoff_top = _quantile([float(v.get("total_event_importance", 0.0)) for v in eligible_base.values()], self.high_tei_quantile)

        candidates = {}
        for a, v in eligible_base.items():
            cond_high_touch = bool(v.get("first_high_repo_touch_time"))
            cond_top_tei = float(v.get("total_event_importance", 0.0)) >= tei_cutoff_top
            cond_distinct = int(v.get("distinct_repos_touched", 0)) >= self.min_distinct_repos
            if cond_high_touch or cond_top_tei or cond_distinct:
                candidates[a] = v

        ranked = sorted(
            candidates.values(),
            key=lambda x: float(x.get("suspicion_score", 0.0)),
            reverse=True,
        )
        top = ranked[: self.top_n]

        attacker_ids = {row.get("actor_node_id") for row in top if row.get("actor_node_id")}
        attackers_core_recent: Dict[str, List[Dict[str, str]]] = defaultdict(list)
        missing_core_projects: List[Dict[str, Any]] = []

        logger.info("附加：在每个项目的【最新月份】判断攻击者是否仍为核心成员")
        for repo_name, entry in index.items():
            core_nodes, month, graph_type, reason = self._core_in_latest_month_for_project(entry)
            if reason is not None:
                missing_core_projects.append({"project": repo_name, "reason": reason, "month": month, "graph_type": graph_type})
                continue
            if not core_nodes:
                continue
            hit = attacker_ids.intersection(core_nodes)
            if not hit:
                continue
            for a in hit:
                attackers_core_recent[a].append({"project": repo_name, "month": month or "", "graph_type": graph_type or ""})

        for row in top:
            a = row.get("actor_node_id")
            recs = attackers_core_recent.get(a, [])
            row["core_projects_recent"] = ";".join(sorted({r["project"] for r in recs}))
            row["core_month_used"] = ",".join(sorted({r["month"] for r in recs if r.get("month")}))
            row["core_graph_type_used"] = ",".join(sorted({r["graph_type"] for r in recs if r.get("graph_type")}))

        summary.update(
            {
                "version": "v3",
                "actors_total": len(actor_out),
                "actors_eligible_after_bottom5": len(eligible_base),
                "actors_candidates_after_any_condition": len(candidates),
                "total_event_importance_cutoff_bottom5": tei_cutoff_bottom5,
                "total_event_importance_cutoff_top_quantile": tei_cutoff_top,
                "high_tei_quantile": self.high_tei_quantile,
                "min_distinct_repos": self.min_distinct_repos,
                "attackers_top_n": len(top),
                "projects_missing_core_judgement": len(missing_core_projects),
            }
        )

        self._write_json("actor_quality.json", actor_out)
        self._write_csv("top_suspects.csv", top)
        self._write_json("attackers_core_recent.json", attackers_core_recent)
        self._write_json("missing_core_projects.json", missing_core_projects)
        self._write_json("summary.json", summary)

        logger.info("=" * 60)
        logger.info("分析完成!")
        logger.info(f"actor 数: {len(actor_out)} | 候选 actor 数: {len(candidates)} | top_n: {len(top)}")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Quality / Permission-gaming risk analyzer (v3)")
    parser.add_argument("--graphs-dir", type=str, default="output/monthly-graphs/", help="月度图目录（含 index.json）")
    parser.add_argument("--output-dir", type=str, default="output/quality-risk/", help="输出目录")
    parser.add_argument("--alpha", type=float, default=0.2, help="文本信息量加分强度（I_e）")
    parser.add_argument("--low-quantile", type=float, default=0.3, help="低价值对象阈值分位数（<=该分位视为 low）")
    parser.add_argument("--high-quantile", type=float, default=0.9, help="高价值对象阈值分位数（>=该分位视为 high）")
    parser.add_argument("--top-n", type=int, default=50, help="输出前 N 个可疑 actor 到 CSV")
    parser.add_argument("--high-tei-quantile", type=float, default=0.8, help="候选条件：total_event_importance 位于 top quantile")
    parser.add_argument("--min-distinct-repos", type=int, default=5, help="候选条件：distinct_repos_touched >= K")
    args = parser.parse_args()

    analyzer = QualityRiskAnalyzer(
        graphs_dir=args.graphs_dir,
        output_dir=args.output_dir,
        alpha=args.alpha,
        low_quantile=args.low_quantile,
        high_quantile=args.high_quantile,
        top_n=args.top_n,
        high_tei_quantile=args.high_tei_quantile,
        min_distinct_repos=args.min_distinct_repos,
    )
    analyzer.run()


if __name__ == "__main__":
    main()
