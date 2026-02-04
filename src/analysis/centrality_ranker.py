from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import networkx as nx


# ===================== 权重设置 =====================
# 定义各种边类型的权重：对应你给出的边类型与权重
EDGE_WEIGHTS = {
    "PR_MERGE": 3.0,              # 合并的 PR（高价值贡献）
    "PR_REVIEW": 1.5,             # PR 代码审查（中等价值）
    "ISSUE_INTERACTION": 0.5,     # Issue 评论（参与度）
    "ISSUE_CO_PARTICIPANT": 0.5,  # 共同参与 Issue（参与度）
    "default": 1.0,               # 默认值（如果边类型未定义）
}

def load_graph(graph_path: Path) -> Optional[nx.MultiDiGraph]:
    """加载 GraphML 文件并返回 MultiDiGraph"""
    try:
        g = nx.read_graphml(str(graph_path))
        print(f"加载图成功：{graph_path}")  # 调试语句，检查是否加载成功
        # 统一为 MultiDiGraph
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
    except Exception as e:
        print(f"加载图失败：{graph_path}, 错误: {e}")  # 调试语句，检查加载错误
        return None


def multidi_to_weighted_digraph(g: nx.MultiDiGraph, mode: str = "base") -> nx.DiGraph:
    """把 MultiDiGraph 压缩成 DiGraph，并设置边权重"""
    dg = nx.DiGraph()
    dg.add_nodes_from(g.nodes(data=True))

    edge_weight: Dict[Tuple[Any, Any], float] = defaultdict(float)
    
    if mode == "base":
        print("使用 Base 模式：每条边权重为 1")  # 调试语句，检查模式
        # Base版：每条边权重都为 1
        for u, v, _k, _data in g.edges(keys=True, data=True):
            edge_weight[(u, v)] += 1.0
    elif mode == "contribution":
        print("使用 Contribution 模式：根据 edge_type 设置权重")  # 调试语句，检查模式
        # Contribution版：根据边类型设置权重
        for u, v, _k, data in g.edges(keys=True, data=True):
            edge_type = data.get("edge_type", "default")
            weight = EDGE_WEIGHTS.get(edge_type, EDGE_WEIGHTS["default"])
            edge_weight[(u, v)] += weight

    # 调试：检查计算的权重
    print(f"计算的边权重：{dict(edge_weight)}")

    for (u, v), w in edge_weight.items():
        dg.add_edge(u, v, weight=w)
    return dg


def multidi_to_weighted_undigraph(g: nx.MultiDiGraph, mode: str = "base") -> nx.Graph:
    """把 MultiDiGraph 压缩成无向 Graph，并设置边权重"""
    ug = nx.Graph()
    ug.add_nodes_from(g.nodes(data=True))

    edge_weight: Dict[Tuple[Any, Any], float] = defaultdict(float)
    
    if mode == "base":
        print("使用 Base 模式：每条边权重为 1")  # 调试语句，检查模式
        # Base版：每条边权重都为 1
        for u, v, _k, _data in g.edges(keys=True, data=True):
            a, b = (u, v) if str(u) <= str(v) else (v, u)
            edge_weight[(a, b)] += 1.0
    elif mode == "contribution":
        print("使用 Contribution 模式：根据 edge_type 设置权重")  # 调试语句，检查模式
        # Contribution版：根据边类型设置权重
        for u, v, _k, data in g.edges(keys=True, data=True):
            a, b = (u, v) if str(u) <= str(v) else (v, u)
            edge_type = data.get("edge_type", "default")
            weight = EDGE_WEIGHTS.get(edge_type, EDGE_WEIGHTS["default"])
            edge_weight[(a, b)] += weight

    # 调试：检查计算的权重
    print(f"计算的边权重：{dict(edge_weight)}")

    for (u, v), w in edge_weight.items():
        ug.add_edge(u, v, weight=w)
    return ug


