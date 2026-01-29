#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Compute "core member migrations AFTER leaving a Top30 repo".

Inputs:
- top30.json: output from rank_repos_by_monthly_events.py
- index.json: monthly graphs index produced by monthly_graph_builder.py

Definition:
- core member for a (repo, month) is computed using the SAME logic as burnout_analyzer.py:
  weighted_degree + k-core -> score -> dynamic pick
- "leave a Top30 repo R" for actor A means: month > last_core_month(A,R)
- "migration target repo" must satisfy denoise:
    after leaving R, A is core in target repo for:
      - cumulative >= 2 months OR
      - consecutive >= 2 months
  (we will compute both; condition is OR)

Outputs:
- top30_leave_migrations.json
- union_repos_after_leave.json
- missing_graphs.json (optional)
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx


EDGE_WEIGHTS = {
    "PR_MERGE": 3.0,
    "PR_REVIEW": 1.5,
    "ISSUE_INTERACTION": 0.5,
    "ISSUE_CO_PARTICIPANT": 0.5,
    "default": 1.0,
}

GRAPH_TYPE_PRIORITY = ["actor-actor"]  # we only need actor-actor for core member


def month_to_int(ym: str) -> int:
    # ym format: "YYYY-MM"
    y, m = ym.split("-")
    return int(y) * 12 + int(m)


def max_consecutive_streak(months: List[str]) -> int:
    """months: list of 'YYYY-MM' (unsorted OK). Return max consecutive streak length."""
    if not months:
        return 0
    ints = sorted({month_to_int(x) for x in months})
    best = 1
    cur = 1
    for i in range(1, len(ints)):
        if ints[i] == ints[i - 1] + 1:
            cur += 1
        else:
            best = max(best, cur)
            cur = 1
    best = max(best, cur)
    return best


def load_graph(graph_path: str) -> Optional[nx.MultiDiGraph]:
    """Load graphml and coerce to MultiDiGraph."""
    try:
        g = nx.read_graphml(graph_path)
    except Exception:
        return None

    if isinstance(g, nx.MultiDiGraph):
        return g

    if isinstance(g, nx.DiGraph):
        mg = nx.MultiDiGraph()
        mg.add_nodes_from(g.nodes(data=True))
        mg.add_edges_from(g.edges(data=True))
        mg.graph.update(g.graph)
        return mg

    if isinstance(g, (nx.Graph, nx.MultiGraph)):
        dg = g.to_directed()
        mg = nx.MultiDiGraph()
        mg.add_nodes_from(dg.nodes(data=True))
        mg.add_edges_from(dg.edges(data=True))
        mg.graph.update(dg.graph)
        return mg

    return None


