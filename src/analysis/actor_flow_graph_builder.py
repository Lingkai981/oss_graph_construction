"""
构建 Repository-Repository 人员流动有向图

功能：
1. 读取 data/filtered/ 下的日粒度数据
2. 统计每位开发者在各 repo 的贡献时间区间与贡献次数
3. 过滤低质量贡献（贡献数 <= 1 或 平均日贡献 < 阈值）
4. 将每位开发者的有效 repo 按时间区间中点排序，相邻 repo 构成有向边
5. 汇总所有开发者，构建 Repo-Repo 有向图

支持三种时间窗口模式：
- global:  全局一张图（覆盖整个数据集）
- yearly:  按年切分，每年一张图
- monthly: 按月切分，每月一张图

输出结构：
output/repo-flow-graphs/
├── global/
│   └── repo-flow.graphml
├── yearly/
│   ├── 2021.graphml
│   ├── 2022.graphml
│   └── ...
└── monthly/
    ├── 2021-01.graphml
    ├── 2021-02.graphml
    └── ...
"""

from __future__ import annotations

import json
import gc
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

try:
    from src.utils.logger import get_logger
    logger = get_logger()
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ==================== 常量 ====================

# 被视为"贡献"的事件类型（默认）
DEFAULT_CONTRIBUTION_TYPES: Set[str] = {
    "PushEvent",
    "PullRequestEvent",
    "IssuesEvent",
    "IssueCommentEvent",
    "PullRequestReviewCommentEvent",
    "CreateEvent",
    "ReleaseEvent",
}

# 不视为贡献的事件类型（仅供参考）
EXCLUDED_EVENT_TYPES: Set[str] = {
    "WatchEvent",   # 仅 star，不算贡献
    "ForkEvent",    # 仅 fork，不算贡献
    "DeleteEvent",  # 删除操作，通常不代表正向贡献
}

# 过滤阈值
DEFAULT_MIN_EVENT_COUNT = 3         # 单个 (actor, repo) 区间最低贡献次数 >= 3
DEFAULT_MIN_AVG_DAILY_EVENTS = 0.05  # 平均每日贡献 >= 0.1（即 10 天至少 1 次）
DEFAULT_MIN_REPOS_PER_ACTOR = 2     # 至少参与 2 个有效 repo 才能产生流动边


# ==================== XML 清洗工具 ====================

_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _sanitize_xml_text(text) -> str:
    """清洗文本，移除 XML 1.0 不允许的字符"""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    cleaned = []
    for ch in text:
        code = ord(ch)
        if ch in ("\t", "\n", "\r"):
            cleaned.append(ch)
        elif 0x20 <= code <= 0xD7FF:
            cleaned.append(ch)
        elif 0xE000 <= code <= 0xFFFD:
            cleaned.append(ch)
        elif 0x10000 <= code <= 0x10FFFF:
            cleaned.append(ch)
        # 其它字符丢弃
    return "".join(cleaned)


def sanitize_graphml_attributes(g: nx.Graph) -> None:
    """就地清洗图、节点、边属性，确保 GraphML 合法"""
    for k, v in list(g.graph.items()):
        if isinstance(v, str) or v is None:
            g.graph[k] = _sanitize_xml_text(v)
        elif isinstance(v, (dict, list)):
            g.graph[k] = _sanitize_xml_text(json.dumps(v, ensure_ascii=False))

    for n, attrs in list(g.nodes(data=True)):
        for k, v in list(attrs.items()):
            if isinstance(v, str) or v is None:
                attrs[k] = _sanitize_xml_text(v)
            elif isinstance(v, (dict, list)):
                attrs[k] = _sanitize_xml_text(json.dumps(v, ensure_ascii=False))

    for u, v, attrs in list(g.edges(data=True)):
        for k, val in list(attrs.items()):
            if isinstance(val, str) or val is None:
                attrs[k] = _sanitize_xml_text(val)
            elif isinstance(val, (dict, list)):
                attrs[k] = _sanitize_xml_text(json.dumps(val, ensure_ascii=False))


# ==================== 时间解析 ====================

def _parse_time(time_str: str) -> Optional[datetime]:
    """解析 GitHub 事件时间戳（UTC）"""
    if not time_str:
        return None
    try:
        clean = time_str.replace("Z", "").replace("+00:00", "")
        return datetime.fromisoformat(clean)
    except (ValueError, AttributeError):
        return None


