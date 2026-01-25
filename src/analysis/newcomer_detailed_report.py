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


def generate_repo_report(repo_name: str, repo_data: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 90)
    lines.append(f"📊 项目: {repo_name}")
    lines.append("=" * 90)

    newcomer = repo_data.get("newcomer_distance", {})
    p2c = repo_data.get("periphery_to_core", {})
    reach = repo_data.get("core_reachability", {})
    three = repo_data.get("three_layer_analysis", {}) or {}

    # ---- 总得分 & 预警等级 ----
    total_score = compute_total_score(repo_data)
    icon, level = warning_level(total_score)

    lines.append(f"⭐ 总得分（四项三层总分之和）: {_fmt(total_score, ndigits=4)}")
    lines.append(f"{icon} 预警等级: {level}")

    issues = flagged_issues(repo_data, threshold=15.0)
    if issues:
        lines.append("⚠️ 单项异常说明（单项得分 > 15）:")
        for _, score, msg in issues:
            lines.append(f"   - {msg}（得分: {_fmt(score, ndigits=4)}）")
    else:
        lines.append("✅ 单项异常说明: 无（所有单项得分 ≤ 15）")

    # ---- 概览 ----
    overall_dist = newcomer.get("overall_avg_shortest_path_to_core")
    avg_months_to_core = p2c.get("average_months_to_core")
    reach_overall = reach.get("overall", {}) or {}
    unreach_all_rate = reach_overall.get("overall_unreachable_to_all_core_rate")
    unreach_any_rate = reach_overall.get("overall_unreachable_to_any_core_rate")

    lines.append("\n🎯 指标概览（项目级）")
    lines.append(f"   ① 新人到核心平均步长（overall）: {_fmt(overall_dist)}")
    lines.append(f"   ② Periphery→Core 平均耗时（月）（overall）: {_fmt(avg_months_to_core)}")
    lines.append("   ③ 不可达比例（overall）:")
    lines.append(f"      - 与所有 core 不可达: {_fmt_pct(unreach_all_rate)}")
    lines.append(f"      - 与至少一个 core 不可达: {_fmt_pct(unreach_any_rate)}")

    # ---- 三层分析 ----
    lines.append("\n" + "-" * 90)
    lines.append("📈 三层分析（长期趋势 / 近期状态 / 稳定性）")
    lines.append("-" * 90)

    lines.extend(_fmt_score_block("新人到核心平均步长", three.get("newcomer_distance", {})))
    lines.extend(_fmt_score_block("每月新晋核心的 Periphery→Core 耗时", three.get("periphery_to_core_monthly", {})))
    lines.extend(_fmt_score_block("与所有 core 不可达比例", three.get("unreachable_to_all_core_rate", {})))
    lines.extend(_fmt_score_block("与至少一个 core 不可达比例", three.get("unreachable_to_any_core_rate", {})))

    # ---- 月度趋势表 ----
    lines.append("\n" + "-" * 90)
    lines.append("📅 月度趋势（来自 newcomer_analyzer 输出的 monthly_summary）")
    lines.append("-" * 90)

    newcomer_monthly = newcomer.get("monthly_summary", []) or []
    p2c_monthly = p2c.get("monthly_summary", []) or []
    reach_monthly = reach.get("monthly_summary", []) or []

    def _index_by_month(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for it in items:
            m = it.get("month")
            if m:
                out[m] = it
        return out

    idx_new = _index_by_month(newcomer_monthly)
    idx_p2c = _index_by_month(p2c_monthly)
    idx_rch = _index_by_month(reach_monthly)

    all_months = sorted(set(idx_new.keys()) | set(idx_p2c.keys()) | set(idx_rch.keys()))
    if not all_months:
        lines.append("   ⚠️ 无月度数据")
        lines.append("")
        return "\n".join(lines)

    header = (
        f"   {'月份':<10}"
        f"{'新人数':>8} {'新人步长':>10}"
        f"{'新晋核':>8} {'晋核耗时':>10}"
        f"{'all不可达':>12} {'any不可达':>12}"
    )
    lines.append(header)
    lines.append("   " + "-" * (len(header) - 3))

    for month in all_months:
        nm = idx_new.get(month, {})
        pm = idx_p2c.get(month, {})
        rm = idx_rch.get(month, {})

        newcomers = nm.get("newcomers", 0)
        avg_dist_m = nm.get("avg_shortest_path_to_core")

        new_core_count = pm.get("new_core_count", 0)
        avg_m2c_m = pm.get("avg_months_to_core")

        all_rate = rm.get("unreachable_to_all_core_rate")
        any_rate = rm.get("unreachable_to_any_core_rate")

        lines.append(
            f"   {month:<10}"
            f"{newcomers:>8} {(_fmt(avg_dist_m, ndigits=4)):>10}"
            f"{new_core_count:>8} {(_fmt(avg_m2c_m, ndigits=4)):>10}"
            f"{(_fmt_pct(all_rate, ndigits=2)):>12} {(_fmt_pct(any_rate, ndigits=2)):>12}"
        )

    lines.append("")
    return "\n".join(lines)


# 兼容原 --top 排序逻辑：按总得分（四项三层总分之和）降序
def _compute_sort_key(repo_data: Dict[str, Any]) -> float:
    return compute_total_score(repo_data)


def main():
    parser = argparse.ArgumentParser(description="生成 Newcomer / Core-evolution 详细分析报告（优化版）")
    parser.add_argument(
        "--input",
        type=str,
        default="output/newcomer-analysis/full_analysis.json",
        help="输入的完整分析文件路径（newcomer_analyzer 输出）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/newcomer-analysis/detailed_report_optimized.txt",
        help="输出报告文件路径",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="只分析指定的仓库（可用逗号分隔多个）",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="只输出总得分最高的前 N 个项目（总得分=四项三层总分之和）",
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
        if not repos_to_analyze:
            print(f"❌ 未找到指定的仓库: {args.repo}")
            return

    repos_ranked: List[Tuple[str, float]] = []
    for repo in repos_to_analyze:
        key = _compute_sort_key(data[repo])
        repos_ranked.append((repo, key))

    repos_ranked.sort(key=lambda x: x[1], reverse=True)

    if args.top is not None:
        repos_ranked = repos_ranked[: args.top]

    if not repos_ranked:
        print("❌ 没有符合条件的项目")
        return

    # 生成报告
    reports: List[str] = []
    reports.append("=" * 90)
    reports.append("🔍 OSS 项目 Newcomer / Core-evolution 详细分析报告（优化版）")
    reports.append("=" * 90)
    reports.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    reports.append(f"分析项目数: {len(repos_ranked)}")
    reports.append("")

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
