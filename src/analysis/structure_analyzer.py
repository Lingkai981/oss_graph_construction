"""
Actor-Actor 图结构指标分析（按项目×月份）

输入：
- graphs_dir: output/monthly-graphs/（包含 index.json 和各 repo 的 graphml）

输出：
- output_dir/full_analysis.json
- output_dir/summary.json
- output_dir/{safe_repo}.json（每个repo单独一份，方便查看）

指标（默认无权图、无向图、合并多重边）：
1) longest_shortest_path (diameter on LCC)
2) average_distance (average shortest path length on LCC)

并额外输出：
- connected_components_count / lcc_node_count / lcc_edge_count
- mean_node_avg_distance_on_lcc（每个节点到同分量其他节点的平均距离，再取平均）
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx


# ==================== 数据类 ====================

@dataclass
class MonthlyStructureMetrics:
    repo_name: str
    month: str

    node_count: int = 0
    edge_count: int = 0

    # 连通性
    connected_components_count: int = 0
    lcc_node_count: int = 0
    lcc_edge_count: int = 0
    is_connected: bool = False

    # 指标 1：最长的最短路径（直径）
    longest_shortest_path: Optional[int] = None  # diameter on LCC

    # 指标 2：最短的到其他节点的平均距离（平均最短路）
    average_distance: Optional[float] = None  # average shortest path length on LCC

    # 补充：节点平均距离的平均值（在 LCC 上）
    mean_node_avg_distance_on_lcc: Optional[float] = None

    # 记录计算时的信息
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_name": self.repo_name,
            "month": self.month,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "connected_components_count": self.connected_components_count,
            "lcc_node_count": self.lcc_node_count,
            "lcc_edge_count": self.lcc_edge_count,
            "is_connected": self.is_connected,
            "longest_shortest_path": self.longest_shortest_path,
            "average_distance": self.average_distance,
            "mean_node_avg_distance_on_lcc": self.mean_node_avg_distance_on_lcc,
            "notes": self.notes,
        }


# ==================== 工具函数 ====================

def load_graph(graph_path: Path) -> Optional[nx.MultiDiGraph]:
    """加载 GraphML 文件并返回 MultiDiGraph（和 burnout_analyzer 的风格保持一致）"""
    try:
        g = nx.read_graphml(str(graph_path))
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
    except Exception:
        return None


def to_simple_undirected(g_multi: nx.MultiDiGraph) -> nx.Graph:
    """
    Actor-Actor 原图是 MultiDiGraph（多重、有向）。
    指标默认无权图：这里转为无向简单图，合并多重边并忽略方向。
    """
    undirected_multi = g_multi.to_undirected()
    # nx.Graph 会自动合并多重边（仅保留一条）
    return nx.Graph(undirected_multi)


def largest_connected_component_subgraph(g: nx.Graph) -> Tuple[nx.Graph, int]:
    """
    返回最大连通分量子图以及连通分量数量。
    若 g 为空，返回空图。
    """
    if g.number_of_nodes() == 0:
        return g.copy(), 0

    comps = list(nx.connected_components(g))
    cc_count = len(comps)
    lcc_nodes = max(comps, key=len) if comps else set()
    lcc = g.subgraph(lcc_nodes).copy()
    return lcc, cc_count


def compute_mean_node_avg_distance(g_cc: nx.Graph) -> Optional[float]:
    """
    在一个连通图上：
    对每个节点 i 计算：avg_dist(i) = mean_{j!=i} dist(i,j)
    再对所有节点取平均。
    """
    n = g_cc.number_of_nodes()
    if n <= 1:
        return None

    # all_pairs_shortest_path_length 在无权图上是 BFS，n大时会比较慢
    # 但你现在先做两项指标，这里保持精确实现
    total = 0.0
    for source, dist_dict in nx.all_pairs_shortest_path_length(g_cc):
        # dist_dict 包含 source->source=0
        if len(dist_dict) <= 1:
            continue
        avg_i = (sum(dist_dict.values()) - 0.0) / (len(dist_dict) - 1)
        total += avg_i
    return total / n


# ==================== 分析器 ====================

class ActorActorStructureAnalyzer:
    def __init__(
        self,
        graphs_dir: str = "output/monthly-graphs/",
        output_dir: str = "output/actor-actor-structure/",
    ):
        self.graphs_dir = Path(graphs_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.repo_metrics: Dict[str, List[MonthlyStructureMetrics]] = defaultdict(list)

    def compute_monthly_metrics(
        self,
        g_multi: nx.MultiDiGraph,
        repo_name: str,
        month: str,
    ) -> MonthlyStructureMetrics:
        metrics = MonthlyStructureMetrics(repo_name=repo_name, month=month)

        g = to_simple_undirected(g_multi)
        metrics.node_count = g.number_of_nodes()
        metrics.edge_count = g.number_of_edges()

        if metrics.node_count == 0:
            metrics.notes.append("empty_graph")
            return metrics

        # 连通分量 & LCC
        lcc, cc_count = largest_connected_component_subgraph(g)
        metrics.connected_components_count = cc_count
        metrics.is_connected = (cc_count == 1)
        metrics.lcc_node_count = lcc.number_of_nodes()
        metrics.lcc_edge_count = lcc.number_of_edges()

        if metrics.lcc_node_count <= 1:
            metrics.notes.append("lcc_too_small")
            return metrics

        # 指标 1：最长的最短路径（直径）
        try:
            metrics.longest_shortest_path = int(nx.diameter(lcc))
        except Exception as e:
            metrics.notes.append(f"diameter_failed:{type(e).__name__}")

        # 指标 2：平均最短路径长度
        try:
            metrics.average_distance = float(nx.average_shortest_path_length(lcc))
        except Exception as e:
            metrics.notes.append(f"avg_shortest_path_failed:{type(e).__name__}")

        # 补充：节点平均距离的平均值
        try:
            metrics.mean_node_avg_distance_on_lcc = compute_mean_node_avg_distance(lcc)
        except Exception as e:
            metrics.notes.append(f"mean_node_avg_distance_failed:{type(e).__name__}")

        return metrics

    def analyze_all_repos(self) -> Dict[str, Any]:
        index_file = self.graphs_dir / "index.json"
        if not index_file.exists():
            raise FileNotFoundError(f"索引文件不存在: {index_file}（请先运行 monthly_graph_builder.py）")

        with open(index_file, "r", encoding="utf-8") as f:
            index = json.load(f)

        all_results: Dict[str, Any] = {}

        for repo_name, graph_types_data in index.items():
            # 兼容 index 两种结构
            first_value = next(iter(graph_types_data.values()), {})
            if isinstance(first_value, dict) and not first_value.get("node_type"):
                months = graph_types_data.get("actor-actor", {})
            else:
                months = graph_types_data

            metrics_series: List[MonthlyStructureMetrics] = []
            for month, graph_path in sorted(months.items()):
                g_multi = load_graph(Path(graph_path))
                if g_multi is None:
                    continue

                m = self.compute_monthly_metrics(g_multi, repo_name, month)
                metrics_series.append(m)
                self.repo_metrics[repo_name].append(m)

            all_results[repo_name] = {
                "repo_name": repo_name,
                "metrics": [m.to_dict() for m in metrics_series],
            }

        return all_results

    def save_results(self, results: Dict[str, Any]):
        # 全量
        full_path = self.output_dir / "full_analysis.json"
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # 每 repo 一份 + 摘要
        summary: List[Dict[str, Any]] = []

        for repo_name, data in results.items():
            safe_repo = repo_name.replace("/", "-")
            repo_path = self.output_dir / f"{safe_repo}.json"
            with open(repo_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            ms = data.get("metrics", [])
            if not ms:
                continue

            # 用最近一个月做摘要（也可以改成平均/中位数）
            last = sorted(ms, key=lambda x: x["month"])[-1]
            summary.append(
                {
                    "repo_name": repo_name,
                    "months_analyzed": len(ms),
                    "latest_month": last["month"],
                    "latest_node_count": last["node_count"],
                    "latest_edge_count": last["edge_count"],
                    "latest_cc_count": last["connected_components_count"],
                    "latest_lcc_node_count": last["lcc_node_count"],
                    "latest_longest_shortest_path": last["longest_shortest_path"],
                    "latest_average_distance": last["average_distance"],
                }
            )

        # 按“最长最短路径”降序（更“拉长”的图排前面）
        summary.sort(key=lambda x: (x["latest_longest_shortest_path"] is None, -(x["latest_longest_shortest_path"] or -1)))

        summary_path = self.output_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        print(f"已输出：{full_path}")
        print(f"已输出：{summary_path}")
        print(f"repo files：{self.output_dir}/*.json")

    def run(self) -> Dict[str, Any]:
        results = self.analyze_all_repos()
        self.save_results(results)
        return results


def main():
    parser = argparse.ArgumentParser(description="Actor-Actor structure metrics analyzer (monthly).")
    parser.add_argument("--graphs-dir", type=str, default="output/monthly-graphs/", help="月度图目录（含 index.json）")
    parser.add_argument("--output-dir", type=str, default="output/actor-actor-structure/", help="输出目录")
    args = parser.parse_args()

    analyzer = ActorActorStructureAnalyzer(
        graphs_dir=args.graphs_dir,
        output_dir=args.output_dir,
    )
    analyzer.run()


if __name__ == "__main__":
    main()
