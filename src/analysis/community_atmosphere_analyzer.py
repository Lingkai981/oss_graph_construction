"""
社区氛围分析器

分析指标：
1. 情感传播模型：分析情绪如何在社区中传播
2. 聚类系数：衡量社区紧密度
3. 网络直径：评估社区沟通效率

输出：
- 每个项目的月度指标时间序列
- 社区氛围综合评分
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import networkx as nx

from src.algorithms.clustering_coefficient import compute_clustering_coefficient
from src.algorithms.emotion_propagation import analyze_emotion_propagation
from src.algorithms.network_diameter import compute_network_diameter
from src.models.community_atmosphere import MonthlyAtmosphereMetrics
from src.services.sentiment.deepseek_client import DeepSeekClient
from src.utils.logger import setup_logger

# 为社区氛围分析器单独配置日志文件，所有运行过程日志写入 logs/community_atmosphere.log
logger = setup_logger(log_file="logs/community_atmosphere.log")


class CommunityAtmosphereAnalyzer:
    """社区氛围分析器"""
    
    def __init__(
        self,
        graphs_dir: str = "output/monthly-graphs/",
        output_dir: str = "output/community-atmosphere/",
    ):
        """
        初始化分析器
        
        Args:
            graphs_dir: 图文件目录
            output_dir: 输出目录
        """
        self.graphs_dir = Path(graphs_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 存储分析结果
        self.repo_metrics: Dict[str, List[MonthlyAtmosphereMetrics]] = defaultdict(list)
        
        # 初始化DeepSeek客户端
        logger.info("正在初始化 DeepSeek 客户端...")
        self.sentiment_client = DeepSeekClient()
        if self.sentiment_client.is_available():
            api_key_preview = self.sentiment_client.api_key[:10] + "..." if len(self.sentiment_client.api_key) > 10 else self.sentiment_client.api_key
            logger.info(f"DeepSeek API key 已配置 (前10位: {api_key_preview})")
            # 测试 API 是否有效（会消耗一次 API 调用，但可以验证 key 是否有效）
            logger.info("正在测试 DeepSeek API 连接（这可能需要几秒钟）...")
            try:
                success, message = self.sentiment_client.test_api()
                if success:
                    logger.info(f"✓ {message}")
                else:
                    logger.warning(f"✗ {message}")
            except Exception as e:
                logger.warning(f"DeepSeek API 测试异常: {e}")
        else:
            logger.warning("DeepSeek API key未配置，情感分析将失败。请在.env文件中设置DEEPSEEK_API_KEY。")
    
    def load_graph(self, graph_path: str) -> Optional[nx.Graph]:
        """
        加载GraphML图文件
        
        Args:
            graph_path: 图文件路径（可能是相对路径）
        
        Returns:
            NetworkX MultiDiGraph对象，如果加载失败返回None
        """
        try:
            # 解析路径：index.json 中的路径是相对于项目根目录的
            # 例如: "output\\monthly-graphs\\angular-angular\\actor-discussion\\2023-01.graphml"
            path_obj = Path(graph_path)
            
            # 如果是绝对路径，直接使用
            if path_obj.is_absolute():
                resolved_path = path_obj
            else:
                # 相对路径：先尝试相对于当前工作目录
                resolved_path = Path.cwd() / path_obj
                # 如果不存在，尝试相对于 graphs_dir 的父目录（项目根目录）
                if not resolved_path.exists():
                    # 从 graphs_dir 推断项目根目录
                    # graphs_dir 通常是 "output/monthly-graphs/"
                    # 项目根目录应该是 graphs_dir 的父目录的父目录
                    project_root = self.graphs_dir.parent.parent if self.graphs_dir.name == "monthly-graphs" else self.graphs_dir.parent
                    resolved_path = project_root / path_obj
            
            if not resolved_path.exists():
                logger.warning(f"图文件不存在: {resolved_path} (原始路径: {graph_path}, 当前目录: {Path.cwd()})")
                return None
            
            logger.info(f"正在加载图文件: {resolved_path}")
            logger.info(f"图文件大小: {resolved_path.stat().st_size / 1024 / 1024:.2f} MB")
            graph = nx.read_graphml(str(resolved_path))
            logger.info(f"成功加载图文件: 节点数={graph.number_of_nodes()}, 边数={graph.number_of_edges()}")
            return graph
        except Exception as e:
            logger.warning(f"加载图失败: {graph_path}, 错误: {e}", exc_info=True)
            return None
    
    def extract_sentiment_from_comments(
        self,
        graph: nx.Graph,
        repo_name: str = "",
        month: str = "",
        max_workers: int = 4,
    ) -> Dict[str, float]:
        """
        从图的边中提取情感信息（使用DeepSeek API）
        
        Args:
            graph: actor-discussion图
            repo_name: 项目名称（用于日志）
            month: 月份（用于日志）
        
        Returns:
            {edge_id: sentiment_score} 映射，score范围在-1到1之间
        """
        if not self.sentiment_client.is_available():
            logger.error("DeepSeek API不可用，无法进行情感分析")
            return {}
        
        sentiment_scores: Dict[str, float] = {}
        edges_with_comment = 0
        edges_processed = 0
        edges_failed = 0
        
        # 先收集所有有comment_body的边（去空白后非空）
        edges_to_process: List[tuple[str, str]] = []
        
        # 根据图类型处理边：MultiDiGraph支持keys，DiGraph不支持
        if isinstance(graph, nx.MultiDiGraph):
            for u, v, key, data in graph.edges(keys=True, data=True):
                comment_body = data.get('comment_body', '')
                # 检查comment_body是否非空（去除空白字符后）
                if comment_body and comment_body.strip():
                    edges_with_comment += 1
                    edge_id = f"{u}_{v}_{key}"
                    edges_to_process.append((edge_id, comment_body.strip()))
        else:
            # DiGraph类型，没有key参数
            for u, v, data in graph.edges(data=True):
                comment_body = data.get('comment_body', '')
                if comment_body and comment_body.strip():
                    edges_with_comment += 1
                    edge_id = f"{u}_{v}"
                    edges_to_process.append((edge_id, comment_body.strip()))
        
        if edges_with_comment == 0:
            logger.info(f"{repo_name} {month}: 没有找到包含comment_body的边（总边数: {graph.number_of_edges()}）")
            return {}
        
        # 总是显示进度
        total_edges = len(edges_to_process)
        print(f"{repo_name} {month}: 开始分析 {total_edges} 条边的情感（这可能需要几分钟）...", flush=True)
        logger.info(f"{repo_name} {month}: 开始分析 {total_edges} 条边的情感（这可能需要几分钟）...")
        logger.info(f"{repo_name} {month}: 使用最多 {max_workers} 个线程并发调用 DeepSeek API")
        
        # 并发处理每条边
        def _analyze_single_edge(edge: tuple[str, str]) -> tuple[str, float, Optional[Exception]]:
            edge_id, comment_body = edge
            try:
                score = self.sentiment_client.analyze_sentiment(comment_body)
                return edge_id, score, None
            except Exception as e:
                return edge_id, 0.0, e
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_edge_id = {
                executor.submit(_analyze_single_edge, edge): edge[0]
                for edge in edges_to_process
            }
            
            for idx, future in enumerate(as_completed(future_to_edge_id), 1):
                edge_id = future_to_edge_id[future]
                
                # 进度显示：边数少时每条打印，边数多时每10条打印一次
                if total_edges > 5:
                    if total_edges <= 20:
                        print(f"{repo_name} {month}: 处理边 {idx}/{total_edges}...", flush=True)
                        logger.info(f"{repo_name} {month}: 处理边 {idx}/{total_edges}...")
                    elif idx % 10 == 0 or idx == 1:
                        print(f"{repo_name} {month}: 处理边 {idx}/{total_edges}...", flush=True)
                        logger.info(f"{repo_name} {month}: 处理边 {idx}/{total_edges}...")
                
                try:
                    result_edge_id, score, error = future.result()
                    sentiment_scores[result_edge_id] = score
                    if error is None:
                        edges_processed += 1
                    else:
                        edges_failed += 1
                        logger.warning(f"情感分析失败 (edge={result_edge_id}, {idx}/{total_edges}): {error}")
                except Exception as e:
                    edges_failed += 1
                    sentiment_scores[edge_id] = 0.0
                    logger.warning(f"情感分析失败 (edge={edge_id}, {idx}/{total_edges}): {e}")
        
        # 总结日志（总是显示）
        print(f"{repo_name} {month}: 情感分析完成 - 成功: {edges_processed}, 失败: {edges_failed}, 总计: {total_edges}", flush=True)
        logger.info(f"{repo_name} {month}: 情感分析完成 - 成功: {edges_processed}, 失败: {edges_failed}, 总计: {total_edges}")
        
        return sentiment_scores
    
    def compute_monthly_metrics(
        self,
        discussion_graph: nx.Graph,
        actor_actor_graph: nx.Graph,
        repo_name: str,
        month: str,
    ) -> Optional[MonthlyAtmosphereMetrics]:
        """
        计算单个月的社区氛围指标
        
        Args:
            discussion_graph: actor-discussion图（用于情感分析/情感传播）
            actor_actor_graph: actor-actor协作图（用于聚类系数/网络直径）
            repo_name: 项目名称
            month: 月份（格式：YYYY-MM）
        
        Returns:
            月度社区氛围指标，如果分析失败返回None
        """
        if discussion_graph.number_of_nodes() == 0:
            logger.warning(f"图为空: {repo_name} {month}")
            return None
        
        print(f"开始分析 {repo_name} {month} 的社区氛围...", flush=True)
        print(f"  discussion图: 节点数={discussion_graph.number_of_nodes()}, 边数={discussion_graph.number_of_edges()}", flush=True)
        print(f"  actor-actor图: 节点数={actor_actor_graph.number_of_nodes()}, 边数={actor_actor_graph.number_of_edges()}", flush=True)
        logger.info(f"开始分析 {repo_name} {month} 的社区氛围...")
        logger.info(f"  discussion图: 节点数={discussion_graph.number_of_nodes()}, 边数={discussion_graph.number_of_edges()}")
        logger.info(f"  actor-actor图: 节点数={actor_actor_graph.number_of_nodes()}, 边数={actor_actor_graph.number_of_edges()}")
        
        # 创建指标对象
        metrics = MonthlyAtmosphereMetrics(month=month, repo_name=repo_name)
        
        # 1. 情感传播分析
        print(f"  [1/3] 开始情感分析...", flush=True)
        logger.info(f"  [1/3] 开始情感分析...")
        sentiment_scores = self.extract_sentiment_from_comments(discussion_graph, repo_name, month,20)
        if not sentiment_scores:
            # 检查是否是因为没有comment_body的边
            has_edges = discussion_graph.number_of_edges() > 0
            if has_edges:
                logger.info(f"  [1/3] 无法提取情感分数（图有 {discussion_graph.number_of_edges()} 条边，但没有包含comment_body的边），跳过情感传播分析")
            else:
                logger.info(f"  [1/3] 无法提取情感分数（图没有边），跳过情感传播分析")
            metrics.average_emotion = 0.0
            metrics.emotion_propagation_steps = 5
            metrics.emotion_damping_factor = 0.85
        else:
            logger.info(f"  [1/3] 情感分析完成，开始情感传播计算...")
            emotion_result = analyze_emotion_propagation(
                discussion_graph,
                sentiment_scores=sentiment_scores,
                propagation_steps=5,
                damping_factor=0.85,
            )
            metrics.average_emotion = emotion_result["average_emotion"]
            metrics.emotion_propagation_steps = emotion_result["propagation_steps"]
            metrics.emotion_damping_factor = emotion_result["damping_factor"]
            logger.info(f"  [1/3] 情感传播计算完成: average_emotion={metrics.average_emotion:.3f}")
        
        # 2. 聚类系数分析
        print(f"  [2/3] 开始计算聚类系数...", flush=True)
        logger.info(f"  [2/3] 开始计算聚类系数...")
        clustering_result = compute_clustering_coefficient(actor_actor_graph)
        metrics.global_clustering_coefficient = clustering_result["global_clustering_coefficient"]
        metrics.average_local_clustering = clustering_result["average_local_clustering"]
        metrics.actor_graph_nodes = clustering_result["actor_graph_nodes"]
        metrics.actor_graph_edges = clustering_result["actor_graph_edges"]
        logger.info(f"  [2/3] 聚类系数计算完成: global={metrics.global_clustering_coefficient:.3f}, average_local={metrics.average_local_clustering:.3f}, actor_nodes={metrics.actor_graph_nodes}, actor_edges={metrics.actor_graph_edges}")
        
        # 3. 网络直径分析
        print(f"  [3/3] 开始计算网络直径...", flush=True)
        logger.info(f"  [3/3] 开始计算网络直径...")
        diameter_result = compute_network_diameter(actor_actor_graph)
        metrics.diameter = diameter_result["diameter"]
        metrics.average_path_length = diameter_result["average_path_length"]
        metrics.is_connected = diameter_result["is_connected"]
        metrics.num_connected_components = diameter_result["num_connected_components"]
        metrics.largest_component_size = diameter_result["largest_component_size"]
        logger.info(f"  [3/3] 网络直径计算完成: diameter={metrics.diameter}, avg_path_length={metrics.average_path_length:.3f}, connected={metrics.is_connected}, components={metrics.num_connected_components}, largest_component={metrics.largest_component_size}")
        
        print(f"分析完成: {repo_name} {month}", flush=True)
        logger.info(f"分析完成: {repo_name} {month}")
        return metrics

    def _get_expected_months_for_repo(self, graph_types_data: Dict[str, Any]) -> List[str]:
        """
        计算一个项目“可分析月份”的集合。
        要求：同一个月份同时存在 actor-discussion 和 actor-actor 图。
        """
        first_value = next(iter(graph_types_data.values()), {})
        if isinstance(first_value, dict) and not first_value.get("node_type"):
            discussion_months = set((graph_types_data.get("actor-discussion") or {}).keys())
            actor_actor_months = set((graph_types_data.get("actor-actor") or {}).keys())
            return sorted(list(discussion_months & actor_actor_months))
        # 旧格式无法区分类型：退化为全部月份（但这种情况下无法按“同时存在两类图”判断）
        return sorted(list((graph_types_data or {}).keys()))

    def _get_processed_months_for_repo(self, repo_name: str, existing_results: Dict[str, Any]) -> set:
        repo_data = existing_results.get(repo_name) or {}
        metrics = repo_data.get("metrics") or []
        processed = set()
        for m in metrics:
            month = m.get("month")
            if month:
                processed.add(month)
        return processed

    def _upsert_month_metric(self, existing_metrics: List[Dict[str, Any]], metric_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """将单个月的 metrics 写入列表：若同月已存在则覆盖，否则追加，并保持按month排序。"""
        month = metric_dict.get("month")
        if not month:
            return existing_metrics
        replaced = False
        new_list: List[Dict[str, Any]] = []
        for m in existing_metrics:
            if m.get("month") == month:
                new_list.append(metric_dict)
                replaced = True
            else:
                new_list.append(m)
        if not replaced:
            new_list.append(metric_dict)
        new_list.sort(key=lambda x: x.get("month") or "")
        return new_list
    
    def compute_atmosphere_score(
        self,
        repo_name: str,
        metrics_series: List[MonthlyAtmosphereMetrics],
    ) -> Dict[str, Any]:
        """
        计算社区氛围综合评分
        
        基于时间序列的指标计算综合评分，考虑：
        - 平均情绪值（正面情绪越高越好）
        - 聚类系数（紧密度越高越好）
        - 网络直径（直径越小，沟通效率越高）
        
        Args:
            repo_name: 项目名称
            metrics_series: 月度指标时间序列
        
        Returns:
            包含综合评分和详细信息的字典
        """
        if not metrics_series:
            return {
                "score": 0.0,
                "level": "unknown",
                "months_analyzed": 0,
                "factors": {},
            }
        
        # 计算时间维度上的平均值
        avg_emotion = sum(m.average_emotion for m in metrics_series) / len(metrics_series)
        avg_clustering = sum(m.average_local_clustering for m in metrics_series) / len(metrics_series)
        avg_diameter = sum(m.diameter for m in metrics_series) / len(metrics_series)
        avg_path_length = sum(m.average_path_length for m in metrics_series) / len(metrics_series)
        
        # ------------------------------
        # 归一化与权重设定（0-100分）
        # 仅保留三类高层因子：
        # 1）情绪氛围（Emotion）
        # 2）社区紧密度（Clustering）
        # 3）网络效率（Network Efficiency：基于直径 + 平均路径长度）
        #
        # 权重分配（调整后）：
        # - 情绪 20%（降低）：技术讨论多为中性，区分度有限
        # - 聚类系数 40%（提高）：反映社区成员间的紧密协作关系，区分度高
        # - 网络效率 40%（提高）：反映信息传播效率和社区连通性，区分度高
        # ------------------------------
        
        # 1) 情绪：-1 ~ 1 线性映射到 0 ~ 1，再乘以 20 分
        emotion_norm = max(0.0, min(1.0, (avg_emotion + 1.0) / 2.0))
        emotion_score = emotion_norm * 20
        
        # 2) 聚类系数：使用平滑函数进行归一化，避免线性映射对低值过于严格
        #   使用对数衰减函数，让低聚类系数也能得到合理分数
        #   对于聚类系数：0 -> 0, 0.1 -> 0.33, 0.2 -> 0.5, 0.4 -> 0.75, 0.6 -> 1.0（平滑增长）
        #   公式：1 / (1 + k * (threshold - clustering) / threshold)，其中 k 控制增长曲线
        #   k=2.0 时：clustering=0 -> 0, clustering=0.1 -> 0.33, clustering=0.2 -> 0.5, clustering=0.4 -> 0.75, clustering=0.6 -> 1.0
        clustering_threshold = 0.6
        clustering_growth_factor = 2.0
        if avg_clustering <= 0.0:
            clustering_norm = 0.0
        elif avg_clustering >= clustering_threshold:
            clustering_norm = 1.0
        else:
            # 使用平滑增长函数，让低值也能得到合理分数
            clustering_norm = 1.0 / (1.0 + clustering_growth_factor * (clustering_threshold - avg_clustering) / clustering_threshold)
            # 确保最小值不会太小，至少保留 0.05（如果 clustering > 0）
            if avg_clustering > 0.01:
                clustering_norm = max(0.05, clustering_norm)
        clustering_score = clustering_norm * 40
        
        # 3) 网络效率：直径/路径越小越好
        #   使用对数/饱和函数进行归一化，避免硬截断，适应不同规模的项目
        #   对于直径：1 -> 1.0, 6 -> 0.4, 10 -> 0.23, 20 -> 0.12（平滑衰减）
        #   对于路径长度：1 -> 1.0, 3.5 -> 0.5, 5 -> 0.38, 8 -> 0.22（平滑衰减）
        
        # 直径分量：使用对数衰减函数，避免硬截断
        # 公式：1 / (1 + k * (diameter - 1))，其中 k 控制衰减速度
        # k=0.3 时：diameter=1 -> 1.0, diameter=6 -> 0.4, diameter=10 -> 0.23, diameter=20 -> 0.12
        diameter_decay_factor = 0.3
        if avg_diameter <= 1.0:
            diameter_component = 1.0
        else:
            diameter_component = 1.0 / (1.0 + diameter_decay_factor * (avg_diameter - 1.0))
            # 确保不会完全为0，最小保留0.05
            diameter_component = max(0.05, diameter_component)
        
        # 路径长度分量：使用对数衰减函数，避免硬截断
        # k=0.4 时：path_length=1 -> 1.0, path_length=3.5 -> 0.5, path_length=5 -> 0.38, path_length=8 -> 0.22
        path_decay_factor = 0.4
        if avg_path_length <= 1.0:
            path_component = 1.0
        else:
            path_component = 1.0 / (1.0 + path_decay_factor * (avg_path_length - 1.0))
            # 确保不会完全为0，最小保留0.05
            path_component = max(0.05, path_component)
        
        network_norm = 0.5 * diameter_component + 0.5 * path_component
        network_score = network_norm * 40
        
        # 综合评分
        total_score = emotion_score + clustering_score + network_score
        
        # 确定风险等级
        if total_score >= 80:
            level = "excellent"
        elif total_score >= 60:
            level = "good"
        elif total_score >= 40:
            level = "moderate"
        else:
            level = "poor"
        
        return {
            "score": round(total_score, 2),
            "level": level,
            "months_analyzed": len(metrics_series),
            "period": f"{metrics_series[0].month} to {metrics_series[-1].month}",
            "factors": {
                "emotion": {
                    "value": round(avg_emotion, 3),
                    "score": round(emotion_score, 2),
                    "weight": 20,
                },
                "clustering": {
                    "value": round(avg_clustering, 3),
                    "score": round(clustering_score, 2),
                    "weight": 40,
                },
                "network_efficiency": {
                    "value": {
                        "average_diameter": round(avg_diameter, 3),
                        "average_path_length": round(avg_path_length, 3),
                    },
                    "score": round(network_score, 2),
                    "weight": 40,
                },
            },
        }
    
    def analyze_all_repos(self) -> Dict[str, Any]:
        """分析所有项目（支持断点续传：按月保存full_analysis，按项目更新summary）"""
        # 从index.json加载所有项目
        index_file = self.graphs_dir / "index.json"
        print(f"正在读取索引文件: {index_file}", flush=True)
        logger.info(f"正在读取索引文件: {index_file}")
        logger.info(f"索引文件绝对路径: {index_file.resolve()}")
        
        if not index_file.exists():
            print(f"错误: 索引文件不存在: {index_file}", flush=True)
            logger.error(f"索引文件不存在: {index_file}")
            logger.info("请先运行 monthly_graph_builder.py 构建图")
            return {}
        
        print(f"索引文件存在，开始加载（这可能需要几秒钟）...", flush=True)
        logger.info(f"索引文件存在，开始加载...")
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
            print(f"索引文件加载成功", flush=True)
            logger.info(f"索引文件加载成功")
        except Exception as e:
            print(f"错误: 加载索引文件失败: {e}", flush=True)
            logger.error(f"加载索引文件失败: {e}", exc_info=True)
            return {}
        
        total_repos = len(index)
        print(f"索引文件加载完成，共 {total_repos} 个项目", flush=True)
        
        # 检查已存在的分析结果，实现断点续传
        # 注意：断点续传以“月份”为单位，而不是项目
        existing_results = self.load_existing_results()

        # 计算哪些项目已经“完整完成”（其可分析月份全部在full_analysis中存在）
        completed_repos = set()
        for repo_name, graph_types_data in index.items():
            expected_months = set(self._get_expected_months_for_repo(graph_types_data))
            if not expected_months:
                continue
            processed_months = self._get_processed_months_for_repo(repo_name, existing_results)
            if expected_months.issubset(processed_months):
                completed_repos.add(repo_name)

        if completed_repos:
            print(f"发现已完成分析的项目: {len(completed_repos)} 个", flush=True)
            print(f"将跳过已完成项目，继续分析其余项目/月份...", flush=True)
            logger.info(f"发现已完成分析的项目: {len(completed_repos)} 个，将跳过")

        remaining_repos = {k: v for k, v in index.items() if k not in completed_repos}
        remaining_count = len(remaining_repos)
        
        if remaining_count == 0:
            print(f"所有项目已完成分析！", flush=True)
            logger.info("所有项目已完成分析")
            return existing_results
        
        print(f"开始分析 {remaining_count} 个待处理项目（共 {total_repos} 个）...", flush=True)
        logger.info(f"开始分析 {remaining_count} 个待处理项目（共 {total_repos} 个）...")
        
        all_results = existing_results.copy()  # 从已存在的结果开始
        
        for repo_idx, (repo_name, graph_types_data) in enumerate(remaining_repos.items(), 1):
            # 新格式: {repo: {graph_type: {month: path}}}
            # 旧格式: {repo: {month: path}}
            # 对于社区氛围分析：需要 actor-discussion + actor-actor 同月都存在
            expected_months = self._get_expected_months_for_repo(graph_types_data)

            first_value = next(iter(graph_types_data.values()), {})
            if isinstance(first_value, dict) and not first_value.get("node_type"):
                discussion_paths = graph_types_data.get("actor-discussion", {}) or {}
                actor_actor_paths = graph_types_data.get("actor-actor", {}) or {}
            else:
                # 旧格式没有类型信息：无法满足“用actor-actor计算结构指标”的要求
                logger.warning(f"{repo_name}: 索引为旧格式，无法同时获取actor-discussion与actor-actor，将跳过")
                continue
            
            # 显示实际进度（包括已完成的）
            actual_idx = len(completed_repos) + repo_idx
            print(f"[{actual_idx}/{total_repos}] 分析: {repo_name} (可分析月份={len(expected_months)})", flush=True)
            logger.info(f"[{actual_idx}/{total_repos}] 分析: {repo_name} (可分析月份={len(expected_months)})")
            
            # 加载所有月份的图并计算指标
            # 从已有结果恢复本项目的已处理月份与metrics
            existing_repo_data = all_results.get(repo_name) or {}
            existing_metrics_list = existing_repo_data.get("metrics") or []
            processed_months = set(m.get("month") for m in existing_metrics_list if m.get("month"))

            total_months = len(expected_months)
            for month_idx, month in enumerate(expected_months, 1):
                if month in processed_months:
                    print(f"  [{month_idx}/{total_months}] 跳过已完成月份: {month}", flush=True)
                    continue

                discussion_path = discussion_paths.get(month)
                actor_actor_path = actor_actor_paths.get(month)
                if not discussion_path or not actor_actor_path:
                    logger.warning(f"  [{month_idx}/{total_months}] 月份 {month} 缺少必要图文件，跳过 (discussion={bool(discussion_path)}, actor-actor={bool(actor_actor_path)})")
                    continue

                print(f"  [{month_idx}/{total_months}] 处理月份: {month}", flush=True)
                logger.info(f"  [{month_idx}/{total_months}] 处理月份: {month}")
                logger.info(f"  [{month_idx}/{total_months}] discussion图路径: {discussion_path}")
                logger.info(f"  [{month_idx}/{total_months}] actor-actor图路径: {actor_actor_path}")

                print(f"  [{month_idx}/{total_months}] 正在加载discussion图...", flush=True)
                discussion_graph = self.load_graph(discussion_path)
                print(f"  [{month_idx}/{total_months}] 正在加载actor-actor图...", flush=True)
                actor_graph = self.load_graph(actor_actor_path)

                if discussion_graph is None or actor_graph is None:
                    logger.warning(f"  [{month_idx}/{total_months}] 图加载失败，跳过: {repo_name} {month}")
                    continue

                print(f"  [{month_idx}/{total_months}] 图加载成功，开始计算指标...", flush=True)
                try:
                    metrics = self.compute_monthly_metrics(discussion_graph, actor_graph, repo_name, month)
                    if metrics is None:
                        logger.warning(f"  [{month_idx}/{total_months}] 月份 {month} 返回了 None，跳过")
                        continue

                    # 写入内存（month级）
                    metric_dict = metrics.to_dict()
                    existing_metrics_list = self._upsert_month_metric(existing_metrics_list, metric_dict)
                    processed_months.add(month)

                    # 计算“当前已完成月份”的阶段性评分，写入full_analysis（每月更新）
                    metrics_series = []
                    for m in existing_metrics_list:
                        metrics_series.append(MonthlyAtmosphereMetrics.from_dict(m))

                    atmosphere_score = self.compute_atmosphere_score(repo_name, metrics_series)
                    repo_result = {
                        "metrics": existing_metrics_list,
                        "atmosphere_score": atmosphere_score,
                    }
                    all_results[repo_name] = repo_result

                    # 每完成一个月就落盘 full_analysis
                    self.save_full_analysis(all_results)
                    print(f"  ✓ 已写入full_analysis: {repo_name} {month}", flush=True)

                except Exception as e:
                    logger.error(f"  [{month_idx}/{total_months}] 计算指标失败: {repo_name} {month}, 错误: {e}", exc_info=True)
                    continue
            
            # 项目级：如果本项目所有expected_months都完成了，则更新summary
            expected_months_set = set(expected_months)
            if expected_months_set and expected_months_set.issubset(processed_months):
                print(f"✓ 项目 {repo_name} 全部月份分析完成，正在更新summary...", flush=True)
                self.save_summary(all_results, index)
            else:
                logger.info(f"{repo_name}: 尚未完成所有月份，summary暂不更新（已完成 {len(processed_months)}/{len(expected_months)}）")
        
        print(f"所有项目分析完成！共分析 {len(all_results)} 个项目", flush=True)
        logger.info(f"所有项目分析完成！共分析 {len(all_results)} 个项目")
        
        return all_results
    
    def load_existing_results(self) -> Dict[str, Any]:
        """
        加载已存在的分析结果
        
        Returns:
            已存在的分析结果字典，如果文件不存在则返回空字典
        """
        full_result_file = self.output_dir / "full_analysis.json"
        if not full_result_file.exists():
            return {}
        
        try:
            with open(full_result_file, "r", encoding="utf-8") as f:
                results = json.load(f)
            logger.info(f"加载已存在的分析结果: {len(results)} 个项目")
            return results
        except Exception as e:
            logger.warning(f"加载已存在的分析结果失败: {e}，将重新开始分析")
            return {}
    
    def save_full_analysis(self, results: Dict[str, Any]):
        """写入 full_analysis.json（按月增量更新时调用）"""
        full_result_file = self.output_dir / "full_analysis.json"
        with open(full_result_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"full_analysis已保存: {full_result_file} (共 {len(results)} 个项目)")

    def save_summary(self, results: Dict[str, Any], index: Dict[str, Any]):
        """
        写入 summary.json（按项目完成时调用）。
        仅包含“完成全部可分析月份”的项目。
        """
        summary = []
        for repo_name, repo_result in results.items():
            graph_types_data = index.get(repo_name)
            if not graph_types_data:
                continue
            expected_months = set(self._get_expected_months_for_repo(graph_types_data))
            if not expected_months:
                continue
            processed_months = self._get_processed_months_for_repo(repo_name, results)
            if not expected_months.issubset(processed_months):
                continue
            score = (repo_result.get("atmosphere_score") or {}).get("score")
            level = (repo_result.get("atmosphere_score") or {}).get("level")
            months_analyzed = (repo_result.get("atmosphere_score") or {}).get("months_analyzed")
            if score is None or level is None or months_analyzed is None:
                continue
            summary.append({
                "repo_name": repo_name,
                "atmosphere_score": score,
                "level": level,
                "months_analyzed": months_analyzed,
            })

        summary.sort(key=lambda x: x["atmosphere_score"], reverse=True)
        summary_file = self.output_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info(f"summary已保存: {summary_file} (项目数={len(summary)})")
    
    def run(self) -> Dict[str, Any]:
        """运行完整分析"""
        
        logger.info("=" * 60)
        logger.info("开始社区氛围分析")
        logger.info(f"图目录: {self.graphs_dir}")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info("=" * 60)
        
        
        results = self.analyze_all_repos()

        # 最终落盘一次 full_analysis，并根据最终状态刷新 summary
        if results:
            self.save_full_analysis(results)
            # 重新加载index并刷新summary（确保最终完整）
            index_file = self.graphs_dir / "index.json"
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    index = json.load(f)
                self.save_summary(results, index)
            except Exception as e:
                logger.warning(f"最终刷新summary失败: {e}")
        
        print("=" * 60, flush=True)
        print("分析完成!", flush=True)
        print(f"分析项目数: {len(results)}", flush=True)
        print(f"输出目录: {self.output_dir}", flush=True)
        print("=" * 60, flush=True)
        logger.info("=" * 60)
        logger.info("分析完成!")
        logger.info(f"分析项目数: {len(results)}")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info("=" * 60)
        
        return results


if __name__ == "__main__":
    import argparse
    
    # 立即输出，确保用户看到程序启动
    print("=" * 60, flush=True)
    print("社区氛围分析程序启动中...", flush=True)
    print("=" * 60, flush=True)
    
    parser = argparse.ArgumentParser(description="社区氛围分析")
    parser.add_argument(
        "--graphs-dir",
        type=str,
        default="output/monthly-graphs/",
        help="月度图目录"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/community-atmosphere/",
        help="输出目录"
    )
    
    args = parser.parse_args()
    
    print(f"图目录: {args.graphs_dir}", flush=True)
    print(f"输出目录: {args.output_dir}", flush=True)
    print("正在初始化分析器...", flush=True)
    
    analyzer = CommunityAtmosphereAnalyzer(
        graphs_dir=args.graphs_dir,
        output_dir=args.output_dir,
    )
    
    print("分析器初始化完成，开始运行分析...", flush=True)
    
    analyzer.run()
