"""
对 Repo-Repo 人员流动图执行 PageRank 分析

功能：
1. 读取全局 repo-flow.graphml
2. 执行 PageRank（支持加权/无权）
3. 按分数排序输出排名
4. 保存结果为 CSV 和 JSON

用法：
  python analyze_repo_flow_pagerank.py
  python analyze_repo_flow_pagerank.py --graph output/repo-flow-graphs/global/repo-flow.graphml
  python analyze_repo_flow_pagerank.py --weighted --alpha 0.85 --top 20
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional

import networkx as nx


def load_graph(graph_path: str) -> nx.DiGraph:
    """加载 GraphML 文件"""
    path = Path(graph_path)
    if not path.exists():
        raise FileNotFoundError(f"图文件不存在: {graph_path}")
    
    graph = nx.read_graphml(str(path))
    
    # read_graphml 默认返回 Graph/DiGraph，确保是 DiGraph
    if not graph.is_directed():
        graph = graph.to_directed()
    
    return graph


def compute_pagerank(
    graph: nx.DiGraph,
    alpha: float = 0.85,
    weighted: bool = True,
    max_iter: int = 1000,
    tol: float = 1e-8,
) -> Dict[str, float]:
    """
    计算 PageRank
    
    Args:
        graph: 有向图
        alpha: 阻尼因子（默认 0.85）
        weighted: 是否使用边权重（weight 属性）
        max_iter: 最大迭代次数
        tol: 收敛容差
    
    Returns:
        {node_id: pagerank_score}
    """
    weight_key = "weight" if weighted else None
    
    pr = nx.pagerank(
        graph,
        alpha=alpha,
        weight=weight_key,
        max_iter=max_iter,
        tol=tol,
    )
    return pr


def build_ranking(
    graph: nx.DiGraph,
    pagerank_scores: Dict[str, float],
) -> list[Dict[str, Any]]:
    """
    构建排名表，附加节点属性和图拓扑统计
    
    Returns:
        排序后的列表，每项包含排名、repo名、PageRank分数、出入度等
    """
    rows = []
    for node, score in pagerank_scores.items():
        attrs = graph.nodes[node]
        
        in_degree = graph.in_degree(node)
        out_degree = graph.out_degree(node)
        
        # 加权入度/出度（即流入/流出的总人数）
        weighted_in = sum(
            d.get("weight", 1) for _, _, d in graph.in_edges(node, data=True)
        )
        weighted_out = sum(
            d.get("weight", 1) for _, _, d in graph.out_edges(node, data=True)
        )
        
        # 净流入 = 流入 - 流出（正值 = 人才汇聚地，负值 = 人才输出地）
        net_flow = weighted_in - weighted_out
        
        rows.append({
            "repo_name": attrs.get("repo_name", node),
            "pagerank": score,
            "in_degree": in_degree,
            "out_degree": out_degree,
            "weighted_in": weighted_in,
            "weighted_out": weighted_out,
            "net_flow": net_flow,
            "contributor_count": int(attrs.get("contributor_count", 0)),
            "total_events": int(attrs.get("total_events", 0)),
        })
    
    rows.sort(key=lambda r: r["pagerank"], reverse=True)
    
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    
    return rows


def print_ranking(rows: list[Dict[str, Any]], top_n: Optional[int] = None):
    """打印排名表"""
    display = rows[:top_n] if top_n else rows
    
    print()
    print(f"{'Rank':>4}  {'Repository':<45} {'PageRank':>10} "
          f"{'In':>4} {'Out':>4} {'W_In':>5} {'W_Out':>5} {'Net':>5} "
          f"{'Contributors':>12}")
    print("-" * 110)
    
    for row in display:
        net = row["net_flow"]
        net_str = f"+{net}" if net > 0 else str(net)
        print(
            f"{row['rank']:>4}  {row['repo_name']:<45} {row['pagerank']:>10.6f} "
            f"{row['in_degree']:>4} {row['out_degree']:>4} "
            f"{row['weighted_in']:>5} {row['weighted_out']:>5} {net_str:>5} "
            f"{row['contributor_count']:>12}"
        )
    
    if top_n and len(rows) > top_n:
        print(f"  ... 共 {len(rows)} 个项目，仅显示前 {top_n}")
    
    print()


def save_results(
    rows: list[Dict[str, Any]],
    output_dir: str,
    prefix: str = "pagerank",
):
    """保存结果为 CSV 和 JSON"""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    # CSV
    csv_path = out_path / f"{prefix}.csv"
    fieldnames = [
        "rank", "repo_name", "pagerank",
        "in_degree", "out_degree",
        "weighted_in", "weighted_out", "net_flow",
        "contributor_count", "total_events",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV 已保存: {csv_path}")
    
    # JSON
    json_path = out_path / f"{prefix}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    print(f"JSON 已保存: {json_path}")
    
    return csv_path, json_path


def analyze(
    graph_path: str = "output/repo-flow-graphs/global/repo-flow.graphml",
    output_dir: str = "output/repo-flow-graphs/global/",
    alpha: float = 0.85,
    weighted: bool = True,
    top_n: Optional[int] = None,
) -> list[Dict[str, Any]]:
    """
    完整分析流程
    
    Returns:
        排名列表
    """
    # 加载
    print(f"加载图: {graph_path}")
    graph = load_graph(graph_path)
    print(f"  节点: {graph.number_of_nodes()}, 边: {graph.number_of_edges()}")
    
    # PageRank
    mode_str = "加权" if weighted else "无权"
    print(f"计算 PageRank (alpha={alpha}, {mode_str})...")
    scores = compute_pagerank(graph, alpha=alpha, weighted=weighted)
    
    # 排名
    rows = build_ranking(graph, scores)
    
    # 打印
    print_ranking(rows, top_n=top_n)
    
    # 额外统计
    _print_flow_insights(rows)
    
    # 保存
    prefix = f"pagerank_{'weighted' if weighted else 'unweighted'}_a{alpha}"
    save_results(rows, output_dir, prefix=prefix)
    
    return rows


def _print_flow_insights(rows: list[Dict[str, Any]]):
    """打印流动洞察"""
    if not rows:
        return
    
    print("=" * 60)
    print("流动洞察")
    print("=" * 60)
    
    # 人才汇聚地 Top 5（净流入最高）
    by_net = sorted(rows, key=lambda r: r["net_flow"], reverse=True)
    print("\n人才汇聚地 Top 5 (净流入最高):")
    for r in by_net[:5]:
        net = r['net_flow']
        net_str = f"+{net}" if net > 0 else str(net)
        print(f"  {r['repo_name']:<45} net={net_str}, "
              f"in={r['weighted_in']}, out={r['weighted_out']}")
    
    # 人才输出地 Top 5（净流入最低 / 净流出最高）
    print("\n人才输出地 Top 5 (净流出最高):")
    for r in by_net[-5:]:
        net = r['net_flow']
        net_str = f"+{net}" if net > 0 else str(net)
        print(f"  {r['repo_name']:<45} net={net_str}, "
              f"in={r['weighted_in']}, out={r['weighted_out']}")
    
    # 枢纽项目（总流动量最大）
    by_total = sorted(rows, key=lambda r: r["weighted_in"] + r["weighted_out"], reverse=True)
    print("\n枢纽项目 Top 5 (总流动量最大):")
    for r in by_total[:5]:
        total = r["weighted_in"] + r["weighted_out"]
        print(f"  {r['repo_name']:<45} total={total}, "
              f"in={r['weighted_in']}, out={r['weighted_out']}")
    
    print()


def main():
    parser = argparse.ArgumentParser(
        description="对 Repo-Repo 人员流动图执行 PageRank 分析",
    )
    parser.add_argument(
        "--graph", type=str,
        default="output/repo-flow-graphs/global/repo-flow.graphml",
        help="GraphML 文件路径",
    )
    parser.add_argument(
        "--output-dir", type=str,
        default=None,
        help="结果输出目录 (默认: 与图文件同目录)",
    )
    parser.add_argument(
        "--alpha", type=float, default=0.85,
        help="PageRank 阻尼因子 (默认: 0.85)",
    )
    parser.add_argument(
        "--weighted", action="store_true", default=True,
        help="使用边权重 (默认: True)",
    )
    parser.add_argument(
        "--unweighted", action="store_true",
        help="不使用边权重",
    )
    parser.add_argument(
        "--top", type=int, default=None,
        help="只显示前 N 名 (默认: 全部)",
    )
    
    args = parser.parse_args()
    
    weighted = not args.unweighted
    output_dir = args.output_dir or str(Path(args.graph).parent)
    
    analyze(
        graph_path=args.graph,
        output_dir=output_dir,
        alpha=args.alpha,
        weighted=weighted,
        top_n=args.top,
    )


if __name__ == "__main__":
    main()