# ==================== 数据类 ====================

@dataclass
class ActorRepoContrib:
    """
    记录一位开发者对一个 repo 的贡献统计
    
    核心属性：
    - event_count: 该 actor 在该 repo 的事件总数
    - first_event_time / last_event_time: 时间区间
    - midpoint: 时间区间中点，用于排序确定流动方向
    """
    actor_id: int
    actor_login: str
    repo_name: str
    repo_id: int = 0
    event_count: int = 0
    first_event_time: Optional[datetime] = None
    last_event_time: Optional[datetime] = None
    event_types: Dict[str, int] = field(default_factory=dict)

    @property
    def active_days(self) -> int:
        """活跃天数（至少 1 天，避免除零）"""
        if self.first_event_time and self.last_event_time:
            return max((self.last_event_time - self.first_event_time).days, 1)
        return 1

    @property
    def avg_daily_events(self) -> float:
        """平均每日贡献数"""
        return self.event_count / self.active_days

    @property
    def midpoint(self) -> datetime:
        """时间区间中点"""
        if self.first_event_time and self.last_event_time:
            return self.first_event_time + (self.last_event_time - self.first_event_time) / 2
        return self.first_event_time or datetime.min

    def add_event(self, event_time: datetime, event_type: str, repo_id: int = 0):
        """添加一条事件"""
        self.event_count += 1
        self.event_types[event_type] = self.event_types.get(event_type, 0) + 1
        if repo_id:
            self.repo_id = repo_id
        if self.first_event_time is None or event_time < self.first_event_time:
            self.first_event_time = event_time
        if self.last_event_time is None or event_time > self.last_event_time:
            self.last_event_time = event_time

    def passes_filter(
        self,
        min_event_count: int = DEFAULT_MIN_EVENT_COUNT,
        min_avg_daily: float = DEFAULT_MIN_AVG_DAILY_EVENTS,
    ) -> bool:
        """判断是否通过过滤条件"""
        return (
            self.event_count >= min_event_count
            and self.avg_daily_events >= min_avg_daily
        )


# ==================== 数据加载 ====================

def get_available_months(data_dir: str) -> List[str]:
    """扫描数据目录，获取所有可用月份"""
    data_path = Path(data_dir)
    months = set()
    for file_path in data_path.glob("*-filtered.json"):
        parts = file_path.stem.replace("-filtered", "").split("-")
        if len(parts) >= 3:
            months.add(f"{parts[0]}-{parts[1]}")
    return sorted(months)


def load_month_events(data_dir: str, month: str) -> List[Dict]:
    """
    加载指定月份的所有事件（不按 repo 分组）
    
    Args:
        data_dir: 数据目录
        month: "YYYY-MM"
    
    Returns:
        事件列表
    """
    data_path = Path(data_dir)
    pattern = f"{month}-*-filtered.json"
    files = sorted(data_path.glob(pattern))
    events = []

    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return events


def load_all_events(data_dir: str) -> List[Dict]:
    """加载所有数据文件的事件"""
    data_path = Path(data_dir)
    files = sorted(data_path.glob("*-filtered.json"))
    events = []
    total_files = len(files)

    print(f"找到 {total_files} 个数据文件")
    for idx, file_path in enumerate(files, 1):
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        if idx % 50 == 0 or idx == total_files:
            print(f"  加载进度: {idx}/{total_files} 文件, 累计 {len(events)} 事件")

    print(f"数据加载完成: {len(events)} 个事件")
    return events


# ==================== 核心逻辑 ====================

