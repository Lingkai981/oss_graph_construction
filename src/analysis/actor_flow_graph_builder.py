"""
人员流动图生成器：Repo → Repo 有向图

基于 Kuzu 数据库中的 ActorToRepo 边，分析开发者在不同仓库间的注意力迁移，
生成描述社区人员流动的 Repo-Repo 有向图。

算法逻辑：
1. 按时间跨度 t（默认一个月）将数据分段
2. 计算每个 actor 在每个时间段内对各 repo 的加权贡献度
3. 确定每个 actor 每段时间的"主要贡献 repo 集合"：
   按贡献度降序累加，直到累计占比首次 >= a%（默认 50%）；
   若触发阈值的 repo 之后仍有贡献占比与之完全相同的 repo，一并纳入（稳定性保证）。
4. 对相邻两个时间段，生成 Repo → Repo 有向边：
   前一段集合 S_prev 中的每个 repo R，向后一段集合 S_next 中满足以下任一条件的 repo R' 连边：
     - R' 不在 S_prev 中（新出现的主要贡献目标）
     - R' 在 S_prev 中，但贡献占比在后一段比前一段更高（贡献占比上升）
     - R ≠ R'（不允许自环）
5. 跨所有 actor 聚合同一对 (R→R') 在同一月份过渡的边，统计 actor_count

输出：
    output/repo-flow-graphs/
        {prev_month}_to_{curr_month}.graphml   每次月份过渡的流动图（GraphML 格式）
        repo_flow_nodes.csv                    所有 Repo 节点（去重聚合）
        repo_flow_edges.csv                    所有流动边（含 prev_period / curr_period）
        index.json                             所有图文件的索引

用法（在仓库根目录执行）：
    python src/analysis/actor_flow_graph_builder.py \
        --db-path output/kuzu_db \
        --output-dir output/repo-flow-graphs \
        --threshold 0.5 \
        --time-span month

参数说明：
    --db-path       Kuzu 数据库路径
    --output-dir    输出目录
    --threshold     主要贡献 repo 集合的累计贡献占比阈值 a（默认 0.5，即 50%）
    --time-span     时间分段粒度，目前支持 "month"（默认），预留 "week" 扩展接口
    --weights-file  JSON 格式的边类型权重配置文件（可选，不提供则使用内置默认权重）
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
import kuzu


# ==================== 默认边权重配置 ====================
# 参考 BusFactorAnalyzer 的 DEFAULT_WEIGHTS 设计风格，
# 对 actor-repo 图中常见的 GitHub 事件类型赋权。
#
# 权重设计原则（与 BusFactorAnalyzer 保持一致的价值层次）：
#   高价值贡献（代码实质性输出）：权重 3.0
#   中等价值贡献（审查/协作）：权重 1.5
#   低价值贡献（参与/讨论）：权重 0.5
#
# actor-repo 图中的边类型通常是 GitHub 原始事件类型（驼峰式命名）
DEFAULT_WEIGHTS: Dict[str, float] = {
    # ---- 高价值：代码直接输出 ----
    "PushEvent":                    3.0,  # 直接推送代码
    "PullRequestEvent":             3.0,  # 提交 PR（open/close/merge）
    "PR_MERGE":                     3.0,  # 合并 PR（与 BurnoutAnalyzer 兼容）

    # ---- 中等价值：审查与协作 ----
    "PullRequestReviewEvent":       1.5,  # PR 审查
    "PullRequestReviewCommentEvent":1.5,  # PR 行级评论
    "PR_REVIEW":                    1.5,  # （与 BurnoutAnalyzer 兼容）

    # ---- 低价值：讨论与参与 ----
    "IssuesEvent":                  0.5,  # 创建/关闭 Issue
    "IssueCommentEvent":            0.5,  # Issue 评论
    "ISSUE_INTERACTION":            0.5,  # （与 BurnoutAnalyzer 兼容）
    "ISSUE_CO_PARTICIPANT":         0.5,  # （与 BurnoutAnalyzer 兼容）

    # ---- 其他常见事件 ----
    "CreateEvent":                  0.5,  # 创建分支/标签
    "DeleteEvent":                  0.3,  # 删除分支/标签
    "ForkEvent":                    0.3,  # Fork 仓库
    "WatchEvent":                   0.1,  # Star 仓库
    "ReleaseEvent":                 1.5,  # 发布版本
    "CommitCommentEvent":           0.5,  # Commit 评论
    "GollumEvent":                  0.3,  # Wiki 编辑

    # 默认权重（未在配置中的边类型）
    "default":                      1.0,
}


# ==================== 数据结构 ====================

# 单个 actor 在某时间段内对某 repo 的贡献
# { actor_id -> { repo_name -> contribution_score } }
ActorRepoPeriodContrib = Dict[str, Dict[str, float]]

# 主要贡献 repo 集合
# { actor_id -> { repo_name -> contribution_ratio } }  (ratio = 占该 actor 本期总贡献的比例)
ActorMainRepos = Dict[str, Dict[str, float]]


# ==================== 核心函数 ====================

def compute_actor_repo_contributions(
    rows: List[Tuple[str, str, str]],
    weights: Dict[str, float],
) -> ActorRepoPeriodContrib:
    """
    计算一个时间段内所有 actor 对各 repo 的加权贡献度。

    参考 BusFactorAnalyzer.aggregate_contributions 的加权逻辑：
    对每条 ActorToRepo 边，按 edge_type 查找权重并累加。

    Args:
        rows:    [(actor_id, repo_name, edge_type), ...]
        weights: 边类型 -> 权重

    Returns:
        { actor_id: { repo_name: total_weighted_contribution } }
    """
    contrib: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for actor_id, repo_name, edge_type in rows:
        w = weights.get(edge_type, weights.get("default", 1.0))
        contrib[actor_id][repo_name] += w
    # 转为普通 dict 方便后续处理
    return {aid: dict(repo_map) for aid, repo_map in contrib.items()}


def compute_main_repos(
    actor_contrib: Dict[str, float],
    threshold: float,
) -> Dict[str, float]:
    """
    确定单个 actor 在某时间段内的主要贡献 repo 集合。

    算法：按贡献度降序累加，直到累计比例首次 >= threshold 为止。
    边界处理：若触发阈值的 repo（boundary_ratio）之后仍有贡献占比与之完全相同的 repo，
    一并纳入集合，确保结果不因同值 repo 的任意排序而产生差异（稳定性保证）。

    示例：
        贡献占比 [30%, 25%, 25%, 20%]，threshold=0.5
        累加到第二个 25% 时达到阈值（30+25+25=80% >= 50%，但第一个25%已达55%）。
        实际上累加到30%+25%=55%时就已超过50%，boundary_ratio=25%。
        剩余的另一个 25% 与 boundary_ratio 相同，故也纳入集合。
        最终集合：前三个 repo（共 80% 贡献）。

    Args:
        actor_contrib: { repo_name: contribution_score }
        threshold:     累计贡献比例阈值（如 0.5 表示 50%）

    Returns:
        { repo_name: contribution_ratio }  仅包含主要贡献 repo
    """
    if not actor_contrib:
        return {}

    total = sum(actor_contrib.values())
    if total <= 0:
        return {}

    # 按贡献度降序；同分时按 repo_name 字典序确保排序稳定
    sorted_repos = sorted(actor_contrib.items(), key=lambda x: (-x[1], x[0]))

    main_repos: Dict[str, float] = {}
    cumsum = 0.0
    boundary_ratio: Optional[float] = None  # 触发阈值那一步的贡献占比

    for repo_name, score in sorted_repos:
        ratio = score / total

        if boundary_ratio is None:
            # 尚未达到阈值，正常纳入
            main_repos[repo_name] = ratio
            cumsum += ratio
            if cumsum >= threshold:
                # 记录边界占比，后续继续扫描同值 repo
                boundary_ratio = ratio
        else:
            # 已达阈值：仅继续纳入与 boundary_ratio 完全相同的 repo
            if ratio == boundary_ratio:
                main_repos[repo_name] = ratio
            else:
                # 占比已低于边界值，停止
                break

    return main_repos


def generate_flow_edges(
    prev_main: Dict[str, float],
    curr_main: Dict[str, float],
) -> List[Tuple[str, str]]:
    """
    根据单个 actor 相邻两期的主要 repo 集合，生成有向流动边。

    连边规则（对 S_prev 中的每个 repo R，遍历 S_curr 中的每个 repo R'）：
      满足以下任一条件，且 R ≠ R'，则生成边 R → R'：
        1. R' 不在 S_prev 中（新出现的主要贡献目标）
        2. R' 在 S_prev 中，但 contribution_ratio(R', curr) > contribution_ratio(R', prev)

    Args:
        prev_main: { repo_name: contribution_ratio } 前一期主要 repo 集合
        curr_main: { repo_name: contribution_ratio } 当前期主要 repo 集合

    Returns:
        [(src_repo, dst_repo), ...]
    """
    edges: List[Tuple[str, str]] = []

    for src_repo in prev_main:
        for dst_repo, curr_ratio in curr_main.items():
            # 不允许自环
            if src_repo == dst_repo:
                continue

            # 条件 1：dst_repo 是新出现的主要贡献目标
            if dst_repo not in prev_main:
                edges.append((src_repo, dst_repo))
                continue

            # 条件 2：dst_repo 在前一期也存在，但贡献占比上升
            prev_ratio = prev_main[dst_repo]
            if curr_ratio > prev_ratio:
                edges.append((src_repo, dst_repo))

    return edges


# ==================== 数据库查询 ====================

def fetch_all_periods(
    conn: kuzu.Connection,
    time_span: str = "month",
) -> List[str]:
    """
    从 Kuzu 查询所有存在 ActorToRepo 边的时间段（去重排序）。

    当前仅支持 time_span="month"，直接使用边上的 month 字段。
    预留 week 等粒度的扩展接口。

    Returns:
        排序后的时间段列表，如 ["2023-01", "2023-02", ...]
    """
    if time_span != "month":
        raise NotImplementedError(f"暂不支持 time_span='{time_span}'，当前仅支持 'month'")

    result = conn.execute(
        "MATCH ()-[r:ActorToRepo]->() RETURN DISTINCT r.month ORDER BY r.month"
    )
    periods = []
    while result.has_next():
        (month,) = result.get_next()
        if month:
            periods.append(month)
    return sorted(set(periods))


def fetch_actor_repo_edges_for_period(
    conn: kuzu.Connection,
    period: str,
    time_span: str = "month",
) -> List[Tuple[str, str, str]]:
    """
    查询某时间段内所有 ActorToRepo 边。

    Returns:
        [(actor_id, repo_name, edge_type), ...]
    """
    if time_span != "month":
        raise NotImplementedError(f"暂不支持 time_span='{time_span}'")

    result = conn.execute(
        """
        MATCH (a:Actor)-[r:ActorToRepo]->(repo:Repo)
        WHERE r.month = $period
        RETURN a.id, repo.name, r.edge_type
        """,
        {"period": period},
    )
    rows: List[Tuple[str, str, str]] = []
    while result.has_next():
        actor_id, repo_name, edge_type = result.get_next()
        if actor_id and repo_name:
            rows.append((str(actor_id), str(repo_name), str(edge_type) if edge_type else "default"))
    return rows


def fetch_repo_metadata(conn: kuzu.Connection) -> Dict[str, Dict[str, str]]:
    """
    查询所有 Repo 节点的元数据（id、repo_id、name）。

    Returns:
        { repo_name: { "id": ..., "repo_id": ... } }
    """
    meta: Dict[str, Dict[str, str]] = {}
    result = conn.execute("MATCH (r:Repo) RETURN r.id, r.repo_id, r.name")
    while result.has_next():
        r_id, repo_id, name = result.get_next()
        if name:
            meta[str(name)] = {
                "id": str(r_id) if r_id else str(name),
                "repo_id": str(repo_id) if repo_id else "",
            }
    return meta


# ==================== 图构建 ====================

def build_flow_graph_for_transition(
    prev_period: str,
    curr_period: str,
    prev_period_contrib: ActorRepoPeriodContrib,
    curr_period_contrib: ActorRepoPeriodContrib,
    threshold: float,
    repo_meta: Dict[str, Dict[str, str]],
) -> nx.DiGraph:
    """
    构建单次时间段过渡（prev → curr）的 Repo 流动有向图。

    节点：Repo（出现在任一期主要集合中的 repo）
    边：(src_repo → dst_repo) 附带：
        - actor_count:  触发此边的 actor 数量
        - actor_ids:    触发此边的 actor id 列表（JSON 字符串，便于 GraphML 序列化）
        - weight:       等同于 actor_count（便于可视化工具直接使用）
        - prev_period:  前一期标识
        - curr_period:  当前期标识

    Returns:
        nx.DiGraph
    """
    # 统计每条 (src, dst) 边被哪些 actor 触发
    # edge_actors: { (src_repo, dst_repo): set of actor_id }
    edge_actors: Dict[Tuple[str, str], Set[str]] = defaultdict(set)

    # 所有出现在主要集合中的 repo（用于构建节点集合）
    involved_repos: Set[str] = set()

    # 遍历在前一期有贡献的所有 actor
    all_actors = set(prev_period_contrib.keys()) | set(curr_period_contrib.keys())

    for actor_id in all_actors:
        prev_contrib = prev_period_contrib.get(actor_id, {})
        curr_contrib = curr_period_contrib.get(actor_id, {})

        # 如果该 actor 在前一期没有贡献，无法产生"迁移"语义
        if not prev_contrib:
            continue

        # 如果该 actor 在当前期没有贡献，也跳过
        if not curr_contrib:
            continue

        # 计算各期主要 repo 集合
        prev_main = compute_main_repos(prev_contrib, threshold)
        curr_main = compute_main_repos(curr_contrib, threshold)

        if not prev_main or not curr_main:
            continue

        involved_repos.update(prev_main.keys())
        involved_repos.update(curr_main.keys())

        # 生成该 actor 贡献的流动边
        flow_edges = generate_flow_edges(prev_main, curr_main)
        for src, dst in flow_edges:
            edge_actors[(src, dst)].add(actor_id)

    # 构建图
    g = nx.DiGraph()
    g.graph["prev_period"] = prev_period
    g.graph["curr_period"] = curr_period
    g.graph["threshold"] = threshold

    # 添加节点（仅涉及流动的 repo）
    for repo_name in involved_repos:
        meta = repo_meta.get(repo_name, {})
        g.add_node(
            repo_name,
            node_type="Repo",
            repo_id=meta.get("repo_id", ""),
            kuzu_id=meta.get("id", repo_name),
        )

    # 添加边
    for (src, dst), actors in edge_actors.items():
        # 确保节点存在（即使没在 involved_repos 中也补充）
        for repo_name in (src, dst):
            if repo_name not in g:
                meta = repo_meta.get(repo_name, {})
                g.add_node(
                    repo_name,
                    node_type="Repo",
                    repo_id=meta.get("repo_id", ""),
                    kuzu_id=meta.get("id", repo_name),
                )
        actor_count = len(actors)
        g.add_edge(
            src,
            dst,
            edge_type="ACTOR_FLOW",
            actor_count=actor_count,
            weight=float(actor_count),
            actor_ids=json.dumps(sorted(actors)),  # GraphML 不支持列表，序列化为 JSON 字符串
            prev_period=prev_period,
            curr_period=curr_period,
        )

    return g


# ==================== CSV 输出 ====================

def write_flow_csv(
    output_dir: Path,
    all_node_rows: List[Dict[str, str]],
    all_edge_rows: List[Dict[str, str]],
) -> None:
    """
    将所有过渡的节点与边聚合写入两个 CSV 文件：
        repo_flow_nodes.csv  —— 所有出现过的 Repo 节点（去重）
        repo_flow_edges.csv  —— 所有流动边（含 prev_period / curr_period）

    字段说明：
        nodes: repo_name, repo_id, kuzu_id
        edges: prev_period, curr_period, src_repo, dst_repo, actor_count, actor_ids
    """
    import csv

    # 节点去重（以 repo_name 为主键）
    seen_nodes: Dict[str, Dict[str, str]] = {}
    for row in all_node_rows:
        seen_nodes.setdefault(row["repo_name"], row)

    nodes_path = output_dir / "repo_flow_nodes.csv"
    with nodes_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["repo_name", "repo_id", "kuzu_id"])
        writer.writeheader()
        for row in sorted(seen_nodes.values(), key=lambda r: r["repo_name"]):
            writer.writerow(row)

    edges_path = output_dir / "repo_flow_edges.csv"
    with edges_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["prev_period", "curr_period", "src_repo", "dst_repo", "actor_count", "actor_ids"],
        )
        writer.writeheader()
        writer.writerows(all_edge_rows)

    print(
        f"[flow] CSV 已保存: {nodes_path} ({len(seen_nodes)} 节点), "
        f"{edges_path} ({len(all_edge_rows)} 边)",
        flush=True,
    )


# ==================== 主流程 ====================

def build_all_flow_graphs(
    conn: kuzu.Connection,
    output_dir: Path,
    threshold: float = 0.5,
    time_span: str = "month",
    weights: Dict[str, float] = None,
) -> Dict[str, Any]:
    """
    构建所有时间段过渡的 Repo 流动图，同步输出 GraphML 与 CSV。

    采用单次滑动窗口遍历，避免重复扫描数据：
      1. 一次性拉取全量 Repo 元数据
      2. 滑动窗口逐对相邻时间段处理，边构图边收集 CSV 行
      3. 所有过渡处理完后，统一写入聚合 CSV

    Returns:
        index 字典，记录所有输出文件的路径信息
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 获取所有时间段
    print("[flow] 正在查询所有时间段...", flush=True)
    periods = fetch_all_periods(conn, time_span)
    if len(periods) < 2:
        print(f"[flow] 时间段数量不足（{len(periods)} 个），无法生成流动图", flush=True)
        return {}
    print(f"[flow] 共发现 {len(periods)} 个时间段: {periods[0]} ~ {periods[-1]}", flush=True)

    # 2. 一次性拉取全量 Repo 元数据（无需预扫描 repo 名称）
    print("[flow] 正在加载 Repo 元数据...", flush=True)
    repo_meta = fetch_repo_metadata(conn)
    print(f"[flow] 共加载 {len(repo_meta)} 个 Repo 节点元数据", flush=True)

    # 3. 滑动窗口：单次遍历生成图 + 收集 CSV 行
    index: Dict[str, Any] = {}
    all_node_rows: List[Dict[str, str]] = []   # 跨所有过渡的节点行（后续去重）
    all_edge_rows: List[Dict[str, str]] = []   # 跨所有过渡的边行

    print("[flow] 正在加载第 1 期数据...", flush=True)
    prev_period = periods[0]
    prev_rows = fetch_actor_repo_edges_for_period(conn, prev_period, time_span)
    prev_contrib = compute_actor_repo_contributions(prev_rows, weights)

    for i in range(1, len(periods)):
        curr_period = periods[i]
        print(
            f"[flow] [{i}/{len(periods)-1}] 生成图: {prev_period} → {curr_period}",
            flush=True,
        )

        curr_rows = fetch_actor_repo_edges_for_period(conn, curr_period, time_span)
        curr_contrib = compute_actor_repo_contributions(curr_rows, weights)

        # 构建流动图
        g = build_flow_graph_for_transition(
            prev_period=prev_period,
            curr_period=curr_period,
            prev_period_contrib=prev_contrib,
            curr_period_contrib=curr_contrib,
            threshold=threshold,
            repo_meta=repo_meta,
        )

        node_count = g.number_of_nodes()
        edge_count = g.number_of_edges()
        print(f"[flow]   节点数: {node_count}, 边数: {edge_count}", flush=True)

        # 保存 GraphML
        filename = f"{prev_period}_to_{curr_period}.graphml"
        output_path = output_dir / filename
        nx.write_graphml(g, str(output_path))

        # 收集 CSV 行
        for repo_name, node_data in g.nodes(data=True):
            all_node_rows.append({
                "repo_name": str(repo_name),
                "repo_id": str(node_data.get("repo_id", "")),
                "kuzu_id": str(node_data.get("kuzu_id", repo_name)),
            })
        for src, dst, edge_data in g.edges(data=True):
            all_edge_rows.append({
                "prev_period": prev_period,
                "curr_period": curr_period,
                "src_repo": str(src),
                "dst_repo": str(dst),
                "actor_count": str(edge_data.get("actor_count", 0)),
                "actor_ids": str(edge_data.get("actor_ids", "[]")),
            })

        index[filename] = {
            "prev_period": prev_period,
            "curr_period": curr_period,
            "node_count": node_count,
            "edge_count": edge_count,
            "path": str(output_path),
        }

        # 滑动窗口前移
        prev_period = curr_period
        prev_contrib = curr_contrib

    # 4. 写入聚合 CSV
    write_flow_csv(output_dir, all_node_rows, all_edge_rows)

    # 5. 保存索引文件
    index_path = output_dir / "index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "time_span": time_span,
                "threshold": threshold,
                "total_transitions": len(index),
                "periods": periods,
                "graphs": index,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"[flow] 索引文件已保存: {index_path}", flush=True)

    return index


