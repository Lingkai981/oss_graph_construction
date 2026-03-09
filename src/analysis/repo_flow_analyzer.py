"""
Repo 流动图结构分析器

对 repo_flow_graph_builder.py 生成的 Repo→Repo 流动图进行多维结构分析：

算法指标：
  1. PageRank（加权，weight=actor_count）
     — 衡量 repo 作为贡献目标的长期吸引力
  2. HITS（Hubs & Authorities）
     — Hub：向外输送贡献者的 repo；Authority：吸引贡献者的 repo
  3. 入度 / 出度中心性
     — 直接衡量每个月流入 / 流出的贡献者量
  4. 加权介数中心性（Betweenness Centrality）
     — 衡量 repo 作为"跳板"的桥梁地位
  5. 净流量（Net Flow = weighted_in_degree - weighted_out_degree）
     — 正值：净吸引者；负值：净输出者
  6. 社区检测（Louvain / Greedy Modularity）
     — 发现经常相互交换贡献者的 repo 集群
  7. 时间序列趋势
     — 以上指标随时间的变化（线性斜率 + 近期变化率）

输出：
    {output_dir}/
        metrics/
            {prev}_to_{curr}_metrics.json   每次过渡的节点指标
        summary.json                         跨期汇总 & 排名
        report.html                          可交互 HTML 报告

用法：
    python src/analysis/repo_flow_analyzer.py \
        --flow-dir output/repo-flow-graphs \
        --output-dir output/repo-flow-analysis \
        --top-n 20 \
        --health-rank-file comprehensive_rank.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx


# ==================== 工具函数 ====================

def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b != 0 else default


def linear_slope(values: List[float]) -> float:
    """最小二乘法线性斜率（归一化到首个非零值）"""
    n = len(values)
    if n < 2:
        return 0.0
    first_nonzero = next((v for v in values if v != 0), 1.0)
    normed = [v / first_nonzero for v in values]
    x_mean = (n - 1) / 2
    y_mean = sum(normed) / n
    num = sum((i - x_mean) * (normed[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return safe_div(num, den)


def change_rate(values: List[float]) -> float:
    """最近3期 vs 最早3期的均值变化率"""
    if len(values) < 2:
        return 0.0
    w = min(3, len(values) // 2) if len(values) >= 4 else 1
    early = sum(values[:w]) / w
    recent = sum(values[-w:]) / w
    return safe_div(recent - early, early)



# ==================== 肯德尔等级相关系数 ====================

def kendall_tau_b(x_ranks: List[float], y_ranks: List[float]) -> float:
    """
    Kendall tau-b，处理并列值。
    tau-b = (C - D) / sqrt((C+D+T_x)*(C+D+T_y))
    C = 一致对，D = 不一致对，T_x/T_y = 仅在一侧并列的对数。
    tau-b in [-1, 1]；O(n^2)，49 个样本完全够用。
    """
    n = len(x_ranks)
    if n != len(y_ranks) or n < 2:
        return float("nan")
    C = D = T_x = T_y = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = x_ranks[i] - x_ranks[j]
            dy = y_ranks[i] - y_ranks[j]
            prod = dx * dy
            if prod > 0:
                C += 1
            elif prod < 0:
                D += 1
            else:
                if dx == 0 and dy != 0:
                    T_x += 1
                elif dy == 0 and dx != 0:
                    T_y += 1
    denom = math.sqrt((C + D + T_x) * (C + D + T_y))
    return float("nan") if denom == 0 else (C - D) / denom


def compute_kendall_correlations(
    aggregated: Dict[str, Any],
    health_ranks: Dict[str, int],
) -> Dict[str, Any]:
    """
    对每个流动图指标的均值排名，与综合健康排名计算 Kendall tau-b。

    仅在 aggregated 与 health_ranks 的交集 repo 上计算。
    指标排名：均值降序，rank=1 最高，并列取平均名次。
    健康排名：health_ranks[repo] = rank_number（rank=1 最健康）。
    tau > 0 表示该指标与健康度正相关。
    """
    common_repos = sorted(set(aggregated.keys()) & set(health_ranks.keys()))
    n = len(common_repos)
    result: Dict[str, Any] = {
        "overlap_count": n,
        "overlap_repos": common_repos,
        "metrics": {},
    }
    if n < 3:
        return result

    metrics_cfg = [
        ("pagerank",     "mean", True,  "PageRank 均值"),
        ("hits_auth",    "mean", True,  "HITS Authority"),
        ("hits_hub",     "mean", True,  "HITS Hub"),
        ("net_flow",     "mean", True,  "净流量均值"),
        ("betweenness",  "mean", True,  "介数中心性"),
        ("weighted_in",  "mean", True,  "加权入度均值"),
        ("weighted_out", "mean", False, "加权出度均值"),
    ]

    health_rank_vec = [health_ranks[r] for r in common_repos]

    for metric_key, sub_key, higher_better, label in metrics_cfg:
        values = {
            repo: aggregated[repo][metric_key][sub_key]
            for repo in common_repos
            if metric_key in aggregated.get(repo, {})
        }
        if len(values) < 3:
            continue

        # 均值降序排列，并列取平均名次
        sorted_by_val = sorted(values.items(), key=lambda x: x[1], reverse=True)
        flow_rank: Dict[str, float] = {}
        i = 0
        while i < len(sorted_by_val):
            j = i
            while j + 1 < len(sorted_by_val) and sorted_by_val[j+1][1] == sorted_by_val[i][1]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                flow_rank[sorted_by_val[k][0]] = avg_rank
            i = j + 1

        flow_rank_vec = [flow_rank[r] for r in common_repos]
        tau = kendall_tau_b(flow_rank_vec, health_rank_vec)

        # Spearman ρ（直接用排名向量，不重新排序，因为 flow_rank 已是排名）
        n_c = len(common_repos)
        mean_x = sum(flow_rank_vec) / n_c
        mean_y = sum(health_rank_vec) / n_c
        num_s = sum((flow_rank_vec[i] - mean_x) * (health_rank_vec[i] - mean_y) for i in range(n_c))
        den_s = math.sqrt(
            sum((v - mean_x) ** 2 for v in flow_rank_vec) *
            sum((v - mean_y) ** 2 for v in health_rank_vec)
        )
        spearman = num_s / den_s if den_s != 0 else float("nan")

        # 取平均（任一为 nan 时退化为另一个）
        if math.isnan(tau) and math.isnan(spearman):
            combined = float("nan")
        elif math.isnan(tau):
            combined = spearman
        elif math.isnan(spearman):
            combined = tau
        else:
            combined = (tau + spearman) / 2

        if math.isnan(combined):          interp = "无法计算"
        elif combined >= 0.5:             interp = "强正相关"
        elif combined >= 0.3:             interp = "中等正相关"
        elif combined >= 0.1:             interp = "弱正相关"
        elif combined >= -0.1:            interp = "几乎无相关"
        elif combined >= -0.3:            interp = "弱负相关"
        elif combined >= -0.5:            interp = "中等负相关"
        else:                        interp = "强负相关"

        result["metrics"][metric_key] = {
            "label":          label,
            "tau":            round(tau, 4),
            "spearman":       round(spearman, 4) if not math.isnan(spearman) else None,
            "combined":       round(combined, 4) if not math.isnan(combined) else None,
            "interpretation": interp,
            "higher_better":  higher_better,
            "ranking_table": [
                {
                    "repo":         r,
                    "flow_rank":    flow_rank[r],
                    "metric_value": round(values[r], 6),
                    "health_rank":  health_ranks[r],
                }
                for r in common_repos
            ],
        }
    return result


# ==================== 图加载 ====================

def load_index(flow_dir: Path) -> Dict[str, Any]:
    index_path = flow_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"index.json 不存在: {index_path}")
    with open(index_path, encoding="utf-8") as f:
        return json.load(f)


def load_flow_graph(path: str | Path) -> nx.DiGraph:
    g = nx.read_graphml(str(path))
    # GraphML 读回来是字符串属性，actor_count 需转为 float
    for u, v, data in g.edges(data=True):
        data["actor_count"] = float(data.get("actor_count", 1))
        data["weight"] = data["actor_count"]
    return g


# ==================== 单期分析 ====================

def analyze_single_graph(
    g: nx.DiGraph,
    prev_period: str,
    curr_period: str,
) -> Dict[str, Any]:
    """
    对单次过渡图计算所有节点指标。

    Returns:
        {
          "transition": ...,
          "graph_stats": {...},
          "nodes": { repo_name: { pagerank, hits_hub, hits_auth,
                                   in_degree, out_degree,
                                   weighted_in, weighted_out, net_flow,
                                   betweenness } }
        }
    """
    nodes = list(g.nodes())
    n = len(nodes)
    e = g.number_of_edges()

    result: Dict[str, Any] = {
        "transition": f"{prev_period}_to_{curr_period}",
        "prev_period": prev_period,
        "curr_period": curr_period,
        "graph_stats": {
            "node_count": n,
            "edge_count": e,
            "density": nx.density(g) if n > 1 else 0.0,
            "weakly_connected_components": nx.number_weakly_connected_components(g),
            "strongly_connected_components": nx.number_strongly_connected_components(g),
        },
        "nodes": {},
    }

    if n == 0:
        return result

    # ── 1. PageRank（加权）──────────────────────────────
    try:
        pagerank = nx.pagerank(g, weight="weight", max_iter=200)
    except nx.PowerIterationFailedConvergence:
        pagerank = nx.pagerank(g, weight=None, max_iter=500)

    # ── 2. HITS ─────────────────────────────────────────
    try:
        hits_hub, hits_auth = nx.hits(g, max_iter=300, normalized=True)
    except nx.PowerIterationFailedConvergence:
        hits_hub = {nd: 0.0 for nd in nodes}
        hits_auth = {nd: 0.0 for nd in nodes}

    # ── 3. 加权度数 ──────────────────────────────────────
    weighted_in: Dict[str, float] = defaultdict(float)
    weighted_out: Dict[str, float] = defaultdict(float)
    for u, v, data in g.edges(data=True):
        w = data.get("actor_count", 1.0)
        weighted_out[u] += w
        weighted_in[v] += w

    in_deg = dict(g.in_degree())
    out_deg = dict(g.out_degree())

    # ── 4. 加权介数中心性 ────────────────────────────────
    # 大图时介数中心性开销较大；节点数 > 500 时降采样近似
    if n <= 500:
        try:
            betweenness = nx.betweenness_centrality(g, weight="weight", normalized=True)
        except Exception:
            betweenness = {nd: 0.0 for nd in nodes}
    else:
        try:
            betweenness = nx.betweenness_centrality(
                g, k=min(200, n), weight="weight", normalized=True, seed=42
            )
        except Exception:
            betweenness = {nd: 0.0 for nd in nodes}

    # ── 5. 汇总 ─────────────────────────────────────────
    for repo in nodes:
        w_in = weighted_in.get(repo, 0.0)
        w_out = weighted_out.get(repo, 0.0)
        result["nodes"][repo] = {
            "pagerank":    round(pagerank.get(repo, 0.0), 6),
            "hits_hub":    round(hits_hub.get(repo, 0.0), 6),
            "hits_auth":   round(hits_auth.get(repo, 0.0), 6),
            "in_degree":   in_deg.get(repo, 0),
            "out_degree":  out_deg.get(repo, 0),
            "weighted_in":  round(w_in, 2),
            "weighted_out": round(w_out, 2),
            "net_flow":    round(w_in - w_out, 2),
            "betweenness": round(betweenness.get(repo, 0.0), 6),
        }

    return result


# ==================== 跨期聚合 ====================

def aggregate_across_periods(
    period_metrics: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    将各期节点指标聚合为每个 repo 的时间序列统计。

    Returns:
        {
          repo_name: {
            "periods": [...],
            "pagerank":    { "values": [...], "mean", "slope", "change_rate" },
            "hits_hub":    { ... },
            "hits_auth":   { ... },
            "net_flow":    { ... },
            "betweenness": { ... },
            "weighted_in": { ... },
            "weighted_out":{ ... },
          }
        }
    """
    # 收集所有 repo 在各期的指标
    repo_timeline: Dict[str, Dict[str, List]] = defaultdict(
        lambda: defaultdict(list)
    )
    repo_periods: Dict[str, List[str]] = defaultdict(list)

    metrics_keys = [
        "pagerank", "hits_hub", "hits_auth",
        "weighted_in", "weighted_out", "net_flow", "betweenness",
    ]

    for pm in sorted(period_metrics, key=lambda x: x["curr_period"]):
        curr = pm["curr_period"]
        for repo, metrics in pm["nodes"].items():
            repo_periods[repo].append(curr)
            for k in metrics_keys:
                repo_timeline[repo][k].append(metrics.get(k, 0.0))

    aggregated: Dict[str, Any] = {}
    for repo in repo_timeline:
        entry: Dict[str, Any] = {"periods": repo_periods[repo]}
        for k in metrics_keys:
            vals = repo_timeline[repo][k]
            entry[k] = {
                "values":      [round(v, 6) for v in vals],
                "mean":        round(sum(vals) / len(vals), 6) if vals else 0.0,
                "max":         round(max(vals), 6) if vals else 0.0,
                "slope":       round(linear_slope(vals), 6),
                "change_rate": round(change_rate(vals), 4),
            }
        aggregated[repo] = entry

    return aggregated


