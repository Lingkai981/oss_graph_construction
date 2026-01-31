"""
Actor-Actor 图结构指标详细报告生成器

定位类似 detailed_report.py：
- 读取 full_analysis.json（来自 actor_actor_structure_analyzer.py 的输出）
- 对每个项目输出：两项指标的数值、变化、解释，以及月度趋势表
- 支持筛选 repo / top / min-threshold 等
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


def _safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _safe_int(x, default=None):
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _pct_change(old: Optional[float], new: Optional[float]) -> Optional[float]:
    if old is None or new is None:
        return None
    if abs(old) < 1e-12:
        return None
    return (new - old) / old * 100.0


def _fmt_num(x: Optional[float], nd: int = 4) -> str:
    if x is None:
        return "N/A"
    return f"{x:.{nd}f}"


def _fmt_int(x: Optional[int]) -> str:
    if x is None:
        return "N/A"
    return str(int(x))


def _pick_latest_metrics(metrics: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not metrics:
        return None
    return sorted(metrics, key=lambda m: m.get("month", ""))[-1]


def _pick_earliest_metrics(metrics: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not metrics:
        return None
    return sorted(metrics, key=lambda m: m.get("month", ""))[0]


def _compute_repo_sort_key(
    metrics: List[Dict[str, Any]],
    sort_by: str
) -> float:
    """
    用于 --top 排序：默认按 latest 的 longest_shortest_path 降序；
    你也可以传 sort_by=avg_distance / lcc_node_count 等。
    """
    last = _pick_latest_metrics(metrics)
    if not last:
        return -1.0

    v = last.get(sort_by)
    if v is None:
        return -1.0

    try:
        return float(v)
    except Exception:
        return -1.0


def generate_repo_report(repo_name: str, repo_data: Dict[str, Any]) -> str:
    """生成单个仓库的结构指标详细报告（风格对齐 detailed_report.py）"""
    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(f"🧩 项目: {repo_name}")
    lines.append("=" * 80)

    metrics = repo_data.get("metrics", [])
    if len(metrics) < 1:
        lines.append("\n⚠️ 没有结构指标数据（可能该 repo 没有 actor-actor 图或图为空）")
        return "\n".join(lines)

    # 按月份排序
    sorted_metrics = sorted(metrics, key=lambda m: m.get("month", ""))
    earliest = sorted_metrics[0]
    latest = sorted_metrics[-1]

    # 读关键字段
    e_diam = _safe_int(earliest.get("longest_shortest_path"))
    l_diam = _safe_int(latest.get("longest_shortest_path"))

    e_avgd = _safe_float(earliest.get("average_distance"))
    l_avgd = _safe_float(latest.get("average_distance"))

    e_cc = _safe_int(earliest.get("connected_components_count"))
    l_cc = _safe_int(latest.get("connected_components_count"))

    e_lcc_n = _safe_int(earliest.get("lcc_node_count"))
    l_lcc_n = _safe_int(latest.get("lcc_node_count"))

    e_nodes = _safe_int(earliest.get("node_count"))
    l_nodes = _safe_int(latest.get("node_count"))

    e_edges = _safe_int(earliest.get("edge_count"))
    l_edges = _safe_int(latest.get("edge_count"))

    # 变化
    diam_chg = None
    if e_diam is not None and l_diam is not None and e_diam != 0:
        diam_chg = (l_diam - e_diam) / e_diam * 100.0

    avgd_chg = _pct_change(e_avgd, l_avgd)

    period = f"{earliest.get('month', 'N/A')} → {latest.get('month', 'N/A')}"
    lines.append(f"\n📅 分析周期: {period} ({len(sorted_metrics)} 个月)")

    lines.append("\n" + "-" * 80)
    lines.append("📌 图结构概览（默认：无权、无向、合并多重边；在最大连通分量 LCC 上计算距离指标）")
    lines.append("-" * 80)

    lines.append(f"   首月节点/边: {l_nodes if False else ''}")  # 占位避免编辑器提示（不会影响输出）
    lines.pop()  # 删除占位行

    lines.append(f"   首月节点数: {e_nodes}   边数: {e_edges}   连通分量数: {e_cc}   LCC节点数: {e_lcc_n}")
    lines.append(f"   末月节点数: {l_nodes}   边数: {l_edges}   连通分量数: {l_cc}   LCC节点数: {l_lcc_n}")

    # 指标解释（仿 detailed_report 的“维度解释 + 计算口径 + 直觉”）
    lines.append("\n" + "-" * 80)
    lines.append("📈 指标 1：最长的最短路径（Longest Shortest Path）")
    lines.append("-" * 80)
    lines.append("   ✅ 口径: 在最大连通分量（LCC）上计算直径（diameter）")
    lines.append("   💡 直觉: 值越大，表示协作网络越“拉长”、信息/协作跨越越多跳，整体更分散")
    lines.append(f"   首月: { _fmt_int(e_diam) }  →  末月: { _fmt_int(l_diam) }")
    if diam_chg is None:
        lines.append("   变化率: N/A（可能首月为0/缺失，或数据不足）")
    else:
        lines.append(f"   变化率: {diam_chg:+.1f}%")

    # 简单提示
    if e_diam is not None and l_diam is not None:
        if l_diam > e_diam:
            lines.append("   ⚠️ 提示: 直径变大，网络可能更分散/跨群协作成本更高")
        elif l_diam < e_diam:
            lines.append("   ✅ 提示: 直径变小，网络可能更紧凑/协作更集中")
        else:
            lines.append("   ➖ 提示: 直径保持不变")

    lines.append("\n" + "-" * 80)
    lines.append("📈 指标 2：最短到其他节点的平均距离（Average Distance）")
    lines.append("-" * 80)
    lines.append("   ✅ 口径: 在最大连通分量（LCC）上计算平均最短路径长度（average shortest path length）")
    lines.append("   💡 直觉: 值越大，任意两人平均需要更多跳才能关联，网络更疏；越小则更紧密")
    lines.append(f"   首月: { _fmt_num(e_avgd, 4) }  →  末月: { _fmt_num(l_avgd, 4) }")
    if avgd_chg is None:
        lines.append("   变化率: N/A（可能首月为0/缺失，或数据不足）")
    else:
        lines.append(f"   变化率: {avgd_chg:+.1f}%")

    if e_avgd is not None and l_avgd is not None:
        if l_avgd > e_avgd:
            lines.append("   ⚠️ 提示: 平均距离上升，网络整体更疏，协作触达可能变慢")
        elif l_avgd < e_avgd:
            lines.append("   ✅ 提示: 平均距离下降，网络更紧密，协作触达可能更快")
        else:
            lines.append("   ➖ 提示: 平均距离保持不变")

    # 月度趋势表（对齐 detailed_report 的“月度指标趋势”）
    lines.append("\n" + "-" * 80)
    lines.append("📅 月度趋势（Actor-Actor 结构指标）")
    lines.append("-" * 80)
    lines.append(f"   {'月份':<10} {'节点':>6} {'边':>6} {'CC':>4} {'LCC_N':>6} {'直径':>6} {'平均距离':>10}")
    lines.append("   " + "-" * 60)

    for m in sorted_metrics:
        month = m.get("month", "N/A")
        nodes = _safe_int(m.get("node_count"), 0)
        edges = _safe_int(m.get("edge_count"), 0)
        cc = _safe_int(m.get("connected_components_count"), 0)
        lcc_n = _safe_int(m.get("lcc_node_count"), 0)
        diam = m.get("longest_shortest_path", None)
        avgd = m.get("average_distance", None)

        diam_s = _fmt_int(_safe_int(diam))
        avgd_s = _fmt_num(_safe_float(avgd), 4)

        lines.append(f"   {month:<10} {nodes:>6} {edges:>6} {cc:>4} {lcc_n:>6} {diam_s:>6} {avgd_s:>10}")

    # notes（如果计算失败/图太小等）
    # 把每个月的 notes 汇总一下
    notes_counter: Dict[str, int] = {}
    for m in sorted_metrics:
        for note in (m.get("notes") or []):
            notes_counter[note] = notes_counter.get(note, 0) + 1
    if notes_counter:
        lines.append("\n" + "-" * 80)
        lines.append("📝 计算备注（notes 统计）")
        lines.append("-" * 80)
        for k, v in sorted(notes_counter.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"   - {k}: {v} 次")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成 Actor-Actor 图结构指标详细报告")
    parser.add_argument(
        "--input",
        type=str,
        default="output/actor-actor-structure/full_analysis.json",
        help="输入的完整结构分析文件路径（full_analysis.json）"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/actor-actor-structure/structure_detailed_report.txt",
        help="输出报告文件路径（txt）"
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="只分析指定的仓库（可用逗号分隔多个）"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="只输出排序靠前的前 N 个项目（默认按 latest longest_shortest_path 排序）"
    )
    parser.add_argument(
        "--sort-by",
        type=str,
        default="longest_shortest_path",
        help="--top 的排序字段（默认 longest_shortest_path，可选 average_distance / lcc_node_count 等）"
    )
    parser.add_argument(
        "--min-diameter",
        type=float,
        default=None,
        help="只输出 latest 直径 >= 该值 的项目"
    )
    parser.add_argument(
        "--min-avg-distance",
        type=float,
        default=None,
        help="只输出 latest 平均距离 >= 该值 的项目"
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 文件不存在: {input_path}")
        return

    print(f"📖 读取结构分析数据: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # data 结构：{repo_name: {"repo_name":..., "metrics":[...]}, ...}
    repos_to_analyze = list(data.keys())

    # repo 筛选
    if args.repo:
        specified_repos = [r.strip() for r in args.repo.split(",")]
        repos_to_analyze = [r for r in repos_to_analyze if r in specified_repos]
        if not repos_to_analyze:
            print(f"❌ 未找到指定的仓库: {args.repo}")
            return

    # 组装 (repo, sort_key, latest_diam, latest_avgd)
    repos_ranked: List[Tuple[str, float, Optional[float], Optional[float]]] = []
    for repo in repos_to_analyze:
        metrics = (data.get(repo) or {}).get("metrics", [])
        last = _pick_latest_metrics(metrics)
        if not last:
            continue

        latest_diam = _safe_float(last.get("longest_shortest_path"))
        latest_avgd = _safe_float(last.get("average_distance"))

        # threshold 筛选
        if args.min_diameter is not None:
            if latest_diam is None or latest_diam < args.min_diameter:
                continue
        if args.min_avg_distance is not None:
            if latest_avgd is None or latest_avgd < args.min_avg_distance:
                continue

        key = _compute_repo_sort_key(metrics, args.sort_by)
        repos_ranked.append((repo, key, latest_diam, latest_avgd))

    if not repos_ranked:
        print("❌ 没有符合条件的项目")
        return

    # 排序：sort_key 降序
    repos_ranked.sort(key=lambda x: x[1], reverse=True)

    # top 截断
    if args.top is not None:
        repos_ranked = repos_ranked[:args.top]

    print(f"📊 将输出 {len(repos_ranked)} 个项目的详细报告")

    # 生成报告
    reports: List[str] = []
    reports.append("=" * 80)
    reports.append("🔍 Actor-Actor 图结构指标详细分析报告")
    reports.append("=" * 80)
    reports.append(f"输入文件: {input_path}")
    reports.append(f"分析项目数: {len(repos_ranked)}")
    reports.append(f"排序字段: latest {args.sort_by} (desc)")
    reports.append("")

    for repo, _key, _d, _a in repos_ranked:
        reports.append(generate_repo_report(repo, data[repo]))

    full_report = "\n".join(reports)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_report)

    print(f"✅ 报告已保存: {output_path}")

    # 控制台预览：<=3 个项目时全量打印，否则打印前 3 个
    if len(repos_ranked) <= 3:
        print("\n" + full_report)
    else:
        print("\n📋 前 3 个项目预览:\n")
        for repo, _key, _d, _a in repos_ranked[:3]:
            print(generate_repo_report(repo, data[repo]))


if __name__ == "__main__":
    main()