def compute_core_members(graph: nx.MultiDiGraph) -> List[str]:
    """
    Core members logic aligned with burnout_analyzer.py:
    - weighted_degree + k-core
    - score = 0.5 * norm(weighted_degree) + 0.5 * norm(kcore)
    - dynamic select in score-desc order
      stop when (cum_contrib >= 50% total) OR (score < avg_score AND core>=3)
      ensure at least 2
    """
    if graph is None or graph.number_of_nodes() == 0:
        return []

    degrees = dict(graph.degree())
    is_multigraph = isinstance(graph, (nx.MultiGraph, nx.MultiDiGraph))

    # weighted degrees
    weighted_degrees: Dict[str, float] = {}
    for node_id in graph.nodes():
        wd = 0.0
        if is_multigraph:
            for _, _, _, data in graph.out_edges(node_id, keys=True, data=True):
                edge_type = data.get("edge_type", "default")
                wd += EDGE_WEIGHTS.get(edge_type, EDGE_WEIGHTS["default"])
            for _, _, _, data in graph.in_edges(node_id, keys=True, data=True):
                edge_type = data.get("edge_type", "default")
                wd += EDGE_WEIGHTS.get(edge_type, EDGE_WEIGHTS["default"])
        else:
            for _, _, data in graph.out_edges(node_id, data=True):
                edge_type = data.get("edge_type", "default")
                wd += EDGE_WEIGHTS.get(edge_type, EDGE_WEIGHTS["default"])
            for _, _, data in graph.in_edges(node_id, data=True):
                edge_type = data.get("edge_type", "default")
                wd += EDGE_WEIGHTS.get(edge_type, EDGE_WEIGHTS["default"])
        weighted_degrees[node_id] = wd

    wvals = list(weighted_degrees.values())
    total_weighted_degree = sum(wvals)
    max_weighted_degree = max(wvals) if wvals else 1.0

    # k-core
    try:
        undirected = graph.to_undirected()
        core_numbers = nx.core_number(undirected)
        max_k = max(core_numbers.values()) if core_numbers else 1
    except Exception:
        core_numbers = {n: 1 for n in graph.nodes()}
        max_k = 1

    # score
    actor_scores: Dict[str, Dict[str, float]] = {}
    for node_id in graph.nodes():
        wd = weighted_degrees.get(node_id, 0.0)
        kc = core_numbers.get(node_id, 0)

        wd_norm = wd / max(max_weighted_degree, 1e-9)
        kc_norm = kc / max(max_k, 1e-9)
        score = 0.5 * wd_norm + 0.5 * kc_norm

        actor_scores[node_id] = {
            "score": score,
            "weighted_degree": wd,
            "degree": float(degrees.get(node_id, 0)),
        }

    sorted_actors = sorted(actor_scores.items(), key=lambda x: x[1]["score"], reverse=True)

    contribution_threshold = total_weighted_degree * 0.5
    avg_score = (
        sum(v["score"] for v in actor_scores.values()) / len(actor_scores)
        if actor_scores
        else 0.0
    )

    core_logins: List[str] = []
    cumsum = 0.0

    # IMPORTANT: stop means break (not continue)
    for node_id, s in sorted_actors:
        if cumsum >= contribution_threshold or (s["score"] < avg_score and len(core_logins) >= 3):
            break

        login = str(graph.nodes[node_id].get("login", node_id))
        core_logins.append(login)
        cumsum += s["weighted_degree"]

    # ensure at least 2
    if len(core_logins) < 2:
        for node_id, _ in sorted_actors[:2]:
            login = str(graph.nodes[node_id].get("login", node_id))
            if login not in core_logins:
                core_logins.append(login)

    return core_logins


def normalize_path(p: str, graph_root: str) -> str:
    """Convert stored path to local filesystem path, keeping relative paths under graph_root."""
    p = str(p).replace("\\", os.sep).replace("/", os.sep)
    if os.path.isabs(p):
        return p
    return os.path.join(graph_root, p)


