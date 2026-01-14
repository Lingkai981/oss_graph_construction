"""
GitHub 事件数据加载器

负责从 GitHub 事件 JSON 行文件中逐行读取并解析事件对象，
为后续的时序语义图构建提供原始事件列表。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.utils.logger import get_logger

logger = get_logger()


def load_events_from_file(path: str) -> List[Dict[str, Any]]:
    """
    从给定的 JSON 行文件中加载所有事件。

    每一行应是一个完整的 GitHub 事件 JSON 对象。
    解析失败的行会被跳过，并在日志中记录详细信息。

    Args:
        path: JSON 行文件路径

    Returns:
        事件字典列表
    """
    file_path = Path(path)
    if not file_path.exists():
        logger.error(f"事件数据文件不存在: {file_path}")
        raise FileNotFoundError(str(file_path))

    events: List[Dict[str, Any]] = []
    total_lines = 0
    error_lines = 0

    logger.info(f"开始加载 GitHub 事件数据文件: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            total_lines += 1
            text = line.strip()
            if not text:
                continue
            try:
                event = json.loads(text)
                if not isinstance(event, dict):
                    error_lines += 1
                    logger.warning(f"第 {line_no} 行不是字典对象，已跳过")
                    continue

                # 基本字段校验：缺失关键字段的记录直接跳过
                if not all(k in event for k in ("id", "type", "created_at")):
                    error_lines += 1
                    logger.warning(
                        f"第 {line_no} 行缺少关键字段(id/type/created_at)，已跳过"
                    )
                    continue

                events.append(event)
            except json.JSONDecodeError as e:
                error_lines += 1
                logger.warning(f"解析第 {line_no} 行 JSON 失败: {e}")

    logger.info(
        f"事件数据加载完成: 共读取 {total_lines} 行，有效事件 {len(events)} 条，"
        f"解析失败 {error_lines} 行"
    )

    return events


def iter_events(path: str) -> Iterable[Dict[str, Any]]:
    """
    以生成器方式按行迭代事件，适合处理更大文件。

    Args:
        path: JSON 行文件路径

    Yields:
        单个事件字典
    """
    file_path = Path(path)
    if not file_path.exists():
        logger.error(f"事件数据文件不存在: {file_path}")
        raise FileNotFoundError(str(file_path))

    with file_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                event = json.loads(text)
                if isinstance(event, dict):
                    yield event
                else:
                    logger.warning(f"第 {line_no} 行不是字典对象，已跳过")
            except json.JSONDecodeError as e:
                logger.warning(f"解析第 {line_no} 行 JSON 失败: {e}")


