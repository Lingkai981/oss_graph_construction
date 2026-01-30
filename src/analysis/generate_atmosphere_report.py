"""
详细社区氛围分析报告生成器

按项目输出每一项得分的来源和数值变化
基于 full_analysis.json 和 summary.json 生成详细分析报告

评分体系说明：
========================================
综合评分 = 大模型评分(40%) + 聚类系数(30%) + 网络直径(30%)
========================================

1. 大模型评分 (40%)：
   - 基于毒性指标（ToxiCR）和 CHAOSS 指标
   - 由 DeepSeek 大模型综合分析后给出评分
   - 包含毒性评分和响应效率评分两个子维度

2. 聚类系数 (30%)：
   - 指标：global_clustering_coefficient
   - 意义：社区越紧密，协作效率越高
   - 正向指标：数值越大越好

3. 网络直径 (30%)：
   - 指标：average_path_length
   - 意义：沟通路径越短，信息传递效率越高
   - 负向指标：数值越小越好
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
    
    # 获取氛围评分
    atmosphere = repo_data.get("atmosphere_score", {})
    score = atmosphere.get("score", 0)
    level = atmosphere.get("level", "unknown")
    period = atmosphere.get("period", "N/A")
    months = atmosphere.get("months_analyzed", 0)
    
    # 氛围等级图标
    level_icons = {
        "excellent": "🟢 优秀",
        "good": "🟢 良好",
        "moderate": "🟡 中等",
        "poor": "🔴 较差",
        "insufficient_data": "⚪ 数据不足",
        "unknown": "⚪ 未知"
    }
    
    lines.append(f"\n🎯 综合氛围评分: {score:.2f} / 100")
    lines.append(f"   氛围等级: {level_icons.get(level, level)}")
    lines.append(f"   分析周期: {period} ({months} 个月)")
    
    # 获取指标时间序列
    metrics = repo_data.get("metrics", [])
    if len(metrics) < 3:
        lines.append("\n⚠️ 数据不足（少于3个月），无法进行趋势分析")
        return "\n".join(lines)
    
    # 按月份排序
    sorted_metrics = sorted(metrics, key=lambda m: m.get("month", ""))
    earliest = sorted_metrics[0]
    latest = sorted_metrics[-1]
    
    lines.append("\n" + "-" * 80)
    lines.append("📈 各因子详细分析（三层架构：长期趋势40% + 近期状态40% + 稳定性20%）")
    lines.append("-" * 80)
    
    factors = atmosphere.get("factors", {})
    weights = atmosphere.get("weights", {"llm": 0.4, "clustering": 0.3, "diameter": 0.3})
    
    # ========================================
    # 1. 大模型评分因子 (40%)
    # ========================================
    lines.append("\n【1. 大模型评分因子】(权重40%)")
    llm_score_factor = factors.get("llm_score", 0)
    
    # 收集 LLM 评分数据
    llm_scores = [m.get("llm_score", 0) for m in sorted_metrics]
    has_llm_data = any(s > 0 for s in llm_scores)
    
    if has_llm_data:
        early_llm = sorted_metrics[0].get("llm_score", 0)
        late_llm = sorted_metrics[-1].get("llm_score", 0)
        
        lines.append(f"   📊 数据概览:")
        lines.append(f"      首月 LLM 评分: {early_llm:.1f}  →  末月 LLM 评分: {late_llm:.1f}")
        
        # 计算趋势
        if len(llm_scores) >= 3:
            early_avg = sum(llm_scores[:3]) / 3
            recent_avg = sum(llm_scores[-3:]) / 3
            change = recent_avg - early_avg
            lines.append(f"      早期3月均值: {early_avg:.1f}  →  近期3月均值: {recent_avg:.1f}")
            if change > 0:
                lines.append(f"      ✅ LLM 评分趋势向好 (提升 {change:+.1f})")
            elif change < 0:
                lines.append(f"      ⚠️ LLM 评分趋势下降 (下降 {abs(change):.1f})")
            else:
                lines.append(f"      ➡️ LLM 评分保持稳定")
        
        # 展示毒性和响应子维度
        lines.append(f"\n   📋 子维度分析:")
        
        # 毒性分析
        toxicity_means = [m.get("toxicity_mean", 0) for m in sorted_metrics]
        toxic_rates = [m.get("toxic_rate_0_5", 0) for m in sorted_metrics]
        avg_toxicity = sum(toxicity_means) / len(toxicity_means)
        avg_toxic_rate = sum(toxic_rates) / len(toxic_rates)
        
        early_toxicity = toxicity_means[0]
        late_toxicity = toxicity_means[-1]
        
        lines.append(f"      [毒性分析]")
        lines.append(f"         首月平均毒性: {early_toxicity:.4f}  →  末月平均毒性: {late_toxicity:.4f}")
        lines.append(f"         整体平均毒性: {avg_toxicity:.4f}")
        lines.append(f"         平均高毒性评论占比: {avg_toxic_rate:.2%}")
        
        # 响应时间分析
        response_times = [m.get("time_to_first_response_median", 0) for m in sorted_metrics]
        closure_ratios = [m.get("change_request_closure_ratio", 0) for m in sorted_metrics]
        avg_response = sum(response_times) / len(response_times)
        avg_closure = sum(closure_ratios) / len(closure_ratios)
        
        early_response = response_times[0]
        late_response = response_times[-1]
        
        lines.append(f"      [响应效率]")
        lines.append(f"         首月响应时间中位数: {early_response:.1f}h  →  末月: {late_response:.1f}h")
        lines.append(f"         整体平均响应时间: {avg_response:.1f}h")
        lines.append(f"         平均变更请求关闭率: {avg_closure:.2f}")
        
        # LLM 给出的理由（取最新月份的）
        latest_reason = latest.get("llm_overall_reason", "")
        if latest_reason:
            lines.append(f"\n   💬 LLM 评价 (最新月份):")
            # 将理由按行显示，每行最多60字符
            reason_lines = [latest_reason[i:i+60] for i in range(0, len(latest_reason), 60)]
            for rl in reason_lines[:3]:  # 最多显示3行
                lines.append(f"      {rl}")
    else:
        lines.append(f"   ⚠️ 无 LLM 评分数据（API 未配置或评分失败）")
        lines.append(f"   ➡️ 该维度使用占位值 0，仅使用聚类系数和网络直径进行评分")
    
    lines.append(f"\n   ➡️ 因子得分: {llm_score_factor:.2f} (三层分析后的综合分，满分100)")
    
    # ========================================
    # 2. 聚类系数因子 (30%)
    # ========================================
    lines.append("\n【2. 聚类系数因子】(权重30%)")
    clustering_score_factor = factors.get("clustering_score", 0)
    
    clustering_values = [m.get("global_clustering_coefficient", 0) for m in sorted_metrics]
    avg_clustering = sum(clustering_values) / len(clustering_values)
    
    early_clustering = earliest.get("global_clustering_coefficient", 0)
    late_clustering = latest.get("global_clustering_coefficient", 0)
    
    lines.append(f"   📊 数据概览:")
    lines.append(f"      首月聚类系数: {early_clustering:.4f}  →  末月聚类系数: {late_clustering:.4f}")
    lines.append(f"      整体平均聚类系数: {avg_clustering:.4f} (范围: 0.0 到 1.0)")
    
    # 计算趋势
    if len(clustering_values) >= 3:
        early_avg = sum(clustering_values[:3]) / 3
        recent_avg = sum(clustering_values[-3:]) / 3
        change = recent_avg - early_avg
        lines.append(f"      早期3月均值: {early_avg:.4f}  →  近期3月均值: {recent_avg:.4f}")
        if change > 0.01:
            lines.append(f"      ✅ 聚类系数提升 (提升 {change:+.4f})")
        elif change < -0.01:
            lines.append(f"      ⚠️ 聚类系数下降 (下降 {abs(change):.4f})")
        else:
            lines.append(f"      ➡️ 聚类系数保持稳定")
    
    # 社区规模信息
    avg_nodes = sum(m.get("actor_graph_nodes", 0) for m in sorted_metrics) / len(sorted_metrics)
    avg_edges = sum(m.get("actor_graph_edges", 0) for m in sorted_metrics) / len(sorted_metrics)
    lines.append(f"      平均参与者数量: {avg_nodes:.0f} 人")
    lines.append(f"      平均协作边数量: {avg_edges:.0f} 条")
    
    lines.append(f"\n   ➡️ 因子得分: {clustering_score_factor:.2f} (三层分析后的综合分，满分100)")
    lines.append(f"      (正向指标：聚类系数越高，社区越紧密，得分越高)")
    
    # ========================================
    # 3. 网络直径因子 (30%)
    # ========================================
    lines.append("\n【3. 网络直径因子】(权重30%)")
    diameter_score_factor = factors.get("diameter_score", 0)
    
    path_values = [m.get("average_path_length", 0) for m in sorted_metrics]
    diameter_values = [m.get("diameter", 0) for m in sorted_metrics]
    avg_path = sum(path_values) / len(path_values)
    avg_diameter = sum(diameter_values) / len(diameter_values)
    
    early_path = earliest.get("average_path_length", 0)
    late_path = latest.get("average_path_length", 0)
    early_diameter = earliest.get("diameter", 0)
    late_diameter = latest.get("diameter", 0)
    
    lines.append(f"   📊 数据概览:")
    lines.append(f"      首月平均路径长度: {early_path:.2f}  →  末月平均路径长度: {late_path:.2f}")
    lines.append(f"      首月网络直径: {early_diameter:.0f}  →  末月网络直径: {late_diameter:.0f}")
    lines.append(f"      整体平均路径长度: {avg_path:.2f}")
    lines.append(f"      整体平均网络直径: {avg_diameter:.1f}")
    
    # 计算趋势
    if len(path_values) >= 3:
        early_avg = sum(path_values[:3]) / 3
        recent_avg = sum(path_values[-3:]) / 3
        change = recent_avg - early_avg
        lines.append(f"      早期3月均值: {early_avg:.2f}  →  近期3月均值: {recent_avg:.2f}")
        if change < -0.1:
            lines.append(f"      ✅ 路径长度缩短 (减少 {abs(change):.2f})")
        elif change > 0.1:
            lines.append(f"      ⚠️ 路径长度增加 (增加 {change:.2f})")
        else:
            lines.append(f"      ➡️ 路径长度保持稳定")
    
    # 连通性信息
    connected_count = sum(1 for m in sorted_metrics if m.get("is_connected", False))
    lines.append(f"      完全连通月份: {connected_count}/{len(sorted_metrics)} 个月")
    
    lines.append(f"\n   ➡️ 因子得分: {diameter_score_factor:.2f} (三层分析后的综合分，满分100)")
    lines.append(f"      (负向指标：路径长度越短，沟通效率越高，得分越高)")
    
    # ========================================
    # 评分汇总
    # ========================================
    lines.append("\n" + "-" * 80)
    lines.append("📋 评分汇总")
    lines.append("-" * 80)
    
    llm_weight = weights.get("llm", 0.4)
    clustering_weight = weights.get("clustering", 0.3)
    diameter_weight = weights.get("diameter", 0.3)
    
    lines.append(f"   大模型评分因子:   {llm_score_factor:6.2f} × {llm_weight:.0%} = {llm_score_factor * llm_weight:6.2f}")
    lines.append(f"   聚类系数因子:     {clustering_score_factor:6.2f} × {clustering_weight:.0%} = {clustering_score_factor * clustering_weight:6.2f}")
    lines.append(f"   网络直径因子:     {diameter_score_factor:6.2f} × {diameter_weight:.0%} = {diameter_score_factor * diameter_weight:6.2f}")
    lines.append(f"   " + "-" * 40)
    lines.append(f"   总分:                              {score:6.2f} / 100")
    
    lines.append(f"\n   📐 分析方法: 三层架构 (长期趋势40% + 近期状态40% + 稳定性20%)")
    
    # ========================================
    # CHAOSS 指标详情
    # ========================================
    lines.append("\n" + "-" * 80)
    lines.append("📊 CHAOSS 社区健康指标详情")
    lines.append("-" * 80)
    
    # 变更请求统计
    total_opened_prs = sum(m.get("opened_prs", 0) for m in sorted_metrics)
    total_closed_prs = sum(m.get("closed_prs", 0) for m in sorted_metrics)
    total_opened_issues = sum(m.get("opened_issues", 0) for m in sorted_metrics)
    total_closed_issues = sum(m.get("closed_issues", 0) for m in sorted_metrics)
    
    lines.append(f"   [变更请求关闭率]")
    lines.append(f"      累计打开 PR: {total_opened_prs}  →  累计关闭 PR: {total_closed_prs}")
    lines.append(f"      累计打开 Issue: {total_opened_issues}  →  累计关闭 Issue: {total_closed_issues}")
    if total_opened_prs + total_opened_issues > 0:
        overall_closure = (total_closed_prs + total_closed_issues) / (total_opened_prs + total_opened_issues)
        lines.append(f"      整体关闭率: {overall_closure:.2f}")
    
    # 响应时间统计
    response_medians = [m.get("time_to_first_response_median", 0) for m in sorted_metrics if m.get("time_to_first_response_median", 0) > 0]
    if response_medians:
        lines.append(f"\n   [首次响应时间]")
        lines.append(f"      中位数范围: {min(response_medians):.1f}h ~ {max(response_medians):.1f}h")
        lines.append(f"      平均中位数: {sum(response_medians)/len(response_medians):.1f}h")
    
    # ========================================
    # 月度指标趋势
    # ========================================
    lines.append("\n" + "-" * 80)
    lines.append("📅 月度指标趋势")
    lines.append("-" * 80)
    
    # 表头
    lines.append(f"   {'月份':<10} {'LLM分':>6} {'毒性':>8} {'聚类系数':>10} {'路径长度':>10} {'响应时间':>10} {'关闭率':>8}")
    lines.append("   " + "-" * 72)
    
    for m in sorted_metrics:
        month = m.get("month", "N/A")
        llm = m.get("llm_score", 0)
        toxicity = m.get("toxicity_mean", 0)
        clustering = m.get("global_clustering_coefficient", 0)
        path_length = m.get("average_path_length", 0)
        response = m.get("time_to_first_response_median", 0)
        closure = m.get("change_request_closure_ratio", 0)
        
        lines.append(f"   {month:<10} {llm:>6.0f} {toxicity:>8.4f} {clustering:>10.4f} {path_length:>10.2f} {response:>9.1f}h {closure:>8.2f}")
    
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成详细社区氛围分析报告")
    parser.add_argument(
        "--input",
        type=str,
        default="output/community-atmosphere-analysis/full_analysis.json",
        help="输入的完整分析文件路径"
    )
    parser.add_argument(
        "--summary",
        type=str,
        default="output/community-atmosphere-analysis/summary.json",
        help="输入的摘要文件路径"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/community-atmosphere-analysis/detailed_report.txt",
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
        help="只输出氛围评分最高的前 N 个项目"
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="只输出氛围评分大于等于该值的项目"
    )
    parser.add_argument(
        "--max-score",
        type=float,
        default=None,
        help="只输出氛围评分小于等于该值的项目"
    )
    parser.add_argument(
        "--level",
        type=str,
        choices=["excellent", "good", "moderate", "poor"],
        default=None,
        help="只输出指定等级的项目"
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
    
    # 读取摘要数据（用于排序）
    summary_path = Path(args.summary)
    summary_data = []
    if summary_path.exists():
        print(f"📖 读取摘要数据: {summary_path}")
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
    
    # 按氛围评分排序
    repos_with_scores = []
    for repo in repos_to_analyze:
        repo_data = data[repo]
        score = repo_data.get("atmosphere_score", {}).get("score", 0)
        level = repo_data.get("atmosphere_score", {}).get("level", "unknown")
        repos_with_scores.append((repo, score, level))
    
    repos_with_scores.sort(key=lambda x: x[1], reverse=True)
    
    # 筛选条件
    if args.min_score is not None:
        repos_with_scores = [(r, s, l) for r, s, l in repos_with_scores if s >= args.min_score]
    
    if args.max_score is not None:
        repos_with_scores = [(r, s, l) for r, s, l in repos_with_scores if s <= args.max_score]
    
    if args.level is not None:
        repos_with_scores = [(r, s, l) for r, s, l in repos_with_scores if l == args.level]
    
    if args.top is not None:
        repos_with_scores = repos_with_scores[:args.top]
    
    if not repos_with_scores:
        print("❌ 没有符合条件的项目")
        return
    
    print(f"📊 将分析 {len(repos_with_scores)} 个项目")
    
    # 生成报告
    reports = []
    reports.append("=" * 80)
    reports.append("🔍 OSS 项目社区氛围详细分析报告")
    reports.append("=" * 80)
    reports.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    reports.append(f"分析项目数: {len(repos_with_scores)}")
    reports.append("")
    
    # 评分体系说明
    reports.append("📐 评分体系说明:")
    reports.append("   综合评分 = 大模型评分(40%) + 聚类系数(30%) + 网络直径(30%)")
    reports.append("   每个维度使用三层分析：长期趋势(40%) + 近期状态(40%) + 稳定性(20%)")
    reports.append("")
    
    # 摘要表格
    reports.append("-" * 80)
    reports.append("📋 项目评分摘要")
    reports.append("-" * 80)
    reports.append(f"   {'排名':<4} {'项目名称':<40} {'评分':>8} {'等级':<12}")
    reports.append("   " + "-" * 70)
    
    for idx, (repo, score, level) in enumerate(repos_with_scores, 1):
        level_icons = {
            "excellent": "🟢优秀",
            "good": "🟢良好",
            "moderate": "🟡中等",
            "poor": "🔴较差",
            "insufficient_data": "⚪数据不足",
        }
        level_str = level_icons.get(level, level)
        reports.append(f"   {idx:<4} {repo:<40} {score:>8.2f} {level_str:<12}")
    
    reports.append("")
    
    # 详细报告
    for repo, score, level in repos_with_scores:
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
        print("\n📋 前 3 个项目预览:\n")
        for repo, score, level in repos_with_scores[:3]:
            print(generate_repo_report(repo, data[repo]))


if __name__ == "__main__":
    main()
