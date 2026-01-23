"""
社区氛围分析报告生成器

根据 full_analysis.json 和 summary.json 生成详细的社区氛围分析报告。
类似倦怠者分析报告，包含概述、项目对比、指标分析和建议。
"""

import json
from pathlib import Path
from typing import Dict, Any, List
import matplotlib.pyplot as plt
import pandas as pd

class AtmosphereReportGenerator:
    """社区氛围分析报告生成器"""

    def __init__(self, full_analysis_path: str, summary_path: str, output_path: str):
        self.full_analysis_path = Path(full_analysis_path)
        self.summary_path = Path(summary_path)
        self.output_path = Path(output_path)
        self.full_data: Dict[str, Any] = {}
        self.summary_data: List[Dict[str, Any]] = []

    def load_data(self):
        """加载分析数据"""
        try:
            with open(self.full_analysis_path, 'r', encoding='utf-8') as f:
                self.full_data = json.load(f)
            with open(self.summary_path, 'r', encoding='utf-8') as f:
                self.summary_data = json.load(f)
            print(f"数据加载成功: {len(self.full_data)} 个项目的详细数据, {len(self.summary_data)} 个项目摘要")
        except Exception as e:
            print(f"数据加载失败: {e}")
            return False
        return True

    def generate_report(self) -> str:
        """生成 Markdown 格式的报告"""
        if not self.full_data or not self.summary_data:
            return "# 社区氛围分析报告\n\n数据加载失败，无法生成报告。"

        report = []

        # 标题
        report.append("# 社区氛围分析报告")
        report.append("")
        report.append("## 概述")
        report.append("")
        report.append("本报告基于社区氛围分析系统生成，评估开源项目的社区健康度。")
        report.append("分析指标包括情绪传播、聚类系数、网络直径等，综合评分范围 0-100。")
        report.append("")

        # 整体统计
        total_projects = len(self.summary_data)
        avg_score = sum(p['atmosphere_score'] for p in self.summary_data) / total_projects
        levels = [p['level'] for p in self.summary_data]
        level_counts = {level: levels.count(level) for level in set(levels)}

        report.append("### 整体统计")
        report.append(f"- 分析项目数: {total_projects}")
        report.append(f"- 平均综合评分: {avg_score:.2f}")
        report.append(f"- 评分等级分布: {level_counts}")
        report.append("")

        # 项目排名
        report.append("### 项目综合评分排名")
        report.append("")
        sorted_projects = sorted(self.summary_data, key=lambda x: x['atmosphere_score'], reverse=True)
        for i, project in enumerate(sorted_projects, 1):
            report.append(f"{i}. **{project['repo_name']}**: {project['atmosphere_score']:.2f} ({project['level']}, {project['months_analyzed']} 个月)")
        report.append("")

        # 详细项目分析
        report.append("## 详细项目分析")
        report.append("")

        for project in sorted_projects:
            repo_name = project['repo_name']
            if repo_name not in self.full_data:
                continue

            repo_data = self.full_data[repo_name]
            if not isinstance(repo_data, list):
                print(f"警告: {repo_name} 的数据格式错误，跳过")
                continue

            report.append(f"### {repo_name}")
            report.append("")
            report.append(f"- **综合评分**: {project['atmosphere_score']:.2f} ({project['level']})")
            report.append(f"- **分析月份**: {project['months_analyzed']}")
            report.append("")

            # 情绪分析
            emotions = [month['average_emotion'] for month in repo_data if 'average_emotion' in month]
            if emotions:
                avg_emotion = sum(emotions) / len(emotions)
                min_emotion = min(emotions)
                max_emotion = max(emotions)
                report.append("#### 情绪分析")
                report.append(f"- 平均情绪: {avg_emotion:.3f} (范围: {min_emotion:.3f} 到 {max_emotion:.3f})")
                report.append(f"- 情绪趋势: {'稳定' if max_emotion - min_emotion < 0.1 else '波动较大'}")
                report.append("")

            # 结构分析
            clustering = [month.get('global_clustering_coefficient', 0) for month in repo_data]
            diameters = [month.get('diameter', 0) for month in repo_data]
            path_lengths = [month.get('average_path_length', 0) for month in repo_data]

            if clustering:
                avg_clustering = sum(clustering) / len(clustering)
                report.append("#### 结构分析")
                report.append(f"- 平均聚类系数: {avg_clustering:.3f} ({'紧密' if avg_clustering > 0.3 else '松散'})")
                report.append(f"- 平均网络直径: {sum(diameters)/len(diameters):.1f}")
                report.append(f"- 平均路径长度: {sum(path_lengths)/len(path_lengths):.2f}")
                report.append("")

            # 月度趋势
            report.append("#### 月度趋势")
            report.append("")
            report.append("| 月份 | 情绪 | 聚类系数 | 直径 | 路径长度 |")
            report.append("|------|------|----------|------|----------|")
            for month in repo_data[-5:]:  # 最近5个月
                month_name = month.get('month', '未知')
                emotion = month.get('average_emotion', 0)
                clustering = month.get('global_clustering_coefficient', 0)
                diameter = month.get('diameter', 0)
                path_length = month.get('average_path_length', 0)
                report.append(f"| {month_name} | {emotion:.3f} | {clustering:.3f} | {diameter} | {path_length:.2f} |")
            report.append("")

        # 指标解释
        report.append("## 指标解释")
        report.append("")
        report.append("### 情绪分析")
        report.append("- **average_emotion**: 社区平均情绪值 (-1 到 1)，越高表示越正面。")
        report.append("- **传播模型**: 使用 PageRank-like 算法模拟情绪在社区中的传播。")
        report.append("")
        report.append("### 结构分析")
        report.append("- **global_clustering_coefficient**: 全局聚类系数 (0-1)，衡量社区紧密程度。")
        report.append("- **diameter**: 网络直径，衡量沟通效率（越小越好）。")
        report.append("- **average_path_length**: 平均最短路径长度，反映信息传播速度。")
        report.append("")
        report.append("### 综合评分")
        report.append("- 基于情绪 (40%)、聚类 (30%)、直径 (20%)、路径长度 (10%) 加权计算。")
        report.append("- 等级: excellent (≥80), good (≥60), moderate (≥40), poor (<40)。")
        report.append("")

        # 建议
        report.append("## 建议")
        report.append("")
        report.append("### 提升社区氛围")
        report.append("- **增加互动**: 鼓励更多正面讨论，提升情绪得分。")
        report.append("- **加强连接**: 组织活动或小组，促进聚类系数提升。")
        report.append("- **优化沟通**: 减少信息孤岛，降低网络直径。")
        report.append("")
        report.append("### 系统改进")
        report.append("- 优化情绪分析提示词，提高区分度。")
        report.append("- 添加更多指标，如活跃度和多样性。")
        report.append("- 定期监控月度趋势，及时干预。")
        report.append("")

        return "\n".join(report)

    def save_report(self, report_content: str):
        """保存报告到文件"""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        print(f"报告已保存到: {self.output_path}")

    def generate_chart(self):
        """生成简单图表（可选）"""
        if not self.summary_data:
            return

        # 评分柱状图
        repos = [p['repo_name'] for p in self.summary_data]
        scores = [p['atmosphere_score'] for p in self.summary_data]

        plt.figure(figsize=(10, 6))
        plt.bar(repos, scores, color='skyblue')
        plt.title('项目综合评分对比')
        plt.xlabel('项目')
        plt.ylabel('评分')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(self.output_path.parent / 'atmosphere_scores.png')
        plt.close()
        print("图表已保存: atmosphere_scores.png")

def main():
    """主函数"""
    generator = AtmosphereReportGenerator(
        full_analysis_path="output/community-atmosphere-analysis/full_analysis.json",
        summary_path="output/community-atmosphere-analysis/summary.json",
        output_path="output/community-atmosphere-analysis/atmosphere_report.md"
    )

    if generator.load_data():
        report = generator.generate_report()
        generator.save_report(report)
        generator.generate_chart()
        print("社区氛围分析报告生成完成！")

if __name__ == "__main__":
    main()