# ==================== CLI 入口 ====================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成 Repo-Repo 人员流动图（基于 ActorToRepo 贡献迁移）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("output/kuzu_db.kuzu"),
        help="Kuzu 数据库路径",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/repo-flow-graphs"),
        help="GraphML 输出目录",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help=(
            "主要贡献 repo 集合的累计贡献占比阈值 a（0~1）。"
            "例如 0.5 表示：按贡献度降序累加，直到累计占比 >= 50%% 为止的 repo 集合。"
        ),
    )
    parser.add_argument(
        "--time-span",
        type=str,
        default="month",
        choices=["month"],
        help="时间分段粒度（当前仅支持 month）",
    )
    parser.add_argument(
        "--weights-file",
        type=Path,
        default=None,
        help=(
            "JSON 格式的边类型权重配置文件（可选）。"
            "格式：{ \"PushEvent\": 3.0, \"IssueCommentEvent\": 0.5, ... }。"
            "不提供则使用内置默认权重。"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 加载权重配置
    weights = DEFAULT_WEIGHTS.copy()
    if args.weights_file:
        if not args.weights_file.exists():
            print(f"[flow] 错误: 权重配置文件不存在: {args.weights_file}", file=sys.stderr)
            sys.exit(1)
        try:
            with open(args.weights_file, "r", encoding="utf-8") as f:
                custom_weights = json.load(f)
            weights.update(custom_weights)
            print(f"[flow] 已加载自定义权重配置: {args.weights_file}", flush=True)
        except Exception as e:
            print(f"[flow] 警告: 无法加载权重配置文件: {e}，使用默认权重", flush=True)

    # 参数校验
    if not (0.0 < args.threshold <= 1.0):
        print(f"[flow] 错误: --threshold 必须在 (0, 1] 范围内，当前值: {args.threshold}", file=sys.stderr)
        sys.exit(1)

    # 连接 Kuzu
    db_path = args.db_path
    if db_path.is_dir():
        # 兼容传入目录的场景
        db_path = db_path / "kuzu_db.kuzu"

    if not db_path.exists():
        print(f"[flow] 错误: Kuzu 数据库不存在: {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[flow] 连接 Kuzu 数据库: {db_path}", flush=True)
    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)

    print(
        f"[flow] 配置参数: threshold={args.threshold} ({args.threshold*100:.0f}%), "
        f"time_span={args.time_span}",
        flush=True,
    )

    # 执行构建
    index = build_all_flow_graphs(
        conn=conn,
        output_dir=args.output_dir,
        threshold=args.threshold,
        time_span=args.time_span,
        weights=weights,
    )

    print(
        f"\n[flow] 完成！共生成 {len(index)} 个流动图，输出目录: {args.output_dir}",
        flush=True,
    )


if __name__ == "__main__":
    main()