def collect_contributions(
    events: List[Dict],
    contribution_types: Optional[Set[str]] = None,
) -> Dict[int, Dict[str, ActorRepoContrib]]:
    """
    从事件列表中收集每位开发者对每个 repo 的贡献统计
    
    Args:
        events: 事件列表
        contribution_types: 视为贡献的事件类型集合；None 表示使用默认集合
    
    Returns:
        {actor_id: {repo_name: ActorRepoContrib}}
    """
    if contribution_types is None:
        contribution_types = DEFAULT_CONTRIBUTION_TYPES

    contributions: Dict[int, Dict[str, ActorRepoContrib]] = defaultdict(dict)

    for event in events:
        event_type = event.get("type") or ""
        if event_type not in contribution_types:
            continue

        actor = event.get("actor") or {}
        actor_id = actor.get("id")
        if actor_id is None:
            continue

        repo = event.get("repo") or {}
        repo_name = (repo.get("name") or "").lower()
        repo_id = repo.get("id") or 0
        if not repo_name:
            continue

        event_time = _parse_time(event.get("created_at") or "")
        if event_time is None:
            continue

        actor_login = _sanitize_xml_text(actor.get("login") or "")

        if repo_name not in contributions[actor_id]:
            contributions[actor_id][repo_name] = ActorRepoContrib(
                actor_id=actor_id,
                actor_login=actor_login,
                repo_name=repo_name,
                repo_id=repo_id,
            )

        contributions[actor_id][repo_name].add_event(event_time, event_type, repo_id)

    return dict(contributions)


def filter_and_sort_contributions(
    contributions: Dict[int, Dict[str, ActorRepoContrib]],
    min_event_count: int = DEFAULT_MIN_EVENT_COUNT,
    min_avg_daily_events: float = DEFAULT_MIN_AVG_DAILY_EVENTS,
    min_repos: int = DEFAULT_MIN_REPOS_PER_ACTOR,
) -> Dict[int, List[ActorRepoContrib]]:
    """
    过滤低质量贡献并按 midpoint 排序
    
    流程：
    1. 对每个 (actor, repo) 对，检查是否通过阈值
    2. 每位 actor 至少保留 min_repos 个有效 repo，否则跳过
    3. 按 midpoint 排序
    
    Args:
        contributions: collect_contributions 的输出
        min_event_count: 最低贡献次数（>= 此值）
        min_avg_daily_events: 最低平均日贡献
        min_repos: 至少参与多少个 repo 才能产生流动
    
    Returns:
        {actor_id: [ActorRepoContrib, ...]}  按 midpoint 升序排列
    """
    result: Dict[int, List[ActorRepoContrib]] = {}

    for actor_id, repo_contribs in contributions.items():
        valid = [
            c for c in repo_contribs.values()
            if c.passes_filter(min_event_count, min_avg_daily_events)
        ]
        if len(valid) < min_repos:
            continue
        # 按 midpoint 排序（相同 midpoint 按 repo_name 稳定排序）
        valid.sort(key=lambda c: (c.midpoint, c.repo_name))
        result[actor_id] = valid

    return result


