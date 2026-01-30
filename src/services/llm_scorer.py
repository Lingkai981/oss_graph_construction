"""
LLM 评分模块

使用 DeepSeek API 对社区氛围指标进行评分。
基于毒性指标和 CHAOSS 指标，给出综合评分和评价理由。
"""

from __future__ import annotations

import json
import os
import re
import time
import threading
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from src.utils.logger import get_logger

logger = get_logger()

# 加载.env文件
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    PROJECT_ROOT = env_path.parent
else:
    load_dotenv()
    PROJECT_ROOT = Path(__file__).parent.parent.parent


# Prompt 模板
LLM_SCORING_PROMPT = """【系统角色】
你是一个开源社区健康度评估专家，精通 CHAOSS（Community Health Analytics for Open Source Software）指标体系和社区毒性分析。请根据给定的月度指标数据，对社区氛围进行客观评分。

【指标定义与解释】

## 毒性指标（来源：ToxiCR 毒性检测模型）

1. toxicity_mean（平均毒性分数）
   - 定义：该月所有评论的毒性概率均值
   - 范围：[0, 1]，0 表示完全无毒，1 表示完全有毒
   - 参考：开源社区的健康值通常在 0.03-0.10 之间

2. toxicity_p95（毒性95分位数）
   - 定义：95%的评论毒性低于此值
   - 意义：反映极端毒性行为的严重程度

3. toxic_rate_0_5（高毒性评论占比）
   - 定义：毒性概率 >= 0.5 的评论占总评论的比例
   - 意义：直接反映有害评论的频率

4. comment_analyzed_count（被分析评论数）
   - 意义：样本量，样本越大指标越可靠；样本量过小时应谨慎评价

## CHAOSS 指标

5. change_request_closure_ratio（变更请求关闭率）
   - 定义：(closed_prs + closed_issues) / (opened_prs + opened_issues)
   - 意义：衡量社区处理贡献的能力
   - 解读：
     - > 1.0：消化能力强，处理速度快于提交速度
     - = 1.0：平衡状态
     - < 1.0：存在积压，可能需要更多维护者
     - 值为 0 时需检查 opened_prs 和 opened_issues 是否也为 0（表示无有效数据）

6. time_to_first_response_median（首次响应时间中位数，单位：小时）
   - 定义：从 Issue/PR 创建到第一条评论的时间间隔的中位数
   - 意义：反映社区活跃度和响应速度，时间越短越好
   - 参考：活跃社区通常在 2-12 小时内响应

7. time_to_first_response_p95（首次响应时间95分位数，单位：小时）
   - 意义：反映最慢响应情况，95%的请求在此时间内得到响应

8. items_with_response / items_without_response
   - 意义：响应覆盖率 = with / (with + without)
   - 解读：覆盖率越高说明社区响应越全面

【评分说明】

总分 100 分，分为两个维度：
- 毒性水平（40 分）：评估社区交流的健康程度
- 响应效率（60 分）：评估社区处理贡献的能力和速度

请根据指标的实际含义，结合你对开源社区健康度的理解，给出合理的评分。

特别注意：
- 如果某些指标数据为 0 或样本量过小，请在理由中说明数据可信度问题
- 评分应基于指标的客观含义，而非主观印象

【输入数据】

仓库：{repo_name}
月份：{month}

指标数据：
- toxicity_mean: {toxicity_mean}
- toxicity_p95: {toxicity_p95}
- toxic_rate_0_5: {toxic_rate_0_5}
- toxic_comment_count_0_5: {toxic_comment_count_0_5}
- comment_analyzed_count: {comment_analyzed_count}
- change_request_closure_ratio: {change_request_closure_ratio}
- opened_prs: {opened_prs}
- closed_prs: {closed_prs}
- opened_issues: {opened_issues}
- closed_issues: {closed_issues}
- time_to_first_response_median: {time_to_first_response_median}
- time_to_first_response_mean: {time_to_first_response_mean}
- time_to_first_response_p95: {time_to_first_response_p95}
- items_with_response: {items_with_response}
- items_without_response: {items_without_response}

【输出要求】

请严格按照以下 JSON 格式输出，不要包含其他内容：

{{
  "score": <0-100的整数>,
  "toxicity_score": <0-40的整数>,
  "response_score": <0-60的整数>,
  "toxicity_reason": "<毒性评分理由，50字以内>",
  "response_reason": "<响应效率评分理由，50字以内>",
  "overall_reason": "<综合评价，80字以内>"
}}"""


