"""
DeepSeek API客户端

用于调用DeepSeek API进行情感分析。
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from src.utils.logger import get_logger

logger = get_logger()

# 加载.env文件（从项目根目录）
env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # 如果项目根目录没有.env文件，尝试加载当前目录的.env
    load_dotenv()


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
        
        Raises:
            Exception: 如果API调用失败
        """
        if not self.is_available():
            raise ValueError("DeepSeek API key未配置")
        
        if not text or not text.strip():
            return 0.0
        
        # 构建API请求
        prompt = f"""请分析以下文本的情感倾向，返回一个-1到1之间的分数：
- 1.0表示非常正面
- 0.5表示正面
- 0.0表示中性
- -0.5表示负面
- -1.0表示非常负面

文本内容：
{text}

只返回一个数字，不要其他内容。"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 10,
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
                
                # 提取数字
                try:
                    sentiment = float(content.strip())
                    # 限制在[-1, 1]范围内
                    sentiment = max(-1.0, min(1.0, sentiment))
                    return sentiment
                except ValueError:
                    logger.warning(f"无法解析API返回的情感分数: {content}，使用默认值0.0")
                    return 0.0
                    
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

