"""
人员流动分析模块

基于倦怠分析结果，研究各 repo 的人员流动情况，重点关注核心成员：

1. 核心成员时间线：首次/末次出现、任期、活跃月份
2. 流入/流出事件：谁何时成为核心、谁何时离开
3. 留存率：N 个月核心成员留存曲线
4. 流动率：按月/按季的流入流出统计
5. 关键流失：长期核心成员离职识别
6. 跨 repo 流向：离开后在哪些其他项目中成为核心

概念说明：
- 「离开」= 某月不再处于该 repo 的核心成员名单（贡献跌出前约 50%）。
  不表示完全不参与，可能是参与减少、完全退出或角色变化。
- 核心成员：由加权贡献量（PR 合并/评审、Issue 互动等）+ 网络位置（k-core）动态计算。
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class CoreMemberRecord:
    """单个月的核心成员记录"""
    login: str
    degree: int
    rank: int  # 1-based 排名


@dataclass
class MemberTimeline:
    """核心成员时间线"""
    login: str
    first_month: str
    last_month: str
    tenure_months: int
    active_months: List[str]
    rank_history: List[Tuple[str, int, int]]  # (month, degree, rank)
    avg_rank: float = 0.0


@dataclass
class JoinEvent:
    """流入事件：某人成为核心成员"""
    month: str
    login: str
    degree: int
    rank: int
    repo_name: str


@dataclass
class LeaveEvent:
    """流出事件：某人不再为核心成员"""
    month: str
    login: str
    tenure_months: int
    was_top_n: bool  # 是否为前 N 名
    repo_name: str


class PersonnelFlowAnalyzer:
    """人员流动分析器"""

    def __init__(
        self,
        input_path: str = "output/burnout-analysis/full_analysis.json",
        output_dir: str = "output/personnel-flow/",
        scope: str = "core",
        graphs_dir: Optional[str] = None,
    ):
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        self.scope = scope  # "core" | "all"
        self.graphs_dir = Path(graphs_dir) if graphs_dir else None
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _scope_label(self) -> str:
        return "全部贡献者" if self.scope == "all" else "核心成员"

    def _load_graph(self, graph_path: str) -> Optional[nx.MultiDiGraph]:
        """加载图（兼容 Windows 路径）"""
        try:
            normalized_path = Path(str(graph_path).replace("\\", "/"))
            g = nx.read_graphml(normalized_path)
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
            logger.warning(f"加载图失败: {graph_path}, 错误: {e}")
            return None

    def _load_burnout_data(self) -> Dict[str, Any]:
        """加载倦怠分析数据"""
        if not self.input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {self.input_path}")
        with open(self.input_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_all_actors_data_from_graphs(
        self,
        repo_names: List[str],
    ) -> Dict[str, Any]:
        """从月度图加载所有节点，构建与 burnout 格式兼容的数据（core_actors = 全部贡献者）"""
        if not self.graphs_dir or not self.graphs_dir.exists():
            raise FileNotFoundError(f"图目录不存在: {self.graphs_dir}，请指定 --graphs-dir")
        index_file = self.graphs_dir / "index.json"
        if not index_file.exists():
            raise FileNotFoundError(f"索引不存在: {index_file}")
        with open(index_file, "r", encoding="utf-8") as f:
            index = json.load(f)

        result = {}
        for repo_name in repo_names:
            graph_types = index.get(repo_name, {})
            first_val = next(iter(graph_types.values()), {})
            if isinstance(first_val, dict) and not first_val.get("node_type"):
                months_data = graph_types.get("actor-actor", {})
            else:
                months_data = graph_types
            if not months_data or not isinstance(months_data, dict):
                continue
            metrics_series = []
            for month, graph_path in sorted(months_data.items()):
                graph = self._load_graph(graph_path)
                if graph is None:
                    continue
                degrees = dict(graph.degree())
                # 按度数降序，构建 (login, degree) 列表
                actors = []
                for node_id in graph.nodes():
                    login = graph.nodes[node_id].get("login", str(node_id))
                    degree = degrees.get(node_id, 0)
                    actors.append((login, degree))
                actors.sort(key=lambda x: -x[1])
                total_events = graph.graph.get("total_events", 0)
                metrics_series.append({
                    "month": month,
                    "repo_name": repo_name,
                    "unique_actors": len(actors),
                    "total_events": total_events,
                    "core_actors": actors,
                })
            if metrics_series:
                result[repo_name] = {"metrics": metrics_series}
        return result

    def _extract_core_per_month(
        self,
        metrics_series: List[Dict],
    ) -> Dict[str, List[CoreMemberRecord]]:
        """从 metrics 序列提取每月核心成员列表"""
        core_by_month: Dict[str, List[CoreMemberRecord]] = {}
        sorted_metrics = sorted(metrics_series, key=lambda m: m.get("month", ""))

        for m in sorted_metrics:
            month = m.get("month", "")
            core_actors = m.get("core_actors", [])
            records = []
            for rank, item in enumerate(core_actors, 1):
                if isinstance(item, (list, tuple)):
                    login = item[0] if len(item) > 0 else ""
                    degree = item[1] if len(item) > 1 else 0
                else:
                    login = str(item)
                    degree = 0
                if login:
                    records.append(CoreMemberRecord(login=login, degree=degree, rank=rank))
            core_by_month[month] = records
        return core_by_month

    def _build_member_timelines(
        self,
        core_by_month: Dict[str, List[CoreMemberRecord]],
    ) -> Dict[str, MemberTimeline]:
        """构建每个核心成员的时间线"""
        # login -> {months: [(degree, rank), ...]}
        member_months: Dict[str, Dict[str, Tuple[int, int]]] = defaultdict(dict)

        for month, records in core_by_month.items():
            for r in records:
                member_months[r.login][month] = (r.degree, r.rank)

        timelines = {}
        for login, months_data in member_months.items():
            active_months = sorted(months_data.keys())
            first_month = active_months[0]
            last_month = active_months[-1]
            tenure = len(active_months)
            rank_history = [
                (m, months_data[m][0], months_data[m][1])
                for m in active_months
            ]
            avg_rank = sum(r[2] for r in rank_history) / len(rank_history) if rank_history else 0

            timelines[login] = MemberTimeline(
                login=login,
                first_month=first_month,
                last_month=last_month,
                tenure_months=tenure,
                active_months=active_months,
                rank_history=rank_history,
                avg_rank=round(avg_rank, 2),
            )
        return timelines

    def _detect_join_leave_events(
        self,
        core_by_month: Dict[str, List[CoreMemberRecord]],
        repo_name: str,
        timelines: Dict[str, MemberTimeline],
    ) -> Tuple[List[Dict], List[Dict]]:
        """检测流入流出事件"""
        months = sorted(core_by_month.keys())
        join_events = []
        leave_events = []

        prev_core = set()

        for month in months:
            curr_core_logins = {r.login for r in core_by_month[month]}
            curr_core_map = {r.login: (r.degree, r.rank) for r in core_by_month[month]}

            # 流入：本月在、上月不在
            for login in curr_core_logins - prev_core:
                degree, rank = curr_core_map[login]
                join_events.append({
                    "month": month,
                    "login": login,
                    "degree": degree,
                    "rank": rank,
                    "repo_name": repo_name,
                })

            # 流出：上月在、本月不在（tenure 从 timeline 补全）
            for login in prev_core - curr_core_logins:
                t = timelines.get(login)
                tenure = t.tenure_months if t else 0
                was_top_3 = any(
                    r.login == login and r.rank <= 3
                    for recs in core_by_month.values()
                    for r in recs
                )
                leave_events.append({
                    "month": month,
                    "login": login,
                    "tenure_months": tenure,
                    "was_top_n": was_top_3,
                    "repo_name": repo_name,
                })

            prev_core = curr_core_logins

        return join_events, leave_events

    def _compute_retention_rates(
        self,
        timelines: Dict[str, MemberTimeline],
        total_months: int,
    ) -> Dict[int, float]:
        """计算 N 个月留存率：任期 >= N 月的核心成员占比"""
        if total_months < 2 or not timelines:
            return {}
        retention = {}
        for n in range(1, min(total_months, 13)):  # 最多 12 个月
            retained = sum(1 for t in timelines.values() if t.tenure_months >= n)
            retention[n] = round(retained / len(timelines), 4)
        return retention

    def _compute_period_churn(
        self,
        core_by_month: Dict[str, List[CoreMemberRecord]],
    ) -> List[Dict]:
        """计算各期流动统计"""
        months = sorted(core_by_month.keys())
        result = []
        prev_core = set()

        for month in months:
            curr_core = {r.login for r in core_by_month[month]}
            joined = len(curr_core - prev_core)
            left = len(prev_core - curr_core)
            result.append({
                "month": month,
                "core_count": len(curr_core),
                "joined": joined,
                "left": left,
                "net_change": len(curr_core) - len(prev_core),
            })
            prev_core = curr_core
        return result

    def _identify_critical_departures(
        self,
        leave_events: List[Dict],
        timelines: Dict[str, MemberTimeline],
        min_tenure: int = 6,
    ) -> List[Dict]:
        """识别关键流失：任期较长的核心成员离开"""
        critical = []
        for evt in leave_events:
            login = evt["login"]
            timeline = timelines.get(login)
            if timeline and timeline.tenure_months >= min_tenure:
                critical.append({
                    **evt,
                    "tenure_months": timeline.tenure_months,
                    "avg_rank": timeline.avg_rank,
                })
        return critical

    def _build_global_core_index(
        self,
        burnout_data: Dict[str, Any],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """构建全局核心成员索引：login -> [(repo, month, rank, degree), ...]"""
        index: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for repo_name, repo_data in burnout_data.items():
            for m in repo_data.get("metrics", []):
                month = m.get("month", "")
                for rank, item in enumerate(m.get("core_actors", []), 1):
                    if isinstance(item, (list, tuple)):
                        login = (item[0] or "").strip()
                        degree = item[1] if len(item) > 1 else 0
                    else:
                        login = str(item).strip()
                        degree = 0
                    if login:
                        index[login].append({
                            "repo": repo_name,
                            "month": month,
                            "rank": rank,
                            "degree": degree,
                        })
        for k in index:
            index[k].sort(key=lambda x: (x["month"], x["repo"]))
        return dict(index)

    def _find_flow_destinations(
        self,
        login: str,
        from_repo: str,
        leave_month: str,
        global_index: Dict[str, List[Dict[str, Any]]],
        months_after: int = 12,
    ) -> List[Dict[str, Any]]:
        """
        查找某人离开某 repo 后流向的其他项目。
        在离开当月及之后 N 个月内，在其它 repo 中首次成为核心的视为流向。
        """
        appearances = global_index.get(login, [])
        flow_to = []
        seen_repos = set()

        for a in appearances:
            repo = a["repo"]
            month = a["month"]
            if repo == from_repo:
                continue
            if repo in seen_repos:
                continue
            if month < leave_month:
                continue
            # 简单月数差：假设 YYYY-MM 可直接比较
            if months_after >= 0 and month > self._month_add(leave_month, months_after):
                break
            seen_repos.add(repo)
            flow_to.append({
                "repo": repo,
                "first_month": month,
                "rank": a["rank"],
                "degree": a["degree"],
            })
        return flow_to

    def _month_add(self, month_str: str, n: int) -> str:
        """YYYY-MM + n 个月"""
        y, m = map(int, month_str.split("-"))
        m += n
        while m > 12:
            m -= 12
            y += 1
        while m < 1:
            m += 12
            y -= 1
        return f"{y:04d}-{m:02d}"

    def analyze_repo(
        self,
        repo_name: str,
        metrics_series: List[Dict],
    ) -> Dict[str, Any]:
        """分析单个 repo 的人员流动"""
        if len(metrics_series) < 2:
            return {"error": "数据不足，需要至少 2 个月"}

        core_by_month = self._extract_core_per_month(metrics_series)
        timelines = self._build_member_timelines(core_by_month)
        join_events, leave_events = self._detect_join_leave_events(
            core_by_month, repo_name, timelines
        )
        period_churn = self._compute_period_churn(core_by_month)
        critical_departures = self._identify_critical_departures(leave_events, timelines)

        months = sorted(core_by_month.keys())
        retention = self._compute_retention_rates(timelines, len(months))

        # 汇总
        total_joins = len(join_events)
        total_leaves = len(leave_events)
        unique_core = len(timelines)
        avg_tenure = (
            sum(t.tenure_months for t in timelines.values()) / len(timelines)
            if timelines else 0
        )

        return {
            "repo_name": repo_name,
            "period": {"start": months[0], "end": months[-1], "months": len(months)},
            "summary": {
                "unique_core_members": unique_core,
                "total_join_events": total_joins,
                "total_leave_events": total_leaves,
                "avg_tenure_months": round(avg_tenure, 2),
                "critical_departures": len(critical_departures),
            },
            "member_timelines": [
                {
                    "login": t.login,
                    "first_month": t.first_month,
                    "last_month": t.last_month,
                    "tenure_months": t.tenure_months,
                    "avg_rank": t.avg_rank,
                }
                for t in sorted(timelines.values(), key=lambda x: -x.tenure_months)
            ],
            "join_events": join_events,
            "leave_events": leave_events,
            "critical_departures": critical_departures,
            "period_churn": period_churn,
            "retention_rates": retention,
        }

    def run(
        self,
        flow_months_after: int = 12,
    ) -> Dict[str, Any]:
        """运行完整分析"""
        scope_label = "全部贡献者" if self.scope == "all" else "核心成员"
        logger.info(f"人员流动分析（{scope_label}）...")

        if self.scope == "all":
            if not self.graphs_dir:
                raise ValueError("scope=all 时需指定 --graphs-dir")
            burnout_data = self._load_burnout_data()
            repo_names = list(burnout_data.keys())
            logger.info(f"从图加载 {len(repo_names)} 个 repo 的全部贡献者...")
            data = self._build_all_actors_data_from_graphs(repo_names)
        else:
            data = self._load_burnout_data()
        self._trend_data = data

        results = {}
        for repo_name, repo_data in data.items():
            metrics = repo_data.get("metrics", [])
            if not metrics:
                continue
            logger.info(f"分析: {repo_name}")
            try:
                results[repo_name] = self.analyze_repo(repo_name, metrics)
            except Exception as e:
                logger.warning(f"分析失败 {repo_name}: {e}")
                results[repo_name] = {"error": str(e)}

        # 跨 repo 流向分析
        logger.info("计算跨 repo 流向...")
        global_index = self._build_global_core_index(data)
        for repo_name, repo_result in results.items():
            if "error" in repo_result:
                continue
            for evt in repo_result.get("leave_events", []):
                flow_to = self._find_flow_destinations(
                    evt["login"],
                    evt["repo_name"],
                    evt["month"],
                    global_index,
                    months_after=flow_months_after,
                )
                evt["flowed_to"] = flow_to
            for evt in repo_result.get("critical_departures", []):
                flow_to = self._find_flow_destinations(
                    evt["login"],
                    evt["repo_name"],
                    evt["month"],
                    global_index,
                    months_after=flow_months_after,
                )
                evt["flowed_to"] = flow_to

        # 保存
        output_file = self.output_dir / "personnel_flow.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"已保存: {output_file}")

        # 生成报告
        self._save_summary_report(results)
        self._save_leave_events_detail(results)
        self._save_flow_statistics(results)
        self._save_flow_by_year_report(results)
        self._save_flow_timeline_report(results)
        self._save_repo_trend_report()
        self._save_cross_repo_flow_report(results)
        self._save_yearly_status_report(results)
        return results

    def _save_leave_events_detail(self, results: Dict[str, Any]) -> None:
        """保存全部流失明细（含跨 repo 流向）"""
        report_path = self.output_dir / "leave_events_detail.txt"
        lines = []
        lines.append("=" * 70)
        lines.append(f"全部流失明细（{self._scope_label()}，含跨 repo 流向）")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"【概念说明】「离开」= 某月不再处于该 repo {self._scope_label()}名单。")
        lines.append("")

        repos_with_data = [
            (r, d) for r, d in results.items()
            if "error" not in d and isinstance(d, dict)
        ]
        for repo_name, repo_result in sorted(repos_with_data, key=lambda x: x[0]):
            leave_events = repo_result.get("leave_events", [])
            if not leave_events:
                continue
            lines.append(f"\n【{repo_name}】共 {len(leave_events)} 条流失")
            lines.append("-" * 50)
            for evt in leave_events:
                flow = evt.get("flowed_to", [])
                flow_str = ""
                if flow:
                    flow_str = " → 流向: " + ", ".join(
                        f"{f['repo']}({f['first_month']})" for f in flow[:5]
                    )
                    if len(flow) > 5:
                        flow_str += f" 等{len(flow)}项"
                lines.append(f"  {evt['login']} 于 {evt['month']} 离开，任期 {evt['tenure_months']} 月{flow_str}")
        lines.append("")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"全部流失明细已保存: {report_path}")

    def _save_flow_statistics(self, results: Dict[str, Any]) -> None:
        """统计整体 repo→repo 流向，按频次排序"""
        report_path = self.output_dir / "flow_statistics.txt"
        flow_counts: Dict[Tuple[str, str], int] = defaultdict(int)
        seen = set()
        for repo_name, repo_result in results.items():
            if "error" in repo_result:
                continue
            for evt in repo_result.get("leave_events", []):
                key = (evt["login"], repo_name, evt["month"])
                if key in seen:
                    continue
                seen.add(key)
                from_repo = repo_name
                for dest in evt.get("flowed_to", []):
                    to_repo = dest["repo"]
                    if from_repo != to_repo:
                        flow_counts[(from_repo, to_repo)] += 1

        sorted_flows = sorted(
            flow_counts.items(),
            key=lambda x: -x[1],
        )

        lines = []
        lines.append("=" * 70)
        lines.append("Repo → Repo 流向统计（按人数排序）")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"说明：从 A 离开后 12 个月内于 B 成为{self._scope_label()}的人数。")
        lines.append("格式：从 [来源] 流向 [目标] : N 人")
        lines.append("")
        lines.append(f"共 {len(sorted_flows)} 条流向记录")
        lines.append("")
        for (from_repo, to_repo), count in sorted_flows[:80]:
            lines.append(f"  {from_repo}  →  {to_repo}  :  {count} 人")

        # 每个 repo 净流入/净流出
        inflow: Dict[str, int] = defaultdict(int)
        outflow: Dict[str, int] = defaultdict(int)
        for (from_repo, to_repo), count in flow_counts.items():
            outflow[from_repo] += count
            inflow[to_repo] += count
        all_repos = sorted(set(inflow) | set(outflow))
        repo_net = [
            (r, inflow[r], outflow[r], inflow[r] - outflow[r])
            for r in all_repos
            if inflow[r] > 0 or outflow[r] > 0
        ]
        repo_net.sort(key=lambda x: -abs(x[3]))  # 按净变化绝对值排序

        lines.append("")
        lines.append("=" * 70)
        lines.append("各 Repo 净流入/净流出（有跨 repo 流动的才统计）")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"说明：流入 = 从其他 repo 离开后流入本 repo 的{self._scope_label()}数；流出 = 从本 repo 离开后流入其他 repo 的人数。")
        lines.append("格式：Repo | 流入 | 流出 | 净（正=净流入，负=净流出）")
        lines.append("")
        for repo, i, o, net in repo_net:
            net_str = f"+{net}" if net > 0 else str(net)
            lines.append(f"  {repo}")
            lines.append(f"    流入: {i} 人  流出: {o} 人  净: {net_str} 人")
        lines.append("")

        # ======================================================================
        # AI 辅助洞察：流动模式分析
        # ======================================================================
        lines.append("=" * 70)
        lines.append("AI 辅助洞察：流动模式自动分析")
        lines.append("=" * 70)
        lines.append("说明：")
        lines.append("- 生态共荣：双向流动频繁，说明技术栈紧密耦合（双向均 ≥ 5 人，且比例 < 3:1）")
        lines.append("- 强单向转移：主要的贡献者流向（A→B人数是B→A的3倍以上，且A→B > 10）")
        lines.append("- 新兴磁铁：人才净流入显著的大型项目（净流入 > 30）")
        lines.append("- 基础设施/人才库：人才净流出显著，通常是底层库或跳板项目（净流出 < -30）")
        lines.append("")

        # 1. 分析双向/单向关系
        repo_pairs = set()
        for (f, t) in flow_counts.keys():
            if f < t:
                repo_pairs.add((f, t))
            else:
                repo_pairs.add((t, f))
        
        symbiotic = []
        one_way = []

        for r1, r2 in repo_pairs:
            f1_to_2 = flow_counts.get((r1, r2), 0)
            f2_to_1 = flow_counts.get((r2, r1), 0)
            total = f1_to_2 + f2_to_1
            if total == 0:
                continue

            # 双向强关联判定: 双方都有一定流动，且不极端失衡
            if f1_to_2 >= 5 and f2_to_1 >= 5:
                ratio = max(f1_to_2, f2_to_1) / min(f1_to_2, f2_to_1)
                if ratio < 3.0:
                    symbiotic.append((r1, r2, f1_to_2, f2_to_1, total))
                    continue
            
            # 单向判定
            if f1_to_2 > 10 and f1_to_2 > f2_to_1 * 3:
                one_way.append((r1, r2, f1_to_2, f2_to_1))
            elif f2_to_1 > 10 and f2_to_1 > f1_to_2 * 3:
                one_way.append((r2, r1, f2_to_1, f1_to_2))

        symbiotic.sort(key=lambda x: -x[4]) # 按总交流人数降序
        lines.append("[ 生态共荣组合 ] (强关联/上下游耦合)")
        for r1, r2, v1, v2, tot in symbiotic[:20]:
            # 为了展示一致性，让名字短的在前，或者不需要特定顺序
            lines.append(f"  {r1} ↔ {r2}")
            lines.append(f"    共 {tot} 人交互 ({r1}→{r2}: {v1} 人, 反向: {v2} 人)")
        if not symbiotic:
            lines.append("  (无显著结果)")
        lines.append("")

        one_way.sort(key=lambda x: -x[2]) # 按流量降序
        lines.append("[ 强单向转移 ] (流行度转移或特定依赖路径)")
        for src, dst, v_forward, v_back in one_way[:20]:
            lines.append(f"  {src} → {dst}")
            lines.append(f"    单向流动: {v_forward} 人 (反向仅 {v_back} 人)")
        if not one_way:
            lines.append("  (无显著结果)")
        lines.append("")

        # 2. 分析净流入流出（改为比率分析，并避免重叠）
        # 这里的重叠主要指：一个项目既是磁铁又是基础设施（不可能，因为净流正负互斥），
        # 或者出现在上面的关系对中。关系对和单点属性不冲突。
        # 使用比率分析：(流入-流出)/(流入+流出)，更能体现“趋势”而非单纯的体量。
        
        repo_stats = []
        for r, i, o, net in repo_net:
            total = i + o
            if total < 50: # 忽略小样本，避免波动太大
                continue
            ratio = net / total if total > 0 else 0
            repo_stats.append((r, i, o, net, ratio))

        # 磁铁：比率 > 15% (即净流入显著)
        magnets = [x for x in repo_stats if x[4] > 0.15]
        magnets.sort(key=lambda x: -x[4]) # 按比率降序

        # 基础设施/流失：比率 < -15% (即净流出显著)
        feeders = [x for x in repo_stats if x[4] < -0.15]
        feeders.sort(key=lambda x: x[4]) # 按比率升序（负得越多越前）

        lines.append("[ 新兴磁铁 ] (高净流入比 - 正在快速吸纳人才)")
        lines.append(f"说明：总流动 > 50 人，且 (流入-流出)/总流动 > 15%")
        for r, i, o, net, ratio in magnets[:15]:
             lines.append(f"  {r:<30} : 净增 {ratio:+.1%} (净+{net} | 入 {i} / 出 {o})")
        if not magnets:
            lines.append("  (无显著结果)")
        lines.append("")

        lines.append("[ 基础设施/人才库 ] (高净流出比 - 广泛被使用或作为跳板)")
        lines.append(f"说明：总流动 > 50 人，且 (流入-流出)/总流动 < -15%")
        for r, i, o, net, ratio in feeders[:15]:
             lines.append(f"  {r:<30} : 净流 {ratio:+.1%} (净{net} | 入 {i} / 出 {o})")
        if not feeders:
            lines.append("  (无显著结果)")
        lines.append("")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"流向统计已保存: {report_path}")

    def _save_flow_by_year_report(self, results: Dict[str, Any]) -> None:
        """按年统计人员流向，并排名流入最多的目标 repo"""
        report_path = self.output_dir / "flow_by_year.txt"
        # year -> (from, to) -> count
        year_flow_counts: Dict[str, Dict[Tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))

        for repo_name, repo_result in results.items():
            if "error" in repo_result:
                continue
            for evt in repo_result.get("leave_events", []):
                leave_month = evt.get("month", "")
                if not leave_month or len(leave_month) < 4:
                    continue
                year = leave_month[:4]
                from_repo = repo_name
                for dest in evt.get("flowed_to", []):
                    to_repo = dest["repo"]
                    if from_repo != to_repo:
                        year_flow_counts[year][(from_repo, to_repo)] += 1

        years = sorted(year_flow_counts.keys())
        lines = []
        lines.append("=" * 70)
        lines.append("按年统计人员流向")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"说明：按离开年份统计跨 repo 流向。年份以离开月为准。")
        lines.append("")

        # 1. 各年流入最多的目标 Repo 排名（Top N）
        lines.append("=" * 70)
        lines.append("各年流入最多的目标 Repo 排名（Top 15）")
        lines.append("=" * 70)
        lines.append("")
        for year in years:
            counts = year_flow_counts[year]
            inflow: Dict[str, int] = defaultdict(int)
            for (_, to_repo), c in counts.items():
                inflow[to_repo] += c
            top_dests = sorted(inflow.items(), key=lambda x: -x[1])[:15]
            lines.append(f"【{year} 年】")
            for rank, (repo, count) in enumerate(top_dests, 1):
                lines.append(f"  {rank}. {repo}  流入 {count} 人")
            lines.append("")

        # 2. 整体流入最多的目标 Repo 排名（Top 30）
        all_inflow: Dict[str, int] = defaultdict(int)
        for year_counts in year_flow_counts.values():
            for (_, to_repo), c in year_counts.items():
                all_inflow[to_repo] += c
        top_all = sorted(all_inflow.items(), key=lambda x: -x[1])[:30]
        lines.append("=" * 70)
        lines.append("整体流入最多的目标 Repo 排名（Top 30）")
        lines.append("=" * 70)
        lines.append("")
        for rank, (repo, count) in enumerate(top_all, 1):
            lines.append(f"  {rank}. {repo}  流入 {count} 人")
        lines.append("")

        # 3. 各年明细：流向条数、流入/流出 repo 统计
        lines.append("=" * 70)
        lines.append("各年流向明细")
        lines.append("=" * 70)
        lines.append("")
        for year in years:
            counts = year_flow_counts[year]
            inflow_y: Dict[str, int] = defaultdict(int)
            outflow_y: Dict[str, int] = defaultdict(int)
            for (from_repo, to_repo), c in counts.items():
                outflow_y[from_repo] += c
                inflow_y[to_repo] += c
            total_flows = sum(counts.values())
            lines.append(f"【{year} 年】共 {total_flows} 条流向")
            top_in = sorted(inflow_y.items(), key=lambda x: -x[1])[:10]
            top_out = sorted(outflow_y.items(), key=lambda x: -x[1])[:10]
            lines.append(f"  流入最多: {', '.join(f'{r}({c})' for r, c in top_in)}")
            lines.append(f"  流出最多: {', '.join(f'{r}({c})' for r, c in top_out)}")
            lines.append("")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"按年流向统计已保存: {report_path}")

    def _save_flow_timeline_report(self, results: Dict[str, Any]) -> None:
        """按时间顺序统计人才流动情况"""
        report_path = self.output_dir / "flow_timeline.txt"
        events = []
        for repo_name, repo_result in results.items():
            if "error" in repo_result:
                continue
            for evt in repo_result.get("leave_events", []):
                events.append({
                    "month": evt["month"],
                    "repo": repo_name,
                    "login": evt["login"],
                    "tenure": evt.get("tenure_months", 0),
                    "flowed_to": evt.get("flowed_to", []),
                })
        events.sort(key=lambda x: (x["month"], x["repo"], x["login"]))

        lines = []
        lines.append("=" * 70)
        lines.append("人才流动时间线（按时间顺序）")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"说明：按月列出{self._scope_label()}离开事件及流向。")
        lines.append("")

        current_month = None
        month_leave_count = 0
        month_with_flow_count = 0

        for evt in events:
            m = evt["month"]
            if m != current_month:
                if current_month is not None:
                    lines.append("")
                    lines.append(f"  【{current_month} 汇总】{month_leave_count} 人离开，"
                                f"其中 {month_with_flow_count} 人有跨 repo 流向")
                current_month = m
                month_leave_count = 0
                month_with_flow_count = 0
                lines.append(f"\n--- {m} ---")

            month_leave_count += 1
            flow_str = ""
            if evt["flowed_to"]:
                month_with_flow_count += 1
                dests = [f"{d['repo']}({d['first_month']})" for d in evt["flowed_to"][:3]]
                flow_str = " → " + ", ".join(dests)
                if len(evt["flowed_to"]) > 3:
                    flow_str += f" 等{len(evt['flowed_to'])}项"
            lines.append(f"  {evt['login']} 离开 {evt['repo']}（任期{evt['tenure']}月）{flow_str}")

        if current_month is not None:
            lines.append("")
            lines.append(f"  【{current_month} 汇总】{month_leave_count} 人离开，"
                        f"其中 {month_with_flow_count} 人有跨 repo 流向")

        lines.append("")
        lines.append("=" * 70)
        lines.append("按月流动量统计")
        lines.append("=" * 70)
        month_totals: Dict[str, int] = defaultdict(int)
        month_with_flow: Dict[str, int] = defaultdict(int)
        for evt in events:
            month_totals[evt["month"]] += 1
            if evt["flowed_to"]:
                month_with_flow[evt["month"]] += 1
        for m in sorted(month_totals.keys()):
            lines.append(f"  {m}: 共 {month_totals[m]} 人离开，{month_with_flow[m]} 人有流向")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"流动时间线已保存: {report_path}")

    def _save_repo_trend_report(self) -> None:
        """统计 repo 流行趋势（按时间维度的活跃度变化）"""
        report_path = self.output_dir / "repo_trend.txt"
        data = getattr(self, "_trend_data", None) or self._load_burnout_data()

        # 提取每个 repo 的月度序列
        repo_series: Dict[str, List[Dict]] = {}
        for repo_name, repo_data in data.items():
            metrics = repo_data.get("metrics", [])
            if not metrics:
                continue
            sorted_m = sorted(metrics, key=lambda x: x.get("month", ""))
            repo_series[repo_name] = [
                {
                    "month": m.get("month", ""),
                    "unique_actors": m.get("unique_actors", 0),
                    "total_events": m.get("total_events", 0),
                    "core_count": len(m.get("core_actors", [])),
                }
                for m in sorted_m
            ]

        def _trend_score(series: List[Dict]) -> Tuple[float, str]:
            """计算趋势：前半段 vs 后半段均值比较，返回 (得分, 趋势描述)"""
            if len(series) < 4:
                return 0.0, "数据不足"
            n = len(series)
            mid = n // 2
            early = series[:mid]
            late = series[mid:]
            early_actors = sum(s["unique_actors"] for s in early) / len(early)
            late_actors = sum(s["unique_actors"] for s in late) / len(late)
            early_events = sum(s["total_events"] for s in early) / len(early)
            late_events = sum(s["total_events"] for s in late) / len(late)
            if early_actors <= 0:
                pct_actors = 1.0 if late_actors > 0 else 0.0
            else:
                pct_actors = (late_actors - early_actors) / early_actors
            if early_events <= 0:
                pct_events = 1.0 if late_events > 0 else 0.0
            else:
                pct_events = (late_events - early_events) / early_events
            score = 0.5 * pct_actors + 0.5 * pct_events
            if score > 0.2:
                desc = "上升"
            elif score < -0.2:
                desc = "下降"
            else:
                desc = "平稳"
            return score, desc

        trends = []
        for repo_name, series in repo_series.items():
            score, desc = _trend_score(series)
            first = series[0]
            last = series[-1]
            trends.append({
                "repo": repo_name,
                "score": score,
                "desc": desc,
                "start_month": first["month"],
                "end_month": last["month"],
                "start_actors": first["unique_actors"],
                "end_actors": last["unique_actors"],
                "start_events": first["total_events"],
                "end_events": last["total_events"],
                "months": len(series),
            })

        trends.sort(key=lambda x: -x["score"])

        lines = []
        lines.append("=" * 70)
        lines.append("Repo 流行趋势")
        lines.append("=" * 70)
        lines.append("")
        lines.append("说明：比较各 repo 前半段与后半段的活跃度（参与者数、事件数），判断趋势。")
        lines.append("趋势：上升 = 后半段明显增长，下降 = 后半段明显减少，平稳 = 变化不大。")
        lines.append("")

        lines.append("【上升趋势】")
        for t in [x for x in trends if x["desc"] == "上升"][:25]:
            lines.append(f"  {t['repo']}")
            lines.append(f"    {t['start_month']} ~ {t['end_month']}: "
                        f"参与者 {t['start_actors']}→{t['end_actors']}, "
                        f"事件 {t['start_events']}→{t['end_events']}")

        lines.append("")
        lines.append("【下降趋势】")
        for t in [x for x in trends if x["desc"] == "下降"][:25]:
            lines.append(f"  {t['repo']}")
            lines.append(f"    {t['start_month']} ~ {t['end_month']}: "
                        f"参与者 {t['start_actors']}→{t['end_actors']}, "
                        f"事件 {t['start_events']}→{t['end_events']}")

        lines.append("")
        lines.append("【平稳】")
        for t in [x for x in trends if x["desc"] == "平稳"][:15]:
            lines.append(f"  {t['repo']} ({t['start_month']}~{t['end_month']})")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"Repo 流行趋势已保存: {report_path}")

    def _save_cross_repo_flow_report(self, results: Dict[str, Any]) -> None:
        """保存跨 repo 流向专题报告"""
        report_path = self.output_dir / "cross_repo_flow.txt"
        lines = []
        lines.append("=" * 70)
        lines.append("跨 Repo 流向报告")
        lines.append("=" * 70)
        lines.append("")
        label = self._scope_label()
        lines.append(f"【「离开」含义】某月不再处于该 repo {label}名单，不表示完全不参与项目。")
        lines.append("")
        lines.append("【流向】离开 A 后，若在 12 个月内于 B/C 等参与（scope=all）或成为核心（scope=core），则记为流向。")
        lines.append("【注】部分账号为 bot（如 github-actions[bot]），会同时出现在多项目中。")
        lines.append("")

        # 收集有流向的关键流失
        flows: List[Dict] = []
        for repo_name, repo_result in results.items():
            if "error" in repo_result:
                continue
            for c in repo_result.get("critical_departures", []):
                ft = c.get("flowed_to", [])
                if ft:
                    flows.append({
                        "login": c["login"],
                        "from_repo": repo_name,
                        "leave_month": c["month"],
                        "tenure": c["tenure_months"],
                        "flowed_to": ft,
                    })

        flows.sort(key=lambda x: -len(x["flowed_to"]))

        lines.append(f"有流向记录的关键流失: {len(flows)} 人")
        lines.append("")
        for f in flows[:50]:
            dests = ", ".join(f"{d['repo']}({d['first_month']})" for d in f["flowed_to"][:5])
            if len(f["flowed_to"]) > 5:
                dests += f" 等{len(f['flowed_to'])}项"
            lines.append(f"  {f['login']}: {f['from_repo']} ({f['leave_month']}, 任期{f['tenure']}月)")
            lines.append(f"    → {dests}")
            lines.append("")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"跨 repo 流向报告已保存: {report_path}")

    def _save_summary_report(self, results: Dict[str, Any]) -> None:
        """保存简要文本报告"""
        report_path = self.output_dir / "summary_report.txt"
        lines = []
        lines.append("=" * 70)
        lines.append(f"人员流动分析报告 - {self._scope_label()}摘要")
        lines.append("=" * 70)
        lines.append("")
        lines.append("【概念说明】")
        label = self._scope_label()
        lines.append(f"  「离开」= 某月不再处于该 repo 的{label}名单。")
        if self.scope == "core":
            lines.append("  核心成员由「加权贡献量+网络位置」动态计算，每月选出贡献约前 50% 者。")
        lines.append("  离开 ≠ 完全不参与，可能是：参与减少、完全退出、或角色变化。")
        lines.append("")
        lines.append("【其他报告】")
        lines.append("  leave_events_detail.txt  - 全部流失明细")
        lines.append("  flow_statistics.txt      - Repo→Repo 流向统计（整体排序）")
        lines.append("  flow_by_year.txt         - 按年统计流向 + 流入最多的目标 Repo 排名")
        lines.append("  flow_timeline.txt        - 人才流动时间线（按时间顺序）")
        lines.append("  repo_trend.txt           - Repo 流行趋势（上升/下降/平稳）")
        lines.append("")

        # 按关键流失数排序
        repos_with_data = [
            (r, d) for r, d in results.items()
            if "error" not in d and isinstance(d, dict)
        ]
        repos_with_data.sort(
            key=lambda x: x[1].get("summary", {}).get("critical_departures", 0),
            reverse=True,
        )

        for repo_name, repo_result in repos_with_data[:30]:
            summary = repo_result.get("summary", {})
            period = repo_result.get("period", {})
            lines.append(f"\n【{repo_name}】")
            lines.append(f"  分析周期: {period.get('start', '')} ~ {period.get('end', '')} ({period.get('months', 0)} 月)")
            lines.append(f"  {label}数: {summary.get('unique_core_members', 0)}")
            lines.append(f"  流入事件: {summary.get('total_join_events', 0)}  流出事件: {summary.get('total_leave_events', 0)}")
            lines.append(f"  平均任期: {summary.get('avg_tenure_months', 0)} 月")
            lines.append(f"  关键流失(任期≥6月): {summary.get('critical_departures', 0)}")

            critical = repo_result.get("critical_departures", [])[:5]
            if critical:
                lines.append("  关键流失明细（含跨 repo 流向）:")
                for c in critical:
                    flow = c.get("flowed_to", [])
                    flow_str = ""
                    if flow:
                        flow_str = " → 流向: " + ", ".join(
                            f"{f['repo']}({f['first_month']})" for f in flow[:3]
                        )
                        if len(flow) > 3:
                            flow_str += f" 等{len(flow)}项"
                    lines.append(f"    - {c['login']} 于 {c['month']} 离开，任期 {c['tenure_months']} 月{flow_str}")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"摘要报告已保存: {report_path}")

    def _save_yearly_status_report(self, results: Dict[str, Any]) -> None:
        """按年分析项目状态（磁铁/基础设施等）"""
        report_path = self.output_dir / "repo_yearly_status.txt"
        
        # 1. 构建每年的流动数据
        # year_stats[year][repo] = {"in": 0, "out": 0}
        year_stats: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"in": 0, "out": 0}))

        for repo_name, repo_result in results.items():
            if "error" in repo_result:
                continue
            
            # 统计流出
            for evt in repo_result.get("leave_events", []):
                month = evt.get("month", "")
                year = month[:4] if len(month) >= 4 else "Unknown"
                if year == "Unknown": continue

                for dest in evt.get("flowed_to", []):
                    to_repo = dest["repo"]
                    # 只有当目标在我们的分析范围内时才计入（确保闭环）
                    if to_repo in results:
                        year_stats[year][repo_name]["out"] += 1
                        year_stats[year][to_repo]["in"] += 1

        years = sorted(year_stats.keys())
        lines = []
        lines.append("=" * 80)
        lines.append("项目年度流动状态分析")
        lines.append("=" * 80)
        lines.append("说明：")
        lines.append("- 磁铁型 (Magnet): 净流入比 > 15% (且总流动 > 5)")
        lines.append("- 输血型 (Feeder): 净流出比 < -15% (且总流动 > 5)")
        lines.append("- 平衡型 (Balanced): 介于两者之间")
        lines.append("- 沉寂型 (Quiet): 总流动 ≤ 5")
        lines.append("")

        for year in years:
            lines.append(f"\n[ {year} 年度状态 ]")
            lines.append("-" * 80)
            
            # 分类存储
            magnets = []
            feeders = []
            balanced = []
            quiet = []

            stats_map = year_stats[year]
            # 确保我们要分析的所有 repo 都在 stats_map 里（即使没有流动记为0）
            current_repos = sorted(results.keys())
            
            for repo in current_repos:
                s = stats_map.get(repo, {"in": 0, "out": 0})
                i, o = s["in"], s["out"]
                net = i - o
                total = i + o
                ratio = net / total if total > 0 else 0

                item = (repo, i, o, net, ratio, total) # 增加 total

                if total <= 5:
                    quiet.append(item)
                elif ratio > 0.15:
                    magnets.append(item)
                elif ratio < -0.15:
                    feeders.append(item)
                else:
                    balanced.append(item)

            # 排序逻辑：磁铁按净流入降序，输血按净流出升序（负最多）
            magnets.sort(key=lambda x: -x[4])
            feeders.sort(key=lambda x: x[4])
            balanced.sort(key=lambda x: -x[5]) # 平衡型按总活跃度
            quiet.sort(key=lambda x: -x[5]) # 沉寂型按总活跃度

            if magnets:
                lines.append("  🚀 磁铁型 (吸纳人才):")
                for r, i, o, n, rat, t in magnets: # 显示全部
                    lines.append(f"    {r:<30} : 净增 {rat:+.1%} (净{n:+d} | 入{i}/出{o})")
            
            if feeders:
                lines.append("\n  🌱 输血型 (人才输出):")
                for r, i, o, n, rat, t in feeders: # 显示全部
                    lines.append(f"    {r:<30} : 净流 {rat:+.1%} (净{n:+d} | 入{i}/出{o})")

            if balanced:
                lines.append("\n  ⚖️ 平衡型 (流动稳定):")
                for r, i, o, n, rat, t in balanced: # 显示全部
                    lines.append(f"    {r:<30} : 净 {rat:+.1%} (入{i}/出{o})")

            if quiet:
                lines.append("\n  💤 沉寂型 (流动极少 ≤ 5):")
                # 沉寂型可以折叠显示，或者只列名字，避免太长
                # 按每行3个显示
                quiet_repos = [r for r, _, _, _, _, _ in quiet]
                for k in range(0, len(quiet_repos), 3):
                    chunk = quiet_repos[k:k+3]
                    lines.append("    " + "  ,  ".join(chunk))

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"年度状态分析已保存: {report_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="人员流动分析")
    parser.add_argument(
        "--input",
        type=str,
        default="output/burnout-analysis/full_analysis.json",
        help="倦怠分析结果文件",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="输出目录（默认：personnel-flow 或 personnel-flow-all）",
    )
    parser.add_argument(
        "--scope",
        type=str,
        choices=["core", "all"],
        default="core",
        help="分析范围：core=核心成员，all=全部贡献者（需 --graphs-dir）",
    )
    parser.add_argument(
        "--graphs-dir",
        type=str,
        default=None,
        help="月度图目录（scope=all 时必填，需与 burnout 分析使用的图一致）",
    )
    parser.add_argument(
        "--flow-months",
        type=int,
        default=12,
        help="离开后追踪流向的月数 (默认: 12)"
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    if output_dir is None:
        output_dir = "output/personnel-flow-all/" if args.scope == "all" else "output/personnel-flow/"

    if args.scope == "all" and not args.graphs_dir:
        parser.error("scope=all 时必须指定 --graphs-dir")

    analyzer = PersonnelFlowAnalyzer(
        input_path=args.input,
        output_dir=output_dir,
        scope=args.scope,
        graphs_dir=args.graphs_dir,
    )
    analyzer.run(flow_months_after=args.flow_months)


if __name__ == "__main__":
    main()
