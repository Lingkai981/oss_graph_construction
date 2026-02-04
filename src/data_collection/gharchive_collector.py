"""
GitHub Archive 数据收集器

功能：
1. 流式下载 GitHub Archive 数据（内存友好）
2. 实时过滤只保留目标项目的事件
3. 支持断点续传
4. 自动清理临时文件

使用方式：
    python -m src.data_collection.gharchive_collector \
        --start-date 2023-01-01 \
        --end-date 2025-01-01 \
        --sample-mode fulldaily \
        --output-dir data/filtered/

采样模式：
    fulldaily: 每天 24 小时全量采集，按日合并为 {YYYY-MM-DD}-filtered.json
    daily: 每天 1 小时（12:00 UTC），输出 {YYYY-MM-DD}-12-filtered.json
    monthly: 每月 1 小时，数据量小
"""

from __future__ import annotations

import gzip
import json
import shutil
import sys
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Set, Dict, Any, List, Tuple
import argparse

from src.data_collection.representative_projects import get_project_set
from src.utils.logger import get_logger

logger = get_logger()

# GitHub Archive URL 模板
GHARCHIVE_URL_TEMPLATE = "https://data.gharchive.org/{date}-{hour}.json.gz"

# 采样模式
SAMPLE_MODES = {
    "hourly": list(range(24)),           # 每小时，每个小时单独存储
    "daily": [12],                         # 每天中午12点 UTC，1小时
    "fulldaily": list(range(24)),         # 每天 24 小时，合并为每日一个 JSON 文件
    "weekly": [12],                        # 每周一中午（需要日期过滤）
    "monthly": [12],                       # 每月1号中午（需要日期过滤）
}


class ProgressTracker:
    """进度跟踪器，支持断点续传（线程安全）"""
    
    def __init__(self, progress_file: str):
        self.progress_file = Path(progress_file)
        self.completed: Set[str] = set()
        self._lock = threading.Lock()
        self._load()
    
    def _load(self):
        """加载已完成的文件列表"""
        if self.progress_file.exists():
            with open(self.progress_file, "r") as f:
                self.completed = set(line.strip() for line in f if line.strip())
            logger.info(f"已加载进度文件，已完成 {len(self.completed)} 个文件")
    
    def is_completed(self, file_id: str) -> bool:
        """检查文件是否已处理"""
        with self._lock:
            return file_id in self.completed
    
    def mark_completed(self, file_id: str):
        """标记文件为已完成"""
        with self._lock:
            self.completed.add(file_id)
            with open(self.progress_file, "a") as f:
                f.write(f"{file_id}\n")
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        with self._lock:
            return {"completed": len(self.completed)}


