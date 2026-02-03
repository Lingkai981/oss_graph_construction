"""
Bus Factor 计算算法单元测试
"""

import math
import unittest
from collections import defaultdict

import networkx as nx

from src.algorithms.bus_factor_calculator import (
    aggregate_contributions,
    calculate_bus_factor,
    calculate_contribution,
    DEFAULT_WEIGHTS,
)


class TestBusFactorCalculator(unittest.TestCase):
    """Bus Factor 计算算法测试"""
    
    def test_calculate_bus_factor_empty(self):
        """测试空贡献量字典"""
        result = calculate_bus_factor({}, 0.5)
        self.assertEqual(result, 0)
    
    def test_calculate_bus_factor_single_contributor(self):
        """测试单个贡献者"""
        contributions = {1: 100.0}
        result = calculate_bus_factor(contributions, 0.5)
        self.assertEqual(result, 1)
    
    def test_calculate_bus_factor_equal_contributions(self):
        """测试贡献量完全相等的情况"""
        contributions = {1: 10.0, 2: 10.0, 3: 10.0, 4: 10.0}
        # 需要2个贡献者达到50%
        result = calculate_bus_factor(contributions, 0.5)
        self.assertEqual(result, 2)
    
    def test_calculate_bus_factor_unequal_contributions(self):
        """测试贡献量不相等的情况"""
        contributions = {1: 50.0, 2: 30.0, 3: 10.0, 4: 10.0}
        # 总贡献量 = 100
        # 目标 = 50
        # 排序: 1(50) -> 达到50，需要1个
        result = calculate_bus_factor(contributions, 0.5)
        self.assertEqual(result, 1)
    
    def test_calculate_bus_factor_custom_threshold(self):
        """测试自定义阈值"""
        contributions = {1: 30.0, 2: 30.0, 3: 20.0, 4: 20.0}
        # 总贡献量 = 100
        # 阈值 0.6 -> 目标 = 60
        # 排序: 1(30) + 2(30) = 60，需要2个
        result = calculate_bus_factor(contributions, 0.6)
        self.assertEqual(result, 2)
    
    def test_calculate_bus_factor_zero_total(self):
        """测试总贡献量为0的情况"""
        contributions = {1: 0.0, 2: 0.0}
        result = calculate_bus_factor(contributions, 0.5)
        self.assertEqual(result, 0)
    
    def test_calculate_bus_factor_invalid_threshold(self):
        """测试无效阈值"""
        contributions = {1: 10.0}
        with self.assertRaises(ValueError):
            calculate_bus_factor(contributions, 1.5)
        with self.assertRaises(ValueError):
            calculate_bus_factor(contributions, -0.1)
    
    def test_calculate_contribution_default_weights(self):
        """测试使用默认权重计算贡献量"""
        edge_data = {
            "commit_count": 10,
            "pr_merged": 2,
            "pr_opened": 5,
            "pr_closed": 1,
            "issue_opened": 3,
            "issue_closed": 2,
            "is_comment": 20,
        }
        result = calculate_contribution(edge_data)
        expected = (
            10 * 1.0 +      # commit_count
            2 * 5.0 +        # pr_merged
            5 * 2.0 +        # pr_opened
            1 * 1.0 +        # pr_closed
            3 * 1.5 +        # issue_opened
            2 * 2.0 +        # issue_closed
            20 * 0.5         # is_comment
        )
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_calculate_contribution_custom_weights(self):
        """测试使用自定义权重计算贡献量"""
        edge_data = {"commit_count": 10, "pr_merged": 2}
        custom_weights = {"commit_count": 2.0, "pr_merged": 10.0}
        result = calculate_contribution(edge_data, custom_weights)
        expected = 10 * 2.0 + 2 * 10.0
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_calculate_contribution_missing_fields(self):
        """测试缺少某些字段的情况"""
        edge_data = {"commit_count": 10}
        result = calculate_contribution(edge_data)
        expected = 10 * 1.0
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_aggregate_contributions_empty_graph(self):
        """测试空图"""
        graph = nx.MultiDiGraph()
        result = aggregate_contributions(graph)
        self.assertEqual(len(result), 0)
    
    def test_aggregate_contributions_single_contributor(self):
        """测试单个贡献者"""
        graph = nx.MultiDiGraph()
        graph.add_node("actor:1", login="user1")
        graph.add_node("repo:1", name="repo1")
        graph.add_edge(
            "actor:1",
            "repo:1",
            key="e1",
            commit_count=10,
            pr_merged=1,
        )
        result = aggregate_contributions(graph)
        self.assertEqual(len(result), 1)
        self.assertIn(1, result)
        self.assertEqual(result[1].contributor_id, 1)
        self.assertEqual(result[1].login, "user1")
        self.assertGreater(result[1].total_contribution, 0)
        self.assertAlmostEqual(result[1].contribution_ratio, 1.0, places=2)
    
    def test_aggregate_contributions_multiple_contributors(self):
        """测试多个贡献者"""
        graph = nx.MultiDiGraph()
        graph.add_node("actor:1", login="user1")
        graph.add_node("actor:2", login="user2")
        graph.add_node("repo:1", name="repo1")
        graph.add_edge("actor:1", "repo:1", key="e1", commit_count=10)
        graph.add_edge("actor:2", "repo:1", key="e2", commit_count=5)
        result = aggregate_contributions(graph)
        self.assertEqual(len(result), 2)
        # 验证贡献占比
        total = sum(c.total_contribution for c in result.values())
        for contrib in result.values():
            expected_ratio = contrib.total_contribution / total
            self.assertAlmostEqual(contrib.contribution_ratio, expected_ratio, places=2)
    
    def test_aggregate_contributions_ignores_non_actor_repo_edges(self):
        """测试忽略非 actor-repo 边"""
        graph = nx.MultiDiGraph()
        graph.add_node("actor:1", login="user1")
        graph.add_node("repo:1", name="repo1")
        graph.add_node("other:1", name="other")
        # 添加 actor-repo 边
        graph.add_edge("actor:1", "repo:1", key="e1", commit_count=10)
        # 添加其他类型的边（应该被忽略）
        graph.add_edge("repo:1", "other:1", key="e2", commit_count=5)
        result = aggregate_contributions(graph)
        # 应该只有 actor:1 的贡献
        self.assertEqual(len(result), 1)
        self.assertIn(1, result)
        # 贡献量应该只包含 actor-repo 边
        self.assertAlmostEqual(result[1].total_contribution, 10.0, places=2)


if __name__ == "__main__":
    unittest.main()