def sort_metric(scores: Dict[Any, float], g: nx.Graph, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
    """排序并输出节点信息，包含具体得分。"""
    items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if top_k is not None and top_k > 0:
        items = items[:top_k]

    out: List[Dict[str, Any]] = []
    for node_id, val in items:
        attrs = g.nodes[node_id] if node_id in g.nodes else {}
        out.append(
            {
                "node_id": str(node_id),
                "actor_id": int(attrs.get("actor_id", 0) or 0),
                "login": attrs.get("login", "") or "",
                "score": float(val),  # 保存具体得分
            }
        )
    return out


def compute_all_metrics(
    g_multi: nx.MultiDiGraph,
    top_k: Optional[int] = None,
) -> Dict[str, Any]:
    """计算 PR / 度中心性 / 介数 / 接近，并输出排序结果。"""
    # 有向（PR）
    dg_base = multidi_to_weighted_digraph(g_multi, mode="base")
    dg_contribution = multidi_to_weighted_digraph(g_multi, mode="contribution")
    
    # 无向（中心性）
    ug_base = multidi_to_weighted_undigraph(g_multi, mode="base")
    ug_contribution = multidi_to_weighted_undigraph(g_multi, mode="contribution")

    n = ug_base.number_of_nodes()
    m = ug_base.number_of_edges()

    if n == 0:
        return {
            "node_count": 0,
            "edge_count": 0,
            "pagerank_base": [],
            "pagerank_contribution": [],
            "degree_centrality_base": [],
            "degree_centrality_contribution": [],
            "betweenness_centrality_base": [],
            "betweenness_centrality_contribution": [],
            "closeness_centrality_base": [],
            "closeness_centrality_contribution": [],
        }

    # PageRank：有向 + weight
    try:
        pr_base = nx.pagerank(dg_base, weight="weight")
        pr_contribution = nx.pagerank(dg_contribution, weight="weight")
    except Exception as e:
        print(f"PageRank 计算失败: {e}")  # 调试语句，捕捉 PageRank 错误
        pr_base = pr_contribution = {}

    # Degree centrality：无向
    try:
        deg_cent_base = nx.degree_centrality(ug_base)  # 归一化到 [0,1]
        deg_cent_contribution = nx.degree_centrality(ug_contribution)
    except Exception as e:
        print(f"Degree centrality 计算失败: {e}")  # 调试语句，捕捉 Degree 错误
        deg_cent_base = deg_cent_contribution = {}

    # Betweenness：无向 + weight（注意：nx 把 weight 当“距离/代价”，权重越大路径越“长”不符合协作直觉）
    # 所以这里把 “交互次数 weight” 转成 “距离 = 1/weight”，让交互越多越“近”
    # 做法：拷贝一个带 distance 的图
    ug_dist_base = nx.Graph()
    ug_dist_contribution = nx.Graph()
    ug_dist_base.add_nodes_from(ug_base.nodes(data=True))
    ug_dist_contribution.add_nodes_from(ug_contribution.nodes(data=True))
    
    for u, v, data in ug_base.edges(data=True):
        w = float(data.get("weight", 1.0) or 1.0)
        ug_dist_base.add_edge(u, v, distance=1.0 / max(w, 1e-9))
    
    for u, v, data in ug_contribution.edges(data=True):
        w = float(data.get("weight", 1.0) or 1.0)
        ug_dist_contribution.add_edge(u, v, distance=1.0 / max(w, 1e-9))

    try:
        btw_base = nx.betweenness_centrality(ug_dist_base, weight="distance", normalized=True)
        btw_contribution = nx.betweenness_centrality(ug_dist_contribution, weight="distance", normalized=True)
    except Exception as e:
        print(f"Betweenness centrality 计算失败: {e}")  # 调试语句，捕捉 Betweenness 错误
        btw_base = btw_contribution = {}

    # Closeness：无向 + distance
    try:
        clo_base = nx.closeness_centrality(ug_dist_base, distance="distance")
        clo_contribution = nx.closeness_centrality(ug_dist_contribution, distance="distance")
    except Exception as e:
        print(f"Closeness centrality 计算失败: {e}")  # 调试语句，捕捉 Closeness 错误
        clo_base = clo_contribution = {}

    return {
        "node_count": int(n),
        "edge_count": int(m),
        "pagerank_base": sort_metric(pr_base, ug_base, top_k=top_k),
        "pagerank_contribution": sort_metric(pr_contribution, ug_contribution, top_k=top_k),
        "degree_centrality_base": sort_metric(deg_cent_base, ug_base, top_k=top_k),
        "degree_centrality_contribution": sort_metric(deg_cent_contribution, ug_contribution, top_k=top_k),
        "betweenness_centrality_base": sort_metric(btw_base, ug_base, top_k=top_k),
        "betweenness_centrality_contribution": sort_metric(btw_contribution, ug_contribution, top_k=top_k),
        "closeness_centrality_base": sort_metric(clo_base, ug_base, top_k=top_k),
        "closeness_centrality_contribution": sort_metric(clo_contribution, ug_contribution, top_k=top_k),
    }


def main():
    parser = argparse.ArgumentParser(description="Compute centrality rankings for monthly actor-actor graphs.")
    parser.add_argument("--graphs-dir", type=str, default="output/monthly-graphs/", help="月度图目录（含 index.json）")
    parser.add_argument("--output-dir", type=str, default="output/centrality-rankings/", help="输出目录")
    parser.add_argument("--top-k", type=int, default=0, help="每个指标只保留前K名（0表示全部）")
    args = parser.parse_args()

    graphs_dir = Path(args.graphs_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    index_path = graphs_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"index.json 不存在：{index_path}（请先运行 monthly_graph_builder 生成图）")

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    top_k = args.top_k if args.top_k and args.top_k > 0 else None
    summary = {
        "graphs_dir": str(graphs_dir),
        "output_dir": str(output_dir),
        "repos_processed": 0,
        "months_processed": 0,
        "errors": 0,
        "repos": [],
    }

    for repo_name, graph_types_data in index.items():
        # 兼容两种 index 结构：
        # 新：{repo: {graph_type: {month: path}}}
        # 旧：{repo: {month: path}}
        first_value = next(iter(graph_types_data.values()), {})
        if isinstance(first_value, dict) and not first_value.get("node_type"):
            months = graph_types_data.get("actor-actor", {})
        else:
            months = graph_types_data  # 旧结构假设就是 actor-actor

        repo_result: Dict[str, Any] = {
            "repo_name": repo_name,
            "months": {},
        }

        safe_repo = repo_name.replace("/", "-")
        repo_out_path = output_dir / f"{safe_repo}.json"

        repo_month_count = 0
        for month, graph_path in sorted(months.items()):
            g = load_graph(Path(graph_path))
            if g is None or g.number_of_nodes() == 0:
                summary["errors"] += 1
                continue

            metrics = compute_all_metrics(g, top_k=top_k)
            repo_result["months"][month] = {
                "graph_path": graph_path,
                "graph_type": "actor-actor",
                "repo_name": repo_name,
                "month": month,
                **metrics,
            }
            repo_month_count += 1
            summary["months_processed"] += 1

        with open(repo_out_path, "w", encoding="utf-8") as f:
            json.dump(repo_result, f, ensure_ascii=False, indent=2)

        summary["repos_processed"] += 1
        summary["repos"].append(
            {
                "repo_name": repo_name,
                "output_file": str(repo_out_path),
                "months": repo_month_count,
            }
        )

    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"完成：repos={summary['repos_processed']} months={summary['months_processed']} errors={summary['errors']}")
    print(f"summary: {summary_path}")


if __name__ == "__main__":
    main()
