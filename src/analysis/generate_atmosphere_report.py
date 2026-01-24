"""
详细社区氛围分析报告生成器

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
        "unknown": "⚪ 未知"
    }
    
    lines.append(f"\n🎯 综合氛围评分: {score:.2f} / 100")
    lines.append(f"   氛围等级: {level_icons.get(level, level)}")
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
    lines.append("📈 各因子详细分析（三大因子：情绪氛围20% + 社区紧密度40% + 网络效率40%）")
    lines.append("-" * 80)
    
    factors = atmosphere.get("factors", {})
    
    # 1. 情绪氛围因子
    lines.append("\n【1. 情绪氛围因子】(0-20分，权重20%)")
    emotion = factors.get("emotion", {})
    emotion_value = emotion.get("value", 0)
    emotion_score = emotion.get("score", 0)
    
    early_emotion = earliest.get("average_emotion", 0)
    late_emotion = latest.get("average_emotion", 0)
    
    lines.append(f"   📊 数据概览:")
    lines.append(f"      首月平均情绪: {early_emotion:+.3f}  →  末月平均情绪: {late_emotion:+.3f}")
    lines.append(f"      整体平均情绪: {emotion_value:+.3f} (范围: -1.0 到 +1.0)")
    
    # 计算趋势
    emotion_values = [m.get("average_emotion", 0) for m in sorted_metrics]
    if len(emotion_values) >= 3:
        early_avg = sum(emotion_values[:3]) / min(3, len(emotion_values))
        recent_avg = sum(emotion_values[-3:]) / min(3, len(emotion_values))
        change = recent_avg - early_avg
        lines.append(f"      早期3月均值: {early_avg:+.3f}  →  近期3月均值: {recent_avg:+.3f}")
        if change > 0:
            lines.append(f"      ✅ 情绪趋势向好 (提升 {change:+.3f})")
        elif change < 0:
            lines.append(f"      ⚠️ 情绪趋势下降 (下降 {abs(change):.3f})")
        else:
            lines.append(f"      ➡️ 情绪保持稳定")
    
    lines.append(f"   ➡️ 因子得分: {emotion_score:.2f} / 20")
    lines.append(f"      (归一化公式: (avg_emotion + 1.0) / 2.0 * 20)")
    
    # 2. 社区紧密度因子（聚类系数）
    lines.append("\n【2. 社区紧密度因子】(0-40分，权重40%)")
    clustering = factors.get("clustering", {})
    clustering_value = clustering.get("value", 0)
    clustering_score = clustering.get("score", 0)
    
    early_clustering = earliest.get("average_local_clustering", 0)
    late_clustering = latest.get("average_local_clustering", 0)
    
    lines.append(f"   📊 数据概览:")
    lines.append(f"      首月平均聚类系数: {early_clustering:.3f}  →  末月平均聚类系数: {late_clustering:.3f}")
    lines.append(f"      整体平均聚类系数: {clustering_value:.3f} (范围: 0.0 到 1.0)")
    
    # 计算趋势
    clustering_values = [m.get("average_local_clustering", 0) for m in sorted_metrics]
    if len(clustering_values) >= 3:
        early_avg = sum(clustering_values[:3]) / min(3, len(clustering_values))
        recent_avg = sum(clustering_values[-3:]) / min(3, len(clustering_values))
        change = recent_avg - early_avg
        lines.append(f"      早期3月均值: {early_avg:.3f}  →  近期3月均值: {recent_avg:.3f}")
        if change > 0.01:
            lines.append(f"      ✅ 紧密度提升 (提升 {change:+.3f})")
        elif change < -0.01:
            lines.append(f"      ⚠️ 紧密度下降 (下降 {abs(change):+.3f})")
        else:
            lines.append(f"      ➡️ 紧密度保持稳定")
    
    # 解释归一化逻辑
    clustering_threshold = 0.6
    clustering_growth_factor = 2.0
    if clustering_value <= 0.0:
        norm_explanation = "0.0 (聚类系数为0)"
    elif clustering_value >= clustering_threshold:
        norm_explanation = "1.0 (达到阈值0.6)"
    else:
        norm_explanation = f"{1.0 / (1.0 + clustering_growth_factor * (clustering_threshold - clustering_value) / clustering_threshold):.3f} (平滑增长函数)"
    
    lines.append(f"   ➡️ 因子得分: {clustering_score:.2f} / 40")
    lines.append(f"      (归一化值: {norm_explanation})")
    lines.append(f"      (归一化公式: 平滑增长函数，阈值={clustering_threshold}, 增长因子={clustering_growth_factor})")
    
    # 3. 网络效率因子
    lines.append("\n【3. 网络效率因子】(0-40分，权重40%)")
    network = factors.get("network_efficiency", {})
    network_value = network.get("value", {})
    network_score = network.get("score", 0)
    
    avg_diameter = network_value.get("average_diameter", 0)
    avg_path_length = network_value.get("average_path_length", 0)
    
    early_diameter = earliest.get("diameter", 0)
    late_diameter = latest.get("diameter", 0)
    early_path = earliest.get("average_path_length", 0)
    late_path = latest.get("average_path_length", 0)
    
    lines.append(f"   📊 数据概览:")
    lines.append(f"      首月网络直径: {early_diameter:.1f}  →  末月网络直径: {late_diameter:.1f}")
    lines.append(f"      首月平均路径长度: {early_path:.2f}  →  末月平均路径长度: {late_path:.2f}")
    lines.append(f"      整体平均直径: {avg_diameter:.3f}")
    lines.append(f"      整体平均路径长度: {avg_path_length:.3f}")
    
    # 计算趋势
    diameter_values = [m.get("diameter", 0) for m in sorted_metrics]
    path_values = [m.get("average_path_length", 0) for m in sorted_metrics]
    
    if len(diameter_values) >= 3:
        early_dia_avg = sum(diameter_values[:3]) / min(3, len(diameter_values))
        recent_dia_avg = sum(diameter_values[-3:]) / min(3, len(diameter_values))
        change_dia = recent_dia_avg - early_dia_avg
        
        early_path_avg = sum(path_values[:3]) / min(3, len(path_values))
        recent_path_avg = sum(path_values[-3:]) / min(3, len(path_values))
        change_path = recent_path_avg - early_path_avg
        
        lines.append(f"      早期3月平均直径: {early_dia_avg:.2f}  →  近期3月平均直径: {recent_dia_avg:.2f}")
        if change_dia < -0.1:
            lines.append(f"      ✅ 直径减小，效率提升 (减少 {abs(change_dia):.2f})")
        elif change_dia > 0.1:
            lines.append(f"      ⚠️ 直径增大，效率下降 (增加 {change_dia:.2f})")
        else:
            lines.append(f"      ➡️ 直径保持稳定")
        
        lines.append(f"      早期3月平均路径: {early_path_avg:.2f}  →  近期3月平均路径: {recent_path_avg:.2f}")
        if change_path < -0.1:
            lines.append(f"      ✅ 路径缩短，效率提升 (减少 {abs(change_path):.2f})")
        elif change_path > 0.1:
            lines.append(f"      ⚠️ 路径增长，效率下降 (增加 {change_path:.2f})")
        else:
            lines.append(f"      ➡️ 路径保持稳定")
    
    # 解释归一化逻辑
    diameter_decay_factor = 0.3
    path_decay_factor = 0.4
    
    if avg_diameter <= 1.0:
        dia_norm = 1.0
        dia_explanation = "1.0 (直径≤1，最优)"
    else:
        dia_norm = 1.0 / (1.0 + diameter_decay_factor * (avg_diameter - 1.0))
        dia_norm = max(0.05, dia_norm)
        dia_explanation = f"{dia_norm:.3f} (对数衰减，衰减因子={diameter_decay_factor})"
    
    if avg_path_length <= 1.0:
        path_norm = 1.0
        path_explanation = "1.0 (路径≤1，最优)"
    else:
        path_norm = 1.0 / (1.0 + path_decay_factor * (avg_path_length - 1.0))
        path_norm = max(0.05, path_norm)
        path_explanation = f"{path_norm:.3f} (对数衰减，衰减因子={path_decay_factor})"
    
    network_norm = 0.5 * dia_norm + 0.5 * path_norm
    
    lines.append(f"   ➡️ 因子得分: {network_score:.2f} / 40")
    lines.append(f"      直径归一化: {dia_explanation}")
    lines.append(f"      路径归一化: {path_explanation}")
    lines.append(f"      综合归一化: {network_norm:.3f} (直径50% + 路径50%)")
    lines.append(f"      (归一化公式: 对数衰减函数，避免硬截断)")
    
    # 汇总
    lines.append("\n" + "-" * 80)
    lines.append("📋 评分汇总")
    lines.append("-" * 80)
    
    emotion_score = factors.get("emotion", {}).get("score", 0)
    clustering_score = factors.get("clustering", {}).get("score", 0)
    network_score = factors.get("network_efficiency", {}).get("score", 0)
    
    lines.append(f"   情绪氛围因子:     {emotion_score:6.2f} / 20  (权重20%)")
    lines.append(f"   社区紧密度因子:    {clustering_score:6.2f} / 40  (权重40%)")
    lines.append(f"   网络效率因子:      {network_score:6.2f} / 40  (权重40%)")
    lines.append(f"   " + "-" * 30)
    lines.append(f"   总分:              {score:6.2f} / 100")
    
    # 月度趋势
    lines.append("\n" + "-" * 80)
    lines.append("📅 月度指标趋势")
    lines.append("-" * 80)
    lines.append(f"   {'月份':<10} {'情绪':>8} {'聚类系数':>10} {'直径':>8} {'路径长度':>10} {'节点数':>8} {'边数':>8}")
    lines.append("   " + "-" * 70)
    
    for m in sorted_metrics:
        month = m.get("month", "N/A")
        emotion = m.get("average_emotion", 0)
        clustering = m.get("average_local_clustering", 0)
        diameter = m.get("diameter", 0)
        path_length = m.get("average_path_length", 0)
        nodes = m.get("actor_graph_nodes", 0)
        edges = m.get("actor_graph_edges", 0)
        lines.append(f"   {month:<10} {emotion:>+8.3f} {clustering:>10.3f} {diameter:>8.1f} {path_length:>10.2f} {nodes:>8} {edges:>8}")
    
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
    
    # 按氛围评分排序
    repos_with_scores = []
    for repo in repos_to_analyze:
        score = data[repo].get("atmosphere_score", {}).get("score", 0)
        repos_with_scores.append((repo, score))
    
    repos_with_scores.sort(key=lambda x: x[1], reverse=True)
    
    # 筛选条件
    if args.min_score is not None:
        repos_with_scores = [(r, s) for r, s in repos_with_scores if s >= args.min_score]
    
    if args.max_score is not None:
        repos_with_scores = [(r, s) for r, s in repos_with_scores if s <= args.max_score]
    
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
        print("\n📋 前 3 个项目预览:\n")
        for repo, score in repos_with_scores[:3]:
            print(generate_repo_report(repo, data[repo]))


if __name__ == "__main__":
    main()