class LLMScorer:
    """
    LLM 评分器
    
    使用 DeepSeek API 对社区氛围指标进行评分。
    支持缓存和断点续传。
    """
    
    API_BASE_URL = "https://api.deepseek.com/v1/chat/completions"
    DEFAULT_TIMEOUT = 60  # 秒
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # 秒
    
    def __init__(self, api_key: Optional[str] = None, cache_file: Optional[str] = None) -> None:
        """
        初始化 LLM 评分器
        
        Args:
            api_key: DeepSeek API 密钥，如果为 None 则从环境变量读取
            cache_file: 缓存文件路径，如果为 None 则使用默认路径
        """
        if api_key is None:
            api_key = os.getenv("DEEPSEEK_API_KEY")
        self.api_key = api_key
        self._available = self.api_key is not None and len(self.api_key.strip()) > 0
        
        # 缓存设置
        if cache_file is None:
            cache_dir = PROJECT_ROOT / "output" / "community-atmosphere-analysis"
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path = cache_dir / "llm_score_cache.json"
        else:
            self._cache_path = Path(cache_file)
        
        self._cache_lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = self._load_cache()
        
        if self._available:
            logger.info(f"✓ LLM 评分器初始化成功，API Key 已配置")
        else:
            logger.warning("✗ LLM 评分器初始化失败，DEEPSEEK_API_KEY 未配置")
    
    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        """加载缓存"""
        if not self._cache_path.exists():
            return {}
        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                logger.info(f"加载 LLM 评分缓存: {len(data)} 条记录")
                return data
        except Exception as e:
            logger.warning(f"加载 LLM 评分缓存失败: {e}")
        return {}
    
    def _save_cache(self) -> None:
        """保存缓存"""
        try:
            with self._cache_lock:
                cache_snapshot = dict(self._cache)
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_snapshot, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存 LLM 评分缓存失败: {e}")
    
    @staticmethod
    def _make_cache_key(repo_name: str, month: str) -> str:
        """生成缓存键"""
        return f"{repo_name}:{month}"
    
    def is_available(self) -> bool:
        """检查 API 是否可用"""
        return self._available
    
    def get_cached_score(self, repo_name: str, month: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的评分结果
        
        Args:
            repo_name: 仓库名称
            month: 月份
            
        Returns:
            缓存的评分结果，如果没有则返回 None
        """
        cache_key = self._make_cache_key(repo_name, month)
        with self._cache_lock:
            return self._cache.get(cache_key)
    
    def score_monthly_metrics(
        self,
        repo_name: str,
        month: str,
        metrics: Dict[str, Any],
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        对月度指标进行 LLM 评分
        
        Args:
            repo_name: 仓库名称
            month: 月份
            metrics: 月度指标数据
            use_cache: 是否使用缓存
            
        Returns:
            评分结果字典，包含：
            - score: 总分 (0-100)
            - toxicity_score: 毒性得分 (0-40)
            - response_score: 响应效率得分 (0-60)
            - toxicity_reason: 毒性评分理由
            - response_reason: 响应效率评分理由
            - overall_reason: 综合评价
        """
        if not self.is_available():
            logger.error("DeepSeek API 不可用，无法进行 LLM 评分")
            return self._default_score("API 不可用")
        
        # 检查缓存
        cache_key = self._make_cache_key(repo_name, month)
        if use_cache:
            with self._cache_lock:
                cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"使用缓存的 LLM 评分: {repo_name} {month}")
                return cached
        
        # 构建 prompt
        prompt = LLM_SCORING_PROMPT.format(
            repo_name=repo_name,
            month=month,
            toxicity_mean=metrics.get("toxicity_mean", 0.0),
            toxicity_p95=metrics.get("toxicity_p95", 0.0),
            toxic_rate_0_5=metrics.get("toxic_rate_0_5", 0.0),
            toxic_comment_count_0_5=metrics.get("toxic_comment_count_0_5", 0),
            comment_analyzed_count=metrics.get("comment_analyzed_count", 0),
            change_request_closure_ratio=metrics.get("change_request_closure_ratio", 0.0),
            opened_prs=metrics.get("opened_prs", 0),
            closed_prs=metrics.get("closed_prs", 0),
            opened_issues=metrics.get("opened_issues", 0),
            closed_issues=metrics.get("closed_issues", 0),
            time_to_first_response_median=metrics.get("time_to_first_response_median", 0.0),
            time_to_first_response_mean=metrics.get("time_to_first_response_mean", 0.0),
            time_to_first_response_p95=metrics.get("time_to_first_response_p95", 0.0),
            items_with_response=metrics.get("items_with_response", 0),
            items_without_response=metrics.get("items_without_response", 0),
        )
        
        # 调用 API
        result = self._call_api(prompt, repo_name, month)
        
        # 缓存结果
        with self._cache_lock:
            self._cache[cache_key] = result
        self._save_cache()
        
        return result
    
    def _call_api(self, prompt: str, repo_name: str, month: str) -> Dict[str, Any]:
        """
        调用 DeepSeek API
        
        Args:
            prompt: 完整的 prompt
            repo_name: 仓库名称（用于日志）
            month: 月份（用于日志）
            
        Returns:
            解析后的评分结果
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,  # 较低的温度以获得更稳定的评分
            "max_tokens": 512,
        }
        
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.post(
                    self.API_BASE_URL,
                    headers=headers,
                    json=payload,
                    timeout=self.DEFAULT_TIMEOUT,
                )
                response.raise_for_status()
                
                # 解析响应
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                content = content.strip()
                
                # 解析 JSON
                parsed = self._parse_response(content)
                if parsed is not None:
                    logger.info(f"  LLM 评分完成: {repo_name} {month} -> {parsed['score']}分")
                    return parsed
                else:
                    logger.warning(f"  LLM 响应解析失败: {repo_name} {month}, 响应: {content[:100]}")
                    last_error = "响应解析失败"
                    
            except requests.exceptions.Timeout:
                last_error = "请求超时"
                logger.warning(f"  LLM 评分超时 (attempt {attempt + 1}/{self.MAX_RETRIES}): {repo_name} {month}")
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                logger.warning(f"  LLM 评分请求失败 (attempt {attempt + 1}/{self.MAX_RETRIES}): {repo_name} {month}, 错误: {e}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"  LLM 评分异常 (attempt {attempt + 1}/{self.MAX_RETRIES}): {repo_name} {month}, 错误: {e}")
            
            # 重试前等待
            if attempt < self.MAX_RETRIES - 1:
                time.sleep(self.RETRY_DELAY * (attempt + 1))
        
        # 所有重试都失败
        logger.error(f"  LLM 评分失败: {repo_name} {month}, 最后错误: {last_error}")
        return self._default_score(f"API 调用失败: {last_error}")
    
    def _parse_response(self, content: str) -> Optional[Dict[str, Any]]:
        """
        解析 LLM 响应
        
        Args:
            content: LLM 返回的内容
            
        Returns:
            解析后的字典，如果解析失败返回 None
        """
        try:
            # 尝试直接解析 JSON
            parsed = json.loads(content)
            return self._validate_and_normalize(parsed)
        except json.JSONDecodeError:
            pass
        
        # 尝试从内容中提取 JSON
        # 匹配 {...} 格式
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                return self._validate_and_normalize(parsed)
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _validate_and_normalize(self, parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        验证并规范化解析结果
        
        Args:
            parsed: 解析后的字典
            
        Returns:
            规范化后的字典，如果验证失败返回 None
        """
        try:
            score = int(parsed.get("score", 0))
            toxicity_score = int(parsed.get("toxicity_score", 0))
            response_score = int(parsed.get("response_score", 0))
            
            # 边界检查
            score = max(0, min(100, score))
            toxicity_score = max(0, min(40, toxicity_score))
            response_score = max(0, min(60, response_score))
            
            return {
                "score": score,
                "toxicity_score": toxicity_score,
                "response_score": response_score,
                "toxicity_reason": str(parsed.get("toxicity_reason", ""))[:100],
                "response_reason": str(parsed.get("response_reason", ""))[:100],
                "overall_reason": str(parsed.get("overall_reason", ""))[:150],
            }
        except (ValueError, TypeError):
            return None
    
    def _default_score(self, reason: str) -> Dict[str, Any]:
        """
        返回默认评分（用于 API 调用失败时）
        
        Args:
            reason: 失败原因
            
        Returns:
            默认评分字典
        """
        return {
            "score": 0,
            "toxicity_score": 0,
            "response_score": 0,
            "toxicity_reason": "",
            "response_reason": "",
            "overall_reason": f"评分失败: {reason}",
        }

    def score_batch(
        self,
        tasks: List[Tuple[str, str, Dict[str, Any]]],
        max_workers: int = 8,
        rate_limit_delay: float = 0.1,
    ) -> Dict[str, Dict[str, Any]]:
        """
        批量并发评分
        
        Args:
            tasks: 评分任务列表，每个任务是 (repo_name, month, metrics) 元组
            max_workers: 最大并发线程数，默认 8
            rate_limit_delay: 每次请求之间的最小间隔（秒），用于限流
            
        Returns:
            {cache_key: score_result} 字典，cache_key 格式为 "repo_name:month"
        """
        if not self.is_available():
            logger.error("DeepSeek API 不可用，无法进行批量 LLM 评分")
            return {}
        
        # 过滤掉已缓存的任务
        tasks_to_process: List[Tuple[str, str, Dict[str, Any]]] = []
        results: Dict[str, Dict[str, Any]] = {}
        
        for repo_name, month, metrics in tasks:
            cache_key = self._make_cache_key(repo_name, month)
            cached = self.get_cached_score(repo_name, month)
            if cached is not None:
                results[cache_key] = cached
                logger.debug(f"使用缓存: {repo_name} {month}")
            else:
                tasks_to_process.append((repo_name, month, metrics))
        
        if not tasks_to_process:
            logger.info(f"批量评分: 全部 {len(tasks)} 个任务已有缓存，无需调用 API")
            return results
        
        total = len(tasks_to_process)
        cached_count = len(tasks) - total
        logger.info(f"批量评分: 共 {len(tasks)} 个任务，{cached_count} 个已缓存，{total} 个需调用 API")
        print(f"开始批量 LLM 评分: {total} 个任务, {max_workers} 并发...", flush=True)
        
        # 用于限流的锁和计数器
        rate_limit_lock = threading.Lock()
        last_request_time = [0.0]  # 使用列表以便在闭包中修改
        completed_count = [0]
        
        def process_single_task(task: Tuple[str, str, Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
            repo_name, month, metrics = task
            cache_key = self._make_cache_key(repo_name, month)
            
            # 限流控制
            with rate_limit_lock:
                now = time.time()
                elapsed = now - last_request_time[0]
                if elapsed < rate_limit_delay:
                    time.sleep(rate_limit_delay - elapsed)
                last_request_time[0] = time.time()
            
            # 调用评分
            result = self.score_monthly_metrics(repo_name, month, metrics, use_cache=True)
            
            # 更新进度
            with rate_limit_lock:
                completed_count[0] += 1
                if completed_count[0] % 10 == 0 or completed_count[0] == total:
                    print(f"  LLM 评分进度: {completed_count[0]}/{total}", flush=True)
            
            return cache_key, result
        
        # 并发执行
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(process_single_task, task): task
                for task in tasks_to_process
            }
            
            for future in as_completed(futures):
                task = futures[future]
                try:
                    cache_key, result = future.result()
                    results[cache_key] = result
                except Exception as e:
                    repo_name, month, _ = task
                    cache_key = self._make_cache_key(repo_name, month)
                    logger.error(f"批量评分异常: {repo_name} {month}, 错误: {e}")
                    results[cache_key] = self._default_score(str(e))
        
        print(f"批量 LLM 评分完成: {total} 个任务", flush=True)
        logger.info(f"批量 LLM 评分完成: {total} 个任务")
        
        return results