def build_summary(
    aggregated: Dict[str, Any],
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    生成排名摘要（各维度 Top-N）。
    """

    def rank_by(key: str, sub: str = "mean", reverse: bool = True) -> List[Dict]:
        items = [
            {"repo": repo, "value": data[key][sub]}
            for repo, data in aggregated.items()
            if key in data
        ]
        items.sort(key=lambda x: x["value"], reverse=reverse)
        return items[:top_n]

    # 趋势上升最显著（slope 最大）
    def rank_trend(key: str) -> List[Dict]:
        items = [
            {"repo": repo, "slope": data[key]["slope"], "change_rate": data[key]["change_rate"]}
            for repo, data in aggregated.items()
            if key in data
        ]
        items.sort(key=lambda x: x["slope"], reverse=True)
        return items[:top_n]

    return {
        "top_pagerank":        rank_by("pagerank", "mean"),
        "top_authority":       rank_by("hits_auth", "mean"),
        "top_hub":             rank_by("hits_hub", "mean"),
        "top_net_inflow":      rank_by("net_flow", "mean"),
        "top_net_outflow":     rank_by("net_flow", "mean", reverse=False),
        "top_betweenness":     rank_by("betweenness", "mean"),
        "rising_pagerank":     rank_trend("pagerank"),
        "falling_pagerank":    sorted(
            [
                {"repo": repo, "slope": data["pagerank"]["slope"], "change_rate": data["pagerank"]["change_rate"]}
                for repo, data in aggregated.items()
                if "pagerank" in data
            ],
            key=lambda x: x["slope"],
        )[:top_n],
    }


# ==================== 社区检测 ====================

def detect_communities(flow_dir: Path, index: Dict[str, Any]) -> Dict[str, Any]:
    """
    在聚合图（所有期边叠加）上做社区检测。
    使用 Louvain（若可用）或回退到贪心模块度。

    Returns:
        { repo_name: community_id }
    """
    # 构建无向聚合图
    agg = nx.Graph()
    for fname, info in index.get("graphs", {}).items():
        path = Path(info["path"])
        if not path.exists():
            path = flow_dir / fname
        if not path.exists():
            continue
        g = load_flow_graph(path)
        for u, v, data in g.edges(data=True):
            w = data.get("actor_count", 1.0)
            if agg.has_edge(u, v):
                agg[u][v]["weight"] += w
            else:
                agg.add_edge(u, v, weight=w)

    if agg.number_of_nodes() == 0:
        return {}

    # 尝试 python-louvain
    try:
        import community as community_louvain
        partition = community_louvain.best_partition(agg, weight="weight", random_state=42)
        method = "louvain"
    except ImportError:
        # 回退：贪心模块度
        try:
            from networkx.algorithms.community import greedy_modularity_communities
            communities = greedy_modularity_communities(agg, weight="weight")
            partition = {}
            for cid, comm in enumerate(communities):
                for node in comm:
                    partition[node] = cid
            method = "greedy_modularity"
        except Exception:
            partition = {node: 0 for node in agg.nodes()}
            method = "none"

    # 按社区大小重编号（0 = 最大社区）
    from collections import Counter
    size_rank = {cid: rank for rank, (cid, _) in
                 enumerate(Counter(partition.values()).most_common())}
    partition = {repo: size_rank[cid] for repo, cid in partition.items()}

    return {"communities": partition, "method": method, "node_count": agg.number_of_nodes()}


# ==================== HTML 报告生成 ====================

def generate_html_report(
    summary: Dict[str, Any],
    aggregated: Dict[str, Any],
    period_metrics: List[Dict[str, Any]],
    community_result: Dict[str, Any],
    output_path: Path,
    top_n: int = 20,
    kendall_result: Dict[str, Any] = None,
) -> None:
    """生成自包含的 HTML 交互式报告（内嵌 Chart.js）"""

    periods = sorted({pm["curr_period"] for pm in period_metrics})

    # 准备图表数据
    top_pr_repos   = [x["repo"] for x in summary["top_pagerank"][:top_n]]
    top_auth_repos = [x["repo"] for x in summary["top_authority"][:top_n]]
    top_hub_repos  = [x["repo"] for x in summary["top_hub"][:top_n]]
    top_btw_repos  = [x["repo"] for x in summary["top_betweenness"][:top_n]]

    def sparkline_data(repos: List[str], key: str) -> str:
        """生成折线图 datasets JSON"""
        palette = [
            "#60a5fa","#34d399","#f59e0b","#f87171","#a78bfa",
            "#38bdf8","#4ade80","#fb923c","#e879f9","#94a3b8",
            "#22d3ee","#86efac","#fcd34d","#fca5a5","#c4b5fd",
            "#7dd3fc","#6ee7b7","#fde68a","#fecaca","#ddd6fe",
        ]
        datasets = []
        for i, repo in enumerate(repos):
            if repo not in aggregated:
                continue
            vals = aggregated[repo][key]["values"]
            repo_periods = aggregated[repo]["periods"]
            # 对齐到全局 periods（缺失补 null）
            period_map = dict(zip(repo_periods, vals))
            data = [period_map.get(p, None) for p in periods]
            color = palette[i % len(palette)]
            datasets.append({
                "label": repo,
                "data": data,
                "borderColor": color,
                "backgroundColor": color + "22",
                "tension": 0.3,
                "pointRadius": 3,
                "borderWidth": 2,
                "fill": False,
            })
        return json.dumps(datasets)

    pr_datasets   = sparkline_data(top_pr_repos[:10], "pagerank")
    auth_datasets = sparkline_data(top_auth_repos[:10], "hits_auth")
    hub_datasets  = sparkline_data(top_hub_repos[:10], "hits_hub")

    # 净流量条形图（Top 正 + Top 负）
    net_flow_repos = (
        summary["top_net_inflow"][:10] +
        summary["top_net_outflow"][:10]
    )
    net_flow_labels = [x["repo"] for x in net_flow_repos]
    net_flow_values = [x["value"] for x in net_flow_repos]
    net_flow_colors = [
        "#34d399" if v >= 0 else "#f87171" for v in net_flow_values
    ]

    # 社区检测结果
    community_data = community_result.get("communities", {})
    community_method = community_result.get("method", "none")
    community_by_id: Dict[int, List[str]] = defaultdict(list)
    for repo, cid in community_data.items():
        community_by_id[cid].append(repo)

    community_rows = ""
    community_palette = [
        "#60a5fa","#34d399","#f59e0b","#f87171","#a78bfa",
        "#38bdf8","#4ade80","#fb923c","#e879f9","#94a3b8",
    ]
    for cid in sorted(community_by_id.keys())[:15]:
        repos = sorted(community_by_id[cid])
        color = community_palette[cid % len(community_palette)]
        repo_pills = "".join(
            f'<span class="pill" style="background:{color}22;border-color:{color}88;color:{color}">{r}</span>'
            for r in repos[:20]
        )
        suffix = f'<span class="pill-more">+{len(repos)-20} more</span>' if len(repos) > 20 else ""
        community_rows += f"""
        <tr>
          <td><span class="comm-badge" style="background:{color}">{cid}</span></td>
          <td>{len(repos)}</td>
          <td class="pill-cell">{repo_pills}{suffix}</td>
        </tr>"""

    # 排名表格构建
    def make_table_rows(items: List[Dict], value_key: str = "value", fmt: str = ".4f") -> str:
        rows = ""
        for i, item in enumerate(items[:top_n], 1):
            val = item.get(value_key, item.get("slope", 0))
            bar_pct = min(100, abs(val) * 300) if abs(val) < 1 else min(100, abs(val) / 10 * 100)
            bar_color = "#60a5fa" if val >= 0 else "#f87171"
            rows += f"""
            <tr>
              <td class="rank">#{i}</td>
              <td class="repo-name">{item['repo']}</td>
              <td class="metric-val">{val:{fmt}}</td>
              <td class="bar-cell">
                <div class="bar" style="width:{bar_pct:.1f}%;background:{bar_color}"></div>
              </td>
            </tr>"""
        return rows

    pr_rows   = make_table_rows(summary["top_pagerank"])
    auth_rows = make_table_rows(summary["top_authority"])
    hub_rows  = make_table_rows(summary["top_hub"])
    btw_rows  = make_table_rows(summary["top_betweenness"])
    rising_rows  = make_table_rows(summary["rising_pagerank"],  value_key="slope", fmt=".4f")
    falling_rows = make_table_rows(summary["falling_pagerank"], value_key="slope", fmt=".4f")

    # 图级统计时间序列
    graph_stats_rows = ""
    for pm in sorted(period_metrics, key=lambda x: x["curr_period"]):
        gs = pm["graph_stats"]
        graph_stats_rows += f"""
        <tr>
          <td>{pm['prev_period']}</td>
          <td>{pm['curr_period']}</td>
          <td>{gs['node_count']}</td>
          <td>{gs['edge_count']}</td>
          <td>{gs['density']:.4f}</td>
          <td>{gs['weakly_connected_components']}</td>
          <td>{gs['strongly_connected_components']}</td>
        </tr>"""

    # ── Kendall Section 09 rendering ─────────────────────────────────────
    k = kendall_result or {}
    k_metrics = k.get("metrics", {})
    k_overlap  = k.get("overlap_count", 0)

    tau_color_map = {
        "强正相关":   "#34d399", "中等正相关": "#86efac",
        "弱正相关":   "#94a3b8", "几乎无相关": "#64748b",
        "弱负相关":   "#fca5a5", "中等负相关": "#f87171",
        "强负相关":   "#ef4444", "无法计算":   "#475569",
    }

    if k_metrics:
        # Summary stat cards
        summary_cards_html = ""
        for mk, mv in k_metrics.items():
            tau_val = mv["combined"]
            interp  = mv["interpretation"]
            color   = tau_color_map.get(interp, "#94a3b8")
            sign    = "+" if tau_val > 0 else ""
            summary_cards_html += (
                f'<div class="stat-card" style="border-color:{color}44">'
                f'<div class="stat-label">{mv["label"]}</div>'
                f'<div class="stat-value" style="color:{color};font-size:22px">{sign}{tau_val:.4f}</div>'
                f'<div class="stat-sub" style="color:{color}">{interp}</div>'
                f'</div>'
            )

        # Per-metric detail tables as tabs
        tab_btns_html  = ""
        tab_panels_html = ""
        for mi, (mk, mv) in enumerate(k_metrics.items()):
            active_cls = "active" if mi == 0 else ""
            pid = "ktab-" + mk
            tab_btns_html += (
                f'<button class="tab-btn {active_cls}"'
                f' onclick="switchTab(this,\'{pid}\')">'
                f'{mv["label"]}</button>'
            )
            rows_html = ""
            for row in sorted(mv["ranking_table"], key=lambda x: x["flow_rank"]):
                diff = row["health_rank"] - row["flow_rank"]
                diff_str   = f"+{diff:.0f}" if diff > 0 else f"{diff:.0f}"
                diff_color = "#f87171" if diff > 3 else ("#34d399" if diff < -3 else "#94a3b8")
                rows_html += (
                    f'<tr>'
                    f'<td class="rank">#{row["flow_rank"]:.0f}</td>'
                    f'<td class="repo-name">{row["repo"]}</td>'
                    f'<td class="metric-val">{row["metric_value"]:.4f}</td>'
                    f'<td class="rank">#{row["health_rank"]}</td>'
                    f'<td class="metric-val" style="color:{diff_color}">{diff_str}</td>'
                    f'</tr>'
                )
            tab_panels_html += (
                f'<div id="{pid}" class="tab-panel {active_cls}">'
                f'<div class="card">'
                f'<div class="card-title">{mv["label"]} vs 健康度排名对照（共 {len(mv["ranking_table"])} 个项目）</div>'
                f'<div class="table-wrap"><table>'
                f'<thead><tr><th>流动图排名</th><th>Repo</th><th>指标值</th><th>健康度排名</th><th>名次差</th></tr></thead>'
                f'<tbody>{rows_html}</tbody>'
                f'</table></div></div></div>'
            )

        kendall_html_block = (
            f'<div class="stat-card" style="margin-bottom:20px;border-color:#3b82f644">'
            f'<div class="stat-label">参与计算的仓库数</div>'
            f'<div class="stat-value">{k_overlap}</div>'
            f'<div class="stat-sub">同时出现在流动图与综合健康排名中的仓库</div>'
            f'</div>'
            f'<div class="grid-4" style="margin-bottom:24px">{summary_cards_html}</div>'
            f'<div class="card" style="margin-bottom:24px">'
            f'<div class="card-title">各指标 Kendall τ-b 一览（水平条形图）</div>'
            f'<div class="chart-wrap"><canvas id="kendallChart" style="max-height:280px"></canvas></div>'
            f'</div>'
            f'<div class="tabs">{tab_btns_html}</div>'
            f'{tab_panels_html}'
        )

        k_labels  = [v["label"]          for v in k_metrics.values()]
        k_values  = [v["combined"]             for v in k_metrics.values()]
        k_interps = [v["interpretation"]  for v in k_metrics.values()]
        kendall_chart_json = json.dumps({
            "labels": k_labels, "values": k_values, "interps": k_interps,
        })
    else:
        kendall_html_block = (
            '<div class="card">'
            '<div class="card-title">未提供综合健康排名文件</div>'
            '<p style="color:var(--muted);padding:16px">'
            '请通过 <code>--health-rank-file</code> 传入 <code>comprehensive_rank.json</code>，'
            '脚本将自动计算 Kendall τ-b 并在此处展示结果。'
            '</p></div>'
        )
        kendall_chart_json = "null"


    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Repo 流动图 · 结构分析报告</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:       #0b0f1a;
    --surface:  #111827;
    --surface2: #1a2236;
    --border:   #1e2d45;
    --accent:   #3b82f6;
    --accent2:  #10b981;
    --accent3:  #f59e0b;
    --text:     #e2e8f0;
    --muted:    #64748b;
    --font-mono: 'Space Mono', monospace;
    --font-sans: 'DM Sans', sans-serif;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-sans);
    font-size: 14px;
    line-height: 1.6;
  }}

  /* ── Header ── */
  .header {{
    padding: 56px 48px 40px;
    border-bottom: 1px solid var(--border);
    background: linear-gradient(135deg, #0b0f1a 60%, #0f172a);
    position: relative;
    overflow: hidden;
  }}
  .header::before {{
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse 60% 80% at 80% 50%, #1e3a5f44 0%, transparent 70%);
    pointer-events: none;
  }}
  .header-tag {{
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--accent);
    letter-spacing: .12em;
    text-transform: uppercase;
    margin-bottom: 12px;
  }}
  .header h1 {{
    font-family: var(--font-mono);
    font-size: clamp(22px, 3vw, 36px);
    font-weight: 700;
    color: #f1f5f9;
    letter-spacing: -.02em;
    line-height: 1.2;
  }}
  .header h1 span {{ color: var(--accent); }}
  .header-sub {{
    margin-top: 10px;
    font-size: 13px;
    color: var(--muted);
    max-width: 600px;
  }}
  .header-meta {{
    margin-top: 24px;
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
  }}
  .meta-chip {{
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 14px;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--muted);
  }}
  .meta-chip strong {{ color: var(--text); font-size: 13px; }}

  /* ── Nav ── */
  nav {{
    position: sticky;
    top: 0;
    z-index: 100;
    background: #0b0f1aee;
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 0 48px;
    display: flex;
    gap: 4px;
    overflow-x: auto;
  }}
  nav a {{
    display: inline-block;
    padding: 14px 16px;
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--muted);
    text-decoration: none;
    border-bottom: 2px solid transparent;
    white-space: nowrap;
    transition: color .2s, border-color .2s;
  }}
  nav a:hover {{ color: var(--text); }}
  nav a.active {{ color: var(--accent); border-color: var(--accent); }}

  /* ── Layout ── */
  .container {{ max-width: 1400px; margin: 0 auto; padding: 40px 48px; }}
  section {{ margin-bottom: 64px; }}
  .section-title {{
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: .15em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 6px;
  }}
  .section-heading {{
    font-size: 20px;
    font-weight: 600;
    color: #f1f5f9;
    margin-bottom: 6px;
  }}
  .section-desc {{
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 28px;
    max-width: 680px;
  }}

  /* ── Cards ── */
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 24px;
  }}
  .card-title {{
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 16px;
  }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }}
  .grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
  @media (max-width: 900px) {{
    .grid-2, .grid-3, .grid-4 {{ grid-template-columns: 1fr; }}
    .container {{ padding: 24px 20px; }}
    nav {{ padding: 0 20px; }}
    .header {{ padding: 32px 20px 24px; }}
  }}

  /* ── Stat cards ── */
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px 24px;
  }}
  .stat-label {{ font-size: 11px; color: var(--muted); margin-bottom: 6px; font-family: var(--font-mono); letter-spacing:.08em; text-transform:uppercase; }}
  .stat-value {{ font-family: var(--font-mono); font-size: 28px; font-weight: 700; color: #f1f5f9; }}
  .stat-sub {{ font-size: 11px; color: var(--muted); margin-top: 4px; }}

  /* ── Charts ── */
  .chart-wrap {{ position: relative; }}
  .chart-wrap canvas {{ max-height: 320px; }}

  /* ── Tables ── */
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--muted);
    padding: 10px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }}
  td {{
    padding: 10px 12px;
    border-bottom: 1px solid #1a2236;
    vertical-align: middle;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #1a2236; }}
  .rank {{ font-family: var(--font-mono); font-size: 11px; color: var(--muted); width: 40px; }}
  .repo-name {{ font-family: var(--font-mono); font-size: 12px; color: var(--accent); max-width: 280px; word-break: break-all; }}
  .metric-val {{ font-family: var(--font-mono); font-size: 12px; text-align: right; width: 90px; }}
  .bar-cell {{ width: 120px; }}
  .bar {{ height: 6px; border-radius: 3px; min-width: 2px; transition: width .3s; }}

  /* ── Tabs ── */
  .tabs {{ display: flex; gap: 4px; margin-bottom: 20px; flex-wrap: wrap; }}
  .tab-btn {{
    padding: 7px 16px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: transparent;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: .08em;
    text-transform: uppercase;
    cursor: pointer;
    transition: all .2s;
  }}
  .tab-btn:hover {{ color: var(--text); border-color: var(--accent); }}
  .tab-btn.active {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}

  /* ── Community pills ── */
  .pill-cell {{ max-width: 500px; }}
  .pill {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    border: 1px solid;
    font-family: var(--font-mono);
    font-size: 10px;
    margin: 2px 2px;
  }}
  .pill-more {{ font-size: 10px; color: var(--muted); margin-left: 4px; }}
  .comm-badge {{
    display: inline-block;
    width: 24px; height: 24px;
    border-radius: 50%;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 700;
    color: #fff;
    line-height: 24px;
    text-align: center;
  }}

  /* ── Divider ── */
  .divider {{ border: none; border-top: 1px solid var(--border); margin: 0; }}

  /* ── Footer ── */
  footer {{
    padding: 32px 48px;
    border-top: 1px solid var(--border);
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--muted);
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
  }}
</style>
</head>
<body>

<!-- Header -->
<header class="header">
  <div class="header-tag">Repo Flow Graph · Structural Analysis</div>
  <h1>社区人员流动<span>·</span>结构分析报告</h1>
  <p class="header-sub">
    基于 PageRank、HITS、介数中心性、净流量及社区检测，
    揭示开源社区贡献者在仓库间的迁移规律与网络结构。
  </p>
  <div class="header-meta">
    <div class="meta-chip">时间范围 <strong>{periods[0] if periods else "—"} → {periods[-1] if periods else "—"}</strong></div>
    <div class="meta-chip">分析期数 <strong>{len(period_metrics)}</strong></div>
    <div class="meta-chip">涉及仓库 <strong>{len(aggregated)}</strong></div>
    <div class="meta-chip">社区算法 <strong>{community_method}</strong></div>
  </div>
</header>

<!-- Nav -->
<nav>
  <a href="#overview" class="active">概览</a>
  <a href="#pagerank">PageRank</a>
  <a href="#hits">HITS</a>
  <a href="#netflow">净流量</a>
  <a href="#betweenness">介数中心性</a>
  <a href="#trends">趋势分析</a>
  <a href="#community">社区检测</a>
  <a href="#timeline">图结构时序</a>
  <a href="#kendall">健康度相关</a>
</nav>

<div class="container">

<!-- ════════════════ 1. OVERVIEW ════════════════ -->
<section id="overview">
  <div class="section-title">Section 01</div>
  <div class="section-heading">数据概览</div>
  <div class="section-desc">各期图结构汇总统计</div>

  <div class="grid-4" style="margin-bottom:24px">
    <div class="stat-card">
      <div class="stat-label">分析时间跨度</div>
      <div class="stat-value">{len(periods)}</div>
      <div class="stat-sub">个月度过渡</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">涉及仓库总数</div>
      <div class="stat-value">{len(aggregated)}</div>
      <div class="stat-sub">unique repos</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">社区数量</div>
      <div class="stat-value">{len(community_by_id)}</div>
      <div class="stat-sub">检测方法：{community_method}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">总流动边数</div>
      <div class="stat-value">{sum(pm['graph_stats']['edge_count'] for pm in period_metrics)}</div>
      <div class="stat-sub">跨所有时间段</div>
    </div>
  </div>

  <div class="card">
    <div class="card-title">各期节点数 & 边数趋势</div>
    <div class="chart-wrap">
      <canvas id="overviewChart"></canvas>
    </div>
  </div>
</section>

<hr class="divider">

<!-- ════════════════ 2. PAGERANK ════════════════ -->
<section id="pagerank">
  <div class="section-title">Section 02</div>
  <div class="section-heading">PageRank — 长期吸引力</div>
  <div class="section-desc">
    PageRank 衡量一个 repo 在整个流动网络中作为贡献目标的<strong>长期权威性</strong>。
    加权版本（weight=actor_count）使更多人流入的路径获得更高权重。
    高 PageRank 的 repo 是整个社区贡献者汇聚的核心目的地。
  </div>
  <div class="grid-2">
    <div class="card">
      <div class="card-title">Top {min(top_n, 10)} Repos · PageRank 时间序列</div>
      <div class="chart-wrap"><canvas id="prTimeChart"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Top {top_n} Repos · 平均 PageRank 排名</div>
      <div class="table-wrap">
        <table><thead><tr><th>#</th><th>Repo</th><th>Avg PR</th><th>分布</th></tr></thead>
        <tbody>{pr_rows}</tbody></table>
      </div>
    </div>
  </div>
</section>

<hr class="divider">

<!-- ════════════════ 3. HITS ════════════════ -->
<section id="hits">
  <div class="section-title">Section 03</div>
  <div class="section-heading">HITS — Hub & Authority</div>
  <div class="section-desc">
    <strong>Authority</strong>（权威度）衡量 repo 被高质量 Hub 指向的程度，即"值得贡献的目的地"。
    <strong>Hub</strong>（枢纽度）衡量 repo 向高质量 Authority 输送贡献者的程度，即"贡献者的跳板"。
    两者不互斥：大型平台型项目往往同时是强 Hub 和强 Authority。
  </div>
  <div class="grid-2">
    <div class="card">
      <div class="card-title">Top {top_n} · Authority 排名</div>
      <div class="table-wrap">
        <table><thead><tr><th>#</th><th>Repo</th><th>Authority</th><th>分布</th></tr></thead>
        <tbody>{auth_rows}</tbody></table>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Top {top_n} · Hub 排名</div>
      <div class="table-wrap">
        <table><thead><tr><th>#</th><th>Repo</th><th>Hub</th><th>分布</th></tr></thead>
        <tbody>{hub_rows}</tbody></table>
      </div>
    </div>
  </div>
  <div class="grid-2" style="margin-top:20px">
    <div class="card">
      <div class="card-title">Top 10 Authority 时间序列</div>
      <div class="chart-wrap"><canvas id="authTimeChart"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Top 10 Hub 时间序列</div>
      <div class="chart-wrap"><canvas id="hubTimeChart"></canvas></div>
    </div>
  </div>
</section>

<hr class="divider">

<!-- ════════════════ 4. NET FLOW ════════════════ -->
<section id="netflow">
  <div class="section-title">Section 04</div>
  <div class="section-heading">净流量 — 吸引者 vs 输出者</div>
  <div class="section-desc">
    净流量 = 加权入度 − 加权出度（单位：actor 人次）。
    <strong>正值</strong>表示该 repo 净吸引更多贡献者流入（人才虹吸效应）；
    <strong>负值</strong>表示该 repo 净输出贡献者至其他 repo（人才孵化效应）。
  </div>
  <div class="card">
    <div class="card-title">净流量分布（Top 净流入 + Top 净流出）</div>
    <div class="chart-wrap">
      <canvas id="netFlowChart" style="max-height:400px"></canvas>
    </div>
  </div>
</section>

<hr class="divider">

<!-- ════════════════ 5. BETWEENNESS ════════════════ -->
<section id="betweenness">
  <div class="section-title">Section 05</div>
  <div class="section-heading">介数中心性 — 桥梁仓库</div>
  <div class="section-desc">
    介数中心性衡量一个 repo 在多少条"贡献者迁移最短路径"上充当中转节点。
    高介数意味着该 repo 是社区不同子群之间的<strong>关键跳板</strong>，
    一旦失去活跃度，可能导致多个子社区之间的贡献者流通中断。
  </div>
  <div class="card">
    <div class="card-title">Top {top_n} · 加权介数中心性排名</div>
    <div class="table-wrap">
      <table><thead><tr><th>#</th><th>Repo</th><th>Betweenness</th><th>分布</th></tr></thead>
      <tbody>{btw_rows}</tbody></table>
    </div>
  </div>
</section>

<hr class="divider">

<!-- ════════════════ 6. TRENDS ════════════════ -->
<section id="trends">
  <div class="section-title">Section 06</div>
  <div class="section-heading">趋势分析 — 兴衰动向</div>
  <div class="section-desc">
    基于线性回归斜率（归一化）识别 PageRank 持续上升或下降的仓库。
    斜率为正表示随时间吸引力在增强；斜率为负表示在社区中的地位逐渐下降。
  </div>
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab(this,'tab-rising')">↑ 上升趋势</button>
    <button class="tab-btn" onclick="switchTab(this,'tab-falling')">↓ 下降趋势</button>
  </div>
  <div id="tab-rising" class="tab-panel active">
    <div class="card">
      <div class="card-title">PageRank 上升最显著仓库（按斜率排序）</div>
      <div class="table-wrap">
        <table><thead><tr><th>#</th><th>Repo</th><th>斜率</th><th>方向</th></tr></thead>
        <tbody>{rising_rows}</tbody></table>
      </div>
    </div>
  </div>
  <div id="tab-falling" class="tab-panel">
    <div class="card">
      <div class="card-title">PageRank 下降最显著仓库（按斜率排序）</div>
      <div class="table-wrap">
        <table><thead><tr><th>#</th><th>Repo</th><th>斜率</th><th>方向</th></tr></thead>
        <tbody>{falling_rows}</tbody></table>
      </div>
    </div>
  </div>
</section>

<hr class="divider">

<!-- ════════════════ 7. COMMUNITY ════════════════ -->
<section id="community">
  <div class="section-title">Section 07</div>
  <div class="section-heading">社区检测 — 贡献者生态圈</div>
  <div class="section-desc">
    在聚合流动图（所有期叠加）上执行 {community_method} 算法，
    识别频繁相互交换贡献者的仓库集群。同一社区的仓库共享更紧密的开发者生态。
  </div>
  <div class="card">
    <div class="card-title">社区构成（按规模排序，展示前 15 个社区）</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>社区</th><th>规模</th><th>成员仓库</th></tr></thead>
        <tbody>{community_rows}</tbody>
      </table>
    </div>
  </div>
</section>

<hr class="divider">

<!-- ════════════════ 8. TIMELINE ════════════════ -->
<section id="timeline">
  <div class="section-title">Section 08</div>
  <div class="section-heading">图结构时序 — 网络演化</div>
  <div class="section-desc">
    每次月度过渡的图级统计：节点数、边数、密度及连通分量数。
    节点数增加代表更多仓库参与流动；密度变化反映网络的整体连接紧密程度。
  </div>
  <div class="card" style="margin-bottom:20px">
    <div class="card-title">网络密度 & 连通分量时序</div>
    <div class="chart-wrap"><canvas id="densityChart"></canvas></div>
  </div>
  <div class="card">
    <div class="card-title">完整时序数据表</div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Prev Period</th><th>Curr Period</th>
          <th>节点数</th><th>边数</th><th>密度</th>
          <th>弱连通</th><th>强连通</th>
        </tr></thead>
        <tbody>{graph_stats_rows}</tbody>
      </table>
    </div>
  </div>
</section>

<hr class="divider">

<!-- ════════════════ 9. KENDALL ════════════════ -->
<section id="kendall">
  <div class="section-title">Section 09</div>
  <div class="section-heading">健康度相关性 — Kendall τ-b</div>
  <div class="section-desc">
    将本报告中每个指标的排名与 <code>comprehensive_rank.json</code> 中的项目健康度综合排名
    计算 <strong>Kendall τ-b 等级相关系数</strong>（仅计算同时出现在两个数据集中的仓库）。
    τ > 0 表示该指标排名越高的仓库，健康度得分也越高；τ &lt; 0 则相反。
    τ-b 范围 [−1, 1]：|τ| ≥ 0.3 视为有意义的相关，|τ| ≥ 0.5 视为强相关。
  </div>
  {kendall_html_block}
</section>


</div><!-- /container -->

<footer>
  <span>Repo Flow · Structural Analysis Report</span>
  <span>算法: PageRank · HITS · Betweenness · {community_method}</span>
  <span>数据期间: {periods[0] if periods else "—"} → {periods[-1] if periods else "—"}</span>
</footer>

<script>
// ── Chart.js 全局配置 ──────────────────────────────
Chart.defaults.color = '#64748b';
Chart.defaults.borderColor = '#1e2d45';
Chart.defaults.font.family = "'Space Mono', monospace";
Chart.defaults.font.size = 11;

const PERIODS = {json.dumps(periods)};

// ── 概览图：节点数 & 边数 ──────────────────────────
const overviewStats = {json.dumps([
    {
        "period": pm["curr_period"],
        "nodes": pm["graph_stats"]["node_count"],
        "edges": pm["graph_stats"]["edge_count"],
    }
    for pm in sorted(period_metrics, key=lambda x: x["curr_period"])
])};
new Chart(document.getElementById('overviewChart'), {{
  type: 'bar',
  data: {{
    labels: overviewStats.map(d => d.period),
    datasets: [
      {{
        label: '节点数',
        data: overviewStats.map(d => d.nodes),
        backgroundColor: '#3b82f644',
        borderColor: '#3b82f6',
        borderWidth: 1,
        yAxisID: 'y',
      }},
      {{
        label: '边数',
        data: overviewStats.map(d => d.edges),
        backgroundColor: '#10b98144',
        borderColor: '#10b981',
        borderWidth: 1,
        yAxisID: 'y1',
      }},
    ]
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{
      y:  {{ position: 'left',  grid: {{ color: '#1e2d45' }}, title: {{ display:true, text:'节点数' }} }},
      y1: {{ position: 'right', grid: {{ drawOnChartArea: false }}, title: {{ display:true, text:'边数' }} }},
    }}
  }}
}});

// ── PageRank 时序 ─────────────────────────────────
new Chart(document.getElementById('prTimeChart'), {{
  type: 'line',
  data: {{ labels: PERIODS, datasets: {pr_datasets} }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'right', labels: {{ boxWidth: 12, font: {{ size: 10 }} }} }} }},
    scales: {{
      x: {{ grid: {{ color: '#1e2d45' }} }},
      y: {{ grid: {{ color: '#1e2d45' }}, title: {{ display:true, text:'PageRank' }} }},
    }}
  }}
}});

// ── Authority 时序 ────────────────────────────────
new Chart(document.getElementById('authTimeChart'), {{
  type: 'line',
  data: {{ labels: PERIODS, datasets: {auth_datasets} }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'right', labels: {{ boxWidth: 12, font: {{ size: 10 }} }} }} }},
    scales: {{
      x: {{ grid: {{ color: '#1e2d45' }} }},
      y: {{ grid: {{ color: '#1e2d45' }}, title: {{ display:true, text:'Authority' }} }},
    }}
  }}
}});

// ── Hub 时序 ──────────────────────────────────────
new Chart(document.getElementById('hubTimeChart'), {{
  type: 'line',
  data: {{ labels: PERIODS, datasets: {hub_datasets} }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'right', labels: {{ boxWidth: 12, font: {{ size: 10 }} }} }} }},
    scales: {{
      x: {{ grid: {{ color: '#1e2d45' }} }},
      y: {{ grid: {{ color: '#1e2d45' }}, title: {{ display:true, text:'Hub' }} }},
    }}
  }}
}});

// ── 净流量条形图 ───────────────────────────────────
new Chart(document.getElementById('netFlowChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(net_flow_labels)},
    datasets: [{{
      label: '净流量（加权入度 - 加权出度）',
      data: {json.dumps(net_flow_values)},
      backgroundColor: {json.dumps(net_flow_colors)},
      borderColor: {json.dumps(net_flow_colors)},
      borderWidth: 1,
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: {{ color: '#1e2d45' }}, title: {{ display:true, text:'净流量 (actor 人次)' }} }},
      y: {{ grid: {{ color: '#1e2d45' }}, ticks: {{ font: {{ size: 10 }} }} }},
    }}
  }}
}});

// ── 密度 & 连通分量时序 ────────────────────────────
const densityStats = {json.dumps([
    {
        "period": pm["curr_period"],
        "density": round(pm["graph_stats"]["density"], 5),
        "wcc": pm["graph_stats"]["weakly_connected_components"],
        "scc": pm["graph_stats"]["strongly_connected_components"],
    }
    for pm in sorted(period_metrics, key=lambda x: x["curr_period"])
])};
new Chart(document.getElementById('densityChart'), {{
  type: 'line',
  data: {{
    labels: densityStats.map(d => d.period),
    datasets: [
      {{
        label: '网络密度',
        data: densityStats.map(d => d.density),
        borderColor: '#f59e0b',
        backgroundColor: '#f59e0b22',
        tension: 0.3,
        yAxisID: 'y',
        pointRadius: 3,
      }},
      {{
        label: '弱连通分量',
        data: densityStats.map(d => d.wcc),
        borderColor: '#60a5fa',
        backgroundColor: '#60a5fa22',
        tension: 0.3,
        yAxisID: 'y1',
        pointRadius: 3,
      }},
      {{
        label: '强连通分量',
        data: densityStats.map(d => d.scc),
        borderColor: '#34d399',
        backgroundColor: '#34d39922',
        tension: 0.3,
        yAxisID: 'y1',
        pointRadius: 3,
      }},
    ]
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'top' }} }},
    scales: {{
      y:  {{ position: 'left',  grid: {{ color: '#1e2d45' }}, title: {{ display:true, text:'密度' }} }},
      y1: {{ position: 'right', grid: {{ drawOnChartArea: false }}, title: {{ display:true, text:'分量数' }} }},
    }}
  }}
}});


// ── Kendall τ-b 条形图 ────────────────────────────────
const kendallData = {kendall_chart_json};
if (kendallData && kendallData.labels && document.getElementById('kendallChart')) {{
  const kendallColors = kendallData.values.map(v =>
    v >= 0.3 ? '#34d399' : v >= 0.1 ? '#86efac' : v >= -0.1 ? '#94a3b8' : v >= -0.3 ? '#fca5a5' : '#f87171'
  );
  new Chart(document.getElementById('kendallChart'), {{
    type: 'bar',
    data: {{
      labels: kendallData.labels,
      datasets: [{{
        label: 'Kendall τ-b',
        data: kendallData.values,
        backgroundColor: kendallColors,
        borderColor: kendallColors,
        borderWidth: 1,
      }}]
    }},
    options: {{
      indexAxis: 'y',
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            afterLabel: ctx => kendallData.interps[ctx.dataIndex]
          }}
        }}
      }},
      scales: {{
        x: {{
          min: -1, max: 1,
          grid: {{ color: '#1e2d45' }},
          title: {{ display: true, text: 'Kendall τ-b' }}
        }},
        y: {{ grid: {{ color: '#1e2d45' }} }}
      }}
    }}
  }});
}}

// ── Tab 切换 ──────────────────────────────────────
function switchTab(btn, panelId) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(panelId).classList.add('active');
}}

// ── Nav 高亮（Intersection Observer）────────────────
const sections = document.querySelectorAll('section[id]');
const navLinks = document.querySelectorAll('nav a');
const observer = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      navLinks.forEach(a => a.classList.remove('active'));
      const link = document.querySelector(`nav a[href="#${{e.target.id}}"]`);
      if (link) link.classList.add('active');
    }}
  }});
}}, {{ threshold: 0.3 }});
sections.forEach(s => observer.observe(s));
</script>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    print(f"[analyze] HTML 报告已保存: {output_path}", flush=True)


# ==================== 主流程 ====================

def run_analysis(
    flow_dir: Path,
    output_dir: Path,
    top_n: int = 20,
    health_rank_file: Optional[Path] = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir = output_dir / "metrics"
    metrics_dir.mkdir(exist_ok=True)

    # 1. 加载索引
    print("[analyze] 加载流动图索引...", flush=True)
    index = load_index(flow_dir)
    graphs_info = index.get("graphs", {})
    if not graphs_info:
        print("[analyze] 错误: 未找到任何图文件记录", file=sys.stderr)
        sys.exit(1)

    print(f"[analyze] 共发现 {len(graphs_info)} 个过渡图", flush=True)

    # 2. 逐图分析
    period_metrics: List[Dict[str, Any]] = []
    for idx, (fname, info) in enumerate(
        sorted(graphs_info.items(), key=lambda x: x[1]["prev_period"]), 1
    ):
        prev = info["prev_period"]
        curr = info["curr_period"]
        path = Path(info["path"])
        if not path.exists():
            path = flow_dir / fname
        if not path.exists():
            print(f"[analyze] 警告: 图文件不存在，跳过: {path}", flush=True)
            continue

        print(f"[analyze] [{idx}/{len(graphs_info)}] {prev} → {curr}", flush=True)
        g = load_flow_graph(path)
        result = analyze_single_graph(g, prev, curr)
        period_metrics.append(result)

        # 保存单期指标
        out_fname = f"{prev}_to_{curr}_metrics.json"
        with open(metrics_dir / out_fname, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    if not period_metrics:
        print("[analyze] 错误: 没有可分析的图", file=sys.stderr)
        sys.exit(1)

    # 3. 跨期聚合
    print("[analyze] 计算跨期聚合指标...", flush=True)
    aggregated = aggregate_across_periods(period_metrics)

    # 4. 排名摘要
    print("[analyze] 生成排名摘要...", flush=True)
    summary = build_summary(aggregated, top_n=top_n)

    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[analyze] 摘要已保存: {summary_path}", flush=True)

    aggregated_path = output_dir / "aggregated.json"
    with open(aggregated_path, "w", encoding="utf-8") as f:
        json.dump(aggregated, f, indent=2, ensure_ascii=False)
    print(f"[analyze] 聚合数据已保存: {aggregated_path}", flush=True)

    # 5. Kendall 相关系数（可选）
    kendall_result: Dict[str, Any] = {}
    if health_rank_file is not None and health_rank_file.exists():
        try:
            with open(health_rank_file, encoding="utf-8") as f:
                health_data = json.load(f)
            # 支持两种格式：list of {project, rank} 或 {project: rank}
            if isinstance(health_data, list):
                health_ranks = {item["project"]: item["rank"] for item in health_data}
            else:
                health_ranks = {k: int(v) for k, v in health_data.items()}
            print(f"[analyze] 加载健康度排名: {len(health_ranks)} 个项目", flush=True)
            kendall_result = compute_kendall_correlations(aggregated, health_ranks)
            kendall_path = output_dir / "kendall_correlations.json"
            with open(kendall_path, "w", encoding="utf-8") as f:
                json.dump(kendall_result, f, indent=2, ensure_ascii=False)
            print(f"[analyze] Kendall 相关系数已保存: {kendall_path}", flush=True)
            n_common = kendall_result.get("overlap_count", 0)
            print(f"[analyze] 交集仓库数: {n_common}", flush=True)
            missing = sorted(set(health_ranks.keys()) - set(aggregated.keys()))
            if missing:
                print(f"[analyze] 以下 {len(missing)} 个健康排名项目未出现在流动图中:", flush=True)
                for r in missing:
                    print(f"[analyze]   · {r}", flush=True)
            for mk, mv in kendall_result.get("metrics", {}).items():
                print(f"[analyze]   {mv['label']:20s}: τ-b = {mv['combined']:+.4f}  ({mv['interpretation']})", flush=True)
        except Exception as e:
            print(f"[analyze] 警告: 加载健康度排名失败: {e}", flush=True)
    else:
        if health_rank_file is not None:
            print(f"[analyze] 警告: 健康度排名文件不存在: {health_rank_file}", flush=True)

    # 6. 社区检测
    print("[analyze] 执行社区检测...", flush=True)
    community_result = detect_communities(flow_dir, index)
    community_path = output_dir / "communities.json"
    with open(community_path, "w", encoding="utf-8") as f:
        json.dump(community_result, f, indent=2, ensure_ascii=False)
    print(f"[analyze] 社区检测结果已保存: {community_path}", flush=True)

    # 6. 生成 HTML 报告
    print("[analyze] 生成 HTML 报告...", flush=True)
    report_path = output_dir / "report.html"
    generate_html_report(
        summary=summary,
        aggregated=aggregated,
        period_metrics=period_metrics,
        community_result=community_result,
        output_path=report_path,
        top_n=top_n,
        kendall_result=kendall_result,
    )

    print(f"\n[analyze] 分析完成！输出目录: {output_dir}", flush=True)
    print(f"  · 单期指标:   {metrics_dir}/", flush=True)
    print(f"  · 摘要:       {summary_path}", flush=True)
    print(f"  · 聚合数据:   {aggregated_path}", flush=True)
    print(f"  · 社区:       {community_path}", flush=True)
    if kendall_result:
        print(f"  · Kendall 相关系数: {output_dir}/kendall_correlations.json", flush=True)
    print(f"  · HTML 报告:  {report_path}", flush=True)


# ==================== CLI ========================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="对 Repo 流动图执行结构分析并生成 HTML 报告",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--flow-dir",
        type=Path,
        default=Path("output/repo-flow-graphs"),
        help="repo_flow_graph_builder.py 的输出目录（含 index.json）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/repo-flow-analysis"),
        help="分析结果输出目录",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="各排名榜单展示的最大条目数",
    )
    parser.add_argument(
        "--health-rank-file",
        type=Path,
        default=None,
        help=(
            "综合健康排名 JSON 文件路径，例如 comprehensive_rank.json。"
            "格式：list of {project, rank} 或 dict {project: rank}。"
            "提供后将计算 Kendall tau-b 相关系数并在报告 Section 09 展示。"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.flow_dir.exists():
        print(f"[analyze] 错误: 流动图目录不存在: {args.flow_dir}", file=sys.stderr)
        sys.exit(1)
    run_analysis(
        flow_dir=args.flow_dir,
        output_dir=args.output_dir,
        top_n=args.top_n,
        health_rank_file=args.health_rank_file,
    )


if __name__ == "__main__":
    main()