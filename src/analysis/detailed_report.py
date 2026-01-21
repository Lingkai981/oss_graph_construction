"""
详细倦怠分析报告生成器

按项目输出每一项得分的来源和数值变化
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Callable


def generate_repo_report(repo_name: str, repo_data: Dict[str, Any]) -> str:
    """生成单个仓库的详细报告"""
    lines = []
    lines.append("=" * 80)
    lines.append(f"📊 项目: {repo_name}")
    lines.append("=" * 80)
    
    # 获取倦怠评分
    burnout = repo_data.get("burnout_score", {})
    score = burnout.get("score", 0)
    level = burnout.get("level", "unknown")
    period = burnout.get("period", "N/A")
    months = burnout.get("months_analyzed", 0)
    
    # 风险等级图标
    level_icons = {
        "high": "🔴 高风险",
        "medium": "🟠 中风险", 
        "low": "🟡 低风险",
        "healthy": "🟢 健康",
        "unknown": "⚪ 未知"
    }
    
    lines.append(f"\n🎯 综合倦怠评分: {score:.2f} / 100")
    lines.append(f"   风险等级: {level_icons.get(level, level)}")
    lines.append(f"   分析周期: {period} ({months} 个月)")
    
    # 获取指标时间序列
    metrics = repo_data.get("metrics", [])
    if len(metrics) < 2:
        lines.append("\n⚠️ 数据不足，无法进行趋势分析")
        return "\n".join(lines)
    
    # 按月份排序
    sorted_metrics = sorted(metrics, key=lambda m: m.get("month", ""))
    earliest = sorted_metrics[0]
    latest = sorted_metrics[-1]
    
    lines.append("\n" + "-" * 80)
    lines.append("📈 各因子详细分析（三层架构：长期趋势40% + 近期状态40% + 稳定性20%）")
    lines.append("-" * 80)
    
    factors = burnout.get("factors", {})
    
    def format_dimension(name: str, dim_data: Dict, early_val: float, late_val: float, unit: str = ""):
        """格式化单个维度的分析"""
        dim_lines = []
        score = dim_data.get("score", 0)
        
        # 长期趋势
        trend = dim_data.get("long_term_trend", {})
        slope_pct = trend.get("slope_percent_per_month", 0)
        trend_score = trend.get("score", 0)
        
        # 近期状态
        recent = dim_data.get("recent_state", {})
        early_avg = recent.get("early_avg", 0)
        recent_avg = recent.get("recent_avg", 0)
        change_pct = recent.get("change_percent", 0)
        recent_score = recent.get("score", 0)
        
        # 稳定性
        stability = dim_data.get("stability", {})
        volatility_pct = stability.get("volatility_percent", 0)
        stability_score = stability.get("score", 0)
        
        dim_lines.append(f"   📊 数据概览:")
        dim_lines.append(f"      首月: {early_val:.2f}{unit}  →  末月: {late_val:.2f}{unit}")
        
        dim_lines.append(f"   📉 长期趋势 (40%权重):")
        dim_lines.append(f"      线性回归斜率: {slope_pct:+.2f}%/月")
        if slope_pct < 0:
            dim_lines.append(f"      ⚠️ 每月平均下降 {abs(slope_pct):.1f}%")
        else:
            dim_lines.append(f"      ✅ 每月平均增长 {slope_pct:.1f}%")
        dim_lines.append(f"      → 趋势得分: {trend_score:.2f}")
        
        dim_lines.append(f"   📅 近期状态 (40%权重):")
        dim_lines.append(f"      早期3月均值: {early_avg:.2f}  →  近期3月均值: {recent_avg:.2f}")
        dim_lines.append(f"      变化率: {change_pct:+.1f}%")
        dim_lines.append(f"      → 近期得分: {recent_score:.2f}")
        
        dim_lines.append(f"   📊 稳定性 (20%权重):")
        dim_lines.append(f"      月度波动率: {volatility_pct:.1f}%")
        if volatility_pct > 30:
            dim_lines.append(f"      ⚠️ 波动较大 (>30%)")
        else:
            dim_lines.append(f"      ✅ 波动可控 (≤30%)")
        dim_lines.append(f"      → 稳定性扣分: {stability_score:.2f}")
        
        dim_lines.append(f"   ➡️ 维度总分: {score:.2f} / 25")
        
        return dim_lines
    
    # 1. 活跃度
    lines.append("\n【1. 活跃度】(0-25分)")
    activity = factors.get("activity", {})
    early_events = earliest.get("total_events", 0)
    late_events = latest.get("total_events", 0)
    lines.extend(format_dimension("活跃度", activity, early_events, late_events, " 事件"))
    
    # 2. 贡献者
    lines.append("\n【2. 贡献者】(0-25分)")
    contributors = factors.get("contributors", {})
    early_actors = earliest.get("unique_actors", earliest.get("node_count", 0))
    late_actors = latest.get("unique_actors", latest.get("node_count", 0))
    lines.extend(format_dimension("贡献者", contributors, early_actors, late_actors, " 人"))
    
    # 3. 核心成员稳定性
    lines.append("\n【3. 核心成员稳定性】(0-25分)")
    core_stability = factors.get("core_stability", {})
    early_core_count = core_stability.get("early_core_count", 0)
    late_core_count = core_stability.get("latest_core_count", 0)
    final_retention = core_stability.get("final_retention", 1)
    retained = core_stability.get("retained_count", 0)
    
    # 获取核心成员名单
    early_core_actors = earliest.get("core_actors", [])[:5]
    late_core_actors = latest.get("core_actors", [])[:5]
    
    lines.append(f"   📊 数据概览:")
    lines.append(f"      首月核心成员: {early_core_count} 人")
    if early_core_actors:
        names = [a[0] if isinstance(a, (list, tuple)) else a for a in early_core_actors]
        lines.append(f"         └─ {', '.join(names[:5])}")
    lines.append(f"      末月核心成员: {late_core_count} 人")
    if late_core_actors:
        names = [a[0] if isinstance(a, (list, tuple)) else a for a in late_core_actors]
        lines.append(f"         └─ {', '.join(names[:5])}")
    lines.append(f"      最终留存: {retained}/{early_core_count} 人 ({final_retention:.1%})")
    
    # 三层分析
    trend = core_stability.get("long_term_trend", {})
    recent = core_stability.get("recent_state", {})
    stability = core_stability.get("stability", {})
    
    lines.append(f"   📉 长期趋势 (40%权重):")
    lines.append(f"      流失率斜率: {trend.get('slope_percent_per_month', 0):+.2f}%/月")
    lines.append(f"      → 趋势得分: {trend.get('score', 0):.2f}")
    
    lines.append(f"   📅 近期状态 (40%权重):")
    lines.append(f"      早期流失率: {recent.get('early_avg', 0)*100:.1f}%  →  近期流失率: {recent.get('recent_avg', 0)*100:.1f}%")
    lines.append(f"      → 近期得分: {recent.get('score', 0):.2f}")
    
    lines.append(f"   📊 稳定性 (20%权重):")
    lines.append(f"      月度波动率: {stability.get('volatility_percent', 0):.1f}%")
    lines.append(f"      → 稳定性扣分: {stability.get('score', 0):.2f}")
    
    lines.append(f"   ➡️ 维度总分: {core_stability.get('score', 0):.2f} / 25")
    
    # 4. 协作密度
    lines.append("\n【4. 协作密度】(0-25分)")
    collaboration = factors.get("collaboration", {})
    early_density = earliest.get("density", 0)
    late_density = latest.get("density", 0)
    lines.extend(format_dimension("协作密度", collaboration, early_density, late_density, ""))
    
    # 汇总
    lines.append("\n" + "-" * 80)
    lines.append("📋 评分汇总")
    lines.append("-" * 80)
    
    activity_score = factors.get("activity", {}).get("score", 0)
    contributor_score = factors.get("contributors", {}).get("score", 0)
    stability_score = factors.get("core_stability", {}).get("score", 0)
    collaboration_score = factors.get("collaboration", {}).get("score", 0)
    
    lines.append(f"   活跃度:         {activity_score:6.2f} / 25")
    lines.append(f"   贡献者:         {contributor_score:6.2f} / 25")
    lines.append(f"   核心成员稳定性: {stability_score:6.2f} / 25")
    lines.append(f"   协作密度:       {collaboration_score:6.2f} / 25")
    lines.append(f"   " + "-" * 30)
    lines.append(f"   总分:           {score:6.2f} / 100")
    
    # 显示分析方法
    method = burnout.get("analysis_method", "legacy")
    if method == "three_layer":
        lines.append(f"\n   📐 分析方法: 三层架构 (长期趋势+近期状态+稳定性)")
    
    # 预警信息
    alerts = repo_data.get("alerts", [])
    if alerts:
        lines.append("\n" + "-" * 80)
        lines.append(f"⚠️ 预警事件 ({len(alerts)} 条)")
        lines.append("-" * 80)
        
        # 按严重程度分组
        high_alerts = [a for a in alerts if a.get("severity") == "high"]
        medium_alerts = [a for a in alerts if a.get("severity") == "medium"]
        
        if high_alerts:
            lines.append(f"\n   🔴 高危预警 ({len(high_alerts)} 条):")
            for alert in high_alerts[:5]:
                lines.append(f"      [{alert.get('month')}] {alert.get('alert_type')}: {alert.get('description')}")
            if len(high_alerts) > 5:
                lines.append(f"      ... 还有 {len(high_alerts) - 5} 条")
        
        if medium_alerts:
            lines.append(f"\n   🟠 中危预警 ({len(medium_alerts)} 条):")
            for alert in medium_alerts[:5]:
                lines.append(f"      [{alert.get('month')}] {alert.get('alert_type')}: {alert.get('description')}")
            if len(medium_alerts) > 5:
                lines.append(f"      ... 还有 {len(medium_alerts) - 5} 条")
    
    # 月度趋势
    lines.append("\n" + "-" * 80)
    lines.append("📅 月度指标趋势")
    lines.append("-" * 80)
    lines.append(f"   {'月份':<10} {'事件数':>8} {'贡献者':>8} {'核心成员':>8} {'密度':>12}")
    lines.append("   " + "-" * 50)
    
    for m in sorted_metrics:
        month = m.get("month", "N/A")
        events = m.get("total_events", 0)
        actors = m.get("unique_actors", m.get("node_count", 0))
        core = m.get("core_actor_count", len(m.get("core_actors", [])))
        density = m.get("density", 0)
        lines.append(f"   {month:<10} {events:>8} {actors:>8} {core:>8} {density:>12.6f}")
    
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成详细倦怠分析报告")
    parser.add_argument(
        "--input",
        type=str,
        default="output/burnout-analysis/full_analysis.json",
        help="输入的完整分析文件路径"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/burnout-analysis/detailed_report.txt",
        help="输出报告文件路径"
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
        help="只输出倦怠评分最高的前 N 个项目"
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="只输出倦怠评分大于等于该值的项目"
    )
    
    args = parser.parse_args()
    
    # 读取分析数据
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 文件不存在: {input_path}")
        return
    
    print(f"📖 读取分析数据: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 筛选仓库
    repos_to_analyze = list(data.keys())
    
    if args.repo:
        specified_repos = [r.strip() for r in args.repo.split(",")]
        repos_to_analyze = [r for r in repos_to_analyze if r in specified_repos]
        if not repos_to_analyze:
            print(f"❌ 未找到指定的仓库: {args.repo}")
            return
    
    # 按倦怠评分排序
    repos_with_scores = []
    for repo in repos_to_analyze:
        score = data[repo].get("burnout_score", {}).get("score", 0)
        repos_with_scores.append((repo, score))
    
    repos_with_scores.sort(key=lambda x: x[1], reverse=True)
    
    # 筛选条件
    if args.min_score is not None:
        repos_with_scores = [(r, s) for r, s in repos_with_scores if s >= args.min_score]
    
    if args.top is not None:
        repos_with_scores = repos_with_scores[:args.top]
    
    if not repos_with_scores:
        print("❌ 没有符合条件的项目")
        return
    
    print(f"📊 将分析 {len(repos_with_scores)} 个项目")
    
    # 生成报告
    reports = []
    reports.append("=" * 80)
    reports.append("🔍 OSS 项目维护者倦怠详细分析报告")
    reports.append("=" * 80)
    reports.append(f"生成时间: {Path(args.input).stat().st_mtime}")
    reports.append(f"分析项目数: {len(repos_with_scores)}")
    reports.append("")
    
    for repo, score in repos_with_scores:
        report = generate_repo_report(repo, data[repo])
        reports.append(report)
    
    full_report = "\n".join(reports)
    
    # 输出到文件
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_report)
    
    print(f"✅ 报告已保存: {output_path}")
    
    # 同时输出到控制台（如果项目数少于等于3）
    if len(repos_with_scores) <= 3:
        print("\n" + full_report)
    else:
        # 只输出前3个
        print("\n📋 前 3 个高风险项目预览:\n")
        for repo, score in repos_with_scores[:3]:
            print(generate_repo_report(repo, data[repo]))


if __name__ == "__main__":
    main()
