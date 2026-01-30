"""
社区氛围分析器

分析指标：
1. 毒性分析：从预计算的 toxicity.json 获取 ToxiCR 毒性检测结果
2. CHAOSS 指标：从 GraphML 提取变更请求关闭率和首次响应时间
3. 聚类系数：衡量社区紧密度
4. 网络直径：评估社区沟通效率

已弃用：
- 情感传播模型：原使用 DeepSeek 大模型进行情绪分析，现已替换为毒性分析

输出：
- 每个项目的月度指标时间序列
- 社区氛围综合评分（后续由大模型基于指标数据评分）
"""

from __future__ import annotations

import json
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import networkx as nx

from src.algorithms.clustering_coefficient import compute_clustering_coefficient
# 注释掉情绪传播算法，已替换为毒性分析
# from src.algorithms.emotion_propagation import analyze_emotion_propagation
from src.algorithms.network_diameter import compute_network_diameter
from src.models.community_atmosphere import MonthlyAtmosphereMetrics
# 注释掉 DeepSeek 客户端，情绪分析已弃用
# from src.services.sentiment.deepseek_client import DeepSeekClient
from src.services.llm_scorer import LLMScorer
from src.utils.logger import setup_logger

# 为社区氛围分析器单独配置日志文件，所有运行过程日志写入 logs/community_atmosphere.log
logger = setup_logger(log_file="logs/community_atmosphere.log")


