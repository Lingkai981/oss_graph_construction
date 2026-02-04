"""
DeepSeek API客户端

用于调用DeepSeek API进行情感分析。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import threading
import requests
from dotenv import load_dotenv

from src.utils.logger import get_logger

logger = get_logger()

# 加载.env文件（从项目根目录）
env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    PROJECT_ROOT = env_path.parent
else:
    # 如果项目根目录没有.env文件，尝试加载当前目录的.env
    load_dotenv()
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class DeepSeekClient:
    """DeepSeek API客户端"""
    
    API_BASE_URL = "https://api.deepseek.com/v1/chat/completions"
    DEFAULT_TIMEOUT = 30  # 秒（增加到30秒，避免超时）
    MAX_RETRIES = 2
    
    def __init__(self, api_key: Optional[str] = None) -> None:
        """
        初始化DeepSeek客户端
        
        Args:
            api_key: API密钥，如果为None则从.env文件中的DEEPSEEK_API_KEY读取
        """
        if api_key is None:
            api_key = os.getenv("DEEPSEEK_API_KEY")
        self.api_key = api_key
        self._available = self.api_key is not None and len(self.api_key.strip()) > 0

        # 情感分析结果缓存：避免对相同文本重复调用 API，并方便后续离线分析
        cache_dir = PROJECT_ROOT / "output"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = cache_dir / "sentiment_cache.json"
        self._cache_lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = self._load_cache()

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        if not self._cache_path.exists():
            return {}
        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning(f"加载情感分析缓存失败，将从空缓存开始: {e}")
        return {}

    def _save_cache(self) -> None:
        try:
            # 多线程并发时，json.dump 会迭代 dict；若此时 dict 被其他线程修改会触发
            # "dictionary changed size during iteration"。这里在锁内拷贝快照，锁外落盘。
            with self._cache_lock:
                cache_snapshot = dict(self._cache)
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_snapshot, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存情感分析缓存失败: {e}")

    @staticmethod
    def _make_cache_key(text: str) -> str:
        """对文本做哈希，作为缓存 key，避免巨长的键"""
        normalized = (text or "").strip()
        h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"sha256:{h}"
    
    def is_available(self) -> bool:
        """
        检查API是否可用
        
        Returns:
            True如果API key已配置，False否则
        """
        return self._available
    
    def test_api(self) -> tuple:
        """
        测试 API key 是否有效
        
        Returns:
            (是否成功, 消息)
        """
        if not self.is_available():
            return False, "API key 未配置"
        
        try:
            # 使用一个简单的测试文本
            result = self.analyze_sentiment("测试")
            return True, f"API key 有效，测试返回分数: {result}"
        except Exception as e:
            return False, f"API key 测试失败: {str(e)}"
    
    def analyze_sentiment(self, text: str) -> float:
        """
        分析文本情感
        
        Args:
            text: 待分析的文本内容
        
        Returns:
            情感分数，范围-1到1之间
            - 正值表示正面情绪
            - 负值表示负面情绪
            - 0表示中性
        
        说明：
            - 优先从本地缓存读取相同文本的情感分数，避免重复调用 API；
            - 调用 DeepSeek 时使用结构化提示词，请求返回 JSON，便于后续分析；
        
        Raises:
            Exception: 如果API调用失败
        """
        if not self.is_available():
            raise ValueError("DeepSeek API key未配置")
        
        if not text or not text.strip():
            return 0.0

        cache_key = self._make_cache_key(text)
        with self._cache_lock:
            cached = self._cache.get(cache_key)
        if cached is not None and "score" in cached:
            try:
                return float(cached["score"])
            except Exception:
                pass
        
        # 构建API请求：要求返回结构化 JSON，鼓励充分利用 [-1, 1] 区间
        prompt = f"""
你是一个专业的情感分析模型，专门分析开源社区中开发者在 Issue / PR / 评论中的语气。
请阅读下面的原文文本（可能包含英文、表情、代码片段）。

请根据整体语气给出一个情感分数，范围为 -1 到 1：
-1.0：极其消极 / 强烈不满、攻击、辱骂、严重冲突
-0.5：明显偏消极 / 抱怨、讽刺、明显负面情绪
 0.0：整体中性或主要是客观描述、技术讨论，几乎没有情绪色彩
+0.5：明显偏积极 / 友好、感谢、鼓励、建设性正面反馈
+1.0：极其积极 / 强烈赞美、兴奋、庆祝

要求：
1. 综合全文语气，不要只看单个词。
2. 可以使用整个 [-1, 1] 区间，不要总是给非常接近 0 的分数。
3. 如果文本几乎是纯日志或代码，没有明显情绪，可以给接近 0 的分数（例如 -0.1 ~ 0.1）。

请严格按以下 JSON 格式回答（不要添加任何多余的文字、注释或 Markdown）：
{{
  "score": <一个介于 -1 和 1 之间的浮点数>,
  "label": "negative" 或 "neutral" 或 "positive",
  "reason": "用一两句话解释你为什么这样打分（可以使用中文或英文）"
}}

需要分析的文本：
\"\"\"
{text}
\"\"\"
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
            "temperature": 0.2,
            "max_tokens": 128,
        }
        
        # 重试机制
        last_error = None
        for attempt in range(self.MAX_RETRIES + 1):
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
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "0")
                raw_content = content.strip()

                sentiment: float = 0.0
                parsed_obj: Dict[str, Any] = {}

                # 1) 优先按 JSON 解析
                try:
                    parsed_obj = json.loads(raw_content)
                    if isinstance(parsed_obj, dict) and "score" in parsed_obj:
                        sentiment = float(parsed_obj.get("score"))
                    else:
                        raise ValueError("JSON 中缺少 score 字段")
                except Exception:
                    # 2) 回退：从文本中用正则提取第一个数字
                    num_match = re.search(r"[-+]?\d+(\.\d+)?", raw_content)
                    if num_match:
                        sentiment = float(num_match.group(0))
                    else:
                        logger.warning(f"无法从API返回内容中解析情感分数: {raw_content}，使用默认值0.0")
                        sentiment = 0.0

                # 限制在 [-1, 1] 范围内
                sentiment = max(-1.0, min(1.0, sentiment))

                # 写入/更新缓存，便于后续复用和人工检查
                cache_record = {
                    "text": text,
                    "score": sentiment,
                    "label": parsed_obj.get("label") if isinstance(parsed_obj, dict) else None,
                    "reason": parsed_obj.get("reason") if isinstance(parsed_obj, dict) else None,
                    "model": payload.get("model"),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "raw_response": raw_content,
                }
                with self._cache_lock:
                    self._cache[cache_key] = cache_record
                self._save_cache()

                return sentiment
                    
            except requests.exceptions.Timeout:
                last_error = "API调用超时"
                if attempt < self.MAX_RETRIES:
                    time.sleep(1)  # 等待1秒后重试
                    continue
            except requests.exceptions.RequestException as e:
                last_error = f"API调用失败: {str(e)}"
                if attempt < self.MAX_RETRIES:
                    time.sleep(1)
                    continue
            except Exception as e:
                last_error = f"未知错误: {str(e)}"
                break
        
        # 所有重试都失败
        raise Exception(f"DeepSeek API调用失败: {last_error}")

        