class GHArchiveCollector:
    """GitHub Archive 数据收集器"""
    
    def __init__(
        self,
        target_projects: Set[str],
        output_dir: str,
        temp_dir: Optional[str] = None,
        chunk_size: int = 8192,
        retry_count: int = 3,
        retry_delay: float = 5.0,
    ):
        """
        初始化收集器
        
        Args:
            target_projects: 目标项目集合（小写，如 "facebook/react"）
            output_dir: 输出目录
            temp_dir: 临时文件目录（默认在 output_dir 下）
            chunk_size: 下载块大小
            retry_count: 重试次数
            retry_delay: 重试延迟（秒）
        """
        self.target_projects = target_projects
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir) if temp_dir else self.output_dir / ".temp"
        self.chunk_size = chunk_size
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        
        # 创建目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 进度跟踪
        self.progress = ProgressTracker(str(self.output_dir / ".progress"))
        
        # 统计（线程安全）
        self.stats = {
            "files_processed": 0,
            "events_total": 0,
            "events_matched": 0,
            "bytes_downloaded": 0,
            "bytes_saved": 0,
        }
        self._stats_lock = threading.Lock()
        self._daily_locks: Dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()
    
    def _get_daily_lock(self, date_str: str) -> threading.Lock:
        """获取某日的写入锁（fulldaily 模式下同日多线程追加用）"""
        with self._locks_lock:
            if date_str not in self._daily_locks:
                self._daily_locks[date_str] = threading.Lock()
            return self._daily_locks[date_str]
    
    def _is_target_event(self, event: Dict[str, Any]) -> bool:
        """检查事件是否属于目标项目"""
        repo = event.get("repo", {})
        repo_name = repo.get("name", "").lower()
        return repo_name in self.target_projects
    
    def _stream_download(self, url: str, dest_path: Path) -> bool:
        """
        流式下载文件
        
        Returns:
            是否成功
        """
        for attempt in range(self.retry_count):
            try:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "OSS-Graph-Collector/1.0"}
                )
                
                with urllib.request.urlopen(req, timeout=60) as response:
                    total_size = response.headers.get("Content-Length")
                    if total_size:
                        total_size = int(total_size)
                    
                    downloaded = 0
                    with open(dest_path, "wb") as f:
                        while True:
                            chunk = response.read(self.chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                    
                    with self._stats_lock:
                        self.stats["bytes_downloaded"] += downloaded
                    return True
                    
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    logger.warning(f"文件不存在: {url}")
                    return False
                logger.warning(f"HTTP 错误 {e.code}，尝试 {attempt + 1}/{self.retry_count}")
            except Exception as e:
                logger.warning(f"下载错误: {e}，尝试 {attempt + 1}/{self.retry_count}")
            
            if attempt < self.retry_count - 1:
                time.sleep(self.retry_delay)
        
        return False
    
    def _stream_filter(
        self,
        gz_path: Path,
        output_path: Path,
        append: bool = False,
    ) -> Dict[str, int]:
        """
        流式读取 gzip 文件并过滤事件
        
        Args:
            gz_path: 输入的 gzip 文件路径
            output_path: 输出的 JSON Lines 文件路径
            append: 若为 True，追加到已有文件末尾
        
        Returns:
            统计信息 {"total": int, "matched": int}
        """
        stats = {"total": 0, "matched": 0}
        mode = "a" if append else "w"
        
        with gzip.open(gz_path, "rt", encoding="utf-8") as fin:
            with open(output_path, mode, encoding="utf-8") as fout:
                for line in fin:
                    stats["total"] += 1
                    
                    try:
                        event = json.loads(line)
                        if self._is_target_event(event):
                            stats["matched"] += 1
                            fout.write(line)
                    except json.JSONDecodeError:
                        continue
        
        # 更新全局统计（线程安全）
        with self._stats_lock:
            self.stats["events_total"] += stats["total"]
            self.stats["events_matched"] += stats["matched"]
            if output_path.exists():
                self.stats["bytes_saved"] += output_path.stat().st_size
        
        return stats
    
    def process_hour(
        self,
        date_str: str,
        hour: int,
        daily_output_path: Optional[Path] = None,
    ) -> bool:
        """
        处理单个小时的数据
        
        Args:
            date_str: 日期字符串，格式 "YYYY-MM-DD"
            hour: 小时 (0-23)
            daily_output_path: 若指定，则追加到该文件（用于 fulldaily 模式，按日合并）
        
        Returns:
            是否成功处理
        """
        file_id = f"{date_str}-{hour}"
        
        # 检查是否已完成
        if self.progress.is_completed(file_id):
            logger.debug(f"跳过已完成: {file_id}")
            return True
        
        url = GHARCHIVE_URL_TEMPLATE.format(date=date_str, hour=hour)
        temp_gz = self.temp_dir / f"{file_id}.json.gz"
        
        if daily_output_path is not None:
            # fulldaily 模式：追加到每日文件（需加锁）
            output_file = daily_output_path
            date_str_for_lock = date_str
        else:
            output_file = self.output_dir / f"{file_id}-filtered.json"
            date_str_for_lock = None
        
        try:
            # 1. 下载（可并行）
            logger.info(f"下载: {url}")
            if not self._stream_download(url, temp_gz):
                logger.warning(f"下载失败: {file_id}")
                return False
            
            # 2. 过滤与写入（fulldaily 时同日多线程需串行追加）
            logger.info(f"过滤: {file_id}")
            if date_str_for_lock is not None:
                lock = self._get_daily_lock(date_str_for_lock)
                with lock:
                    append = output_file.exists()
                    stats = self._stream_filter(temp_gz, output_file, append=append)
            else:
                append = False
                stats = self._stream_filter(temp_gz, output_file, append=append)
            
            logger.info(
                f"完成 {file_id}: "
                f"总事件={stats['total']}, "
                f"匹配={stats['matched']} "
                f"({stats['matched']/max(stats['total'],1)*100:.2f}%)"
            )
            
            # 3. 清理临时文件
            if temp_gz.exists():
                temp_gz.unlink()
            
            # 4. 仅默认模式：若没有匹配且为单独文件，删除空文件
            if daily_output_path is None and stats["matched"] == 0 and output_file.exists():
                output_file.unlink()
            
            # 5. 标记完成
            self.progress.mark_completed(file_id)
            with self._stats_lock:
                self.stats["files_processed"] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"处理失败 {file_id}: {e}")
            if temp_gz.exists():
                temp_gz.unlink()
            return False
    
    def collect(
        self,
        start_date: str,
        end_date: str,
        sample_mode: str = "daily",
        workers: int = 1,
    ) -> Dict[str, Any]:
        """
        收集指定时间范围的数据
        
        Args:
            start_date: 开始日期，格式 "YYYY-MM-DD"
            end_date: 结束日期，格式 "YYYY-MM-DD"
            sample_mode: 采样模式 (hourly/daily/fulldaily/weekly/monthly)
            workers: 并发下载线程数，1 为串行
        
        Returns:
            统计信息
        """
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        hours = SAMPLE_MODES.get(sample_mode, [12])
        
        # 生成任务列表
        dates_to_process: List[Tuple[str, int, Optional[Path]]] = []
        current = start
        is_fulldaily = sample_mode == "fulldaily"
        
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            
            should_process = True
            if sample_mode == "weekly":
                should_process = current.weekday() == 0
            elif sample_mode == "monthly":
                should_process = current.day == 1
            
            if should_process:
                daily_path = (
                    self.output_dir / f"{date_str}-filtered.json"
                    if is_fulldaily
                    else None
                )
                for hour in hours:
                    dates_to_process.append((date_str, hour, daily_path))
            
            current += timedelta(days=1)
        
        total_files = len(dates_to_process)
        logger.info(f"计划处理 {total_files} 个文件")
        logger.info(f"采样模式: {sample_mode}")
        logger.info(f"并发线程: {workers}")
        logger.info(f"时间范围: {start_date} 到 {end_date}")
        logger.info(f"目标项目数: {len(self.target_projects)}")

        def process_one(task: Tuple[str, int, Optional[Path]]) -> bool:
            date_str, hour, daily_path = task
            return self.process_hour(date_str, hour, daily_output_path=daily_path)

        if workers <= 1:
            for i, task in enumerate(dates_to_process, 1):
                logger.info(f"进度: {i}/{total_files} ({i/total_files*100:.1f}%)")
                process_one(task)
                if i % 10 == 0:
                    self._print_stats()
        else:
            completed = 0
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(process_one, t): t for t in dates_to_process}
                for future in as_completed(futures):
                    completed += 1
                    if completed % 10 == 0 or completed == total_files:
                        logger.info(f"进度: {completed}/{total_files} ({completed/total_files*100:.1f}%)")
                        self._print_stats()
        
        self._print_stats()
        return self.stats
    
    def _print_stats(self):
        """输出统计信息"""
        with self._stats_lock:
            s = dict(self.stats)
        total = max(s["events_total"], 1)
        dl = s["bytes_downloaded"]
        saved = s["bytes_saved"]
        logger.info("=" * 50)
        logger.info("当前统计:")
        logger.info(f"  已处理文件: {s['files_processed']}")
        logger.info(f"  总事件数: {s['events_total']:,}")
        logger.info(f"  匹配事件数: {s['events_matched']:,}")
        logger.info(f"  匹配率: {s['events_matched']/total*100:.2f}%")
        logger.info(f"  下载数据量: {dl/1024/1024:.2f} MB")
        logger.info(f"  保存数据量: {saved/1024/1024:.2f} MB")
        logger.info(f"  压缩比: {saved/max(dl,1)*100:.2f}%")
        logger.info("=" * 50)
    
    def cleanup_temp(self):
        """清理临时目录"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            logger.info(f"已清理临时目录: {self.temp_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="GitHub Archive 数据收集器 - 流式下载并过滤目标项目数据"
    )
    
    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="开始日期 (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
        help="结束日期 (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--sample-mode",
        type=str,
        default="daily",
        choices=["hourly", "daily", "fulldaily", "weekly", "monthly"],
        help="采样模式: daily=每天1小时; fulldaily=每天24小时合并为1个JSON; hourly=每小时1文件; weekly/monthly=采样 (默认: daily)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/filtered/",
        help="输出目录 (默认: data/filtered/)"
    )
    
    parser.add_argument(
        "--project-count",
        type=int,
        default=100,
        help="目标项目数量 (默认: 100)"
    )
    
    parser.add_argument(
        "--repos-from-index",
        type=str,
        default=None,
        help="从 monthly-graphs index.json 读取仓库列表，覆盖 --project-count (如: output/monthly-graphs2/index.json)"
    )
    
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="并发下载线程数 (默认: 16，设为 1 则串行)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别 (默认: INFO)"
    )

    parser.add_argument(
        "--repo-list",
        type=str,
        default=None,
        help="repo 名单 JSON 文件路径（内容为 ['owner/repo', ...]）"
    )
    
    args = parser.parse_args()
    
    # 获取目标项目
    if args.repos_from_index:
        index_path = Path(args.repos_from_index)
        if not index_path.exists():
            logger.error(f"索引文件不存在: {index_path}")
            sys.exit(1)
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
        target_projects = {repo.lower() for repo in index.keys()}
        logger.info(f"从索引加载 {len(target_projects)} 个仓库: {index_path}")
    else:
        target_projects = get_project_set(args.project_count)
    logger.info(f"目标项目数: {len(target_projects)}")
    
    # 创建收集器
    collector = GHArchiveCollector(
        target_projects=target_projects,
        output_dir=args.output_dir,
    )
    
    try:
        # 开始收集
        stats = collector.collect(
            start_date=args.start_date,
            end_date=args.end_date,
            sample_mode=args.sample_mode,
            workers=args.workers,
        )
        
        logger.info("=" * 60)
        logger.info("数据收集完成!")
        logger.info(f"输出目录: {args.output_dir}")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("\n用户中断，进度已保存，可稍后继续...")
    
    finally:
        # 清理临时文件
        collector.cleanup_temp()


if __name__ == "__main__":
    main()