def generate_flow_edges(
    sorted_contributions: Dict[int, List[ActorRepoContrib]],
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    从排序后的贡献列表生成 repo→repo 流动边（聚合）
    
    对每位开发者，相邻 repo 对构成一条有向边 src→dst。
    所有开发者的边聚合后，得到带权重的汇总边。
    
    Returns:
        {(src_repo_name, dst_repo_name): {
            "weight": int,
            "actors": [{"actor_id", "login", "from_midpoint", "to_midpoint"}, ...],
            "time_gaps_days": [float, ...],
        }}
    """
    edges: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(
        lambda: {"weight": 0, "actors": [], "time_gaps_days": []}
    )

    for actor_id, contribs in sorted_contributions.items():
        for i in range(len(contribs) - 1):
            src = contribs[i]
            dst = contribs[i + 1]

            # 跳过自环（同名 repo，理论上不会出现，但防御性编程）
            if src.repo_name == dst.repo_name:
                continue

            key = (src.repo_name, dst.repo_name)
            edges[key]["weight"] += 1
            edges[key]["actors"].append({
                "actor_id": src.actor_id,
                "login": src.actor_login,
                "from_midpoint": src.midpoint.isoformat(),
                "to_midpoint": dst.midpoint.isoformat(),
            })
            gap_days = (dst.midpoint - src.midpoint).total_seconds() / 86400.0
            edges[key]["time_gaps_days"].append(gap_days)

    return dict(edges)


def build_repo_flow_graph(
    events: List[Dict],
    time_window: str = "global",
    contribution_types: Optional[Set[str]] = None,
    min_event_count: int = DEFAULT_MIN_EVENT_COUNT,
    min_avg_daily_events: float = DEFAULT_MIN_AVG_DAILY_EVENTS,
    min_repos: int = DEFAULT_MIN_REPOS_PER_ACTOR,
) -> nx.DiGraph:
    """
    构建 Repo-Repo 人员流动有向图
    
    Args:
        events: 事件列表
        time_window: 时间窗口标签（如 "global", "2021", "2021-01"）
        contribution_types: 贡献事件类型
        min_event_count: 最低贡献次数
        min_avg_daily_events: 最低平均日贡献
        min_repos: 最低参与 repo 数
    
    Returns:
        nx.DiGraph，节点为 repo，边为开发者流动
    """
    # 1. 收集贡献
    contributions = collect_contributions(events, contribution_types)
    total_actors = len(contributions)
    total_contrib_pairs = sum(len(repos) for repos in contributions.values())

    # 2. 过滤与排序
    sorted_contribs = filter_and_sort_contributions(
        contributions, min_event_count, min_avg_daily_events, min_repos
    )
    qualified_actors = len(sorted_contribs)
    valid_contrib_pairs = sum(len(repos) for repos in sorted_contribs.values())

    # 3. 生成流动边
    flow_edges = generate_flow_edges(sorted_contribs)

    # 4. 收集 repo 级别统计（用于节点属性）
    repo_stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"repo_id": 0, "contributor_count": 0, "total_events": 0}
    )
    for actor_id, contribs in sorted_contribs.items():
        for c in contribs:
            stats = repo_stats[c.repo_name]
            stats["repo_id"] = c.repo_id
            stats["contributor_count"] += 1
            stats["total_events"] += c.event_count

    # 5. 构建图
    graph = nx.DiGraph()

    # 添加节点（只添加出现在流动边中的 repo）
    repos_in_edges = set()
    for (src, dst) in flow_edges:
        repos_in_edges.add(src)
        repos_in_edges.add(dst)

    for repo_name in repos_in_edges:
        stats = repo_stats.get(repo_name, {})
        graph.add_node(
            repo_name,
            node_type="Repository",
            repo_id=stats.get("repo_id", 0),
            repo_name=_sanitize_xml_text(repo_name),
            contributor_count=stats.get("contributor_count", 0),
            total_events=stats.get("total_events", 0),
        )

    # 添加边
    for (src, dst), data in flow_edges.items():
        time_gaps = data["time_gaps_days"]
        avg_gap = sum(time_gaps) / len(time_gaps) if time_gaps else 0.0
        min_gap = min(time_gaps) if time_gaps else 0.0
        max_gap = max(time_gaps) if time_gaps else 0.0

        # 收集流动的 actor login 列表（去重）
        seen_logins = {}
        for a in data["actors"]:
            seen_logins[a["actor_id"]] = a["login"]
        actor_logins = ",".join(sorted(seen_logins.values()))

        graph.add_edge(
            src, dst,
            weight=data["weight"],
            actor_count=data["weight"],
            actor_logins=_sanitize_xml_text(actor_logins),
            avg_gap_days=round(avg_gap, 2),
            min_gap_days=round(min_gap, 2),
            max_gap_days=round(max_gap, 2),
            # 完整的 actor 流动详情（JSON）
            flow_details=_sanitize_xml_text(
                json.dumps(data["actors"], ensure_ascii=False)
            ),
        )

    # 图级别属性
    graph.graph["graph_type"] = "repo-flow"
    graph.graph["time_window"] = _sanitize_xml_text(time_window)
    graph.graph["total_events"] = len(events)
    graph.graph["total_actors"] = total_actors
    graph.graph["qualified_actors"] = qualified_actors
    graph.graph["total_contrib_pairs"] = total_contrib_pairs
    graph.graph["valid_contrib_pairs"] = valid_contrib_pairs
    graph.graph["min_event_count"] = min_event_count
    graph.graph["min_avg_daily_events"] = min_avg_daily_events
    graph.graph["node_count"] = graph.number_of_nodes()
    graph.graph["edge_count"] = graph.number_of_edges()

    return graph


def save_graph(graph: nx.DiGraph, output_path: str) -> bool:
    """保存图为 GraphML 文件"""
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        sanitize_graphml_attributes(graph)
        nx.write_graphml(graph, output_path)
        return True
    except Exception as e:
        print(f"  保存失败 {output_path}: {e}")
        return False


# ==================== 主流程函数 ====================

def build_global(
    data_dir: str,
    output_dir: str,
    **kwargs,
) -> Optional[str]:
    """
    全局模式：将所有数据构建为一张 Repo-Repo 流动图
    
    Returns:
        输出文件路径，失败返回 None
    """
    print("\n" + "=" * 60)
    print("模式: 全局 (global)")
    print("=" * 60)

    print("加载所有数据...")
    events = load_all_events(data_dir)
    if not events:
        print("无数据，跳过")
        return None

    print(f"构建全局 Repo-Repo 流动图 ({len(events)} 事件)...")
    graph = build_repo_flow_graph(events, time_window="global", **kwargs)

    output_path = str(Path(output_dir) / "global" / "repo-flow.graphml")
    _print_graph_summary(graph, "global")

    if graph.number_of_nodes() < 2:
        print("  图节点不足，跳过保存")
        return None

    if save_graph(graph, output_path):
        print(f"  已保存: {output_path}")
        return output_path
    return None


def build_yearly(
    data_dir: str,
    output_dir: str,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    **kwargs,
) -> Dict[str, str]:
    """
    按年切分模式
    
    Returns:
        {year: output_path}
    """
    print("\n" + "=" * 60)
    print("模式: 按年 (yearly)")
    print("=" * 60)

    months = get_available_months(data_dir)
    if not months:
        print("无可用数据")
        return {}

    # 按年分组月份
    year_months: Dict[str, List[str]] = defaultdict(list)
    for m in months:
        year = m[:4]
        year_months[year].append(m)

    # 过滤年份范围
    years = sorted(year_months.keys())
    if start_year:
        years = [y for y in years if int(y) >= start_year]
    if end_year:
        years = [y for y in years if int(y) <= end_year]

    print(f"将处理 {len(years)} 年: {years[0]} ~ {years[-1]}")

    results = {}
    for year_idx, year in enumerate(years, 1):
        print(f"\n--- 年份 {year} ({year_idx}/{len(years)}) ---")

        # 加载该年所有月份的事件
        all_events = []
        for month in sorted(year_months[year]):
            month_events = load_month_events(data_dir, month)
            all_events.extend(month_events)
            print(f"  加载 {month}: {len(month_events)} 事件")

        if not all_events:
            print(f"  年份 {year} 无数据，跳过")
            continue

        print(f"  构建图 ({len(all_events)} 事件)...")
        graph = build_repo_flow_graph(all_events, time_window=year, **kwargs)
        _print_graph_summary(graph, year)

        if graph.number_of_nodes() < 2:
            print(f"  节点不足，跳过")
            del all_events
            gc.collect()
            continue

        output_path = str(Path(output_dir) / "yearly" / f"{year}.graphml")
        if save_graph(graph, output_path):
            results[year] = output_path
            print(f"  已保存: {output_path}")

        del all_events
        gc.collect()

    return results


def build_monthly(
    data_dir: str,
    output_dir: str,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    **kwargs,
) -> Dict[str, str]:
    """
    按月切分模式（流式加载，低内存）
    
    Returns:
        {month: output_path}
    """
    print("\n" + "=" * 60)
    print("模式: 按月 (monthly)")
    print("=" * 60)

    months = get_available_months(data_dir)
    if not months:
        print("无可用数据")
        return {}

    # 过滤月份范围
    if start_month:
        months = [m for m in months if m >= start_month]
    if end_month:
        months = [m for m in months if m <= end_month]

    print(f"将处理 {len(months)} 个月: {months[0]} ~ {months[-1]}")

    results = {}
    for month_idx, month in enumerate(months, 1):
        print(f"\n--- 月份 {month} ({month_idx}/{len(months)}) ---")

        events = load_month_events(data_dir, month)
        if not events:
            print(f"  无数据，跳过")
            continue

        print(f"  构建图 ({len(events)} 事件)...")
        graph = build_repo_flow_graph(events, time_window=month, **kwargs)
        _print_graph_summary(graph, month)

        if graph.number_of_nodes() < 2:
            print(f"  节点不足，跳过")
            del events
            gc.collect()
            continue

        output_path = str(Path(output_dir) / "monthly" / f"{month}.graphml")
        if save_graph(graph, output_path):
            results[month] = output_path
            print(f"  已保存: {output_path}")

        del events
        gc.collect()

    return results


def _print_graph_summary(graph: nx.DiGraph, label: str):
    """打印图的简要统计"""
    n_nodes = graph.number_of_nodes()
    n_edges = graph.number_of_edges()
    total_weight = sum(d.get("weight", 0) for _, _, d in graph.edges(data=True))
    qualified = graph.graph.get("qualified_actors", 0)
    total_actors = graph.graph.get("total_actors", 0)
    total_contribs = graph.graph.get("total_contrib_pairs", 0)
    valid_contribs = graph.graph.get("valid_contrib_pairs", 0)

    print(f"  [{label}] 节点={n_nodes}, 边={n_edges}, "
          f"总流动权重={total_weight}")
    print(f"         开发者: {total_actors} 总计, "
          f"{qualified} 人拥有 >=2 个有效区间可产生流动")
    print(f"         (actor,repo) 区间: {total_contribs} 总计, "
          f"{valid_contribs} 通过过滤")

    # 打印权重最大的 top-5 边
    if n_edges > 0:
        top_edges = sorted(
            graph.edges(data=True),
            key=lambda e: e[2].get("weight", 0),
            reverse=True,
        )[:5]
        print(f"  Top 流动边:")
        for src, dst, data in top_edges:
            print(f"    {src} → {dst}  (权重={data.get('weight', 0)}, "
                  f"avg_gap={data.get('avg_gap_days', 0):.1f}天)")


# ==================== 统一入口 ====================

def build_repo_flow_graphs(
    data_dir: str = "data/filtered/",
    output_dir: str = "output/repo-flow-graphs/",
    mode: str = "global",
    contribution_types: Optional[Set[str]] = None,
    min_event_count: int = DEFAULT_MIN_EVENT_COUNT,
    min_avg_daily_events: float = DEFAULT_MIN_AVG_DAILY_EVENTS,
    min_repos: int = DEFAULT_MIN_REPOS_PER_ACTOR,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    统一入口：根据 mode 参数选择时间窗口模式
    
    Args:
        data_dir: 输入数据目录
        output_dir: 输出目录
        mode: "global" | "yearly" | "monthly" | "all"
        contribution_types: 贡献事件类型集合
        min_event_count: 最低贡献次数
        min_avg_daily_events: 最低平均日贡献
        min_repos: 最低参与 repo 数
        start_month: 月份下界 (YYYY-MM)
        end_month: 月份上界 (YYYY-MM)
        start_year: 年份下界 (int)
        end_year: 年份上界 (int)
    
    Returns:
        {mode: results}
    """
    common_kwargs = dict(
        contribution_types=contribution_types,
        min_event_count=min_event_count,
        min_avg_daily_events=min_avg_daily_events,
        min_repos=min_repos,
    )

    results = {}

    if mode in ("global", "all"):
        path = build_global(data_dir, output_dir, **common_kwargs)
        results["global"] = path

    if mode in ("yearly", "all"):
        yearly_results = build_yearly(
            data_dir, output_dir,
            start_year=start_year, end_year=end_year,
            **common_kwargs,
        )
        results["yearly"] = yearly_results

    if mode in ("monthly", "all"):
        monthly_results = build_monthly(
            data_dir, output_dir,
            start_month=start_month, end_month=end_month,
            **common_kwargs,
        )
        results["monthly"] = monthly_results

    # 保存索引
    index_path = Path(output_dir) / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)

    # 合并已有索引
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            existing_index = json.load(f)
    else:
        existing_index = {}

    # 将 results 序列化友好化
    serializable = _make_serializable(results)
    existing_index.update(serializable)

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(existing_index, f, indent=2, ensure_ascii=False)
    print(f"\n索引已保存: {index_path}")

    # 总结
    _print_final_summary(results)

    return results


