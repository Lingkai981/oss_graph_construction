import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

import networkx as nx


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def pct(x: float) -> str:
    return f"{x*100:.2f}%"


def quantile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    if q <= 0:
        return vs[0]
    if q >= 1:
        return vs[-1]
    idx = int(round((len(vs) - 1) * q))
    idx = max(0, min(len(vs) - 1, idx))
    return float(vs[idx])


def summarize_numeric(values: List[float], name: str, zero_eps: float = 1e-12) -> None:
    if not values:
        print(f"[{name}] empty")
        return

    n = len(values)
    zeros = sum(1 for v in values if abs(v) <= zero_eps)
    unique = len(set(values))

    print(f"\n=== {name} ===")
    print(f"count={n}")
    print(f"zeros={zeros} ({pct(zeros/n)})")
    print(f"unique_values={unique} ({pct(unique/n)})")
    print(
        "quantiles: "
        f"p0={quantile(values,0):.6g}, "
        f"p5={quantile(values,0.05):.6g}, "
        f"p25={quantile(values,0.25):.6g}, "
        f"p50={quantile(values,0.5):.6g}, "
        f"p75={quantile(values,0.75):.6g}, "
        f"p95={quantile(values,0.95):.6g}, "
        f"p100={quantile(values,1):.6g}"
    )


def summarize_importance_file(path: Path, kind: str) -> None:
    data = load_json(path)
    if not isinstance(data, dict) or not data:
        print(f"\n[{kind}] {path} is empty or not dict")
        return

    # 支持两种格式：
    # 1) {id: {"importance":..., "structure":...}}
    # 2) {id: {"importance":..., "activity":..., ...}}
    imp = []
    struct = []
    act = []
    cov = []

    for _, v in data.items():
        if not isinstance(v, dict):
            continue
        if "importance" in v:
            imp.append(float(v.get("importance", 0.0)))
        if "structure" in v:
            struct.append(float(v.get("structure", 0.0)))
        if "activity" in v:
            act.append(float(v.get("activity", 0.0)))
        if "coverage" in v:
            cov.append(float(v.get("coverage", 0.0)))

    print(f"\n############################")
    print(f"# {kind}: {path.name}")
    print(f"items={len(data)}")
    summarize_numeric(imp, f"{kind}.importance")
    summarize_numeric(struct, f"{kind}.structure")
    if act:
        summarize_numeric(act, f"{kind}.activity")
    if cov:
        summarize_numeric(cov, f"{kind}.coverage")

    # 重点：structure=0 导致 importance=0 的比例
    if struct and imp:
        pair_n = min(len(struct), len(imp))
        both_zero = sum(
            1 for i in range(pair_n)
            if abs(struct[i]) <= 1e-12 and abs(imp[i]) <= 1e-12
        )
        print(f"\n[{kind}] structure==0 AND importance==0: {both_zero}/{pair_n} ({pct(both_zero/pair_n)})")


def summarize_actor_quality(path: Path) -> None:
    data = load_json(path)
    if not isinstance(data, dict) or not data:
        print(f"\n[actor] {path} is empty or not dict")
        return

    tei = []
    low_ratio = []
    low_cost_ratio = []
    entropy = []
    jump = []
    high_contrib = []
    all_contrib = []
    has_tstar = 0
    distinct_repos = []

    for _, v in data.items():
        if not isinstance(v, dict):
            continue
        tei.append(float(v.get("total_event_importance", 0.0)))
        low_ratio.append(float(v.get("low_value_event_ratio", 0.0)))
        low_cost_ratio.append(float(v.get("low_cost_event_ratio", 0.0)))
        entropy.append(float(v.get("type_entropy", 0.0)))
        jump.append(float(v.get("jumpiness", 0.0)))
        high_contrib.append(float(v.get("high_value_contrib", 0.0)))
        all_contrib.append(float(v.get("all_value_contrib", 0.0)))
        distinct_repos.append(int(v.get("distinct_repos_touched", 0)))
        if v.get("first_high_repo_touch_time"):
            has_tstar += 1

    print(f"\n############################")
    print(f"# actor_quality: {path.name}")
    print(f"actors={len(data)}")
    print(f"has_first_high_repo_touch_time: {has_tstar}/{len(data)} ({pct(has_tstar/len(data))})")

    summarize_numeric(tei, "actor.total_event_importance")
    summarize_numeric(low_ratio, "actor.low_value_event_ratio")
    summarize_numeric(low_cost_ratio, "actor.low_cost_event_ratio")
    summarize_numeric(entropy, "actor.type_entropy")
    summarize_numeric(jump, "actor.jumpiness")
    summarize_numeric(high_contrib, "actor.high_value_contrib")
    summarize_numeric(all_contrib, "actor.all_value_contrib")

    # distinct_repos 是整数，单独看分布
    if distinct_repos:
        c = Counter(distinct_repos)
        top = c.most_common(10)
        print("\n=== actor.distinct_repos_touched (top10 counts) ===")
        for k, v in top:
            print(f"{k}: {v} ({pct(v/len(distinct_repos))})")


