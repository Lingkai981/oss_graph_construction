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


def recalculate_score(metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    """根据metrics列表重新计算评分 (4:3:3)"""
    if not metrics:
        return {"score": 0, "level": "unknown", "factors": {}}
    
    # 提取并映射字段
    tox_values = []
    resp_values = []
    close_values = []
    
    for m in metrics:
        # 毒性: toxicity_ratio 或 toxic_rate_0_5
        tox = m.get("toxicity_ratio")
        if tox is None:
            tox = m.get("toxic_rate_0_5", 0.0)
        tox_values.append(tox)
        
        # 响应时间: avg_response_time 或 time_to_first_response_mean
        resp = m.get("avg_response_time")
        if resp is None:
            resp = m.get("time_to_first_response_mean", 0.0)
        resp_values.append(resp)
        
        # 关闭率: closing_rate 或 change_request_closure_ratio
        close = m.get("closing_rate")
        if close is None:
            close = m.get("change_request_closure_ratio", 0.0)
        close_values.append(close)
    
    avg_toxicity = sum(tox_values) / len(tox_values)
    avg_response_time = sum(resp_values) / len(resp_values)
    avg_closing_rate = sum(close_values) / len(close_values)
    
    # 计算得分
    # 1) 毒性 (40%)
    toxicity_score_raw = max(0.0, 1.0 - avg_toxicity / 0.05) * 100
    toxicity_weighted = toxicity_score_raw * 0.40
    
    # 2) 响应时间 (30%)
    response_score_raw = 100.0 / (1.0 + avg_response_time / 48.0)
    response_weighted = response_score_raw * 0.30
    
    # 3) 关闭率 (30%)
    closing_score_raw = min(100.0, avg_closing_rate * 100.0)
    closing_weighted = closing_score_raw * 0.30
    
    total_score = toxicity_weighted + response_weighted + closing_weighted
    
    level = "poor"
    if total_score >= 80:
        level = "excellent"
    elif total_score >= 60:
        level = "good"
    elif total_score >= 40:
        level = "moderate"
        
    return {
        "score": total_score,
        "level": level,
        "factors": {
            "toxicity": {
                "value": avg_toxicity,
                "score": toxicity_score_raw,
                "weighted_score": toxicity_weighted
            },
            "response_time": {
                "value": avg_response_time,
                "score": response_score_raw,
                "weighted_score": response_weighted
            },
            "closing_rate": {
                "value": avg_closing_rate,
                "score": closing_score_raw,
                "weighted_score": closing_weighted
            }
        }
    }


def generate_repo_report(repo_name: str, repo_data: Dict[str, Any]) -> str:
    """生成单个仓库的详细报告"""
    lines = []
    lines.append("=" * 80)
    lines.append(f"📊 项目: {repo_name}")
    lines.append("=" * 80)
    
    # 获取指标时间序列
    metrics = repo_data.get("metrics", [])
    if len(metrics) < 2:
        lines.append("\n⚠️ 数据不足，无法进行趋势分析")
        return "\n".join(lines)
        
    # 重新计算评分 (覆盖原来的 atmosphere_score)
    atmosphere = recalculate_score(metrics)
    score = atmosphere.get("score", 0)
    level = atmosphere.get("level", "unknown")
    
    # 获取原来的元数据 (period, months)
    orig_atmosphere = repo_data.get("atmosphere_score", {})
    if not orig_atmosphere:
         orig_atmosphere = {}
    
    # 尝试从 metrics 推断
    months_list = [m.get("month") for m in metrics]
    months_list.sort()
    if months_list:
        period = f"{months_list[0]} to {months_list[-1]}"
        months = len(months_list)
    else:
        period = orig_atmosphere.get("period", "N/A")
        months = orig_atmosphere.get("months_analyzed", 0)
    
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
    
    # 按月份排序
    sorted_metrics = sorted(metrics, key=lambda m: m.get("month", ""))
    earliest = sorted_metrics[0]
    latest = sorted_metrics[-1]
    
    lines.append("\n" + "-" * 80)
    lines.append("📈 各因子详细分析（三大因子：毒性40% + 响应时间30% + 关闭率30%）")
    lines.append("-" * 80)
    
    factors = atmosphere.get("factors", {})
    
    # ========================================
    # 1. 毒性因子 (40%)
    # ========================================
    lines.append("\n【1. 毒性因子】(0-40分，权重40%)")
    tox_factor = factors.get("toxicity", {})
    
    # 收集数据
    tox_values = []
    for m in sorted_metrics:
        # 兼容新旧字段
        v = m.get("toxicity_ratio")
        if v is None:
            v = m.get("toxic_rate_0_5", 0.0)
        tox_values.append(v)
        
    avg_tox = tox_factor.get("value", 0)
    early_tox = tox_values[0]
    late_tox = tox_values[-1]
    
    lines.append(f"   📊 数据概览:")
    lines.append(f"      首月毒性占比: {early_tox:.2%}  →  末月毒性占比: {late_tox:.2%}")
    lines.append(f"      整体平均毒性: {avg_tox:.2%}")
    
    lines.append(f"   ➡️ 因子得分: {tox_factor.get('weighted_score', 0):.2f} / 40 (原始分: {tox_factor.get('score', 0):.2f})")
    lines.append(f"      (目标: 0%毒性 -> 100分)")

    # ========================================
    # 2. 响应时间因子 (30%)
    # ========================================
    lines.append("\n【2. 响应时间因子】(0-30分，权重30%)")
    resp_factor = factors.get("response_time", {})
    
    resp_values = []
    for m in sorted_metrics:
        v = m.get("avg_response_time")
        if v is None:
            v = m.get("time_to_first_response_mean") # 优先用 mean
        if v is None:
            v = m.get("time_to_first_response_median", 0.0)
        resp_values.append(v)
        
    avg_resp = resp_factor.get("value", 0)
    early_resp = resp_values[0]
    late_resp = resp_values[-1]
    
    lines.append(f"   📊 数据概览:")
    lines.append(f"      首月平均响应: {early_resp:.1f}h  →  末月平均响应: {late_resp:.1f}h")
    lines.append(f"      整体平均响应: {avg_resp:.1f}h")
    
    lines.append(f"   ➡️ 因子得分: {resp_factor.get('weighted_score', 0):.2f} / 30 (原始分: {resp_factor.get('score', 0):.2f})")

    # ========================================
    # 3. 关闭率因子 (30%)
    # ========================================
    lines.append("\n【3. 关闭率因子】(0-30分，权重30%)")
    close_factor = factors.get("closing_rate", {})
    
    close_values = []
    for m in sorted_metrics:
        v = m.get("closing_rate")
        if v is None:
            v = m.get("change_request_closure_ratio", 0.0)
        close_values.append(v)
        
    avg_close = close_factor.get("value", 0)
    early_close = close_values[0]
    late_close = close_values[-1]
    
    lines.append(f"   📊 数据概览:")
    lines.append(f"      首月关闭率: {early_close:.2%}  →  末月关闭率: {late_close:.2%}")
    lines.append(f"      整体平均关闭率: {avg_close:.2%}")
    
    lines.append(f"   ➡️ 因子得分: {close_factor.get('weighted_score', 0):.2f} / 30 (原始分: {close_factor.get('score', 0):.2f})")
    
    # ========================================
    # 评分汇总
    # ========================================
    lines.append("\n" + "-" * 80)
    lines.append("📋 评分汇总")
    lines.append("-" * 80)
    
    lines.append(f"   毒性因子:         {tox_factor.get('weighted_score', 0):.2f} / 40  (权重40%)")
    lines.append(f"   响应时间因子:      {resp_factor.get('weighted_score', 0):.2f} / 30  (权重30%)")
    lines.append(f"   关闭率因子:        {close_factor.get('weighted_score', 0):.2f} / 30  (权重30%)")
    lines.append(f"   " + "-" * 30)
    lines.append(f"   总分:               {score:.2f} / 100")
    
    # ========================================
    # 月度指标趋势
    # ========================================
    lines.append("\n" + "-" * 80)
    lines.append("📅 月度指标趋势")
    lines.append("-" * 80)
    
    # 表头
    lines.append(f"   {'月份':<10} {'毒性':>10} {'响应时间(h)':>15} {'关闭率':>12}")
    lines.append("   " + "-" * 70)
    
    for i, m in enumerate(sorted_metrics):
        month = m.get("month", "N/A")
        # Reuse collected values
        tox = tox_values[i]
        resp = resp_values[i]
        close = close_values[i]
        
        lines.append(f"   {month:<10} {tox:>10.2%} {resp:>15.1f} {close:>12.2%}")
    
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
        # 使用新的评分逻辑进行排序
        metrics = data[repo].get("metrics", [])
        new_atmosphere = recalculate_score(metrics)
        score = new_atmosphere.get("score", 0)
        level = new_atmosphere.get("level", "unknown")
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
    reports.append("   综合评分 = 毒性因子(40%) + 响应时间因子(30%) + 关闭率因子(30%)")
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
