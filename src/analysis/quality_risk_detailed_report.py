"""
Quality-risk detailed report generator

Reads outputs from quality_risk_analyzer (summary.json, actor_quality.json, top_suspects.csv, etc.)
and produces a human-readable detailed_report.txt focusing on each top suspect actor.

Design goals (per user requirements):
- Put global metric explanations at the report header
- No extra time-series computations
- Friendlier IDs for repo/discussion
- Sort suspects prioritizing those who are STILL core in the latest month of any project
- Include additional useful results (candidate conditions, missing core judgement, etc.)

Usage:
  python scripts/quality_risk_detailed_report.py --input-dir output/quality-risk --graphs-dir output/monthly-graphs

Optional:
  --top 50
  --actor <actor_id1,actor_id2,...>
  --no-breakdown  (skip graph scanning breakdown if you only want summary-based metrics)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import networkx as nx


# -----------------------------
# Shared utilities
# -----------------------------

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


def _quantile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    if q <= 0:
        return float(vs[0])
    if q >= 1:
        return float(vs[-1])
    idx = int(round((len(vs) - 1) * q))
    idx = max(0, min(len(vs) - 1, idx))
    return float(vs[idx])


def _zscore(values: Dict[str, float]) -> Dict[str, float]:
    if not values:
        return {}
    vals = list(values.values())
    if len(vals) < 2:
        return {k: 0.0 for k in values.keys()}
    mu = sum(vals) / len(vals)
    var = sum((v - mu) ** 2 for v in vals) / len(vals)
    sd = math.sqrt(var) if var > 1e-12 else 1.0
    return {k: (v - mu) / sd for k, v in values.items()}


def _looks_like_month(s: str) -> bool:
    return isinstance(s, str) and len(s) == 7 and s[4] == "-" and s[:4].isdigit() and s[5:7].isdigit()


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_csv(path: Path) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]


def _fmt_pct(x: float) -> str:
    return f"{x*100:.2f}%"


def _fmt_float(x: Any, nd: int = 6) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except Exception:
        return "N/A"


def _short_id(x: str, max_len: int = 30) -> str:
    s = _safe_str(x)
    if len(s) <= max_len:
        return s
    # Try keep last 2 path segments if looks like repo/discussion
    if "/" in s:
        parts = [p for p in s.split("/") if p]
        if len(parts) >= 2:
            cand = "/".join(parts[-2:])
            if len(cand) <= max_len:
                return "…/" + cand
    return s[:12] + "…" + s[-10:]


def _is_truthy(x: Any) -> bool:
    if x is None:
        return False
    if isinstance(x, str):
        return x.strip() != "" and x.lower() not in {"none", "null", "nan"}
    return bool(x)


def iter_edges(g: nx.Graph):
    """Yield edges in a Multi(Graph/DiGraph) or simple Graph/DiGraph as (u,v,k,attr)."""
    if g.is_multigraph():
        for u, v, k, attr in g.edges(keys=True, data=True):
            yield u, v, k, attr
    else:
        for u, v, attr in g.edges(data=True):
            yield u, v, None, attr


def _read_graphml(path: str) -> Optional[nx.Graph]:
    try:
        # networkx versions differ; force_multigraph not always supported
        try:
            return nx.read_graphml(path, force_multigraph=True)
        except TypeError:
            return nx.read_graphml(path)
    except Exception:
        return None


def _get_month_map(entry: Any, preferred_type: str) -> Dict[str, str]:
    """Index entry -> {month: path}; supports both old and new index formats, with fallback."""
    if not isinstance(entry, dict) or not entry:
        return {}
    # Old: {month: path}
    if all(_looks_like_month(k) for k in entry.keys()):
        return {m: p for m, p in entry.items() if isinstance(p, (str, bytes))}
    # New: {graph_type: {month: path}}
    sub = entry.get(preferred_type)
    if isinstance(sub, dict) and sub:
        return {m: p for m, p in sub.items() if _looks_like_month(m) and isinstance(p, (str, bytes))}
    # Fallback: pick first dict that looks like month map
    for _, v in entry.items():
        if isinstance(v, dict) and any(_looks_like_month(k) for k in v.keys()):
            return {m: p for m, p in v.items() if _looks_like_month(m) and isinstance(p, (str, bytes))}
    return {}


# -----------------------------
# Breakdown computation (optional)
# -----------------------------

class BreakdownStore:
    """
    Holds per-actor contribution breakdown computed by scanning graphmls:
    - repo_ie_sum[actor][repo] = sum I_e
    - dis_ie_sum[actor][discussion] = sum I_e
    - edge_type_counts[actor][edge_type] = count edges
    - low_cost_ie_sum[actor] = sum I_e for low-cost types (STAR/WATCH/FORK)
    """
    def __init__(self):
        self.repo_ie_sum: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.dis_ie_sum: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.edge_type_counts: Dict[str, Counter] = defaultdict(Counter)
        self.low_cost_ie_sum: Dict[str, float] = defaultdict(float)
        self.total_ie_sum: Dict[str, float] = defaultdict(float)


def compute_breakdowns(
    graphs_dir: Path,
    target_actors: Set[str],
    alpha: float,
) -> BreakdownStore:
    store = BreakdownStore()
    index_path = graphs_dir / "index.json"
    if not index_path.exists():
        return store
    index = _load_json(index_path)

    for _, entry in index.items():
        # actor-repo
        months = _get_month_map(entry, "actor-repo")
        for _, p in months.items():
            g = _read_graphml(str(p))
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
                if a not in target_actors:
                    continue

                et = _safe_str(attr.get("edge_type", "OTHER")).upper()
                ie = event_importance(attr, alpha=alpha)

                store.repo_ie_sum[a][r] += ie
                store.edge_type_counts[a][et] += 1
                store.total_ie_sum[a] += ie
                if et in LOW_COST_EDGE_TYPES:
                    store.low_cost_ie_sum[a] += ie

        # actor-discussion
        months = _get_month_map(entry, "actor-discussion")
        for _, p in months.items():
            g = _read_graphml(str(p))
            if g is None or g.number_of_edges() == 0:
                continue

            node_type = nx.get_node_attributes(g, "node_type")
            actors = {n for n, t in node_type.items() if str(t) == "Actor"}
            discussions = {n for n, t in node_type.items() if str(t) in {"Discussion", "Issue", "PullRequest"}}

            for u, v, _, attr in iter_edges(g):
                if u in actors and v in discussions:
                    a, d = u, v
                elif v in actors and u in discussions:
                    a, d = v, u
                else:
                    continue
                if a not in target_actors:
                    continue

                et = _safe_str(attr.get("edge_type", "OTHER")).upper()
                ie = event_importance(attr, alpha=alpha)

                store.dis_ie_sum[a][d] += ie
                store.edge_type_counts[a][et] += 1
                store.total_ie_sum[a] += ie
                if et in LOW_COST_EDGE_TYPES:
                    store.low_cost_ie_sum[a] += ie

    return store


# -----------------------------
# Report building
# -----------------------------

def build_global_explanations() -> List[str]:
    lines = []
    lines.append("📚 指标释义（全局）")
    lines.append("-" * 80)
    lines.append("本报告聚焦 top_suspects 中的“可疑攻击者”actor。核心思想：")
    lines.append("  - 事件重要性 I_e = w(edge_type) * (1 + α * log(1 + 文本长度))")
    lines.append("  - 对象重要性（Repo/Discussion）≈ 活跃度 * 覆盖面 * 结构性（结构性用 edge_type 分布熵表示，并做了软化处理）")
    lines.append("  - actor 的价值贡献：Σ(I_e * 对象重要性)，分别统计 high-value 与 all-value")
    lines.append("")
    lines.append("actor 级指标：")
    lines.append("  - total_event_importance (TEI): 该 actor 在 repo+discussion 上的 I_e 总和（越大代表活动总量越多）")
    lines.append("  - low_value_event_ratio: 落在 low-value 对象上的 I_e / TEI（越大越像刷低价值）")
    lines.append("  - low_cost_event_ratio: STAR/WATCH/FORK 等低成本事件的 I_e / TEI（越大越像廉价刷贡献）")
    lines.append("  - type_entropy: edge_type 分布熵（越低越单一）")
    lines.append("  - jumpiness: log(1+pre_low_repo_ie) - log(1+high_value_contrib)（越大越像先刷低价值再触达高价值）")
    lines.append("  - high_value_contrib / all_value_contrib: 分别是高价值对象 / 所有对象上的 Σ(I_e * 对象重要性)")
    lines.append("")
    lines.append("可疑分 suspicion_score（越大越可疑，按 z-score 归一化后组合）：")
    lines.append("  suspicion = z(low_value_event_ratio) + z(low_cost_event_ratio) + z(jumpiness) - z(log(1+high_value_contrib))")
    lines.append("")
    lines.append("“仍为核心成员”的判定：按每个项目的最新月份图判断，优先 actor-actor；缺失则用 actor-discussion 投影。")
    return lines


def _compute_low_high_sets(obj_imp_map: Dict[str, float], low_q: float, high_q: float) -> Tuple[Set[str], Set[str], float, float]:
    vals = list(obj_imp_map.values())
    low_th = _quantile(vals, low_q)
    high_th = _quantile(vals, high_q)
    low = {k for k, v in obj_imp_map.items() if v <= low_th}
    high = {k for k, v in obj_imp_map.items() if v >= high_th}
    return low, high, low_th, high_th


def generate_actor_section(
    actor_id: str,
    actor_row: Dict[str, Any],
    actor_quality: Dict[str, Any],
    z_terms: Dict[str, Dict[str, float]],
    core_recent: Dict[str, List[Dict[str, str]]],
    repo_imp_map: Dict[str, float],
    dis_imp_map: Dict[str, float],
    low_repos: Set[str],
    high_repos: Set[str],
    low_dis: Set[str],
    high_dis: Set[str],
    breakdown: Optional[BreakdownStore],
    top_k: int = 10,
) -> str:
    lines: List[str] = []
    lines.append("=" * 90)
    lines.append(f"🧑‍💻 可疑攻击者: {actor_id}")
    lines.append("=" * 90)

    suspicion = float(actor_row.get("suspicion_score", actor_quality.get("suspicion_score", 0.0)) or 0.0)
    tei = float(actor_quality.get("total_event_importance", actor_row.get("total_event_importance", 0.0)) or 0.0)

    recs = core_recent.get(actor_id, [])
    if recs:
        lines.append(f"\n🛑 最新月仍为核心成员: ✅ 是（命中 {len(recs)} 个项目）")
        # friendly list
        shown = []
        for r in recs[:8]:
            proj = r.get("project", "")
            month = r.get("month", "")
            gt = r.get("graph_type", "")
            shown.append(f"{proj}({month},{gt})")
        lines.append("   " + "；".join(shown))
        if len(recs) > 8:
            lines.append(f"   ... 还有 {len(recs)-8} 个项目")
    else:
        lines.append(f"\n🛡️ 最新月仍为核心成员: ❌ 否（或该 actor 未命中任何项目核心集合）")

    tstar = actor_quality.get("first_high_repo_touch_time")
    lines.append(f"\n🎯 综合可疑分 (suspicion_score): {suspicion:.6f}")
    lines.append(f"   total_event_importance (TEI): {tei:.6f}")
    lines.append(f"   first_high_repo_touch_time: {tstar if _is_truthy(tstar) else 'N/A'}")

    # Candidate condition flags (from top_suspects.csv row columns may exist)
    # We'll recompute defensively from available fields.
    distinct_repos = int(float(actor_quality.get("distinct_repos_touched", actor_row.get("distinct_repos_touched", 0) or 0)))
    lines.append(f"   distinct_repos_touched: {distinct_repos}")

    lines.append("\n" + "-" * 90)
    lines.append("📌 指标总览（原始值）")
    lines.append("-" * 90)

    def kv(k, v, nd=6):
        if isinstance(v, (int,)) and not isinstance(v, bool):
            lines.append(f"   - {k}: {v}")
        else:
            lines.append(f"   - {k}: {_fmt_float(v, nd)}")

    kv("low_value_event_ratio", actor_quality.get("low_value_event_ratio", 0.0))
    kv("low_cost_event_ratio", actor_quality.get("low_cost_event_ratio", 0.0))
    kv("type_entropy", actor_quality.get("type_entropy", 0.0))
    kv("jumpiness", actor_quality.get("jumpiness", 0.0))
    kv("high_value_contrib", actor_quality.get("high_value_contrib", 0.0))
    kv("all_value_contrib", actor_quality.get("all_value_contrib", 0.0))

    lines.append("\n" + "-" * 90)
    lines.append("🧮 可疑分拆解（z-score 子项）")
    lines.append("-" * 90)
    z_low = z_terms["z_low_value"].get(actor_id, 0.0)
    z_low_cost = z_terms["z_low_cost"].get(actor_id, 0.0)
    z_jump = z_terms["z_jump"].get(actor_id, 0.0)
    z_high = z_terms["z_high_contrib"].get(actor_id, 0.0)
    lines.append(f"   z(low_value_event_ratio): {z_low:+.4f}")
    lines.append(f"   z(low_cost_event_ratio):  {z_low_cost:+.4f}")
    lines.append(f"   z(jumpiness):             {z_jump:+.4f}")
    lines.append(f"   -z(log1p(high_value_contrib)): {(-z_high):+.4f}   (raw z={z_high:+.4f})")
    lines.append(f"   => suspicion_score ≈ {z_low + z_low_cost + z_jump - z_high:+.4f}  (报告值 {suspicion:+.4f})")

    # Optional breakdown
    if breakdown is not None:
        lines.append("\n" + "-" * 90)
        lines.append("🧩 贡献构成拆解（按对象聚合；Top 列表）")
        lines.append("-" * 90)

        # Repo top
        repo_map = breakdown.repo_ie_sum.get(actor_id, {})
        if repo_map:
            rows = []
            for rid, ie_sum in repo_map.items():
                imp = float(repo_imp_map.get(rid, 0.0))
                weighted = ie_sum * imp
                label = "HIGH" if rid in high_repos else ("LOW" if rid in low_repos else "MID")
                rows.append((weighted, rid, ie_sum, imp, label))
            rows.sort(reverse=True, key=lambda x: x[0])
            lines.append("\n   🗂️ Repo 侧 Top（按 ie_sum * repo_importance 排序）")
            lines.append("   " + f"{'repo':<32} {'tag':<4} {'repo_imp':>10} {'ie_sum':>12} {'weighted':>12}")
            lines.append("   " + "-" * 78)
            for weighted, rid, ie_sum, imp, label in rows[:top_k]:
                lines.append(
                    "   "
                    + f"{_short_id(rid):<32} {label:<4} {imp:>10.6f} {ie_sum:>12.6f} {weighted:>12.6f}"
                )
            if len(rows) > top_k:
                lines.append(f"   ... 还有 {len(rows)-top_k} 个 repo")
        else:
            lines.append("\n   🗂️ Repo 侧 Top：N/A（未在图扫描中捕获到该 actor 的 repo 边）")

        # Discussion top
        dis_map = breakdown.dis_ie_sum.get(actor_id, {})
        if dis_map:
            rows = []
            for did, ie_sum in dis_map.items():
                imp = float(dis_imp_map.get(did, 0.0))
                weighted = ie_sum * imp
                label = "HIGH" if did in high_dis else ("LOW" if did in low_dis else "MID")
                rows.append((weighted, did, ie_sum, imp, label))
            rows.sort(reverse=True, key=lambda x: x[0])
            lines.append("\n   💬 Discussion 侧 Top（按 ie_sum * discussion_importance 排序）")
            lines.append("   " + f"{'discussion':<32} {'tag':<4} {'dis_imp':>10} {'ie_sum':>12} {'weighted':>12}")
            lines.append("   " + "-" * 78)
            for weighted, did, ie_sum, imp, label in rows[:top_k]:
                lines.append(
                    "   "
                    + f"{_short_id(did):<32} {label:<4} {imp:>10.6f} {ie_sum:>12.6f} {weighted:>12.6f}"
                )
            if len(rows) > top_k:
                lines.append(f"   ... 还有 {len(rows)-top_k} 个 discussion")
        else:
            lines.append("\n   💬 Discussion 侧 Top：N/A（未在图扫描中捕获到该 actor 的 discussion 边）")

        # Edge types
        et = breakdown.edge_type_counts.get(actor_id, Counter())
        if et:
            total_edges = sum(et.values()) or 1
            top_types = et.most_common(10)
            lines.append("\n   🧷 事件类型分布（按边条数；Top10）")
            for t, c in top_types:
                lines.append(f"      - {t:<24} {c:>6}  ({_fmt_pct(c/total_edges)})")
            low_cost_edges = sum(et.get(t, 0) for t in LOW_COST_EDGE_TYPES)
            lines.append(f"      - LOW_COST(STAR/WATCH/FORK): {low_cost_edges}  ({_fmt_pct(low_cost_edges/total_edges)})")

    lines.append("")  # trailing newline
    return "\n".join(lines)


def generate_report(
    input_dir: Path,
    graphs_dir: Optional[Path],
    output_path: Path,
    top_n: Optional[int],
    actor_filter: Optional[Set[str]],
    top_k_objects: int,
    no_breakdown: bool,
) -> str:
    # Required files
    summary_path = input_dir / "summary.json"
    actor_quality_path = input_dir / "actor_quality.json"
    top_csv_path = input_dir / "top_suspects.csv"
    repo_imp_path = input_dir / "repo_importance.json"
    dis_imp_path = input_dir / "discussion_importance.json"

    for p in [summary_path, actor_quality_path, top_csv_path, repo_imp_path, dis_imp_path]:
        if not p.exists():
            raise FileNotFoundError(f"缺少文件: {p}")

    summary = _load_json(summary_path)
    actor_quality = _load_json(actor_quality_path)
    top_rows = _load_csv(top_csv_path)
    repo_imp = _load_json(repo_imp_path)
    dis_imp = _load_json(dis_imp_path)

    core_recent_path = input_dir / "attackers_core_recent.json"
    core_recent: Dict[str, List[Dict[str, str]]] = {}
    if core_recent_path.exists():
        core_recent = _load_json(core_recent_path)

    missing_core_path = input_dir / "missing_core_projects.json"
    missing_core = []
    if missing_core_path.exists():
        missing_core = _load_json(missing_core_path)

    # Normalize maps
    repo_imp_map = {k: float(v.get("importance", 0.0)) for k, v in repo_imp.items() if isinstance(v, dict)}
    dis_imp_map = {k: float(v.get("importance", 0.0)) for k, v in dis_imp.items() if isinstance(v, dict)}

    low_q = float(summary.get("low_quantile", 0.3))
    high_q = float(summary.get("high_quantile", 0.9))
    low_repos, high_repos, low_repo_th, high_repo_th = _compute_low_high_sets(repo_imp_map, low_q, high_q)
    low_dis, high_dis, low_dis_th, high_dis_th = _compute_low_high_sets(dis_imp_map, low_q, high_q)

    # Choose top suspects list
    if actor_filter:
        top_rows = [r for r in top_rows if r.get("actor_node_id") in actor_filter]

    if top_n is not None:
        top_rows = top_rows[:top_n]

    # Sort: still-core first, then suspicion desc
    def _row_key(r: Dict[str, Any]) -> Tuple[int, float]:
        aid = r.get("actor_node_id", "")
        still_core = 1 if (aid in core_recent and core_recent.get(aid)) else 0
        # still_core first => sort key should be (-still_core)
        sus = float(r.get("suspicion_score", 0.0) or 0.0)
        return (-still_core, sus)

    top_rows = sorted(top_rows, key=_row_key, reverse=True)

    # Build z-score terms (recomputed from actor_quality.json)
    low_value_map = {a: float(v.get("low_value_event_ratio", 0.0)) for a, v in actor_quality.items()}
    low_cost_map = {a: float(v.get("low_cost_event_ratio", 0.0)) for a, v in actor_quality.items()}
    jump_map = {a: float(v.get("jumpiness", 0.0)) for a, v in actor_quality.items()}
    high_contrib_log_map = {a: math.log1p(float(v.get("high_value_contrib", 0.0))) for a, v in actor_quality.items()}

    z_terms = {
        "z_low_value": _zscore(low_value_map),
        "z_low_cost": _zscore(low_cost_map),
        "z_jump": _zscore(jump_map),
        "z_high_contrib": _zscore(high_contrib_log_map),
    }

    # Optional breakdown via scanning graphs
    breakdown = None
    alpha = float(summary.get("alpha", 0.2))
    if not no_breakdown and graphs_dir is not None and graphs_dir.exists():
        target = {r.get("actor_node_id", "") for r in top_rows if r.get("actor_node_id")}
        breakdown = compute_breakdowns(graphs_dir, target, alpha=alpha)

    # Build report
    lines: List[str] = []
    lines.append("=" * 90)
    lines.append("🛡️ OSS 权限投机 / 低质参与者风险 详细报告（Quality Risk）")
    lines.append("=" * 90)
    lines.append(f"生成时间: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"输入目录: {input_dir}")
    if graphs_dir is not None:
        lines.append(f"图目录: {graphs_dir}  ({'跳过对象拆解' if no_breakdown else '用于对象拆解'})")
    lines.append("")

    # Global summary
    lines.append("📌 全局配置与阈值（summary.json）")
    lines.append("-" * 90)
    keys_to_show = [
        "version",
        "alpha",
        "low_quantile",
        "high_quantile",
        "actors_total",
        "actors_eligible_after_bottom5",
        "actors_candidates_after_any_condition",
        "total_event_importance_cutoff_bottom5",
        "total_event_importance_cutoff_top_quantile",
        "high_tei_quantile",
        "min_distinct_repos",
        "attackers_top_n",
        "projects_missing_core_judgement",
    ]
    for k in keys_to_show:
        if k in summary:
            lines.append(f"   - {k}: {summary[k]}")
    lines.append(f"   - repo low/high thresholds: <= {low_repo_th:.6f}  /  >= {high_repo_th:.6f}")
    lines.append(f"   - discussion low/high thresholds: <= {low_dis_th:.6f}  /  >= {high_dis_th:.6f}")
    if missing_core:
        lines.append(f"   - missing_core_projects: {len(missing_core)} (详情见 missing_core_projects.json)")
    lines.append("")

    # Explanations
    lines.extend(build_global_explanations())
    lines.append("")

    # Top table
    lines.append("=" * 90)
    lines.append("📋 Top 可疑攻击者一览（仍为 core 优先排序）")
    lines.append("=" * 90)
    lines.append(f"{'rank':<4} {'still_core':<10} {'actor_id':<26} {'suspicion':>10} {'TEI':>10} {'distinct_repo':>13} {'first_high_touch':>19}")
    lines.append("-" * 90)
    for i, r in enumerate(top_rows, start=1):
        aid = r.get("actor_node_id", "")
        still = "YES" if (aid in core_recent and core_recent.get(aid)) else "NO"
        sus = float(r.get("suspicion_score", 0.0) or 0.0)
        tei = float(r.get("total_event_importance", 0.0) or 0.0)
        dr = r.get("distinct_repos_touched", "")
        tstar = r.get("first_high_repo_touch_time", "")
        tstar = tstar if _is_truthy(tstar) else "N/A"
        lines.append(f"{i:<4} {still:<10} {_short_id(aid, 26):<26} {sus:>10.4f} {tei:>10.2f} {str(dr):>13} {str(tstar):>19}")
    lines.append("")

    # Actor sections
    for r in top_rows:
        aid = r.get("actor_node_id", "")
        if not aid:
            continue
        aq = actor_quality.get(aid, {})
        if not isinstance(aq, dict):
            aq = {}
        lines.append(
            generate_actor_section(
                actor_id=aid,
                actor_row=r,
                actor_quality=aq,
                z_terms=z_terms,
                core_recent=core_recent,
                repo_imp_map=repo_imp_map,
                dis_imp_map=dis_imp_map,
                low_repos=low_repos,
                high_repos=high_repos,
                low_dis=low_dis,
                high_dis=high_dis,
                breakdown=breakdown,
                top_k=top_k_objects,
            )
        )

    report = "\n".join(lines)

    # Write out
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    return report


def main():
    parser = argparse.ArgumentParser(description="Generate detailed report for quality-risk outputs")
    parser.add_argument("--input-dir", type=str, default="output/quality-risk", help="quality-risk 输出目录")
    parser.add_argument("--graphs-dir", type=str, default="output/monthly-graphs", help="月度图目录（用于对象拆解）")
    parser.add_argument("--output", type=str, default=None, help="输出 txt 文件路径（默认: <input-dir>/detailed_report.txt）")
    parser.add_argument("--top", type=int, default=None, help="只输出前 N 个（默认全部 top_suspects.csv）")
    parser.add_argument("--actor", type=str, default=None, help="只分析指定 actor（逗号分隔多个 actor_node_id）")
    parser.add_argument("--top-k", type=int, default=10, help="每个 actor 展示 Top-K repo/discussion 构成")
    parser.add_argument("--no-breakdown", action="store_true", help="不扫描 graphml 计算对象贡献构成（更快）")

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    graphs_dir = Path(args.graphs_dir) if args.graphs_dir else None
    output_path = Path(args.output) if args.output else (input_dir / "detailed_report.txt")

    actor_filter = None
    if args.actor:
        actor_filter = {a.strip() for a in args.actor.split(",") if a.strip()}

    report = generate_report(
        input_dir=input_dir,
        graphs_dir=graphs_dir,
        output_path=output_path,
        top_n=args.top,
        actor_filter=actor_filter,
        top_k_objects=args.top_k,
        no_breakdown=args.no_breakdown,
    )

    print(f"✅ 报告已保存: {output_path}")
    if args.top is not None and args.top <= 3:
        print("\n📋 预览:\n")
        print(report)


if __name__ == "__main__":
    main()
