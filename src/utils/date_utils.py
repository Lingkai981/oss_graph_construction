"""
日期处理工具

包含时间戳解析函数，支持多种日期格式（ISO 8601、标准格式、Unix时间戳）
"""

from datetime import datetime
from typing import Optional


def parse_timestamp(timestamp: str) -> Optional[datetime]:
    """
    解析时间戳字符串，支持多种格式
    
    支持的格式：
    - ISO 8601格式：2024-01-01T12:00:00Z 或 2024-01-01T12:00:00+00:00
    - 标准格式：2024-01-01 12:00:00
    - Unix时间戳（字符串）：1609459200
    
    Args:
        timestamp: 时间戳字符串
    
    Returns:
        解析后的datetime对象，如果解析失败返回None
    """
    if not timestamp or not isinstance(timestamp, str):
        return None
    
    # 尝试ISO 8601格式
    try:
        # 处理带Z的格式
        if timestamp.endswith('Z'):
            timestamp = timestamp[:-1] + '+00:00'
        return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        pass
    
    # 尝试标准格式：YYYY-MM-DD HH:MM:SS
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d',
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(timestamp, fmt)
        except ValueError:
            continue
    
    # 尝试Unix时间戳（字符串格式）
    try:
        # 检查是否为数字字符串
        if timestamp.isdigit() or (timestamp.replace('.', '').isdigit()):
            ts = float(timestamp)
            # 如果是毫秒时间戳（13位），转换为秒
            if ts > 1e10:
                ts = ts / 1000
            return datetime.fromtimestamp(ts)
    except (ValueError, OSError):
        pass
    
    return None


def extract_date(timestamp: str) -> Optional[str]:
    """
    从时间戳中提取日期（YYYY-MM-DD格式）
    
    Args:
        timestamp: 时间戳字符串
    
    Returns:
        日期字符串（YYYY-MM-DD格式），如果解析失败返回None
    """
    dt = parse_timestamp(timestamp)
    if dt:
        return dt.strftime('%Y-%m-%d')
    return None


def format_date(date_str: str) -> Optional[datetime]:
    """
    格式化日期字符串为datetime对象
    
    Args:
        date_str: 日期字符串（YYYY-MM-DD格式）
    
    Returns:
        datetime对象，如果解析失败返回None
    """
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return None

