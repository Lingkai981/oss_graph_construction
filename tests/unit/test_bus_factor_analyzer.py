"""
Bus Factor 分析器单元测试
"""

import json
import tempfile
import unittest
from pathlib import Path

import networkx as nx

from src.analysis.bus_factor_analyzer import BusFactorAnalyzer
from src.models.bus_factor import MonthlyRiskMetrics


class TestBusFactorAnalyzer(unittest.TestCase):
    """Bus Factor 分析器测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.graphs_dir = Path(self.temp_dir) / "graphs"
        self.output_dir = Path(self.temp_dir) / "output"
        self.graphs_dir.mkdir(parents=True)
        self.output_dir.mkdir(parents=True)
        
        # 创建测试图
        self.test_graph = self._create_test_graph()
        self.test_graph_path = self.graphs_dir / "test_repo" / "actor-repo" / "2023-01.graphml"
        self.test_graph_path.parent.mkdir(parents=True)
        nx.write_graphml(self.test_graph, self.test_graph_path)
        
        # 创建索引文件
        index_file = self.graphs_dir / "index.json"
        index_data = {
            "test_repo": {
                "actor-repo": {
                    "2023-01": str(self.test_graph_path.relative_to(self.graphs_dir))
                }
            }
        }
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index_data, f)
    
    def _create_test_graph(self) -> nx.MultiDiGraph:
        """创建测试图"""
        graph = nx.MultiDiGraph()
        # 添加节点
        graph.add_node("actor:1", login="user1")
        graph.add_node("actor:2", login="user2")
        graph.add_node("repo:1", name="test_repo")
        # 添加边
        graph.add_edge("actor:1", "repo:1", key="e1", commit_count=10, pr_merged=1)
        graph.add_edge("actor:2", "repo:1", key="e2", commit_count=5)
        return graph
    
    def test_load_graph(self):
        """测试加载图"""
        analyzer = BusFactorAnalyzer(
            graphs_dir=str(self.graphs_dir),
            output_dir=str(self.output_dir),
        )
        graph = analyzer.load_graph(str(self.test_graph_path))
        self.assertIsNotNone(graph)
        self.assertEqual(graph.number_of_nodes(), 3)
        self.assertEqual(graph.number_of_edges(), 2)
    
    def test_load_graph_nonexistent(self):
        """测试加载不存在的图"""
        analyzer = BusFactorAnalyzer(
            graphs_dir=str(self.graphs_dir),
            output_dir=str(self.output_dir),
        )
        graph = analyzer.load_graph("nonexistent.graphml")
        self.assertIsNone(graph)
    
    def test_compute_monthly_metrics(self):
        """测试计算月度指标"""
        analyzer = BusFactorAnalyzer(
            graphs_dir=str(self.graphs_dir),
            output_dir=str(self.output_dir),
        )
        metrics = analyzer.compute_monthly_metrics(
            self.test_graph,
            "test_repo",
            "2023-01",
        )
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.month, "2023-01")
        self.assertEqual(metrics.repo_name, "test_repo")
        self.assertGreater(metrics.bus_factor, 0)
        self.assertGreater(metrics.total_contribution, 0)
        self.assertGreater(metrics.contributor_count, 0)
    
    def test_compute_monthly_metrics_empty_graph(self):
        """测试空图"""
        analyzer = BusFactorAnalyzer(
            graphs_dir=str(self.graphs_dir),
            output_dir=str(self.output_dir),
        )
        empty_graph = nx.MultiDiGraph()
        metrics = analyzer.compute_monthly_metrics(
            empty_graph,
            "test_repo",
            "2023-01",
        )
        self.assertIsNone(metrics)
    
    def test_compute_monthly_metrics_no_edges(self):
        """测试没有边的图"""
        analyzer = BusFactorAnalyzer(
            graphs_dir=str(self.graphs_dir),
            output_dir=str(self.output_dir),
        )
        graph = nx.MultiDiGraph()
        graph.add_node("actor:1", login="user1")
        graph.add_node("repo:1", name="test_repo")
        metrics = analyzer.compute_monthly_metrics(
            graph,
            "test_repo",
            "2023-01",
        )
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.bus_factor, 0)
        self.assertEqual(metrics.total_contribution, 0.0)
        self.assertEqual(metrics.contributor_count, 0)
    
    def test_save_single_result(self):
        """测试保存单个月份结果"""
        analyzer = BusFactorAnalyzer(
            graphs_dir=str(self.graphs_dir),
            output_dir=str(self.output_dir),
        )
        metrics = analyzer.compute_monthly_metrics(
            self.test_graph,
            "test_repo",
            "2023-01",
        )
        self.assertIsNotNone(metrics)
        
        output_file = self.output_dir / "test_output.json"
        analyzer.save_single_result(metrics, str(output_file))
        
        self.assertTrue(output_file.exists())
        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["month"], "2023-01")
        self.assertEqual(data["repo_name"], "test_repo")
    
    def test_load_index(self):
        """测试加载索引"""
        analyzer = BusFactorAnalyzer(
            graphs_dir=str(self.graphs_dir),
            output_dir=str(self.output_dir),
        )
        index = analyzer.load_index()
        self.assertIn("test_repo", index)
    
    def test_calculate_trend(self):
        """测试趋势计算"""
        # 上升趋势
        values = [1, 2, 3, 4, 5]
        trend = BusFactorAnalyzer.calculate_trend(values)
        self.assertEqual(trend["direction"], "上升")
        self.assertGreater(trend["slope"], 0)
        
        # 下降趋势
        values = [5, 4, 3, 2, 1]
        trend = BusFactorAnalyzer.calculate_trend(values)
        self.assertEqual(trend["direction"], "下降")
        self.assertLess(trend["slope"], 0)
        
        # 数据不足
        values = [1]
        trend = BusFactorAnalyzer.calculate_trend(values)
        self.assertEqual(trend["direction"], "数据不足")
    
    def test_calculate_risk_score(self):
        """测试风险评分计算"""
        # 低风险：Bus Factor 很高（接近最大值），趋势上升
        # Bus Factor = 40，在 1-50 范围内归一化为 0.796，当前值得分 = (1-0.796)*50 = 10.2
        # 趋势上升，change_rate = 10.0，趋势得分 = 25.0 - 10.0*0.2 = 23.0
        # 总评分 = 10.2 + 23.0 = 33.2 < 40，应该是"低"
        score = BusFactorAnalyzer.calculate_risk_score(
            current_bus_factor=40,
            trend_direction="上升",
            trend_change_rate=10.0,
            min_bus_factor=1.0,
            max_bus_factor=50.0,
        )
        self.assertLess(score["total_score"], 40)  # 应该是低风险
        self.assertEqual(score["risk_level"], "低")
        self.assertLess(score["current_score"], 15)  # 当前值得分应该很低
        self.assertLess(score["trend_score"], 25)  # 趋势得分应该低于基准值（因为上升是好事）
        
        # 高风险：Bus Factor 很低，趋势下降
        # Bus Factor = 2，在 1-50 范围内归一化为 0.020，当前值得分 = (1-0.020)*50 = 49.0
        # 趋势下降，change_rate = -20.0，趋势得分 = 25.0 + 20.0*0.2 = 29.0
        # 总评分 = 49.0 + 29.0 = 78.0 > 70，应该是"高"
        score = BusFactorAnalyzer.calculate_risk_score(
            current_bus_factor=2,
            trend_direction="下降",
            trend_change_rate=-20.0,
            min_bus_factor=1.0,
            max_bus_factor=50.0,
        )
        self.assertGreater(score["total_score"], 70)  # 应该是高风险
        self.assertEqual(score["risk_level"], "高")
        self.assertGreater(score["current_score"], 45)  # 当前值得分应该很高
        self.assertGreater(score["trend_score"], 25)  # 趋势得分应该高于基准值（因为下降是坏事）
        
        # 中等风险：Bus Factor 中等，趋势稳定
        # Bus Factor = 10，在 1-50 范围内归一化为 0.184，当前值得分 = (1-0.184)*50 = 40.8
        # 趋势稳定，趋势得分 = 25.0
        # 总评分 = 40.8 + 25.0 = 65.8，应该是"中"
        score = BusFactorAnalyzer.calculate_risk_score(
            current_bus_factor=10,
            trend_direction="稳定",
            trend_change_rate=0.0,
            min_bus_factor=1.0,
            max_bus_factor=50.0,
        )
        self.assertGreaterEqual(score["total_score"], 40)
        self.assertLessEqual(score["total_score"], 70)
        self.assertEqual(score["risk_level"], "中")


if __name__ == "__main__":
    unittest.main()

