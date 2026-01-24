"""
Bus Factor 分析集成测试

测试完整的分析流程，包括：
1. 加载图文件
2. 计算月度指标
3. 时间序列分析
4. 趋势计算
5. 风险评分
6. 结果保存

使用真实的图文件进行测试（如果存在）。
"""

import json
import tempfile
import unittest
from pathlib import Path

from src.analysis.bus_factor_analyzer import BusFactorAnalyzer


class TestBusFactorIntegration(unittest.TestCase):
    """Bus Factor 分析集成测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.graphs_dir = Path("output/monthly-graphs")
        self.output_dir = Path(tempfile.mkdtemp()) / "output"
        self.output_dir.mkdir(parents=True)
        
        # 检查图文件目录是否存在
        if not self.graphs_dir.exists():
            self.skipTest("图文件目录不存在，跳过测试")
        
        # 检查索引文件是否存在
        index_file = self.graphs_dir / "index.json"
        if not index_file.exists():
            self.skipTest("index.json不存在，跳过测试")
        
        # 加载索引，获取第一个项目用于测试
        with open(index_file, "r", encoding="utf-8") as f:
            self.index = json.load(f)
        
        if not self.index:
            self.skipTest("索引文件为空，跳过测试")
        
        # 选择第一个项目进行测试
        self.repo_name = next(iter(self.index.keys()))
    
    def test_full_analysis_workflow(self):
        """测试完整分析流程"""
        analyzer = BusFactorAnalyzer(
            graphs_dir=str(self.graphs_dir),
            output_dir=str(self.output_dir),
        )
        
        # 运行完整分析
        results = analyzer.run(resume=False)
        
        # 验证结果不为空
        self.assertGreater(len(results), 0, "应该至少分析一个项目")
        
        # 验证第一个项目的结果结构
        if self.repo_name in results:
            repo_data = results[self.repo_name]
            
            # 验证月度指标
            self.assertIn("metrics", repo_data)
            metrics = repo_data["metrics"]
            self.assertGreater(len(metrics), 0, "应该至少有一个月份的指标")
            
            # 验证每个月份的指标
            for metric in metrics:
                self.assertIn("month", metric)
                self.assertIn("bus_factor", metric)
                self.assertIn("total_contribution", metric)
                self.assertIn("contributor_count", metric)
                self.assertGreaterEqual(metric["bus_factor"], 0)
            
            # 验证趋势分析（如果有多个月份）
            if len(metrics) >= 2:
                self.assertIn("trend", repo_data)
                trend = repo_data["trend"]
                self.assertIn("bus_factor_trend", trend)
                self.assertIn("direction", trend["bus_factor_trend"])
                self.assertIn("slope", trend["bus_factor_trend"])
            
            # 验证风险评分
            self.assertIn("risk_score", repo_data)
            risk_score = repo_data["risk_score"]
            self.assertIn("total_score", risk_score)
            self.assertIn("risk_level", risk_score)
            self.assertGreaterEqual(risk_score["total_score"], 0)
            self.assertLessEqual(risk_score["total_score"], 100)
        
        # 验证输出文件
        full_analysis_file = self.output_dir / "full_analysis.json"
        self.assertTrue(full_analysis_file.exists(), "应该生成完整分析文件")
        
        summary_file = self.output_dir / "summary.json"
        self.assertTrue(summary_file.exists(), "应该生成摘要文件")
        
        # 验证摘要文件
        with open(summary_file, "r", encoding="utf-8") as f:
            summary = json.load(f)
        self.assertIn("repos", summary)
        self.assertGreater(len(summary["repos"]), 0, "摘要应该包含至少一个项目")
    
    def test_single_repo_analysis(self):
        """测试单个项目的分析"""
        analyzer = BusFactorAnalyzer(
            graphs_dir=str(self.graphs_dir),
            output_dir=str(self.output_dir),
        )
        
        # 分析单个项目
        repo_data = self.index[self.repo_name]
        
        # 检查是否有 actor-repo 图
        if "actor-repo" not in repo_data:
            self.skipTest(f"项目 {self.repo_name} 没有 actor-repo 图，跳过测试")
        
        months = repo_data["actor-repo"]
        if not months:
            self.skipTest(f"项目 {self.repo_name} 没有月份数据，跳过测试")
        
        # 选择第一个月份进行测试
        first_month = sorted(months.keys())[0]
        graph_path = self.graphs_dir / months[first_month]
        
        if not graph_path.exists():
            self.skipTest(f"图文件不存在: {graph_path}")
        
        # 加载图并计算指标
        graph = analyzer.load_graph(str(graph_path))
        self.assertIsNotNone(graph, "应该能够加载图文件")
        
        metrics = analyzer.compute_monthly_metrics(graph, self.repo_name, first_month)
        self.assertIsNotNone(metrics, "应该能够计算月度指标")
        self.assertEqual(metrics.month, first_month)
        self.assertEqual(metrics.repo_name, self.repo_name)
        self.assertGreaterEqual(metrics.bus_factor, 0)


if __name__ == "__main__":
    unittest.main()

