#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Rank repos by monthly total_events stored in monthly GraphML graphs.
Sort key: mean desc, then median desc.

It matches burnout_analyzer.py's convention:
  total_events = graph.graph.get("total_events", 0)

Expected input directory structure:
  output/monthly-graphs/
    index.json
    <many .graphml files...>

index.json format (supported both):
  1) New format:
     {repo: {graph_type: {month: path}}}
     and we will prefer graph_type "actor-actor" if present
  2) Old format:
     {repo: {month: path}}
"""

import argparse
import csv
import json
from collections import OrderedDict
from pathlib import Path, PureWindowsPath
from statistics import mean, median
from typing import Any, Dict, List, Tuple, Optional

import networkx as nx

def normalize_index_path(p: str) -> Path:
    # 把 index.json 里的 "output\\monthly-graphs\\..." 转成跨平台路径
    # PureWindowsPath 会按反斜杠正确拆分成 parts
    return Path(*PureWindowsPath(p).parts)

def load_index(graphs_dir: Path) -> Dict[str, Any]:
    index_path = graphs_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"index.json not found: {index_path}")
    return json.loads(index_path.read_text(encoding="utf-8"))

from pathlib import Path, PureWindowsPath

def resolve_graph_path(graphs_dir: Path, raw: str) -> Path:
    # 统一把 index 里的 windows 字符串变成当前平台可用的 Path parts
    p = Path(*PureWindowsPath(raw).parts)

    # 1) 如果 index 里已经是绝对路径（有盘符），直接用
    # Windows 下：p.drive 形如 'D:'
    if getattr(p, "drive", ""):
        return p

    # 2) 如果 index 里写的是以 output/monthly-graphs 开头的相对路径
    parts = [x.lower() for x in p.parts]
    try:
        i = parts.index("output")
        if i + 1 < len(parts) and parts[i + 1] in ("monthly-graphs", "monthly_graphs", "monthlygraphs"):
            # 从 output/monthly-graphs 之后开始取，避免重复前缀
            p_rel = Path(*p.parts[i+2:])
            return (graphs_dir / p_rel).resolve()
    except ValueError:
        pass

    # 3) 否则认为它是相对 graphs_dir 的路径
    return (graphs_dir / p).resolve()


def pick_month_map(graph_types_data: Any) -> Dict[str, str]:
    """
    Return {month: graph_path}.

    New format:
      graph_types_data is dict like {"actor-actor": {...}, "actor-repo": {...}, ...}
      We choose "actor-actor" if exists, else first dict value that looks like {month:path}.
    Old format:
      graph_types_data is already {month: path}.
    """
    if not isinstance(graph_types_data, dict):
        return {}

    # Detect "new format": values are dicts keyed by month
    # In burnout_analyzer.py it checks the first value; we mimic robustly.
    if "actor-actor" in graph_types_data and isinstance(graph_types_data["actor-actor"], dict):
        return graph_types_data["actor-actor"]

    # If it already looks like {month: path} (month keys like '2023-01')
    # we'll accept it as old format.
    sample_key = next(iter(graph_types_data.keys()), "")
    if isinstance(sample_key, str) and len(sample_key) == 7 and sample_key[4] == "-":
        # likely old format
        return graph_types_data  # type: ignore

    # Otherwise, try the first nested dict
    for v in graph_types_data.values():
        if isinstance(v, dict):
            # heuristic: month-like keys
            k = next(iter(v.keys()), "")
            if isinstance(k, str) and len(k) == 7 and k[4] == "-":
                return v  # type: ignore

    return {}

'''def read_total_events(graph_path: Path) -> int:
    try:
        g = nx.read_graphml(graph_path)
    except Exception:
        return 0
    val = g.graph.get("total_events", 0)
    try:
        return int(val)
    except Exception:
        return 0'''

def read_total_events(graph_path_str: str) -> int:
    graph_path = normalize_index_path(graph_path_str)
    print(graph_path_str)
    print(graph_path)
    if not graph_path.exists():
        # 可选：这里加日志，帮助你确认是不是路径问题导致全 0
        # print(f"[MISS] graphml not found: {graph_path} (raw={graph_path_str})")
        return 0

    g = nx.read_graphml(graph_path)
    # 和 burnout_analyzer.py 一样：从图元数据取
    return int(g.graph.get("total_events", 0))

def compute_repo_monthly_totals(graphs_dir: Path) -> Dict[str, "OrderedDict[str, int]"]:
    """
    Returns:
      repo -> OrderedDict(month -> total_events)
    """
    index = load_index(graphs_dir)
    out: Dict[str, OrderedDict[str, int]] = {}

    for repo, graph_types_data in index.items():
        month_map = pick_month_map(graph_types_data)
        if not month_map:
            continue

        months_sorted = sorted(month_map.keys())
        od: OrderedDict[str, int] = OrderedDict()

        for m in months_sorted:
            p = resolve_graph_path(graphs_dir, month_map[m])
            od[m] = read_total_events(p)

        out[repo] = od

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graphs-dir", default="output/monthly-graphs/", help="monthly graphs dir containing index.json")
    ap.add_argument("--top", type=int, default=30, help="top N repos")
    ap.add_argument("--min-months", type=int, default=1, help="only include repos with >= this many months")
    ap.add_argument("--out", default="", help="optional output file: .json or .csv; otherwise print")
    args = ap.parse_args()

    graphs_dir = Path(args.graphs_dir).expanduser().resolve()
    repo_month_totals = compute_repo_monthly_totals(graphs_dir)

    rows: List[Dict[str, Any]] = []
    for repo, od in repo_month_totals.items():
        counts = list(od.values())
        if len(counts) < args.min_months:
            continue
        rows.append(
            {
                "repo": repo,
                "months_count": len(counts),
                "monthly_counts": od,
                "mean": float(mean(counts)) if counts else 0.0,
                "median": float(median(counts)) if counts else 0.0,
            }
        )

    # Sort by mean desc, then median desc, then months desc, then repo asc
    rows.sort(key=lambda r: (-r["mean"], -r["median"], -r["months_count"], r["repo"]))
    top_rows = rows[: args.top]

    def monthly_counts_str(od: "OrderedDict[str, int]") -> str:
        return ", ".join([f"{m}:{c}" for m, c in od.items()])

    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if out_path.suffix.lower() == ".json":
            payload = []
            for i, r in enumerate(top_rows, start=1):
                payload.append(
                    {
                        "rank": i,
                        "repo": r["repo"],
                        "months_count": r["months_count"],
                        "monthly_counts": dict(r["monthly_counts"]),
                        "mean": r["mean"],
                        "median": r["median"],
                    }
                )
            out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        elif out_path.suffix.lower() == ".csv":
            with out_path.open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["rank", "repo", "months_count", "mean", "median", "monthly_counts"])
                for i, r in enumerate(top_rows, start=1):
                    w.writerow([i, r["repo"], r["months_count"], r["mean"], r["median"], monthly_counts_str(r["monthly_counts"])])
        else:
            raise ValueError("Unsupported output extension. Use .json or .csv")

        print(f"Saved: {out_path}")
        return

    print(f"Top {len(top_rows)} repos (from GraphML total_events; sort: mean desc, median desc)\n")
    for i, r in enumerate(top_rows, start=1):
        print(f"#{i:02d} {r['repo']}")
        print(f"  months_count: {r['months_count']}")
        print(f"  mean:   {r['mean']:.6f}")
        print(f"  median: {r['median']:.6f}")
        print(f"  monthly_counts: {monthly_counts_str(r['monthly_counts'])}")
        print("")


if __name__ == "__main__":
    main()