def _make_serializable(obj):
    """确保对象可以 JSON 序列化"""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_make_serializable(i) for i in obj]
    elif isinstance(obj, Path):
        return str(obj)
    elif obj is None:
        return None
    else:
        return obj


def _print_final_summary(results: Dict[str, Any]):
    """打印最终汇总"""
    print("\n" + "=" * 60)
    print("全部完成！汇总：")
    print("=" * 60)

    if "global" in results:
        path = results["global"]
        print(f"  全局图: {'已生成' if path else '无数据/跳过'}")

    if "yearly" in results:
        yearly = results["yearly"]
        if isinstance(yearly, dict):
            print(f"  年度图: {len(yearly)} 张 ({', '.join(sorted(yearly.keys()))})")

    if "monthly" in results:
        monthly = results["monthly"]
        if isinstance(monthly, dict):
            print(f"  月度图: {len(monthly)} 张")
            if monthly:
                keys = sorted(monthly.keys())
                print(f"          {keys[0]} ~ {keys[-1]}")


# ==================== CLI ====================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="构建 Repository-Repository 人员流动有向图",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法：
  # 全局模式
  python build_repo_flow_graph.py --mode global

  # 按年切分
  python build_repo_flow_graph.py --mode yearly --start-year 2021 --end-year 2023

  # 按月切分
  python build_repo_flow_graph.py --mode monthly --start-month 2021-01 --end-month 2021-12

  # 同时生成全部三种
  python build_repo_flow_graph.py --mode all

  # 自定义过滤阈值
  python build_repo_flow_graph.py --mode global --min-events 5 --min-avg-daily 0.5
        """,
    )
    parser.add_argument(
        "--data-dir", type=str, default="data/filtered/",
        help="输入数据目录 (默认: data/filtered/)",
    )
    parser.add_argument(
        "--output-dir", type=str, default="output/repo-flow-graphs/",
        help="输出目录 (默认: output/repo-flow-graphs/)",
    )
    parser.add_argument(
        "--mode", type=str, default="global",
        choices=["global", "yearly", "monthly", "all"],
        help="时间窗口模式 (默认: global)",
    )
    parser.add_argument(
        "--min-events", type=int, default=DEFAULT_MIN_EVENT_COUNT,
        help=f"最低贡献次数，>= 此值 (默认: {DEFAULT_MIN_EVENT_COUNT})",
    )
    parser.add_argument(
        "--min-avg-daily", type=float, default=DEFAULT_MIN_AVG_DAILY_EVENTS,
        help=f"最低平均日贡献 (默认: {DEFAULT_MIN_AVG_DAILY_EVENTS})",
    )
    parser.add_argument(
        "--min-repos", type=int, default=DEFAULT_MIN_REPOS_PER_ACTOR,
        help=f"开发者至少参与多少个 repo 才计入流动 (默认: {DEFAULT_MIN_REPOS_PER_ACTOR})",
    )
    parser.add_argument(
        "--start-month", type=str, default=None,
        help="月份下界，YYYY-MM (仅 monthly 模式)",
    )
    parser.add_argument(
        "--end-month", type=str, default=None,
        help="月份上界，YYYY-MM (仅 monthly 模式)",
    )
    parser.add_argument(
        "--start-year", type=int, default=None,
        help="年份下界 (仅 yearly 模式)",
    )
    parser.add_argument(
        "--end-year", type=int, default=None,
        help="年份上界 (仅 yearly 模式)",
    )
    parser.add_argument(
        "--include-watch-fork", action="store_true",
        help="将 WatchEvent 和 ForkEvent 也视为贡献 (默认排除)",
    )

    args = parser.parse_args()

    # 设置贡献类型
    contribution_types = set(DEFAULT_CONTRIBUTION_TYPES)
    if args.include_watch_fork:
        contribution_types.add("WatchEvent")
        contribution_types.add("ForkEvent")

    # 打印配置
    print("=" * 60)
    print("构建 Repo-Repo 人员流动图")
    print("=" * 60)
    print(f"  数据目录:      {args.data_dir}")
    print(f"  输出目录:      {args.output_dir}")
    print(f"  模式:          {args.mode}")
    print(f"  最低贡献次数:  >= {args.min_events}")
    print(f"  最低日均贡献:  >= {args.min_avg_daily}")
    print(f"  最低参与 repo: >= {args.min_repos}")
    print(f"  贡献事件类型:  {sorted(contribution_types)}")
    if args.start_month or args.end_month:
        print(f"  月份范围:      {args.start_month or '不限'} ~ {args.end_month or '不限'}")
    if args.start_year or args.end_year:
        print(f"  年份范围:      {args.start_year or '不限'} ~ {args.end_year or '不限'}")
    print("=" * 60)

    build_repo_flow_graphs(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        mode=args.mode,
        contribution_types=contribution_types,
        min_event_count=args.min_events,
        min_avg_daily_events=args.min_avg_daily,
        min_repos=args.min_repos,
        start_month=args.start_month,
        end_month=args.end_month,
        start_year=args.start_year,
        end_year=args.end_year,
    )


if __name__ == "__main__":
    main()