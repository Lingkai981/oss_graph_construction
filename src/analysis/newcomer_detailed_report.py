"""
Newcomer / Core-evolution 详细报告生成器（优化版）

基于 newcomer_analyzer 输出结构（output/newcomer-analysis/full_analysis.json）生成面向阅读者的可解释报告。

本版本在原有基础上新增：
1) 每个项目显示“总得分”（四个三层分析 total_score 之和）
2) 每个项目显示“预警等级”（参考 README.md 风险等级划分逻辑）
3) 若单项三层得分 > 15（严格大于），则单独给出问题来源说明（可解释提示）

用法示例：
python -m src.analysis.newcomer_detailed_report_optimized --top 10
python -m src.analysis.newcomer_detailed_report_optimized --repo "kubernetes/kubernetes"
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime


# -----------------------------
# Format helpers
# -----------------------------
def _fmt(v: Any, default: str = "N/A", ndigits: int = 4) -> str:
    if v is None:
        return default
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:.{ndigits}f}"
    return str(v)


def _fmt_pct(v: Any, default: str = "N/A", ndigits: int = 2) -> str:
    if v is None:
        return default
    try:
        return f"{float(v) * 100:.{ndigits}f}%"
    except Exception:
        return default


# -----------------------------
# Scoring & warning level
# -----------------------------
_THREE_LAYER_KEYS = [
    "newcomer_distance",
    "periphery_to_core_monthly",
    "unreachable_to_all_core_rate",
    "unreachable_to_any_core_rate",
]


def compute_total_score(repo_data: Dict[str, Any]) -> float:
    """四个三层分析 total_score 之和（缺失项按 0 计）。"""
    three = repo_data.get("three_layer_analysis", {}) or {}
    total = 0.0
    for k in _THREE_LAYER_KEYS:
        total += float((three.get(k, {}) or {}).get("total_score") or 0.0)
    return total


def warning_level(total_score: float) -> Tuple[str, str]:
    """参考 README.md 的风险等级划分逻辑。"""
    # README: ≥60 high, 40-59 medium, 20-39 low, <20 healthy
    if total_score >= 60:
        return "🔴", "high"
    if total_score >= 40:
        return "🟠", "medium"
    if total_score >= 20:
        return "🟡", "low"
    return "🟢", "healthy"


def flagged_issues(repo_data: Dict[str, Any], threshold: float = 15.0) -> List[Tuple[str, float, str]]:
    """返回单项 total_score > threshold 的问题说明列表：[(key, score, message), ...]."""
    three = repo_data.get("three_layer_analysis", {}) or {}

    explanations = {
        "newcomer_distance": "新人和核心贡献者联系不够紧密",
        "periphery_to_core_monthly": "新人需要较长时间才能成为核心",
        # 对可达性两项，给出同一类解释并标明口径
        "unreachable_to_all_core_rate": "新人和核心贡献者之间可达性断裂（与所有 core 不可达）",
        "unreachable_to_any_core_rate": "新人和核心贡献者之间可达性断裂（与至少一个 core 不可达）",
    }

    out: List[Tuple[str, float, str]] = []
    for k in _THREE_LAYER_KEYS:
        score = float((three.get(k, {}) or {}).get("total_score") or 0.0)
        if score > threshold:
            out.append((k, score, explanations.get(k, k)))
    # 按严重程度从高到低
    out.sort(key=lambda x: x[1], reverse=True)
    return out


# -----------------------------
# Report blocks
# -----------------------------
def _fmt_score_block(name: str, three_layer: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    if not three_layer:
        lines.append(f"   ⚪ {name}: 无三层分析数据")
        return lines

    n_points = three_layer.get("n_points", 0)
    total = three_layer.get("total_score", 0.0)

    trend = three_layer.get("trend", {})
    recent = three_layer.get("recent", {})
    stability = three_layer.get("stability", {})

    lines.append(f"   【{name}】")
    lines.append(f"      数据点数: {n_points}")
    lines.append(f"      三层总分: {_fmt(total, ndigits=4)} / 25")
    lines.append(
        f"      📉 长期趋势: slope={_fmt(trend.get('slope'), ndigits=6)}  score={_fmt(trend.get('score'), ndigits=4)}"
    )
    lines.append(
        f"      📅 近期状态: early_avg={_fmt(recent.get('early_avg'))}  recent_avg={_fmt(recent.get('recent_avg'))}  "
        f"change={_fmt(recent.get('change'), ndigits=6)}  score={_fmt(recent.get('score'), ndigits=4)}"
    )
    lines.append(
        f"      📊 稳定性: volatility={_fmt(stability.get('volatility'), ndigits=6)}  "
        f"threshold={_fmt(stability.get('threshold'), ndigits=3)}  score={_fmt(stability.get('score'), ndigits=4)}"
    )
    return lines


def _compute_health_score(repo_data: Dict[str, Any]) -> float:
    """计算健康分 (100 - total_risk)"""
    three = repo_data.get("three_layer_analysis", {}) or {}
    risk_scores = [
        (three.get("newcomer_distance", {}) or {}).get("total_score", 0),
        (three.get("periphery_to_core_monthly", {}) or {}).get("total_score", 0),
        (three.get("unreachable_to_all_core_rate", {}) or {}).get("total_score", 0),
        (three.get("unreachable_to_any_core_rate", {}) or {}).get("total_score", 0),
    ]
    return max(0.0, 100.0 - sum(risk_scores))


def generate_summary_table(repos_ranked: List[Tuple[str, float]], all_data: Dict[str, Any]) -> str:
    """生成汇总排名表"""
    lines = []
    lines.append("-" * 90)
    lines.append("🏆 项目新人友好度总排名 (分数越高越好)")
    lines.append("-" * 90)
    lines.append(f"{'排名':<6} {'项目名称':<40} {'健康分':>10}")
    lines.append("-" * 90)

    for idx, (repo, score) in enumerate(repos_ranked, 1):
        lines.append(f"{idx:<6} {repo:<40} {score:>10.2f}")

    lines.append("-" * 90)
    lines.append("")
    return "\n".join(lines)


def generate_repo_report(repo_name: str, repo_data: Dict[str, Any]) -> str:
    """生成单个项目的详细报告"""
    # 提取数据
    newcomer = repo_data.get("newcomer_distance", {}) or {}
    p2c = repo_data.get("periphery_to_core", {}) or {}
    reach = repo_data.get("core_reachability", {}) or {}
    three = repo_data.get("three_layer_analysis", {}) or {}

    reach_overall = reach.get("overall", {}) or {}

    # 计算分数
    health_score = _compute_health_score(repo_data)

    # 预警等级
    warning_level = "low"
    if health_score < 60:
        warning_level = "high"
    elif health_score < 80:
        warning_level = "medium"

    level_icons = {
        "low": "🟢 优秀 (Low Risk)",
        "medium": "🟡 良好 (Medium Risk)",
        "high": "🔴 需关注 (High Risk)"
    }

    lines = []
    lines.append("=" * 90)
    lines.append(f"📊 项目: {repo_name}")
    lines.append("=" * 90)
    lines.append(f"⭐ 新人友好度健康分: {health_score:.4f} / 100")
    lines.append(f"   等级: {level_icons.get(warning_level)}")

    # 异常说明 (Risk > 10)
    abnormalities = []
    keys_map = {
        "newcomer_distance": "新人需要较长时间才能成为核心(距离远)",
        "periphery_to_core_monthly": "新人晋升核心耗时变长",
        "unreachable_to_all_core_rate": "新人无法接触任何核心成员(完全断裂)",
        "unreachable_to_any_core_rate": "新人难以接触部分核心成员(部分断裂)"
    }

    for key, desc in keys_map.items():
        score = (three.get(key, {}) or {}).get("total_score", 0)
        if score > 10:
             abnormalities.append(f"   - {desc} (风险扣分: {score:.4f})")
             
    if abnormalities:
        lines.append(f"⚠️ 主要风险点:")
        for a in abnormalities:
            lines.append(a)

    lines.append("")
    lines.append("🎯 核心指标概览")
    lines.append(f"   ① 新人到核心平均步长: {_fmt(newcomer.get('overall_avg_shortest_path_to_core'))}")
    lines.append(f"   ② 晋升核心平均耗时: {_fmt(p2c.get('average_months_to_core'))} 个月")
    lines.append(f"   ③ 核心成员不可达比例:")
    lines.append(f"      - 与所有 Core 不可达: {_fmt_pct(reach_overall.get('overall_unreachable_to_all_core_rate'))}")
    lines.append(f"      - 与任一 Core 不可达: {_fmt_pct(reach_overall.get('overall_unreachable_to_any_core_rate'))}")

    # ---- 三层分析 ----
    lines.append("\n" + "-" * 90)
    lines.append("📈 三层分析详情 (Trend / Recent / Stability) - 扣分制(分数越低越好)")
    lines.append("-" * 90)

    def _print_three(title, key):
        tdata = three.get(key, {}) or {}
        n = tdata.get("n_points", 0)
        total = tdata.get("total_score", 0.0)
        trend = tdata.get("trend", {})
        recent = tdata.get("recent", {})
        stability = tdata.get("stability", {})

        lines.append(f"   【{title}】")
        lines.append(f"      数据点数: {n}")
        lines.append(f"      风险扣分: {total:.4f} / 25")

        # Trend
        slope = trend.get("slope", 0)
        t_score = trend.get("score", 0)
        icon = "📉" if slope > 0 else "📈"  # growth is bad here
        lines.append(f"      {icon} 长期趋势: slope={slope:.6f}  score={t_score:.4f}")

        # Recent
        e_avg = recent.get("early_avg", 0)
        r_avg = recent.get("recent_avg", 0)
        change = recent.get("change", 0)
        r_score = recent.get("score", 0)
        lines.append(f"      📅 近期状态: early={e_avg:.4f}  recent={r_avg:.4f}  change={change:.6f}  score={r_score:.4f}")

        # Stability
        vol = stability.get("volatility", 0)
        s_score = stability.get("score", 0)
        lines.append(f"      📊 稳定性: volatility={vol:.6f}  score={s_score:.4f}")

    _print_three("新人到核心平均步长", "newcomer_distance")
    _print_three("晋升核心耗时", "periphery_to_core_monthly")
    _print_three("与所有 Core 不可达比例", "unreachable_to_all_core_rate")
    _print_three("与任一 Core 不可达比例", "unreachable_to_any_core_rate")

    lines.append("")
    lines.append("-" * 90)
    lines.append("📅 月度趋势表")
    lines.append("-" * 90)
    lines.append(f"   {'月份':<16} {'新人数':<10} {'新人步长':<10} {'新晋核':<10} {'晋核耗时':<12} {'all不可达':<12} {'any不可达':<12}")
    lines.append("   " + "-" * 86)

    # Merge monthly data
    # newcomer_distance.monthly_summary
    # periphery_to_core.monthly_summary
    # core_reachability.monthly_summary

    nm_map = {m["month"]: m for m in newcomer.get("monthly_summary", [])}
    pc_map = {m["month"]: m for m in p2c.get("monthly_summary", [])}
    cr_map = {m["month"]: m for m in reach.get("monthly_summary", [])}

    all_months = sorted(set(nm_map.keys()) | set(pc_map.keys()) | set(cr_map.keys()))

    for mon in all_months:
        nm = nm_map.get(mon, {})
        pc = pc_map.get(mon, {})
        cr = cr_map.get(mon, {})

        c0 = _fmt(nm.get("newcomers", 0))
        c1 = _fmt(nm.get("avg_shortest_path_to_core"), "N/A")
        c2 = _fmt(pc.get("new_core_count", 0))
        c3 = _fmt(pc.get("avg_months_to_core"), "N/A")
        c4 = _fmt_pct(cr.get("unreachable_to_all_core_rate"), "N/A")
        c5 = _fmt_pct(cr.get("unreachable_to_any_core_rate"), "N/A")

        lines.append(f"   {mon:<16} {c0:<10} {c1:<10} {c2:<10} {c3:<12} {c4:<12} {c5:<12}")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Newcomer / Core-evolution 详细报告生成器")
    parser.add_argument(
        "--input",
        type=str,
        default="output/newcomer-analysis/full_analysis.json",
        help="输入分析文件路径",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/newcomer-analysis/detailed_report.txt",
        help="输出报告文件路径",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="只分析指定的仓库",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="只输出前 N 个项目",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 文件不存在: {input_path}")
        return

    print(f"📖 读取分析数据: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    repos_to_analyze = list(data.keys())

    if args.repo:
        specified = [r.strip() for r in args.repo.split(",") if r.strip()]
        repos_to_analyze = [r for r in repos_to_analyze if r in specified]

    # 计算分数并排序
    repos_ranked: List[Tuple[str, float]] = []
    for repo in repos_to_analyze:
        score = _compute_health_score(data[repo])
        repos_ranked.append((repo, score))

    # 从大到小排序 (越大约好)
    repos_ranked.sort(key=lambda x: x[1], reverse=True)

    if args.top is not None:
        repos_ranked = repos_ranked[: args.top]

    if not repos_ranked:
        print("❌ 没有符合条件的项目")
        return

    # 生成报告
    reports: List[str] = []
    reports.append("=" * 90)
    reports.append("🔍 OSS 项目新人体验与核心晋升分析报告")
    reports.append("=" * 90)
    reports.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    reports.append(f"分析项目数: {len(repos_ranked)}")
    reports.append("")

    # 1. 插入总览表
    reports.append(generate_summary_table(repos_ranked, data))

    # 2. 详细报告
    for repo, _ in repos_ranked:
        reports.append(generate_repo_report(repo, data[repo]))

    full_report = "\n".join(reports)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_report)

    print(f"✅ 报告已保存: {output_path}")

    # 控制台预览
    if len(repos_ranked) <= 3:
        print("\n" + full_report)
    else:
        print("\n📋 前 3 个项目预览:\n")
        for repo, _ in repos_ranked[:3]:
            print(generate_repo_report(repo, data[repo]))


if __name__ == "__main__":
    main()
