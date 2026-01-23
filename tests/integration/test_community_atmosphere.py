# tests/integration/test_community_atmosphere.py
"""
社区氛围分析集成测试
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
import networkx as nx

from src.analysis.community_atmosphere_analyzer import CommunityAtmosphereAnalyzer


@pytest.fixture
def mock_deepseek_client():
    """Mock DeepSeek客户端，避免消耗token"""
    with patch('src.analysis.community_atmosphere_analyzer.DeepSeekClient') as mock_class:
        # 模拟返回正面的情感分数（float类型，不是字典）
        mock_instance = Mock()
        mock_instance.analyze_sentiment.return_value = 0.7  # 返回float，不是字典
        mock_instance.is_available.return_value = True
        mock_class.return_value = mock_instance
        yield mock_instance


def test_analyze_all_projects_with_real_graphs(mock_deepseek_client, tmp_path):
    """使用真实的图文件测试所有项目的完整流程"""
    graphs_dir = Path("output/monthly-graphs")
    output_dir = tmp_path / "community-atmosphere"
    
    if not graphs_dir.exists():
        pytest.skip("图文件目录不存在，跳过测试")
    
    # 检查是否有index.json
    index_file = graphs_dir / "index.json"
    if not index_file.exists():
        pytest.skip("index.json不存在，跳过测试")
    
    analyzer = CommunityAtmosphereAnalyzer(
        graphs_dir=str(graphs_dir),
        output_dir=str(output_dir)
    )
    
    # 运行分析
    results = analyzer.analyze_all_repos()
    
    # 保存结果
    analyzer.save_results(results)
    
    # 验证结果
    assert len(results) > 0, "应该至少分析一个项目"
    
    # 验证每个项目的结果结构
    for repo_name, project_result in results.items():
        assert "metrics" in project_result, f"项目 {repo_name} 缺少 metrics"
        assert "atmosphere_score" in project_result, f"项目 {repo_name} 缺少 atmosphere_score"
        assert len(project_result["metrics"]) > 0, f"项目 {repo_name} 没有月度指标"
        
        # 验证atmosphere_score结构
        score = project_result["atmosphere_score"]
        assert "score" in score, f"项目 {repo_name} 的评分缺少 score 字段"
        assert "level" in score, f"项目 {repo_name} 的评分缺少 level 字段"
        assert 0 <= score["score"] <= 100, f"项目 {repo_name} 的评分超出范围"
        
        # 验证metrics结构
        for metric in project_result["metrics"]:
            assert "month" in metric, "月度指标缺少 month 字段"
            assert "repo_name" in metric, "月度指标缺少 repo_name 字段"
            assert "average_emotion" in metric, "月度指标缺少 average_emotion 字段"
            assert "global_clustering_coefficient" in metric, "月度指标缺少 global_clustering_coefficient 字段"
            assert "diameter" in metric, "月度指标缺少 diameter 字段"
    
    # 验证输出文件
    assert (output_dir / "full_analysis.json").exists(), "应该生成 full_analysis.json"
    assert (output_dir / "summary.json").exists(), "应该生成 summary.json"
    
    # 验证mock被调用（说明情感分析确实执行了）
    assert mock_deepseek_client.analyze_sentiment.called, "应该调用情感分析API"
    
    # 输出统计信息
    print(f"\n成功分析 {len(results)} 个项目")
    total_months = sum(len(r["metrics"]) for r in results.values())
    print(f"总共分析了 {total_months} 个月的数据")
def test_analyze_single_month(mock_deepseek_client, tmp_path):
    """测试单个月份的图分析"""
    graph_file = Path("output/monthly-graphs/angular-angular/actor-discussion/2023-01.graphml")
    
    if not graph_file.exists():
        pytest.skip("图文件不存在，跳过测试")
    
    analyzer = CommunityAtmosphereAnalyzer(
        graphs_dir=str(graph_file.parent.parent),
        output_dir=str(tmp_path)
    )
    
    # 加载图
    graph = analyzer.load_graph(str(graph_file))
    assert graph is not None
    assert graph.number_of_nodes() > 0
    
    # 计算指标
    metrics = analyzer.compute_monthly_metrics(graph, "angular/angular", "2023-01")
    assert metrics is not None
    assert metrics.month == "2023-01"
    assert metrics.repo_name == "angular/angular"
    
    # 验证指标值存在（即使为0也是有效值）
    assert hasattr(metrics, "average_emotion")
    assert hasattr(metrics, "global_clustering_coefficient")
    assert hasattr(metrics, "diameter")
    
    # 验证情感分析被调用（如果有comment_body的话）
    if any(data.get('comment_body') for _, _, data in graph.edges(data=True)):
        assert mock_deepseek_client.analyze_sentiment.called


def test_extract_sentiment_from_comments(mock_deepseek_client, tmp_path):
    """测试情感提取功能"""
    # 创建一个简单的测试图
    graph = nx.MultiDiGraph()
    graph.add_node("actor1", node_type="Actor")
    graph.add_node("issue1", node_type="Issue")
    graph.add_edge("actor1", "issue1", comment_body="Great work! Thanks!")
    graph.add_edge("actor1", "issue1", comment_body="This is awesome!")
    
    analyzer = CommunityAtmosphereAnalyzer(
        graphs_dir=str(tmp_path),
        output_dir=str(tmp_path)
    )
    
    # 提取情感分数
    sentiment_scores = analyzer.extract_sentiment_from_comments(graph)
    
    # 验证结果
    assert len(sentiment_scores) > 0
    # 验证每个分数都在合理范围内
    for edge_id, score in sentiment_scores.items():
        assert -1.0 <= score <= 1.0, f"情感分数 {score} 超出范围"
    
    # 验证mock被调用
    assert mock_deepseek_client.analyze_sentiment.called
    # 应该被调用2次（因为有2条边有comment_body）
    assert mock_deepseek_client.analyze_sentiment.call_count == 2

