"""
Bus Factor 风险分析报告生成器

按项目输出每一项得分的来源和数值变化
"""

import json
import argparse
import sys
import io
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# 修复 Windows 控制台编码问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def generate_repo_report(repo_name: str, repo_data: Dict[str, Any]) -> str:
    """生成单个仓库的详细报告"""
    lines = []
    lines.append("=" * 80)
    lines.append(f"📊 项目: {repo_name}")
    lines.append("=" * 80)
    
    # 获取风险评分
    risk_score = repo_data.get("risk_score", {})
    total_score = risk_score.get("total_score", 0)
    risk_level = risk_score.get("risk_level", "unknown")
    current_score = risk_score.get("current_score", 0)
    trend_score = risk_score.get("trend_score", 0)
    
    # 风险等级图标
    level_icons = {
        "高": "🔴 高风险",
        "中": "🟡 中风险",
        "低": "🟢 低风险",
        "unknown": "⚪ 未知"
    }
    
    lines.append(f"\n🎯 综合风险评分: {total_score:.2f} / 100")
    lines.append(f"   风险等级: {level_icons.get(risk_level, risk_level)}")
    lines.append(f"   当前状态得分: {current_score:.2f} / 50")
    lines.append(f"   趋势得分: {trend_score:.2f} / 50")
    
    # 获取指标时间序列
    metrics = repo_data.get("metrics", [])
    if not metrics:
        lines.append("\n⚠️ 无数据")
        return "\n".join(lines)
    
    # 按月份排序
    sorted_metrics = sorted(metrics, key=lambda m: m.get("month", ""))
    earliest = sorted_metrics[0]
    latest = sorted_metrics[-1]
    
    lines.append(f"   分析周期: {earliest['month']} 至 {latest['month']} ({len(sorted_metrics)} 个月)")
    
    # 当前状态分析
    lines.append("\n" + "-" * 80)
    lines.append("📈 当前状态分析 (50分，基于最近月份)")
    lines.append("-" * 80)
    
    current_bf = latest.get("bus_factor", 0)
    current_contributors = latest.get("contributor_count", 0)
    current_contribution = latest.get("total_contribution", 0)
    
    lines.append(f"\n【当前 Bus Factor】")
    lines.append(f"   📊 Bus Factor: {current_bf}")
    lines.append(f"   👥 贡献者数量: {current_contributors}")
    lines.append(f"   📦 总贡献量: {current_contribution:.2f}")
    
    # 解释 Bus Factor 含义
    if current_bf == 0:
        lines.append(f"   ⚠️ 极高风险: 无有效贡献或总贡献量为0")
    elif current_bf == 1:
        lines.append(f"   🔴 极高风险: 仅1人就能贡献50%以上的工作量")
    elif current_bf == 2:
        lines.append(f"   🔴 高风险: 仅2人就能贡献50%以上的工作量")
    elif current_bf <= 5:
        lines.append(f"   🟡 中风险: {current_bf}人贡献了50%以上的工作量")
    else:
        lines.append(f"   🟢 低风险: {current_bf}人贡献了50%以上的工作量，贡献较为分散")
    
    # 显示 Top 贡献者
    top_contributors = latest.get("contributors", [])[:5]
    if top_contributors:
        lines.append(f"\n   🏆 Top 5 贡献者:")
        for i, contributor in enumerate(top_contributors, 1):
            login = contributor.get("login", "unknown")
            contrib = contributor.get("total_contribution", 0)
            ratio = contributor.get("contribution_ratio", 0) * 100
            
            # 详细活动统计
            commits = contributor.get("commit_count", 0)
            pr_merged = contributor.get("pr_merged", 0)
            pr_opened = contributor.get("pr_opened", 0)
            issues_closed = contributor.get("issue_closed", 0)
            issues_opened = contributor.get("issue_opened", 0)
            comments = contributor.get("comment_count", 0)
            
            lines.append(f"      {i}. {login}: {contrib:.2f} ({ratio:.1f}%)")
            
            # 显示活动分解
            activities = []
            if commits > 0:
                activities.append(f"commit×{commits}")
            if pr_merged > 0:
                activities.append(f"PR合并×{pr_merged}")
            if pr_opened > 0:
                activities.append(f"PR打开×{pr_opened}")
            if issues_closed > 0:
                activities.append(f"Issue关闭×{issues_closed}")
            if issues_opened > 0:
                activities.append(f"Issue打开×{issues_opened}")
            if comments > 0:
                activities.append(f"评论×{comments}")
            
            if activities:
                lines.append(f"         └─ {', '.join(activities)}")
    
    # 计算当前状态得分
    lines.append(f"\n   ➡️ 当前状态得分计算:")
    if current_bf == 0:
        lines.append(f"      Bus Factor = 0 → 极高风险 → 50分")
    elif current_bf == 1:
        lines.append(f"      Bus Factor = 1 → 极高风险 → 50分")
    elif current_bf == 2:
        lines.append(f"      Bus Factor = 2 → 高风险 → 47.22分")
    elif current_bf == 3:
        lines.append(f"      Bus Factor = 3 → 高风险 → 44.44分")
    elif current_bf <= 5:
        lines.append(f"      Bus Factor = {current_bf} → 中风险")
    else:
        lines.append(f"      Bus Factor = {current_bf} → 低风险")
    lines.append(f"      最终得分: {current_score:.2f} / 50")
    
    # 趋势分析
    lines.append("\n" + "-" * 80)
    lines.append("📉 趋势分析 (50分，基于时间序列)")
    lines.append("-" * 80)
    
    trend_analysis = repo_data.get("trend_analysis", {})
    if trend_analysis:
        slope = trend_analysis.get("slope", 0)
        r_squared = trend_analysis.get("r_squared", 0)
        avg_bf = trend_analysis.get("average_bus_factor", 0)
        trend_direction = trend_analysis.get("direction", "unknown")
        
        lines.append(f"\n【趋势统计】")
        lines.append(f"   📊 平均 Bus Factor: {avg_bf:.2f}")
        lines.append(f"   📈 线性回归斜率: {slope:+.4f}/月")
        lines.append(f"   📊 拟合优度 (R²): {r_squared:.3f}")
        
        # 趋势方向
        if trend_direction == "上升":
            lines.append(f"   ✅ 趋势: {trend_direction} (Bus Factor 逐渐增加，风险降低)")
        elif trend_direction == "下降":
            lines.append(f"   ⚠️ 趋势: {trend_direction} (Bus Factor 逐渐减少，风险增加)")
        else:
            lines.append(f"   ➡️ 趋势: {trend_direction} (Bus Factor 保持稳定)")
        
        # 早期 vs 近期
        early_values = [m.get("bus_factor", 0) for m in sorted_metrics[:3]]
        recent_values = [m.get("bus_factor", 0) for m in sorted_metrics[-3:]]
        
        if len(early_values) >= 1 and len(recent_values) >= 1:
            early_avg = sum(early_values) / len(early_values)
            recent_avg = sum(recent_values) / len(recent_values)
            
            lines.append(f"\n   📅 早期 vs 近期:")
            lines.append(f"      早期3月平均: {early_avg:.2f}")
            lines.append(f"      近期3月平均: {recent_avg:.2f}")
            
            change = recent_avg - early_avg
            if change > 0.5:
                lines.append(f"      ✅ 改善明显: Bus Factor 提升 {change:+.2f}")
            elif change < -0.5:
                lines.append(f"      ⚠️ 恶化明显: Bus Factor 下降 {abs(change):.2f}")
            else:
                lines.append(f"      ➡️ 基本稳定: 变化 {change:+.2f}")
    
    lines.append(f"\n   ➡️ 趋势得分: {trend_score:.2f} / 50")
    
    # 风险评估
    lines.append("\n" + "-" * 80)
    lines.append("⚠️ 风险评估与建议")
    lines.append("-" * 80)
    
    lines.append(f"\n【综合评估】")
    if total_score >= 70:
        lines.append(f"   🔴 高风险项目 (总分 {total_score:.2f}/100)")
        lines.append(f"   建议:")
        lines.append(f"      • 立即采取措施分散知识和责任")
        lines.append(f"      • 增加核心贡献者数量")
        lines.append(f"      • 建立知识文档和代码审查机制")
        lines.append(f"      • 培养新的核心维护者")
    elif total_score >= 40:
        lines.append(f"   🟡 中风险项目 (总分 {total_score:.2f}/100)")
        lines.append(f"   建议:")
        lines.append(f"      • 继续鼓励新贡献者参与")
        lines.append(f"      • 关注核心贡献者的留存")
        lines.append(f"      • 完善项目文档和贡献指南")
    else:
        lines.append(f"   🟢 低风险项目 (总分 {total_score:.2f}/100)")
        lines.append(f"   状态:")
        lines.append(f"      • 贡献分布较为均衡")
        lines.append(f"      • 继续保持当前的健康状态")
    
    # 详细的月度数据
    lines.append("\n" + "-" * 80)
    lines.append("📅 月度指标详情")
    lines.append("-" * 80)
    lines.append(f"   {'月份':<12} {'BF':>4} {'贡献者':>8} {'总贡献量':>12} {'节点数':>8} {'边数':>8}")
    lines.append("   " + "-" * 70)
    
    for m in sorted_metrics:
        month = m.get("month", "N/A")
        bf = m.get("bus_factor", 0)
        contributors = m.get("contributor_count", 0)
        contribution = m.get("total_contribution", 0)
        nodes = m.get("node_count", 0)
        edges = m.get("edge_count", 0)
        
        lines.append(f"   {month:<12} {bf:>4} {contributors:>8} {contribution:>12.2f} {nodes:>8} {edges:>8}")
    
    lines.append("")
    return "\n".join(lines)