def pick_month_map(repo_entry: dict) -> Tuple[Optional[str], dict]:
    """Pick actor-actor month map."""
    for gt in GRAPH_TYPE_PRIORITY:
        mm = repo_entry.get(gt)
        if isinstance(mm, dict) and mm:
            return gt, mm
    return None, {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top30", type=str, required=True, help="Path to top30.json")
    ap.add_argument("--index", type=str, required=True, help="Path to index.json")
    ap.add_argument("--graph-root", type=str, default=".", help="Base dir for relative graph paths")
    ap.add_argument("--outdir", type=str, default="output", help="Output directory")
    ap.add_argument("--min-months", type=int, default=2, help="Denoise: min cumulative core months in target repo")
    ap.add_argument("--min-streak", type=int, default=2, help="Denoise: min consecutive core months streak in target repo")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    top30 = json.load(open(args.top30, "r", encoding="utf-8"))
    index = json.load(open(args.index, "r", encoding="utf-8"))

    top30_repos: List[str] = [x["repo"] for x in top30 if "repo" in x]
    top30_set: Set[str] = set(top30_repos)

    # repo_month_core[repo][month] = set(actor_login)
    repo_month_core: Dict[str, Dict[str, Set[str]]] = defaultdict(dict)

    # actor_core_months[actor][repo] = list of months where actor is core in that repo
    actor_core_months: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))

    missing_graphs: List[dict] = []

    # 1) Build repo_month_core and actor_core_months for all repos in index (actor-actor only)
    for repo, entry in index.items():
        _, month_map = pick_month_map(entry)
        if not month_map:
            continue

        for month, rel_path in month_map.items():
            graph_path = normalize_path(rel_path, args.graph_root)

            if not os.path.exists(graph_path):
                missing_graphs.append({"repo": repo, "month": month, "path": graph_path, "reason": "not_found"})
                continue

            g = load_graph(graph_path)
            if g is None:
                missing_graphs.append({"repo": repo, "month": month, "path": graph_path, "reason": "load_failed"})
                continue

            core = compute_core_members(g)
            core_set = set(core)

            repo_month_core[repo][month] = core_set
            for a in core_set:
                actor_core_months[a][repo].append(month)

    # sort months list for each actor-repo
    for a, repo_map in actor_core_months.items():
        for r, mlist in repo_map.items():
            repo_map[r] = sorted(set(mlist))  # dedup + sort

    # 2) For Top30 repos, compute last_core_month[(actor, repo)]
    last_core_month: Dict[Tuple[str, str], str] = {}

    for repo in top30_repos:
        month_map = repo_month_core.get(repo, {})
        for month in sorted(month_map.keys()):
            for a in month_map[month]:
                key = (a, repo)
                prev = last_core_month.get(key)
                if prev is None or month > prev:
                    last_core_month[key] = month

    # 3) Migrations after leaving: actor -> from_repo -> to_repo -> later_months
    migrations: Dict[str, Dict[str, dict]] = defaultdict(dict)
    union_repos: Set[str] = set(top30_repos)

    for (actor, src_repo), last_month in last_core_month.items():
        # candidate target repos are where actor was ever core
        repo_map = actor_core_months.get(actor, {})

        moved_to: Dict[str, dict] = {}

        for dst_repo, months in repo_map.items():
            if dst_repo == src_repo:
                continue

            later_months = [m for m in months if m > last_month]
            if not later_months:
                continue

            cum_ok = (len(later_months) >= args.min_months)
            streak = max_consecutive_streak(later_months)
            streak_ok = (streak >= args.min_streak)

            # denoise condition: cumulative OR consecutive
            if not (cum_ok or streak_ok):
                continue

            moved_to[dst_repo] = {
                "months": later_months,
                "cumulative_months": len(later_months),
                "max_consecutive_streak": streak,
            }
            union_repos.add(dst_repo)

        if moved_to:
            migrations[actor][src_repo] = {
                "last_core_month_in_src": last_month,
                "moved_to": moved_to,
            }

    out_migrations = {
        "top30_repos": top30_repos,
        "denoise": {
            "min_cumulative_months_in_target_repo": args.min_months,
            "min_consecutive_streak_in_target_repo": args.min_streak,
            "condition": "cumulative >= min_months OR consecutive_streak >= min_streak",
        },
        "actor_count_with_migrations": len(migrations),
        "migrations": migrations,
    }

    with open(os.path.join(args.outdir, "top30_leave_migrations.json"), "w", encoding="utf-8") as f:
        json.dump(out_migrations, f, ensure_ascii=False, indent=2)

    with open(os.path.join(args.outdir, "union_repos_after_leave.json"), "w", encoding="utf-8") as f:
        json.dump(sorted(union_repos), f, ensure_ascii=False, indent=2)

    if missing_graphs:
        with open(os.path.join(args.outdir, "missing_graphs.json"), "w", encoding="utf-8") as f:
            json.dump(missing_graphs, f, ensure_ascii=False, indent=2)

    print("Done.")
    print(f"- {os.path.join(args.outdir, 'top30_leave_migrations.json')}")
    print(f"- {os.path.join(args.outdir, 'union_repos_after_leave.json')}")
    if missing_graphs:
        print(f"- {os.path.join(args.outdir, 'missing_graphs.json')} (some graphs not found/loaded)")


if __name__ == "__main__":
    main()
