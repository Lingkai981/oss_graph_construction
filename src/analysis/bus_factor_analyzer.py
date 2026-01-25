"""
Bus Factor 分析器

分析指标：
1. Bus Factor：达到总贡献量50%所需的最少贡献者数量
2. 贡献者贡献量分布
3. 时间序列趋势分析
4. 综合风险评分

输出：
- 每个项目的月度指标时间序列
- 趋势分析结果
- 综合风险评分
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import networkx as nx
import numpy as np

from src.algorithms.bus_factor_calculator import (
    aggregate_contributions,
    calculate_bus_factor,
    DEFAULT_WEIGHTS,
)
from src.models.bus_factor import (
    ContributorContribution,
    MonthlyRiskMetrics,
    RiskScore,
    TrendAnalysis,
)
from src.utils.logger import get_logger, setup_logger

# 为 Bus Factor 分析器配置专门的日志记录器
logger = setup_logger(log_level="INFO", log_file="logs/bus_factor.log")


class BusFactorAnalyzer:
    """Bus Factor 分析器"""
    
    def __init__(
        self,
        graphs_dir: str = "output/monthly-graphs/",
        output_dir: str = "output/bus-factor-analysis/",
        threshold: float = 0.5,
        weights: Dict[str, float] = None,
    ):
        """
        初始化 Bus Factor 分析器
        
        Args:
            graphs_dir: 图文件目录
            output_dir: 输出目录
            threshold: Bus Factor 计算阈值（默认0.5）
            weights: 贡献权重配置（如果为 None，使用默认权重）
        """
        self.graphs_dir = Path(graphs_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.threshold = threshold
        self.weights = weights if weights is not None else DEFAULT_WEIGHTS
        
        # 存储分析结果
        self.repo_metrics: Dict[str, List[MonthlyRiskMetrics]] = defaultdict(list)
        self.trends: Dict[str, TrendAnalysis] = {}
        self.risk_scores: Dict[str, RiskScore] = {}
    
    def load_graph(self, graph_path: str) -> Optional[nx.Graph]:
        """
        加载图文件
        
        Args:
            graph_path: 图文件路径
        
        Returns:
            图对象（DiGraph 或 MultiDiGraph），如果加载失败返回 None
        """
        try:
            graph = nx.read_graphml(graph_path)
            graph_type = type(graph).__name__
            node_count = graph.number_of_nodes()
            edge_count = graph.number_of_edges()
            logger.info(f"成功加载图: {graph_path}")
            logger.info(f"  图类型: {graph_type}, 节点数: {node_count}, 边数: {edge_count}")
            return graph
        except Exception as e:
            logger.error(f"加载图失败: {graph_path}, 错误: {e}", exc_info=True)
            return None
    
    def compute_monthly_metrics(
        self,
        graph: nx.Graph,
        repo_name: str,
        month: str,
    ) -> Optional[MonthlyRiskMetrics]:
        """
        计算单个月份的风险指标
        
        Args:
            graph: actor-repo 图
            repo_name: 项目名称
            month: 月份（格式：YYYY-MM）
        
        Returns:
            月度风险指标，如果计算失败返回 None
        """
        if graph.number_of_nodes() == 0:
            logger.warning(f"图为空: {repo_name} {month}")
            return None
        
        if graph.number_of_edges() == 0:
            logger.warning(f"图没有边: {repo_name} {month}")
            # 返回默认值
            return MonthlyRiskMetrics(
                month=month,
                repo_name=repo_name,
                bus_factor=0,
                total_contribution=0.0,
                contributor_count=0,
                node_count=graph.number_of_nodes(),
                edge_count=0,
            )
        
        print(f"开始分析 {repo_name} {month} 的 Bus Factor...", flush=True)
        logger.info(f"开始分析 {repo_name} {month} 的 Bus Factor...")
        logger.info(f"  图: 节点数={graph.number_of_nodes()}, 边数={graph.number_of_edges()}")
        
        # 聚合贡献量
        logger.debug(f"开始聚合贡献量: {repo_name} {month}")
        contributor_contributions = aggregate_contributions(graph, self.weights)
        logger.debug(f"聚合完成: 找到 {len(contributor_contributions)} 个贡献者")
        
        if not contributor_contributions:
            logger.warning(f"没有找到贡献者: {repo_name} {month}")
            return MonthlyRiskMetrics(
                month=month,
                repo_name=repo_name,
                bus_factor=0,
                total_contribution=0.0,
                contributor_count=0,
                node_count=graph.number_of_nodes(),
                edge_count=graph.number_of_edges(),
            )
        
        # 计算总贡献量
        total_contribution = sum(
            c.total_contribution for c in contributor_contributions.values()
        )
        
        # 检查总贡献量是否为0
        if math.isclose(total_contribution, 0.0, abs_tol=1e-9):
            logger.warning(f"总贡献量为0: {repo_name} {month}")
            return MonthlyRiskMetrics(
                month=month,
                repo_name=repo_name,
                bus_factor=None,
                total_contribution=0.0,
                contributor_count=len(contributor_contributions),
                contributors=list(contributor_contributions.values()),
                node_count=graph.number_of_nodes(),
                edge_count=graph.number_of_edges(),
            )
        
        # 计算 Bus Factor
        contributions_dict = {
            cid: c.total_contribution
            for cid, c in contributor_contributions.items()
        }
        bus_factor = calculate_bus_factor(contributions_dict, self.threshold)
        
        # 按贡献量降序排序贡献者
        sorted_contributors = sorted(
            contributor_contributions.values(),
            key=lambda c: c.total_contribution,
            reverse=True,
        )
        
        # 创建月度指标
        metrics = MonthlyRiskMetrics(
            month=month,
            repo_name=repo_name,
            bus_factor=bus_factor,
            total_contribution=total_contribution,
            contributor_count=len(contributor_contributions),
            contributors=sorted_contributors,
            node_count=graph.number_of_nodes(),
            edge_count=graph.number_of_edges(),
        )
        
        print(f"  Bus Factor: {bus_factor}, 贡献者数: {len(contributor_contributions)}, 总贡献量: {total_contribution:.2f}", flush=True)
        logger.info(f"  Bus Factor: {bus_factor}, 贡献者数: {len(contributor_contributions)}, 总贡献量: {total_contribution:.2f}")
        
        return metrics
    
    def save_single_result(
        self,
        metrics: MonthlyRiskMetrics,
        output_file: str = None,
    ) -> None:
        """
        保存单个月份的分析结果到 JSON
        
        Args:
            metrics: 月度风险指标
            output_file: 输出文件路径（如果为 None，使用默认路径）
        """
        if output_file is None:
            output_file = self.output_dir / f"{metrics.repo_name.replace('/', '-')}_{metrics.month}.json"
        else:
            output_file = Path(output_file)
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(metrics.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"结果已保存: {output_file}")
    
    def load_index(self) -> Dict[str, Any]:
        """
        从 index.json 加载项目索引
        
        Returns:
            项目索引字典，如果加载失败返回空字典
        """
        index_file = self.graphs_dir / "index.json"
        if not index_file.exists():
            logger.error(f"索引文件不存在: {index_file}")
            logger.info("请先运行 monthly_graph_builder.py 构建图")
            return {}
        
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
            logger.info(f"成功加载索引文件: {len(index)} 个项目")
            return index
        except Exception as e:
            logger.error(f"加载索引文件失败: {e}")
            return {}
    
    def analyze_all_repos(self, resume: bool = True) -> Dict[str, Any]:
        """
        分析所有项目的月度风险指标时间序列
        
        Args:
            resume: 是否启用断点续传
        
        Returns:
            分析结果字典
        """
        # 加载索引
        index = self.load_index()
        if not index:
            return {}
        
        total_repos = len(index)
        logger.info(f"开始分析 {total_repos} 个项目...")
        
        # 检查已存在的结果（断点续传）
        full_analysis_file = self.output_dir / "full_analysis.json"
        existing_results = {}
        if resume and full_analysis_file.exists():
            try:
                with open(full_analysis_file, "r", encoding="utf-8") as f:
                    existing_results = json.load(f)
                logger.info(f"检测到已存在的分析结果，将跳过已处理的月份")
            except json.JSONDecodeError as e:
                # JSON 格式错误，尝试恢复
                logger.warning(f"无法加载已存在的分析结果（JSON格式错误）: {e}")
                logger.warning(f"错误位置: 第 {e.lineno} 行，第 {e.colno} 列")
                
                # 备份损坏的文件
                import shutil
                backup_file = self.output_dir / f"full_analysis.json.corrupted.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                try:
                    shutil.copy2(full_analysis_file, backup_file)
                    logger.info(f"已备份损坏的文件到: {backup_file}")
                except Exception as backup_error:
                    logger.warning(f"备份损坏文件失败: {backup_error}")
                
                # 尝试从临时文件恢复（如果存在）
                temp_file = self.output_dir / "full_analysis.json.tmp"
                if temp_file.exists():
                    try:
                        with open(temp_file, "r", encoding="utf-8") as f:
                            existing_results = json.load(f)
                        logger.info(f"从临时文件恢复成功，将跳过已处理的月份")
                        # 将临时文件重命名为正式文件
                        temp_file.replace(full_analysis_file)
                    except Exception as recover_error:
                        logger.warning(f"从临时文件恢复失败: {recover_error}")
                        existing_results = {}
                else:
                    logger.warning("未找到临时文件，将从头开始分析")
                    existing_results = {}
            except Exception as e:
                logger.warning(f"无法加载已存在的分析结果: {e}")
                existing_results = {}
        
        all_results = existing_results.copy()
        
        # 计算总月份数（用于进度显示）
        total_months = 0
        for graph_types_data in index.values():
            first_value = next(iter(graph_types_data.values()), {})
            if isinstance(first_value, dict) and not first_value.get("node_type"):
                months = graph_types_data.get("actor-repo", {})
            else:
                months = graph_types_data
            total_months += len(months) if months else 0
        
        # 计算已处理的月份数
        processed_months_count = 0
        for repo_data in existing_results.values():
            processed_months_count += len(repo_data.get("metrics", []))
        
        logger.info(f"总月份数: {total_months}, 已处理: {processed_months_count}, 待处理: {total_months - processed_months_count}")
        
        # 遍历所有项目
        for repo_idx, (repo_name, graph_types_data) in enumerate(index.items(), 1):
            # 检测格式：新格式 {graph_type: {month: path}} 或旧格式 {month: path}
            first_value = next(iter(graph_types_data.values()), {})
            if isinstance(first_value, dict) and not first_value.get("node_type"):
                # 新格式，取 actor-repo 类型
                months = graph_types_data.get("actor-repo", {})
            else:
                # 旧格式
                months = graph_types_data
            
            if not months:
                logger.warning(f"项目 {repo_name} 没有月份数据，跳过")
                continue
            
            logger.info(f"[{repo_idx}/{total_repos}] 分析: {repo_name} ({len(months)} 个月)")
            
            # 检查是否已处理过
            if repo_name in existing_results:
                existing_months = {m["month"] for m in existing_results[repo_name].get("metrics", [])}
                logger.info(f"  已处理月份: {len(existing_months)} 个")
            else:
                existing_months = set()
            
            # 加载所有月份的图并计算指标
            metrics_series = []
            if repo_name in existing_results:
                # 恢复已存在的指标
                # 需要将 contributors 字典转换为 ContributorContribution 对象
                restored_metrics = []
                for m in existing_results[repo_name].get("metrics", []):
                    # 复制字典以避免修改原始数据
                    m_copy = m.copy()
                    # 如果 contributors 是字典列表，转换为 ContributorContribution 对象
                    if "contributors" in m_copy and m_copy["contributors"]:
                        if isinstance(m_copy["contributors"][0], dict):
                            m_copy["contributors"] = [
                                ContributorContribution(**c) for c in m_copy["contributors"]
                            ]
                    else:
                        m_copy["contributors"] = []
                    restored_metrics.append(MonthlyRiskMetrics(**m_copy))
                metrics_series = restored_metrics
                self.repo_metrics[repo_name] = metrics_series.copy()
            
            processed_count = 0
            skipped_count = 0
            error_count = 0
            total_months_in_repo = len(months)
            months_to_process = total_months_in_repo - len(existing_months)
            
            for month_idx, (month, graph_path) in enumerate(sorted(months.items()), 1):
                # 跳过已处理的月份
                if month in existing_months:
                    skipped_count += 1
                    continue
                
                # 计算当前项目内的进度
                current_month_in_repo = month_idx - skipped_count
                repo_progress = (current_month_in_repo / months_to_process * 100) if months_to_process > 0 else 100
                
                # 计算全局进度（估算）
                global_processed = processed_months_count + processed_count
                global_progress = (global_processed / total_months * 100) if total_months > 0 else 0
                
                logger.info(f"  处理月份 [{current_month_in_repo}/{months_to_process}] ({repo_progress:.1f}%) | 全局进度: {global_processed}/{total_months} ({global_progress:.1f}%) | {month}")
                
                graph_path_obj = Path(graph_path)
                if not graph_path_obj.is_absolute():
                    # 检查路径是否已经包含 graphs_dir 作为前缀
                    # index.json 中的路径可能是相对于项目根目录的（如 output/monthly-graphs/...）
                    # 或者是相对于 graphs_dir 的（如 mochajs-mocha/actor-repo/...）
                    graph_path_str = str(graph_path).replace("\\", "/")
                    graphs_dir_str = str(self.graphs_dir).replace("\\", "/")
                    
                    # 标准化路径字符串以便比较
                    if graph_path_str.startswith(graphs_dir_str + "/") or graph_path_str == graphs_dir_str:
                        # 路径已经包含 graphs_dir 作为前缀，从项目根目录解析
                        graph_path_obj = Path(graph_path)
                    else:
                        # 路径不包含 graphs_dir，从 graphs_dir 解析
                        graph_path_obj = self.graphs_dir / graph_path
                
                if not graph_path_obj.exists():
                    logger.warning(f"图文件不存在: {graph_path_obj}，跳过")
                    error_count += 1
                    continue
                
                try:
                    logger.debug(f"开始处理: {repo_name} {month}, 图文件: {graph_path_obj}")
                    graph = self.load_graph(str(graph_path_obj))
                    if graph is None:
                        logger.warning(f"无法加载图文件: {graph_path_obj}, 跳过 {repo_name} {month}")
                        error_count += 1
                        continue
                    
                    metrics = self.compute_monthly_metrics(graph, repo_name, month)
                    if metrics:
                        metrics_series.append(metrics)
                        self.repo_metrics[repo_name].append(metrics)
                        processed_count += 1
                        processed_months_count += 1
                        
                        # 更新 all_results（无论 resume 是否为 True）
                        if repo_name not in all_results:
                            all_results[repo_name] = {"metrics": []}
                        all_results[repo_name]["metrics"] = [m.to_dict() for m in metrics_series]
                        
                        # 计算更新后的全局进度
                        updated_global_progress = (processed_months_count / total_months * 100) if total_months > 0 else 0
                        logger.info(f"    ✓ 完成: {repo_name} {month}, Bus Factor={metrics.bus_factor} | 全局进度: {processed_months_count}/{total_months} ({updated_global_progress:.1f}%)")
                        
                        # 增量保存（仅在 resume=True 时保存）
                        if resume:
                            self._save_results_incremental(all_results)
                    else:
                        logger.warning(f"计算指标失败: {repo_name} {month}")
                        error_count += 1
                    
                    # 释放图对象，避免内存泄漏
                    del graph
                except Exception as e:
                    logger.error(f"处理 {repo_name} {month} 时出错: {e}", exc_info=True)
                    error_count += 1
                    continue
            
            if not metrics_series:
                logger.warning(f"项目 {repo_name} 没有有效的指标数据，跳过")
                continue
            
            # 按月份排序（处理 None 值）
            metrics_series.sort(key=lambda m: m.month if m.month else "")
            self.repo_metrics[repo_name] = metrics_series
            
            # 确保 all_results 包含最终排序后的指标（即使 resume=False）
            if repo_name not in all_results:
                all_results[repo_name] = {"metrics": []}
            all_results[repo_name]["metrics"] = [m.to_dict() for m in metrics_series]
            
            # 计算项目完成进度
            repo_progress_pct = ((processed_count + skipped_count) / total_months_in_repo * 100) if total_months_in_repo > 0 else 100
            global_progress_pct = (processed_months_count / total_months * 100) if total_months > 0 else 0
            
            logger.info(f"  ✓ 项目完成 [{repo_idx}/{total_repos}] ({repo_idx/total_repos*100:.1f}%) | 处理 {processed_count} 个，跳过 {skipped_count} 个，错误 {error_count} 个")
            logger.info(f"  全局进度: {processed_months_count}/{total_months} ({global_progress_pct:.1f}%)")
            
            # 项目完成后，如果启用断点续传，更新 summary.json
            if resume:
                try:
                    # 计算该项目的趋势和风险评分
                    self.compute_trend_for_repo(repo_name)
                    self.compute_risk_score_for_repo(repo_name)
                    # 增量更新 summary.json
                    self._update_summary_incremental()
                    logger.debug(f"已更新摘要: {repo_name}")
                except Exception as e:
                    logger.warning(f"更新摘要时出错: {repo_name}, 错误: {e}")
        
        return all_results
    
    def _save_results_incremental(self, results: Dict[str, Any]) -> None:
        """增量保存结果（内部方法）- 使用原子写入防止文件损坏"""
        import os
        
        full_analysis_file = self.output_dir / "full_analysis.json"
        # 使用临时文件，写入成功后再重命名（原子操作）
        temp_file = self.output_dir / "full_analysis.json.tmp"
        
        # 添加趋势分析和风险评分（如果已计算）
        for repo_name in results:
            if repo_name in self.trends:
                results[repo_name]["trend"] = self.trends[repo_name].to_dict()
            if repo_name in self.risk_scores:
                results[repo_name]["risk_score"] = self.risk_scores[repo_name].to_dict()
        
        try:
            # 先写入临时文件
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
                # 确保数据已刷新到磁盘
                f.flush()
                os.fsync(f.fileno())
            
            # 原子操作：重命名临时文件为目标文件
            # 在 Windows 上，如果目标文件存在，需要先删除
            if full_analysis_file.exists():
                full_analysis_file.unlink()
            temp_file.replace(full_analysis_file)
            
            logger.debug(f"增量保存成功: {full_analysis_file}")
        except Exception as e:
            logger.warning(f"增量保存失败: {e}")
            # 清理临时文件
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
    
    def save_results(self, results: Dict[str, Any]) -> None:
        """
        保存完整分析结果到 full_analysis.json - 使用原子写入防止文件损坏
        
        Args:
            results: 分析结果字典
        """
        import os
        
        full_analysis_file = self.output_dir / "full_analysis.json"
        temp_file = self.output_dir / "full_analysis.json.tmp"
        
        # 添加趋势分析和风险评分（如果已计算）
        for repo_name in results:
            if repo_name in self.trends:
                results[repo_name]["trend"] = self.trends[repo_name].to_dict()
            if repo_name in self.risk_scores:
                results[repo_name]["risk_score"] = self.risk_scores[repo_name].to_dict()
        
        try:
            # 先写入临时文件
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
                # 确保数据已刷新到磁盘
                f.flush()
                os.fsync(f.fileno())
            
            # 原子操作：重命名临时文件为目标文件
            if full_analysis_file.exists():
                full_analysis_file.unlink()
            temp_file.replace(full_analysis_file)
            
            logger.info(f"完整分析结果已保存: {full_analysis_file}")
        except Exception as e:
            logger.error(f"保存完整分析结果失败: {e}")
            # 清理临时文件
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
            raise
    
    @staticmethod
    def calculate_trend(values: List[float], threshold: float = 0.1) -> Dict[str, Any]:
        """
        计算时间序列趋势（使用线性回归）
        
        Args:
            values: 时间序列值列表（按时间顺序）
            threshold: 判断"稳定"的斜率阈值
        
        Returns:
            趋势分析字典
        """
        if len(values) < 2:
            return {
                "direction": "数据不足",
                "slope": 0.0,
                "change_rate": 0.0,
                "values": values,
            }
        
        # 使用线性回归计算斜率
        n = len(values)
        x = np.arange(n)
        slope = np.polyfit(x, values, 1)[0]
        
        # 计算变化率
        first_value = values[0]
        last_value = values[-1]
        if math.isclose(first_value, 0.0, abs_tol=1e-9):
            change_rate = float('inf') if last_value > 0 else 0.0
        else:
            change_rate = ((last_value - first_value) / first_value) * 100
        
        # 判断趋势方向
        if abs(slope) < threshold:
            direction = "稳定"
        elif slope > 0:
            direction = "上升"
        else:
            direction = "下降"
        
        return {
            "direction": direction,
            "slope": float(slope),
            "change_rate": float(change_rate),
            "values": values,
        }
    
    def compute_trend_for_repo(self, repo_name: str) -> Optional[TrendAnalysis]:
        """
        为单个项目计算趋势分析
        
        Args:
            repo_name: 项目名称
        
        Returns:
            趋势分析对象，如果数据不足返回 None
        """
        if repo_name not in self.repo_metrics:
            return None
        
        metrics_series = self.repo_metrics[repo_name]
        
        if len(metrics_series) < 2:
            logger.debug(f"项目 {repo_name} 数据不足（少于2个月），标记为'数据不足'")
            trend_analysis = TrendAnalysis(
                repo_name=repo_name,
                bus_factor_trend={
                    "direction": "数据不足",
                    "slope": 0.0,
                    "change_rate": 0.0,
                    "values": [m.bus_factor for m in metrics_series] if metrics_series else [],
                },
                months=[m.month for m in metrics_series],
                bus_factor_values=[m.bus_factor for m in metrics_series],
            )
            self.trends[repo_name] = trend_analysis
            return trend_analysis
        
        # 按月份排序（处理 None 值）
        sorted_metrics = sorted(metrics_series, key=lambda m: m.month if m.month else "")
        bus_factor_values = [
            m.bus_factor
            for m in sorted_metrics
            if m.bus_factor is not None
        ]
        
        # 计算趋势
        trend = self.calculate_trend(bus_factor_values)
        
        trend_analysis = TrendAnalysis(
            repo_name=repo_name,
            bus_factor_trend=trend,
            months=[m.month for m in sorted_metrics],
            bus_factor_values=bus_factor_values,
        )
        self.trends[repo_name] = trend_analysis
        return trend_analysis
    
    def compute_trends(self) -> Dict[str, TrendAnalysis]:
        """
        为所有项目计算趋势分析
        
        Returns:
            趋势分析字典
        """
        logger.info("开始计算趋势分析...")
        
        for repo_name, metrics_series in self.repo_metrics.items():
            self.compute_trend_for_repo(repo_name)
        
        logger.info(f"趋势分析完成: {len(self.trends)} 个项目")
        return self.trends
    
    @staticmethod
    def calculate_risk_score(
        current_bus_factor: int,
        trend_direction: str,
        trend_change_rate: float,
        min_bus_factor: float = 1.0,
        max_bus_factor: float = 50.0,
    ) -> Dict[str, Any]:
        """
        计算综合风险评分（0-100，分数越高风险越高）
        
        Args:
            current_bus_factor: 当前 Bus Factor 值（基于整个时间序列的加权平均值）
            trend_direction: 趋势方向（"上升" | "下降" | "稳定" | "数据不足"）
            trend_change_rate: 变化率（百分比）
            min_bus_factor: 最小 Bus Factor 值（用于归一化，基于所有项目的所有月份）
            max_bus_factor: 最大 Bus Factor 值（用于归一化，基于所有项目的所有月份）
        
        Returns:
            风险评分字典
        """
        # 当前值得分（0-50）：Bus Factor 越小，风险越高
        normalized_factor = (current_bus_factor - min_bus_factor) / (max_bus_factor - min_bus_factor)
        normalized_factor = max(0.0, min(1.0, normalized_factor))  # 限制在 [0, 1]
        current_score = (1.0 - normalized_factor) * 50  # 反转：值越小得分越高
        
        # 趋势得分（0-50）：上升趋势风险高，下降趋势风险低
        if trend_direction == "数据不足":
            trend_score = 25.0  # 数据不足时给中等分数
        elif trend_direction == "上升":
            # Bus Factor 上升是好事（风险降低），所以趋势得分应该降低
            trend_score = max(0.0, 25.0 - abs(trend_change_rate) * 0.2)
        elif trend_direction == "下降":
            # Bus Factor 下降是坏事（风险增加），所以趋势得分应该增加
            trend_score = min(50.0, 25.0 + abs(trend_change_rate) * 0.2)
        else:  # 稳定
            trend_score = 25.0
        
        total_score = current_score + trend_score
        
        # 确定风险等级
        if total_score >= 70:
            risk_level = "高"
        elif total_score >= 40:
            risk_level = "中"
        else:
            risk_level = "低"
        
        return {
            "total_score": round(total_score, 2),
            "current_score": round(current_score, 2),
            "trend_score": round(trend_score, 2),
            "risk_level": risk_level,
        }
    
    def compute_risk_score_for_repo(
        self, 
        repo_name: str,
        min_bus_factor: float = None,
        max_bus_factor: float = None,
    ) -> Optional[RiskScore]:
        """
        为单个项目计算风险评分（基于整个时间序列）
        
        Args:
            repo_name: 项目名称
            min_bus_factor: 最小 Bus Factor 值（用于归一化，如果为 None 则从所有项目中计算）
            max_bus_factor: 最大 Bus Factor 值（用于归一化，如果为 None 则从所有项目中计算）
        
        Returns:
            风险评分对象，如果数据不足返回 None
        """
        if repo_name not in self.repo_metrics:
            return None
        
        metrics_series = self.repo_metrics[repo_name]
        if not metrics_series:
            return None
        
        # 计算趋势（如果还没有计算）
        if repo_name not in self.trends:
            self.compute_trend_for_repo(repo_name)
        
        # 如果没有提供范围，从所有已分析的项目中计算
        if min_bus_factor is None or max_bus_factor is None:
            all_bus_factors = []
            for ms in self.repo_metrics.values():
                # 过滤 None 值
                all_bus_factors.extend([m.bus_factor for m in ms if m.bus_factor is not None])
            min_bus_factor = min(all_bus_factors) if all_bus_factors else 1.0
            max_bus_factor = max(all_bus_factors) if all_bus_factors else 50.0
        
        # 改进：使用整个时间序列的加权平均 Bus Factor（按总贡献量加权）
        # 先过滤掉 bus_factor 为 None 的指标
        valid_metrics = [m for m in metrics_series if m.bus_factor is not None]
        
        if not valid_metrics:
            logger.warning(f"项目 {repo_name} 没有有效的 Bus Factor 数据，跳过评分")
            return None
        
        # 按月份排序
        sorted_metrics = sorted(valid_metrics, key=lambda m: m.month if m.month else "")
        
        # 计算加权平均 Bus Factor
        total_weights = sum(m.total_contribution for m in sorted_metrics)
        if total_weights > 0:
            # 使用加权平均（按总贡献量加权，更准确反映项目整体状况）
            avg_bus_factor = sum(
                m.bus_factor * m.total_contribution 
                for m in sorted_metrics
            ) / total_weights
        else:
            # 如果总贡献量都是0，使用简单平均
            avg_bus_factor = sum(m.bus_factor for m in sorted_metrics) / len(sorted_metrics)
        
        # 转换为整数（四舍五入）
        current_bus_factor = int(round(avg_bus_factor))
        
        # 获取趋势信息（基于整个时间序列）
        if repo_name in self.trends:
            trend = self.trends[repo_name]
            trend_direction = trend.bus_factor_trend["direction"]
            trend_change_rate = trend.bus_factor_trend["change_rate"]
        else:
            trend_direction = "数据不足"
            trend_change_rate = 0.0
        
        # 计算风险评分
        score_dict = self.calculate_risk_score(
            current_bus_factor,
            trend_direction,
            trend_change_rate,
            min_bus_factor,
            max_bus_factor,
        )
        
        risk_score = RiskScore(
            repo_name=repo_name,
            total_score=score_dict["total_score"],
            current_score=score_dict["current_score"],
            trend_score=score_dict["trend_score"],
            risk_level=score_dict["risk_level"],
            current_bus_factor=current_bus_factor,
            trend_direction=trend_direction,
        )
        self.risk_scores[repo_name] = risk_score
        return risk_score
    
    def compute_risk_scores(self) -> Dict[str, RiskScore]:
        """
        为所有项目计算风险评分
        
        Returns:
            风险评分字典
        """
        logger.info("开始计算风险评分...")
        
        # 先计算趋势（如果还没有计算）
        if not self.trends:
            self.compute_trends()
        
        # 找到所有 Bus Factor 值的范围（用于归一化）
        all_bus_factors = []
        for metrics_series in self.repo_metrics.values():
            # --- 修复点：添加 if m.bus_factor is not None ---
            all_bus_factors.extend([m.bus_factor for m in metrics_series if m.bus_factor is not None])
        
        # 增加兜底逻辑，防止整个列表为空
        if not all_bus_factors:
            min_bus_factor, max_bus_factor = 1.0, 50.0
        else:
            min_bus_factor = min(all_bus_factors)
            max_bus_factor = max(all_bus_factors)
        
        for repo_name, metrics_series in self.repo_metrics.items():
            if not metrics_series:
                continue
            self.compute_risk_score_for_repo(repo_name, min_bus_factor, max_bus_factor)
        
        logger.info(f"风险评分完成: {len(self.risk_scores)} 个项目")
        return self.risk_scores
    
    def _update_summary_incremental(self) -> None:
        """
        增量更新 summary.json（内部方法）
        只包含已分析完成的项目
        """
        # 计算所有已分析项目的风险评分
        # 找到所有 Bus Factor 值的范围（用于归一化）
        all_bus_factors = []
        for metrics_series in self.repo_metrics.values():
            # 修复点：过滤 None
            all_bus_factors.extend([
                m.bus_factor for m in metrics_series 
                if m.bus_factor is not None
            ])
        
        # --- 修复点：增加判空 ---
        if not all_bus_factors:
            min_bus_factor, max_bus_factor = 1.0, 50.0
        else:
            min_bus_factor = min(all_bus_factors)
            max_bus_factor = max(all_bus_factors)
        
        # 为所有已分析的项目计算风险评分
        for repo_name in self.repo_metrics.keys():
            if repo_name not in self.risk_scores:
                self.compute_risk_score_for_repo(repo_name, min_bus_factor, max_bus_factor)
        
        # 按风险评分降序排序
        sorted_repos = sorted(
            self.risk_scores.items(),
            key=lambda x: x[1].total_score,
            reverse=True,
        )
        
        summary = {
            "generated_at": datetime.now().isoformat(),
            "total_repos": len(sorted_repos),
            "repos": [score.to_dict() for _, score in sorted_repos],
        }
        
        summary_file = self.output_dir / "summary.json"
        temp_file = self.output_dir / "summary.json.tmp"
        
        try:
            import os
            # 先写入临时文件
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
                # 确保数据已刷新到磁盘
                f.flush()
                os.fsync(f.fileno())
            
            # 原子操作：重命名临时文件为目标文件
            if summary_file.exists():
                summary_file.unlink()
            temp_file.replace(summary_file)
            
            logger.debug(f"增量更新摘要: {summary_file}, 包含 {len(sorted_repos)} 个项目")
        except Exception as e:
            logger.warning(f"增量更新摘要失败: {e}")
            # 清理临时文件
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
    
    def save_summary(self) -> None:
        """
        生成 summary.json（按风险评分排序）
        """
        # 先计算风险评分（如果还没有计算）
        if not self.risk_scores:
            self.compute_risk_scores()
        
        # 按风险评分降序排序
        sorted_repos = sorted(
            self.risk_scores.items(),
            key=lambda x: x[1].total_score,
            reverse=True,
        )
        
        summary = {
            "generated_at": datetime.now().isoformat(),
            "total_repos": len(sorted_repos),
            "repos": [score.to_dict() for _, score in sorted_repos],
        }
        
        summary_file = self.output_dir / "summary.json"
        temp_file = self.output_dir / "summary.json.tmp"
        
        try:
            import os
            # 先写入临时文件
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
                # 确保数据已刷新到磁盘
                f.flush()
                os.fsync(f.fileno())
            
            # 原子操作：重命名临时文件为目标文件
            if summary_file.exists():
                summary_file.unlink()
            temp_file.replace(summary_file)
            
            logger.info(f"摘要已保存: {summary_file}")
        except Exception as e:
            logger.error(f"保存摘要失败: {e}")
            # 清理临时文件
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
            raise
        
        # 打印前10个高风险项目
        print("\n" + "=" * 60)
        print("前10个高风险项目:")
        print("=" * 60)
        for i, (repo_name, score) in enumerate(sorted_repos[:10], 1):
            print(
                f"{i:2d}. {repo_name:30s} "
                f"评分={score.total_score:5.1f} "
                f"等级={score.risk_level:4s} "
                f"Bus Factor={score.current_bus_factor:3d}"
            )
        print("=" * 60)
    
    def run(self, resume: bool = True) -> Dict[str, Any]:
        """
        运行完整分析流程
        
        Args:
            resume: 是否启用断点续传
        
        Returns:
            分析结果字典
        """
        logger.info("=" * 60)
        logger.info("开始 Bus Factor 分析")
        logger.info("=" * 60)
        
        # 1. 分析所有项目的时间序列
        results = self.analyze_all_repos(resume=resume)
        
        if not results:
            logger.warning("没有分析结果")
            return {}
        
        # 2. 计算趋势分析
        self.compute_trends()
        
        # 3. 计算风险评分
        self.compute_risk_scores()
        
        # 4. 保存完整结果
        self.save_results(results)
        
        # 5. 生成摘要
        self.save_summary()
        
        logger.info("=" * 60)
        logger.info("分析完成!")
        logger.info(f"分析项目数: {len(results)}")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info("=" * 60)
        
        return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Bus Factor 分析")
    parser.add_argument(
        "--graphs-dir",
        type=str,
        default="output/monthly-graphs/",
        help="图文件目录",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/bus-factor-analysis/",
        help="输出目录",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Bus Factor 计算阈值（默认0.5）",
    )
    parser.add_argument(
        "--weights-file",
        type=str,
        default=None,
        help="权重配置文件路径（JSON格式）",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="单项目分析模式：项目名称（如 angular-angular）",
    )
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        help="单月份分析模式：月份（如 2023-01）",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="禁用断点续传",
    )
    
    args = parser.parse_args()
    
    # 加载权重配置（如果提供）
    weights = None
    if args.weights_file:
        try:
            with open(args.weights_file, "r", encoding="utf-8") as f:
                weights = json.load(f)
            print(f"已加载权重配置: {args.weights_file}")
        except Exception as e:
            print(f"警告: 无法加载权重配置文件: {e}")
            print("使用默认权重配置")
    
    analyzer = BusFactorAnalyzer(
        graphs_dir=args.graphs_dir,
        output_dir=args.output_dir,
        threshold=args.threshold,
        weights=weights,
    )
    
    # 单项目单月份分析模式（用于测试）
    if args.repo and args.month:
        print(f"单项目单月份分析模式: {args.repo} {args.month}")
        graph_path = Path(args.graphs_dir) / args.repo / "actor-repo" / f"{args.month}.graphml"
        
        if not graph_path.exists():
            print(f"错误: 图文件不存在: {graph_path}")
            exit(1)
        
        graph = analyzer.load_graph(str(graph_path))
        if graph is None:
            print(f"错误: 无法加载图文件: {graph_path}")
            exit(1)
        
        metrics = analyzer.compute_monthly_metrics(graph, args.repo, args.month)
        if metrics:
            analyzer.save_single_result(metrics)
            print(f"分析完成！Bus Factor: {metrics.bus_factor}")
        else:
            print("分析失败")
            exit(1)
    else:
        # 运行完整分析
        analyzer.run(resume=not args.no_resume)