def generate_summary_report(summary_data: Dict[str, Any]) -> str:
    """生成汇总报告"""
    lines = []
    lines.append("=" * 80)
    lines.append("📊 Bus Factor 风险分析汇总")
    lines.append("=" * 80)
    
    generated_at = summary_data.get("generated_at", "N/A")
    total_repos = summary_data.get("total_repos", 0)
    repos = summary_data.get("repos", [])
    
    lines.append(f"\n生成时间: {generated_at}")
    lines.append(f"分析项目数: {total_repos}")
    
    # 风险等级分布
    lines.append("\n" + "-" * 80)
    lines.append("🎯 风险等级分布")
    lines.append("-" * 80)
    
    high_risk = [r for r in repos if r.get("risk_level") == "高"]
    medium_risk = [r for r in repos if r.get("risk_level") == "中"]
    low_risk = [r for r in repos if r.get("risk_level") == "低"]
    
    lines.append(f"\n   🔴 高风险 (≥70分): {len(high_risk)} 个项目 ({len(high_risk)/total_repos*100:.1f}%)")
    lines.append(f"   🟡 中风险 (40-70分): {len(medium_risk)} 个项目 ({len(medium_risk)/total_repos*100:.1f}%)")
    lines.append(f"   🟢 低风险 (<40分): {len(low_risk)} 个项目 ({len(low_risk)/total_repos*100:.1f}%)")
    
    # Bus Factor 分布
    lines.append("\n" + "-" * 80)
    lines.append("📊 当前 Bus Factor 分布")
    lines.append("-" * 80)
    
    bf_0 = [r for r in repos if r.get("current_bus_factor") == 0]
    bf_1 = [r for r in repos if r.get("current_bus_factor") == 1]
    bf_2 = [r for r in repos if r.get("current_bus_factor") == 2]
    bf_3_5 = [r for r in repos if 3 <= r.get("current_bus_factor", 0) <= 5]
    bf_6plus = [r for r in repos if r.get("current_bus_factor", 0) >= 6]
    
    lines.append(f"\n   BF = 0 (极高风险): {len(bf_0)} 个 ({len(bf_0)/total_repos*100:.1f}%)")
    lines.append(f"   BF = 1 (极高风险): {len(bf_1)} 个 ({len(bf_1)/total_repos*100:.1f}%)")
    lines.append(f"   BF = 2 (高风险):   {len(bf_2)} 个 ({len(bf_2)/total_repos*100:.1f}%)")
    lines.append(f"   BF = 3-5 (中风险): {len(bf_3_5)} 个 ({len(bf_3_5)/total_repos*100:.1f}%)")
    lines.append(f"   BF ≥ 6 (低风险):   {len(bf_6plus)} 个 ({len(bf_6plus)/total_repos*100:.1f}%)")
    
    # 趋势分布
    lines.append("\n" + "-" * 80)
    lines.append("📈 趋势方向分布")
    lines.append("-" * 80)
    
    trend_up = [r for r in repos if r.get("trend_direction") == "上升"]
    trend_stable = [r for r in repos if r.get("trend_direction") == "稳定"]
    trend_down = [r for r in repos if r.get("trend_direction") == "下降"]
    
    lines.append(f"\n   ✅ 上升 (风险降低): {len(trend_up)} 个 ({len(trend_up)/total_repos*100:.1f}%)")
    lines.append(f"   ➡️ 稳定:            {len(trend_stable)} 个 ({len(trend_stable)/total_repos*100:.1f}%)")
    lines.append(f"   ⚠️ 下降 (风险增加): {len(trend_down)} 个 ({len(trend_down)/total_repos*100:.1f}%)")
    
    # Top 高风险项目
    lines.append("\n" + "-" * 80)
    lines.append("🔴 Top 10 高风险项目")
    lines.append("-" * 80)
    
    sorted_repos = sorted(repos, key=lambda r: r.get("total_score", 0), reverse=True)
    lines.append(f"\n   {'排名':<6} {'项目':<40} {'总分':>8} {'当前BF':>8} {'趋势':>8}")
    lines.append("   " + "-" * 72)
    
    for i, repo in enumerate(sorted_repos[:10], 1):
        name = repo.get("repo_name", "N/A")
        score = repo.get("total_score", 0)
        bf = repo.get("current_bus_factor", 0)
        trend = repo.get("trend_direction", "N/A")
        
        # 趋势图标
        trend_icon = {"上升": "↑", "稳定": "→", "下降": "↓"}.get(trend, "?")
        
        lines.append(f"   {i:<6} {name:<40} {score:>8.2f} {bf:>8} {trend_icon:>6} {trend}")
    
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成 Bus Factor 风险分析报告")
    parser.add_argument(
        "--input",
        type=str,
        default="output/bus-factor-analysis/full_analysis.json",
        help="输入的完整分析文件路径"
    )
    parser.add_argument(
        "--summary",
        type=str,
        default="output/bus-factor-analysis/summary.json",
        help="输入的汇总文件路径"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/bus-factor-analysis/detailed_report.txt",
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
        help="只输出风险评分最高的前 N 个项目"
    )
    parser.add_argument(
        "--min-risk",
        type=float,
        default=None,
        help="只输出风险评分大于等于该值的项目"
    )
    parser.add_argument(
        "--max-risk",
        type=float,
        default=None,
        help="只输出风险评分小于等于该值的项目"
    )
    parser.add_argument(
        "--include-summary",
        action="store_true",
        help="在报告开头包含汇总信息"
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
    
    # 读取汇总数据
    summary_data = None
    if args.include_summary:
        summary_path = Path(args.summary)
        if summary_path.exists():
            print(f"📖 读取汇总数据: {summary_path}")
            with open(summary_path, "r", encoding="utf-8") as f:
                summary_data = json.load(f)
    
    # 筛选仓库
    repos_to_analyze = list(data.keys())
    
    if args.repo:
        specified_repos = [r.strip() for r in args.repo.split(",")]
        repos_to_analyze = [r for r in repos_to_analyze if r in specified_repos]
        if not repos_to_analyze:
            print(f"❌ 未找到指定的仓库: {args.repo}")
            return
    
    # 按风险评分排序
    repos_with_scores = []
    for repo in repos_to_analyze:
        risk_score = data[repo].get("risk_score", {})
        score = risk_score.get("total_score", 0)
        repos_with_scores.append((repo, score))
    
    repos_with_scores.sort(key=lambda x: x[1], reverse=True)
    
    # 筛选条件
    if args.min_risk is not None:
        repos_with_scores = [(r, s) for r, s in repos_with_scores if s >= args.min_risk]
    
    if args.max_risk is not None:
        repos_with_scores = [(r, s) for r, s in repos_with_scores if s <= args.max_risk]
    
    if args.top is not None:
        repos_with_scores = repos_with_scores[:args.top]
    
    if not repos_with_scores:
        print("❌ 没有符合条件的项目")
        return
    
    print(f"📊 将分析 {len(repos_with_scores)} 个项目")
    
    # 生成报告
    reports = []
    reports.append("=" * 80)
    reports.append("🔍 OSS 项目 Bus Factor 风险详细分析报告")
    reports.append("=" * 80)
    reports.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    reports.append(f"分析项目数: {len(repos_with_scores)}")
    reports.append("")
    
    # 添加汇总信息
    if args.include_summary and summary_data:
        summary_report = generate_summary_report(summary_data)
        reports.append(summary_report)
        reports.append("")
    
    # 生成各项目详细报告
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