class CommunityAtmosphereAnalyzer:
    """
    社区氛围分析器
    
    分析指标体系：
    1. 毒性指标（ToxiCR）：从预计算的 toxicity.json 获取，按仓库+月份聚合
    2. CHAOSS 指标：从 GraphML 提取
       - 变更请求关闭率（Change Request Closure Ratio）
       - 首次响应时间（Time to First Response）
    3. 网络结构指标：
       - 聚类系数（Clustering Coefficient）
       - 网络直径（Network Diameter）
    
    已弃用：
    - 情感传播分析：原使用 DeepSeek 大模型，现已替换
    """
    
    def __init__(
        self,
        graphs_dir: str = "output/monthly-graphs/",
        output_dir: str = "output/community-atmosphere-analysis/",
    ):
        """
        初始化分析器
        
        Args:
            graphs_dir: 图文件目录，包含月度 GraphML 文件
            output_dir: 输出目录，存放分析结果
        """
        self.graphs_dir = Path(graphs_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 存储分析结果
        self.repo_metrics: Dict[str, List[MonthlyAtmosphereMetrics]] = defaultdict(list)
        
        # ========================================
        # 新增：LLM 评分器
        # 使用 DeepSeek API 对毒性指标和 CHAOSS 指标进行综合评分
        # ========================================
        logger.info("正在初始化 LLM 评分器...")
        self.llm_scorer = LLMScorer()
        if self.llm_scorer.is_available():
            logger.info("✓ LLM 评分器初始化成功")
        else:
            logger.warning("✗ LLM 评分器不可用，DEEPSEEK_API_KEY 未配置")
        
        # ========================================
        # 已弃用：DeepSeek 情绪分析客户端
        # 现在使用预计算的毒性分析结果（toxicity.json）
        # ========================================
        # logger.info("正在初始化 DeepSeek 客户端...")
        # self.sentiment_client = DeepSeekClient()
        # if self.sentiment_client.is_available():
        #     api_key_preview = self.sentiment_client.api_key[:10] + "..." if len(self.sentiment_client.api_key) > 10 else self.sentiment_client.api_key
        #     logger.info(f"DeepSeek API key 已配置 (前10位: {api_key_preview})")
        #     logger.info("正在测试 DeepSeek API 连接（这可能需要几秒钟）...")
        #     try:
        #         success, message = self.sentiment_client.test_api()
        #         if success:
        #             logger.info(f"✓ {message}")
        #         else:
        #             logger.warning(f"✗ {message}")
        #     except Exception as e:
        #         logger.warning(f"DeepSeek API 测试异常: {e}")
        # else:
        #     logger.warning("DeepSeek API key未配置，情感分析将失败。请在.env文件中设置DEEPSEEK_API_KEY。")
        
        # ========================================
        # 已弃用：ToxiCR 实时客户端
        # 现在使用预计算的毒性分析结果（toxicity.json）
        # ========================================
        # logger.info("正在初始化 ToxiCR 客户端...")
        # self.toxicr_client = ToxiCRClient(
        #     cache_file=str(self.output_dir / "toxicity_cache.json")
        # )
        # if self.toxicr_client.is_available():
        #     logger.info("✓ ToxiCR 模型可用")
        # else:
        #     logger.warning("✗ ToxiCR 模型不可用，毒性分析将跳过")
        
        # ========================================
        # 新增：加载预计算的毒性分析缓存
        # 来源：scripts/analyze_oss_comments.py 的输出
        # 格式：{hash: {toxicity, repo, month, comment}}
        # ========================================
        logger.info("正在加载预计算的毒性分析缓存...")
        self.toxicity_cache: Dict[str, Dict[str, Any]] = {}
        self._load_toxicity_cache()
        
        # 加载 Top30 仓库列表
        self.top30_repos: set = set()
        top30_file = Path("top30.json")
        if top30_file.exists():
            try:
                with open(top30_file, "r", encoding="utf-8") as f:
                    top30_data = json.load(f)
                    self.top30_repos = {item["repo"] for item in top30_data}
                logger.info(f"加载 Top30 仓库列表成功，共 {len(self.top30_repos)} 个仓库")
            except Exception as e:
                logger.warning(f"加载 Top30 仓库列表失败: {e}，将分析所有仓库")
        else:
            logger.warning(f"Top30 仓库文件不存在: {top30_file}，将分析所有仓库")
    
    def _load_toxicity_cache(self) -> None:
        """
        加载预计算的毒性分析缓存
        
        缓存文件位置：output/community-atmosphere-analysis/toxicity.json
        格式：{
            "hash": {
                "toxicity": 0.85,
                "repo": "python/cpython",
                "month": "2023-01",
                "comment": "原始评论文本"
            },
            ...
        }
        
        使用 ToxiCR 模型对所有仓库的评论进行批量毒性分析。
        """
        # 固定路径：output/community-atmosphere-analysis/toxicity.json
        toxicity_file = Path("output/community-atmosphere-analysis/toxicity.json")
        
        if not toxicity_file.exists():
            logger.warning(f"毒性分析缓存文件不存在: {toxicity_file}")
            logger.warning("请先运行 scripts/analyze_oss_comments.py 生成毒性分析结果")
            return
        
        try:
            with open(toxicity_file, "r", encoding="utf-8") as f:
                self.toxicity_cache = json.load(f)
            logger.info(f"✓ 加载毒性分析缓存成功: {len(self.toxicity_cache)} 条记录")
            logger.info(f"  缓存文件路径: {toxicity_file}")
            
            # 统计各仓库的评论数量
            repo_counts = defaultdict(int)
            for item in self.toxicity_cache.values():
                if isinstance(item, dict) and "repo" in item:
                    repo_counts[item["repo"]] += 1
            logger.info(f"  覆盖仓库数量: {len(repo_counts)}")
            
        except Exception as e:
            logger.error(f"加载毒性分析缓存失败: {e}")
            self.toxicity_cache = {}
    
    def _aggregate_toxicity_by_repo_month(self, repo_name: str, month: str) -> Dict[str, Any]:
        """
        按仓库+月份聚合毒性数据
        
        从预计算的毒性缓存中筛选指定仓库和月份的评论，
        计算该月的毒性统计指标。
        
        Args:
            repo_name: 仓库名称，如 "python/cpython"
            month: 月份，格式 "YYYY-MM"
            
        Returns:
            毒性统计指标字典，包含：
            - toxicity_mean: 平均毒性分数
            - toxicity_p95: 毒性分数95分位数
            - toxic_rate_0_5: 毒性>=0.5的评论占比
            - toxic_comment_count_0_5: 毒性>=0.5的评论数量
            - comment_analyzed_count: 被分析的评论总数
        """
        # 筛选指定仓库和月份的评论
        toxicity_scores: List[float] = []
        
        for item in self.toxicity_cache.values():
            if not isinstance(item, dict):
                continue
            if item.get("repo") == repo_name and item.get("month") == month:
                score = item.get("toxicity")
                if score is not None:
                    toxicity_scores.append(float(score))
        
        # 如果没有找到任何评论，返回默认值
        if not toxicity_scores:
            logger.debug(f"  {repo_name} {month}: 未找到毒性分析数据")
            return {
                "toxicity_mean": 0.0,
                "toxicity_p95": 0.0,
                "toxic_rate_0_5": 0.0,
                "toxic_comment_count_0_5": 0,
                "comment_analyzed_count": 0,
            }
        
        # 计算统计指标
        toxicity_array = np.array(toxicity_scores)
        toxic_threshold = 0.5
        
        toxicity_mean = float(np.mean(toxicity_array))
        toxicity_p95 = float(np.percentile(toxicity_array, 95))
        toxic_count = int(np.sum(toxicity_array >= toxic_threshold))
        toxic_rate = toxic_count / len(toxicity_scores)
        
        logger.info(f"  {repo_name} {month}: 评论数={len(toxicity_scores)}, "
                   f"平均毒性={toxicity_mean:.4f}, P95={toxicity_p95:.4f}, "
                   f"毒性评论占比={toxic_rate:.2%}")
        
        return {
            "toxicity_mean": toxicity_mean,
            "toxicity_p95": toxicity_p95,
            "toxic_rate_0_5": toxic_rate,
            "toxic_comment_count_0_5": toxic_count,
            "comment_analyzed_count": len(toxicity_scores),
        }
    
    def compute_chaoss_metrics(
        self,
        discussion_graph: nx.Graph,
        repo_name: str,
        month: str,
    ) -> Dict[str, Any]:
        """
        从 GraphML 提取 CHAOSS 社区健康指标
        
        CHAOSS (Community Health Analytics for Open Source Software) 是一个
        开源项目，专注于开源社区健康的度量标准。本方法实现了两个核心指标：
        
        1. 变更请求关闭率 (Change Request Closure Ratio)
           - 来源: https://chaoss.community/kb/metric-change-request-closure-ratio/
           - 定义: 一段时间内关闭的变更请求数量 / 新打开的变更请求数量
           - 意义: 衡量社区处理贡献的能力
             - > 1: 消化能力强，处理速度快于提交速度
             - < 1: 存在积压，可能需要更多维护者
             - = 1: 平衡状态
        
        2. 首次响应时间 (Time to First Response)
           - 来源: https://chaoss.community/kb/metric-time-to-first-response/
           - 定义: 从 Issue/PR 创建到第一条响应的时间间隔
           - 意义: 反映社区活跃度和响应速度
             - 时间短: 社区活跃，贡献者体验好
             - 时间长: 可能导致贡献者流失
        
        数据来源说明：
        - GraphML 边属性 'edge_type' (d18): 边的类型
          - CREATED_PR: 用户创建了一个 PR
          - MERGED_PR: 用户合并了一个 PR
          - CLOSED_PR: 用户关闭了一个 PR
          - CREATED_ISSUE: 用户创建了一个 Issue
          - CLOSED_ISSUE: 用户关闭了一个 Issue
          - COMMENTED_ISSUE, COMMENTED_PR: 用户发表了评论
          - REVIEWED_PR: 用户对 PR 进行了审查
        - GraphML 边属性 'created_at' (d19, d17): 事件发生时间
        
        Args:
            discussion_graph: actor-discussion 图，包含 Issue/PR 交互数据
            repo_name: 仓库名称，用于日志
            month: 月份，格式 "YYYY-MM"
            
        Returns:
            CHAOSS 指标字典，包含：
            - change_request_closure_ratio: 变更请求关闭率
            - opened_prs, closed_prs: PR 计数
            - opened_issues, closed_issues: Issue 计数
            - time_to_first_response_median: 首次响应时间中位数（小时）
            - time_to_first_response_mean: 首次响应时间均值（小时）
            - time_to_first_response_p95: 首次响应时间95分位数（小时）
            - items_with_response, items_without_response: 响应情况统计
        """
        # ========================================
        # 第一部分：变更请求关闭率 (Change Request Closure Ratio)
        # ========================================
        # 统计边类型计数
        opened_prs = 0
        closed_prs = 0  # 包含 MERGED_PR 和 CLOSED_PR
        opened_issues = 0
        closed_issues = 0
        
        # 用于计算首次响应时间的数据结构
        # {item_id: {"created_at": datetime, "first_response_at": datetime|None}}
        items_timeline: Dict[str, Dict[str, Any]] = {}
        
        # 遍历所有边，统计边类型和收集时间线数据
        if isinstance(discussion_graph, nx.MultiDiGraph):
            edges_iter = discussion_graph.edges(keys=True, data=True)
            edge_key_func = lambda u, v, k, d: (u, v, k, d)
        else:
            edges_iter = discussion_graph.edges(data=True)
            edge_key_func = lambda u, v, d: (u, v, None, d)
        
        for edge_data in edges_iter:
            if len(edge_data) == 4:
                u, v, key, data = edge_data
            else:
                u, v, data = edge_data
                key = None
            
            edge_type = data.get("edge_type", "")
            created_at_str = data.get("created_at", "")
            
            # 解析时间戳
            created_at = None
            if created_at_str:
                try:
                    # 支持多种时间格式
                    if "T" in created_at_str:
                        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    else:
                        created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    pass
            
            # 统计变更请求类型
            # 注意：GraphML 中使用 CREATED_PR/CREATED_ISSUE 而非 OPENED_PR/OPENED_ISSUE
            if edge_type == "CREATED_PR":
                opened_prs += 1
                # 记录 PR 创建时间，用于计算首次响应时间
                # v 是 PR 节点 ID
                if v not in items_timeline:
                    items_timeline[v] = {"created_at": created_at, "first_response_at": None, "type": "PR"}
                elif items_timeline[v]["created_at"] is None and created_at:
                    items_timeline[v]["created_at"] = created_at
                    
            elif edge_type in ("MERGED_PR", "CLOSED_PR"):
                closed_prs += 1
                
            elif edge_type == "CREATED_ISSUE":
                opened_issues += 1
                # 记录 Issue 创建时间
                if v not in items_timeline:
                    items_timeline[v] = {"created_at": created_at, "first_response_at": None, "type": "Issue"}
                elif items_timeline[v]["created_at"] is None and created_at:
                    items_timeline[v]["created_at"] = created_at
                    
            elif edge_type == "CLOSED_ISSUE":
                closed_issues += 1
                
            elif edge_type in ("COMMENTED_ISSUE", "COMMENTED_PR", "REVIEWED_PR"):
                # 评论/Review 表示响应
                # v 是 Issue/PR 节点 ID
                if v in items_timeline:
                    if items_timeline[v]["first_response_at"] is None and created_at:
                        items_timeline[v]["first_response_at"] = created_at
                    elif created_at and items_timeline[v]["first_response_at"]:
                        # 保留最早的响应时间
                        if created_at < items_timeline[v]["first_response_at"]:
                            items_timeline[v]["first_response_at"] = created_at
        
        # 计算变更请求关闭率
        # 公式: (closed_prs + closed_issues) / (opened_prs + opened_issues)
        total_opened = opened_prs + opened_issues
        total_closed = closed_prs + closed_issues
        
        if total_opened > 0:
            change_request_closure_ratio = total_closed / total_opened
        else:
            change_request_closure_ratio = 0.0
        
        logger.info(f"  {repo_name} {month} CHAOSS 变更请求: "
                   f"opened_prs={opened_prs}, closed_prs={closed_prs}, "
                   f"opened_issues={opened_issues}, closed_issues={closed_issues}, "
                   f"closure_ratio={change_request_closure_ratio:.3f}")
        
        # ========================================
        # 第二部分：首次响应时间 (Time to First Response)
        # ========================================
        response_times_hours: List[float] = []
        items_with_response = 0
        items_without_response = 0
        
        for item_id, timeline in items_timeline.items():
            created_at = timeline.get("created_at")
            first_response_at = timeline.get("first_response_at")
            
            if created_at is None:
                continue
            
            if first_response_at is not None and first_response_at > created_at:
                # 计算响应时间（小时）
                delta = first_response_at - created_at
                response_time_hours = delta.total_seconds() / 3600.0
                response_times_hours.append(response_time_hours)
                items_with_response += 1
            else:
                items_without_response += 1
        
        # 计算响应时间统计指标
        if response_times_hours:
            response_array = np.array(response_times_hours)
            time_to_first_response_median = float(np.median(response_array))
            time_to_first_response_mean = float(np.mean(response_array))
            time_to_first_response_p95 = float(np.percentile(response_array, 95))
        else:
            time_to_first_response_median = 0.0
            time_to_first_response_mean = 0.0
            time_to_first_response_p95 = 0.0
        
        logger.info(f"  {repo_name} {month} CHAOSS 首次响应时间: "
                   f"median={time_to_first_response_median:.2f}h, "
                   f"mean={time_to_first_response_mean:.2f}h, "
                   f"p95={time_to_first_response_p95:.2f}h, "
                   f"with_response={items_with_response}, "
                   f"without_response={items_without_response}")
        
        return {
            # 变更请求关闭率
            "change_request_closure_ratio": change_request_closure_ratio,
            "opened_prs": opened_prs,
            "closed_prs": closed_prs,
            "opened_issues": opened_issues,
            "closed_issues": closed_issues,
            # 首次响应时间
            "time_to_first_response_median": time_to_first_response_median,
            "time_to_first_response_mean": time_to_first_response_mean,
            "time_to_first_response_p95": time_to_first_response_p95,
            "items_with_response": items_with_response,
            "items_without_response": items_without_response,
        }
    
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
    
    # def extract_sentiment_from_comments(
    #     self,
    #     graph: nx.Graph,
    #     repo_name: str = "",
    #     month: str = "",
    #     max_workers: int = 4,
    # ) -> Dict[str, float]:
    #     """
    #     从图的边中提取情感信息（使用DeepSeek API）
        
    #     Args:
    #         graph: actor-discussion图
    #         repo_name: 项目名称（用于日志）
    #         month: 月份（用于日志）
        
    #     Returns:
    #         {edge_id: sentiment_score} 映射，score范围在-1到1之间
    #     """
    #     if not self.sentiment_client.is_available():
    #         logger.error("DeepSeek API不可用，无法进行情感分析")
    #         return {}
        
    #     sentiment_scores: Dict[str, float] = {}
    #     edges_with_comment = 0
    #     edges_processed = 0
    #     edges_failed = 0
        
    #     # 先收集所有有comment_body的边（去空白后非空）
    #     edges_to_process: List[tuple[str, str]] = []
        
    #     # 根据图类型处理边：MultiDiGraph支持keys，DiGraph不支持
    #     if isinstance(graph, nx.MultiDiGraph):
    #         for u, v, key, data in graph.edges(keys=True, data=True):
    #             comment_body = data.get('comment_body', '')
    #             # 检查comment_body是否非空（去除空白字符后）
    #             if comment_body and comment_body.strip():
    #                 edges_with_comment += 1
    #                 edge_id = f"{u}_{v}_{key}"
    #                 edges_to_process.append((edge_id, comment_body.strip()))
    #     else:
    #         # DiGraph类型，没有key参数
    #         for u, v, data in graph.edges(data=True):
    #             comment_body = data.get('comment_body', '')
    #             if comment_body and comment_body.strip():
    #                 edges_with_comment += 1
    #                 edge_id = f"{u}_{v}"
    #                 edges_to_process.append((edge_id, comment_body.strip()))
        
    #     if edges_with_comment == 0:
    #         logger.info(f"{repo_name} {month}: 没有找到包含comment_body的边（总边数: {graph.number_of_edges()}）")
    #         return {}
        
    #     # 总是显示进度
    #     total_edges = len(edges_to_process)
    #     print(f"{repo_name} {month}: 开始分析 {total_edges} 条边的情感（这可能需要几分钟）...", flush=True)
    #     logger.info(f"{repo_name} {month}: 开始分析 {total_edges} 条边的情感（这可能需要几分钟）...")
    #     logger.info(f"{repo_name} {month}: 使用最多 {max_workers} 个线程并发调用 DeepSeek API")
        
    #     # 并发处理每条边
    #     def _analyze_single_edge(edge: tuple[str, str]) -> tuple[str, float, Optional[Exception]]:
    #         edge_id, comment_body = edge
    #         try:
    #             score = self.sentiment_client.analyze_sentiment(comment_body)
    #             return edge_id, score, None
    #         except Exception as e:
    #             return edge_id, 0.0, e
        
    #     with ThreadPoolExecutor(max_workers=max_workers) as executor:
    #         future_to_edge_id = {
    #             executor.submit(_analyze_single_edge, edge): edge[0]
    #             for edge in edges_to_process
    #         }
            
    #         for idx, future in enumerate(as_completed(future_to_edge_id), 1):
    #             edge_id = future_to_edge_id[future]
                
    #             # 进度显示：边数少时每条打印，边数多时每10条打印一次
    #             if total_edges > 5:
    #                 if total_edges <= 20:
    #                     print(f"{repo_name} {month}: 处理边 {idx}/{total_edges}...", flush=True)
    #                     logger.info(f"{repo_name} {month}: 处理边 {idx}/{total_edges}...")
    #                 elif idx % 10 == 0 or idx == 1:
    #                     print(f"{repo_name} {month}: 处理边 {idx}/{total_edges}...", flush=True)
    #                     logger.info(f"{repo_name} {month}: 处理边 {idx}/{total_edges}...")
                
    #             try:
    #                 result_edge_id, score, error = future.result()
    #                 sentiment_scores[result_edge_id] = score
    #                 if error is None:
    #                     edges_processed += 1
    #                 else:
    #                     edges_failed += 1
    #                     logger.warning(f"情感分析失败 (edge={result_edge_id}, {idx}/{total_edges}): {error}")
    #             except Exception as e:
    #                 edges_failed += 1
    #                 sentiment_scores[edge_id] = 0.0
    #                 logger.warning(f"情感分析失败 (edge={edge_id}, {idx}/{total_edges}): {e}")
        
    #     # 总结日志（总是显示）
    #     print(f"{repo_name} {month}: 情感分析完成 - 成功: {edges_processed}, 失败: {edges_failed}, 总计: {total_edges}", flush=True)
    #     logger.info(f"{repo_name} {month}: 情感分析完成 - 成功: {edges_processed}, 失败: {edges_failed}, 总计: {total_edges}")
        
    #     return sentiment_scores
    
    
    def compute_monthly_metrics(
        self,
        discussion_graph: nx.Graph,
        actor_actor_graph: nx.Graph,
        repo_name: str,
        month: str,
    ) -> Optional[MonthlyAtmosphereMetrics]:
        """
        计算单个月的社区氛围指标
        
        分析流程（共5步）：
        1. 毒性指标：从预计算的 toxicity.json 获取，按仓库+月份聚合
        2. CHAOSS 变更请求关闭率：从 GraphML 边类型统计
        3. CHAOSS 首次响应时间：从 GraphML 时间戳计算
        4. 聚类系数：基于 actor-actor 协作图
        5. 网络直径：基于 actor-actor 协作图
        
        已弃用：
        - 情感传播分析：原使用 DeepSeek 大模型，现已注释
        
        Args:
            discussion_graph: actor-discussion图（用于 CHAOSS 指标提取）
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
        
        # ========================================
        # 已弃用：情感传播分析
        # 原来使用 DeepSeek 大模型进行情绪分析，现已替换为毒性分析
        # ========================================
        # print(f"  [1/4] 开始情感分析...", flush=True)
        # logger.info(f"  [1/4] 开始情感分析...")
        # sentiment_scores = self.extract_sentiment_from_comments(discussion_graph, repo_name, month, 20)
        # if not sentiment_scores:
        #     has_edges = discussion_graph.number_of_edges() > 0
        #     if has_edges:
        #         logger.info(f"  [1/4] 无法提取情感分数（图有 {discussion_graph.number_of_edges()} 条边，但没有包含comment_body的边），跳过情感传播分析")
        #     else:
        #         logger.info(f"  [1/4] 无法提取情感分数（图没有边），跳过情感传播分析")
        #     metrics.average_emotion = 0.0
        #     metrics.emotion_propagation_steps = 5
        #     metrics.emotion_damping_factor = 0.85
        # else:
        #     logger.info(f"  [1/4] 情感分析完成，开始情感传播计算...")
        #     emotion_result = analyze_emotion_propagation(
        #         discussion_graph,
        #         sentiment_scores=sentiment_scores,
        #         propagation_steps=5,
        #         damping_factor=0.85,
        #     )
        #     metrics.average_emotion = emotion_result["average_emotion"]
        #     metrics.emotion_propagation_steps = emotion_result["propagation_steps"]
        #     metrics.emotion_damping_factor = emotion_result["damping_factor"]
        #     logger.info(f"  [1/4] 情感传播计算完成: average_emotion={metrics.average_emotion:.3f}")
        
        # # 保留默认情感值（兼容旧数据格式）
        # metrics.average_emotion = 0.0
        # metrics.emotion_propagation_steps = 5
        # metrics.emotion_damping_factor = 0.85
        
        # ========================================
        # 步骤 1/5：毒性分析（从预计算缓存获取）
        # 来源：scripts/analyze_oss_comments.py 生成的 toxicity.json
        # ========================================
        print(f"  [1/5] 开始毒性分析（从缓存获取）...", flush=True)
        logger.info(f"  [1/5] 开始毒性分析（从缓存获取）...")
        toxicity_data = self._aggregate_toxicity_by_repo_month(repo_name, month)
        metrics.toxicity_mean = toxicity_data["toxicity_mean"]
        metrics.toxicity_p95 = toxicity_data["toxicity_p95"]
        metrics.toxic_rate_0_5 = toxicity_data["toxic_rate_0_5"]
        metrics.toxic_comment_count_0_5 = toxicity_data["toxic_comment_count_0_5"]
        metrics.comment_analyzed_count = toxicity_data["comment_analyzed_count"]
        print(f"  [1/5] 毒性分析完成: mean={metrics.toxicity_mean:.3f}, p95={metrics.toxicity_p95:.3f}, "
              f"toxic_rate={metrics.toxic_rate_0_5:.2%}, comments={metrics.comment_analyzed_count}", flush=True)
        
        # ========================================
        # 步骤 2/5：CHAOSS 指标（从 GraphML 提取）
        # 包括变更请求关闭率和首次响应时间
        # ========================================
        print(f"  [2/5] 开始计算 CHAOSS 指标...", flush=True)
        logger.info(f"  [2/5] 开始计算 CHAOSS 指标...")
        chaoss_data = self.compute_chaoss_metrics(discussion_graph, repo_name, month)
        # 变更请求关闭率
        metrics.change_request_closure_ratio = chaoss_data["change_request_closure_ratio"]
        metrics.opened_prs = chaoss_data["opened_prs"]
        metrics.closed_prs = chaoss_data["closed_prs"]
        metrics.opened_issues = chaoss_data["opened_issues"]
        metrics.closed_issues = chaoss_data["closed_issues"]
        # 首次响应时间
        metrics.time_to_first_response_median = chaoss_data["time_to_first_response_median"]
        metrics.time_to_first_response_mean = chaoss_data["time_to_first_response_mean"]
        metrics.time_to_first_response_p95 = chaoss_data["time_to_first_response_p95"]
        metrics.items_with_response = chaoss_data["items_with_response"]
        metrics.items_without_response = chaoss_data["items_without_response"]
        print(f"  [2/5] CHAOSS 指标计算完成: closure_ratio={metrics.change_request_closure_ratio:.2f}, "
              f"response_time_median={metrics.time_to_first_response_median:.1f}h", flush=True)
        
        # ========================================
        # 步骤 3/5：聚类系数分析
        # 基于 actor-actor 协作图计算
        # ========================================
        print(f"  [3/5] 开始计算聚类系数...", flush=True)
        logger.info(f"  [3/5] 开始计算聚类系数...")
        clustering_result = compute_clustering_coefficient(actor_actor_graph)
        metrics.global_clustering_coefficient = clustering_result["global_clustering_coefficient"]
        metrics.average_local_clustering = clustering_result["average_local_clustering"]
        metrics.actor_graph_nodes = clustering_result["actor_graph_nodes"]
        metrics.actor_graph_edges = clustering_result["actor_graph_edges"]
        logger.info(f"  [3/5] 聚类系数计算完成: global={metrics.global_clustering_coefficient:.3f}, "
                   f"average_local={metrics.average_local_clustering:.3f}, "
                   f"actor_nodes={metrics.actor_graph_nodes}, actor_edges={metrics.actor_graph_edges}")
        print(f"  [3/5] 聚类系数计算完成: global={metrics.global_clustering_coefficient:.3f}", flush=True)
        
        # ========================================
        # 步骤 4/5：网络直径分析
        # 基于 actor-actor 协作图计算
        # ========================================
        print(f"  [4/5] 开始计算网络直径...", flush=True)
        logger.info(f"  [4/5] 开始计算网络直径...")
        diameter_result = compute_network_diameter(actor_actor_graph)
        metrics.diameter = diameter_result["diameter"]
        metrics.average_path_length = diameter_result["average_path_length"]
        metrics.is_connected = diameter_result["is_connected"]
        metrics.num_connected_components = diameter_result["num_connected_components"]
        metrics.largest_component_size = diameter_result["largest_component_size"]
        logger.info(f"  [4/5] 网络直径计算完成: diameter={metrics.diameter}, "
                   f"avg_path_length={metrics.average_path_length:.3f}, "
                   f"connected={metrics.is_connected}, components={metrics.num_connected_components}, "
                   f"largest_component={metrics.largest_component_size}")
        print(f"  [4/5] 网络直径计算完成: diameter={metrics.diameter}, avg_path={metrics.average_path_length:.2f}", flush=True)
        
        # ========================================
        # 步骤 5/5：基础指标计算完成
        # LLM 评分已移至 analyze_all_repos 中批量并发执行
        # ========================================
        print(f"  [5/5] 基础指标计算完成: {repo_name} {month}", flush=True)
        logger.info(f"  [5/5] 基础指标计算完成: {repo_name} {month}")
        
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
        
        评分体系说明：
        ========================================
        综合评分 = 大模型评分(40%) + 聚类系数(30%) + 网络直径(30%)
        ========================================
        
        1. 大模型评分 (40%)：
           - 基于毒性指标（ToxiCR）和 CHAOSS 指标的结构化数据
           - 由大模型综合分析后给出评分
           - 当前版本暂未实现，占位值为 0
           - 毒性指标和 CHAOSS 指标仅作为数据保存，供后续大模型评分使用
        
        2. 聚类系数 (30%)：
           - 指标：global_clustering_coefficient
           - 意义：社区越紧密，协作效率越高
           - 正向指标：数值越大越好
        
        3. 网络直径 (30%)：
           - 指标：average_path_length
           - 意义：沟通路径越短，信息传递效率越高
           - 负向指标：数值越小越好
        
        每个维度通过三层分析算法计算得分：
        - 长期趋势 (40%)：线性回归斜率判断持续性增长或衰退
        - 近期状态 (40%)：对比最近3个月与最早3个月的均值
        - 稳定性 (20%)：月度变化率的标准差，惩罚高波动性
        
        Args:
            repo_name: 仓库名称
            metrics_series: 按月排序的指标对象列表
            
        Returns:
            评分字典，包含 score, level, months_analyzed, period, factors
        """
        # 数据量不足以进行时间序列分析（至少需要3个月来计算趋势和对比）
        if len(metrics_series) < 3:
            return {
                "score": 0.0,
                "level": "insufficient_data",
                "months_analyzed": len(metrics_series),
                "details": "数据量不足(少于3个月)，无法执行时间序列评分模型"
            }

        def calculate_time_series_component_score(data: List[float], is_positive_metric: bool = True) -> float:
            """
            针对单个指标维度应用三层分析算法
            
            三层分析：
            1. 长期趋势 (40%)：线性回归斜率
            2. 近期状态 (40%)：最近3月 vs 最早3月 均值对比
            3. 稳定性 (20%)：月度变化率标准差
            
            Args:
                data: 时间序列数据
                is_positive_metric: True=数值越大越好，False=数值越小越好
                
            Returns:
                0-100 的综合得分
            """
            y = np.array(data)
            n = len(y)
            x = np.arange(n)

            # --- 1. 长期趋势分析 (40% 权重) ---
            slope, _ = np.polyfit(x, y, 1)
            
            trend_score = 100.0
            if is_positive_metric:
                if slope < 0:
                    trend_score = max(0.0, 100.0 - abs(slope) * 100)
            else:
                if slope > 0:
                    trend_score = max(0.0, 100.0 - slope * 100)

            # --- 2. 近期状态分析 (40% 权重) ---
            recent_mean = np.mean(y[-3:])
            early_mean = np.mean(y[:3])
            
            denominator = abs(early_mean) if early_mean != 0 else 1.0
            change_rate = (recent_mean - early_mean) / denominator
            
            recent_score = 100.0
            if is_positive_metric:
                if change_rate < 0:
                    recent_score = max(0.0, 100.0 - abs(change_rate) * 100)
            else:
                if change_rate > 0:
                    recent_score = max(0.0, 100.0 - change_rate * 100)

            # --- 3. 稳定性分析 (20% 权重) ---
            monthly_changes = []
            for i in range(1, n):
                prev = y[i-1]
                change = (y[i] - prev) / abs(prev) if prev != 0 else 0.0
                monthly_changes.append(change)
            
            volatility = np.std(monthly_changes) if monthly_changes else 0.0
            
            stability_score = 100.0
            if volatility > 0.3:
                penalty = (volatility - 0.3) * 25
                stability_score = max(0.0, 100.0 - penalty)

            return (trend_score * 0.4) + (recent_score * 0.4) + (stability_score * 0.2)

        # ========================================
        # 维度 1：大模型评分 (40%)
        # 基于毒性指标和 CHAOSS 指标，由大模型综合评分
        # 指标：llm_score (0-100)
        # 意义：大模型对社区氛围的综合评估
        # 正向指标：数值越大越好
        # ========================================
        llm_scores = [m.llm_score for m in metrics_series]
        if any(score > 0 for score in llm_scores):
            # 有 LLM 评分数据：使用三层分析
            s_llm = calculate_time_series_component_score(llm_scores, is_positive_metric=True)
            logger.info(f"LLM 评分维度: 使用 {len(llm_scores)} 个月的数据进行三层分析，得分={s_llm:.2f}")
        else:
            # 没有 LLM 评分数据：使用 0
            s_llm = 0.0
            # 如果 LLM 评分器可用，说明后续会进行评分，此时只是暂时无数据，使用 info 级别
            # 如果 LLM 评分器不可用，说明确实无法评分，使用 warning 级别
            if self.llm_scorer.is_available():
                logger.info(f"LLM 评分维度: 暂无评分数据，使用占位值 0（后续将进行 LLM 评分）")
            else:
                logger.warning(f"LLM 评分维度: 无有效数据，使用占位值 0（LLM 评分器不可用）")
        
        # ========================================
        # 维度 2：聚类系数 (30%)
        # 指标：global_clustering_coefficient
        # 意义：聚类系数越高，社区越紧密，协作效率越高
        # 正向指标：数值越大越好
        # ========================================
        clustering_series = [m.global_clustering_coefficient for m in metrics_series]
        s_clustering = calculate_time_series_component_score(clustering_series, is_positive_metric=True)

        # ========================================
        # 维度 3：网络直径 (30%)
        # 指标：average_path_length
        # 意义：平均路径长度越短，沟通效率越高
        # 负向指标：数值越小越好
        # ========================================
        diameter_series = [m.average_path_length for m in metrics_series]
        s_diameter = calculate_time_series_component_score(diameter_series, is_positive_metric=False)

        # ========================================
        # 综合评分计算
        # 权重分配：大模型评分(40%) + 聚类系数(30%) + 网络直径(30%)
        # ========================================
        final_score = (
            s_llm * 0.40 + 
            s_clustering * 0.30 + 
            s_diameter * 0.30
        )

        # 映射等级
        if final_score >= 80: level = "excellent"
        elif final_score >= 60: level = "good"
        elif final_score >= 40: level = "moderate"
        else: level = "poor"

        return {
            "score": round(final_score, 2),
            "level": level,
            "months_analyzed": len(metrics_series),
            "period": f"{metrics_series[0].month} to {metrics_series[-1].month}",
            "factors": {
                # 三个评分维度
                "llm_score": round(s_llm, 2),  # 大模型评分（毒性+响应效率）
                "clustering_score": round(s_clustering, 2),  # 聚类系数评分
                "diameter_score": round(s_diameter, 2),  # 网络直径评分
            },
            "weights": {
                "llm": 0.40,  # 大模型评分权重
                "clustering": 0.30,  # 聚类系数权重
                "diameter": 0.30,  # 网络直径权重
            }
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
        
        # Top30 过滤：如果配置了 Top30 列表，则只分析 Top30 仓库
        if self.top30_repos:
            before_filter = len(remaining_repos)
            remaining_repos = {k: v for k, v in remaining_repos.items() if k in self.top30_repos}
            after_filter = len(remaining_repos)
            print(f"Top30 过滤：{before_filter} → {after_filter} 个待分析仓库", flush=True)
            logger.info(f"Top30 过滤：{before_filter} → {after_filter} 个待分析仓库")
            remaining_count = after_filter
        
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
            
            # 项目级：计算 atmosphere_score（在 LLM 评分之前先计算一次，确保即使 LLM 不可用也有基础分数）
            repo_data = all_results.get(repo_name, {})
            metrics_list = repo_data.get("metrics", [])
            if metrics_list:
                metrics_series = [MonthlyAtmosphereMetrics.from_dict(m) for m in metrics_list]
                atmosphere_score = self.compute_atmosphere_score(repo_name, metrics_series)
                repo_data["atmosphere_score"] = atmosphere_score
                all_results[repo_name] = repo_data
            
            # 项目级：如果本项目所有expected_months都完成了，则更新summary
            expected_months_set = set(expected_months)
            if expected_months_set and expected_months_set.issubset(processed_months):
                print(f"✓ 项目 {repo_name} 全部月份基础指标计算完成", flush=True)
                # summary 将在 LLM 评分后更新
            else:
                logger.info(f"{repo_name}: 尚未完成所有月份（已完成 {len(processed_months)}/{len(expected_months)}）")
            
            # ========================================
            # 项目级批量 LLM 评分
            # 每个仓库处理完后，立即对该仓库进行批量 LLM 评分
            # 这样可以避免程序中途退出时丢失评分
            # ========================================
            if self.llm_scorer.is_available():
                repo_data = all_results.get(repo_name, {})
                metrics_list = repo_data.get("metrics", [])
                
                # 收集该仓库中缺少 LLM 评分的月份
                llm_tasks = []
                for m in metrics_list:
                    # 检查是否已有 LLM 评分（score > 0 或有 overall_reason）
                    if m.get("llm_score", 0) == 0 and m.get("llm_overall_reason", "") == "":
                        month = m.get("month", "")
                        if month:
                            metrics_dict = {
                                "toxicity_mean": m.get("toxicity_mean", 0.0),
                                "toxicity_p95": m.get("toxicity_p95", 0.0),
                                "toxic_rate_0_5": m.get("toxic_rate_0_5", 0.0),
                                "toxic_comment_count_0_5": m.get("toxic_comment_count_0_5", 0),
                                "comment_analyzed_count": m.get("comment_analyzed_count", 0),
                                "change_request_closure_ratio": m.get("change_request_closure_ratio", 0.0),
                                "opened_prs": m.get("opened_prs", 0),
                                "closed_prs": m.get("closed_prs", 0),
                                "opened_issues": m.get("opened_issues", 0),
                                "closed_issues": m.get("closed_issues", 0),
                                "time_to_first_response_median": m.get("time_to_first_response_median", 0.0),
                                "time_to_first_response_mean": m.get("time_to_first_response_mean", 0.0),
                                "time_to_first_response_p95": m.get("time_to_first_response_p95", 0.0),
                                "items_with_response": m.get("items_with_response", 0),
                                "items_without_response": m.get("items_without_response", 0),
                            }
                            llm_tasks.append((repo_name, month, metrics_dict))
                
                if llm_tasks:
                    print(f"  开始 LLM 评分: {len(llm_tasks)} 个月份待评分", flush=True)
                    logger.info(f"  {repo_name}: 开始 LLM 评分，{len(llm_tasks)} 个月份待评分")
                    
                    # 批量并发评分
                    llm_results = self.llm_scorer.score_batch(llm_tasks, max_workers=8, rate_limit_delay=0.1)
                    
                    # 将 LLM 评分结果写入 metrics_list
                    updated_count = 0
                    for m in metrics_list:
                        month = m.get("month", "")
                        cache_key = f"{repo_name}:{month}"
                        if cache_key in llm_results:
                            llm_result = llm_results[cache_key]
                            m["llm_score"] = llm_result.get("score", 0)
                            m["llm_toxicity_score"] = llm_result.get("toxicity_score", 0)
                            m["llm_response_score"] = llm_result.get("response_score", 0)
                            m["llm_toxicity_reason"] = llm_result.get("toxicity_reason", "")
                            m["llm_response_reason"] = llm_result.get("response_reason", "")
                            m["llm_overall_reason"] = llm_result.get("overall_reason", "")
                            updated_count += 1
                    
                    # 重新计算 atmosphere_score（因为 LLM 评分已更新）
                    metrics_series = [MonthlyAtmosphereMetrics.from_dict(m) for m in metrics_list]
                    atmosphere_score = self.compute_atmosphere_score(repo_name, metrics_series)
                    repo_data["metrics"] = metrics_list
                    repo_data["atmosphere_score"] = atmosphere_score
                    all_results[repo_name] = repo_data
                    
                    # 保存更新后的结果
                    self.save_full_analysis(all_results)
                    print(f"  ✓ LLM 评分完成: 更新 {updated_count} 条记录", flush=True)
                    logger.info(f"  {repo_name}: LLM 评分完成，更新 {updated_count} 条记录")
                    
                    # 如果该项目已完成所有月份，则更新 summary
                    # 重新计算 processed_months 以确保准确性
                    current_processed_months = self._get_processed_months_for_repo(repo_name, all_results)
                    expected_months_set = set(expected_months)
                    if expected_months_set and expected_months_set.issubset(current_processed_months):
                        try:
                            self.save_summary(all_results, index)
                            print(f"  ✓ summary 已更新（项目 {repo_name} LLM 评分完成）", flush=True)
                            logger.info(f"  summary 已更新（项目 {repo_name} LLM 评分完成）")
                        except Exception as e:
                            logger.warning(f"  更新 summary 失败: {e}")
        
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
        default="output/community-atmosphere-analysis/",
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