def pick_graphml_samples(graphs_dir: Path, sample_k: int = 6) -> List[Path]:
    # 从 graphs_dir 下递归找 graphml
    graphmls = list(graphs_dir.rglob("*.graphml"))
    if not graphmls:
        return []
    if len(graphmls) <= sample_k:
        return graphmls
    return random.sample(graphmls, sample_k)


def inspect_graphml(path: Path, max_edges_inspect: int = 5000) -> None:
    print(f"\n==============================")
    print(f"Graph: {path}")
    try:
        g = nx.read_graphml(path, force_multigraph=True)
    except TypeError:
        # 老版本 networkx 可能没有这个参数
        g = nx.read_graphml(path)

    print(f"type={type(g).__name__}, is_multigraph={g.is_multigraph()}")
    print(f"nodes={g.number_of_nodes()}, edges={g.number_of_edges()}")

    # node_type 统计
    node_type = nx.get_node_attributes(g, "node_type")
    ntc = Counter(str(t) for t in node_type.values())
    if ntc:
        print("node_type top5:", ntc.most_common(5))

    # edge 属性抽样：edge_type、comment_body 是否为空
    edge_type_counter = Counter()
    body_len = []
    created_at_present = 0

    inspected = 0
    if g.is_multigraph():
        it = g.edges(keys=True, data=True)
        for _, _, _, attr in it:
            inspected += 1
            if inspected > max_edges_inspect:
                break
            et = str(attr.get("edge_type", "OTHER")).upper()
            edge_type_counter[et] += 1
            cb = attr.get("comment_body")
            body_len.append(len(str(cb)) if cb is not None else 0)
            if attr.get("created_at"):
                created_at_present += 1
    else:
        it = g.edges(data=True)
        for _, _, attr in it:
            inspected += 1
            if inspected > max_edges_inspect:
                break
            et = str(attr.get("edge_type", "OTHER")).upper()
            edge_type_counter[et] += 1
            cb = attr.get("comment_body")
            body_len.append(len(str(cb)) if cb is not None else 0)
            if attr.get("created_at"):
                created_at_present += 1

    if inspected:
        print(f"inspected_edges={inspected}")
        print("edge_type top8:", edge_type_counter.most_common(8))
        zero_body = sum(1 for l in body_len if l == 0)
        print(f"comment_body empty: {zero_body}/{len(body_len)} ({pct(zero_body/len(body_len))})")
        print(f"created_at present: {created_at_present}/{inspected} ({pct(created_at_present/inspected)})")


def main():
    parser = argparse.ArgumentParser("Verify quality-risk outputs and graph characteristics")
    parser.add_argument("--output-dir", type=str, default="output/quality-risk", help="quality-risk 输出目录")
    parser.add_argument("--graphs-dir", type=str, default="output/monthly-graphs", help="月度图目录（用于抽样检查 graphml）")
    parser.add_argument("--sample-graphs", type=int, default=6, help="抽样检查 graphml 数量")
    parser.add_argument("--seed", type=int, default=123, help="随机种子")
    args = parser.parse_args()

    random.seed(args.seed)

    out_dir = Path(args.output_dir)
    graphs_dir = Path(args.graphs_dir)

    repo_path = out_dir / "repo_importance.json"
    dis_path = out_dir / "discussion_importance.json"
    actor_path = out_dir / "actor_quality.json"

    print("=== Verifier Start ===")
    print(f"output_dir={out_dir.resolve()}")
    print(f"graphs_dir={graphs_dir.resolve()}")

    if repo_path.exists():
        summarize_importance_file(repo_path, "repo")
    else:
        print(f"\n[repo] missing: {repo_path}")

    if dis_path.exists():
        summarize_importance_file(dis_path, "discussion")
    else:
        print(f"\n[discussion] missing: {dis_path}")

    if actor_path.exists():
        summarize_actor_quality(actor_path)
    else:
        print(f"\n[actor] missing: {actor_path}")

    # graphml 抽样检查
    if graphs_dir.exists():
        samples = pick_graphml_samples(graphs_dir, args.sample_graphs)
        if not samples:
            print("\nNo graphml found under graphs_dir.")
        else:
            print(f"\nInspecting {len(samples)} sampled graphml files ...")
            for p in samples:
                inspect_graphml(p)
    else:
        print(f"\n[graphs] graphs_dir not found: {graphs_dir}")

    print("\n=== Verifier Done ===")


if __name__ == "__main__":
    main()
