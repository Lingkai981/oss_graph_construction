"""
日志配置工具

配置logging模块，支持文件和控制台输出，所有日志消息使用中文
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(log_level: str = "INFO", log_file: str = "logs/app.log") -> logging.Logger:
    """
    设置并配置日志记录器
    
    Args:
        log_level: 日志级别（DEBUG/INFO/WARNING/ERROR）
        log_file: 日志文件路径
    
    Returns:
        配置好的日志记录器
    """
    # 确保日志目录存在
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 创建日志记录器
    logger = logging.getLogger("snapshot_graph")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # 清除已有的处理器
    logger.handlers.clear()
    
    # 创建格式化器（使用中文）
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 文件处理器（带轮转）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


def get_logger() -> logging.Logger:
    """
    获取默认日志记录器
    
    Returns:
        默认日志记录器
    """
    return logging.getLogger("snapshot_graph")

