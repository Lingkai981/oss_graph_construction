"""
GitHub Archive 数据收集器（并行版）

改动点（相对原版）：
1) 支持 --workers 并行处理（ThreadPoolExecutor）
2) ProgressTracker / stats 线程安全
3) 支持 --repo-list 直接读取你的 repo 名单 JSON（['owner/repo', ...]）；不传则沿用代表性项目 get_project_set

仍然保持：
- 流式下载、流式过滤（内存友好）
- 断点续传（.progress）
- 自动清理临时文件（.temp）

示例：
  python gharchive_collector_parallel.py \
    --start-date 2021-01-01 --end-date 2025-12-31 \
    --sample-mode daily \
    --repo-list union_repos_after_leave.json \
    --output-dir data/filtered_union \
    --workers 8
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import threading

# ----------------------------
# 日志：优先使用项目内 logger；没有就退化到标准 logging
# ----------------------------
try:
    from src.utils.logger import get_logger  # type: ignore
    logger = get_logger()
except Exception:  # pragma: no cover
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    logger = logging.getLogger("gharchive_collector_parallel")

# 代表性项目集合（可选）
try:
    from src.data_collection.representative_projects import get_project_set  # type: ignore
except Exception:  # pragma: no cover
    get_project_set = None  # type: ignore

GHARCHIVE_URL_TEMPLATE = "https://data.gharchive.org/{date}-{hour}.json.gz"

SAMPLE_MODES = {
    "hourly": list(range(24)),
    "daily": [12],    # 每天中午12点 UTC
    "weekly": [12],   # 每周一中午
    "monthly": [12],  # 每月1号中午
}


class ProgressTracker:
    """线程安全进度跟踪器（断点续传）"""

    def __init__(self, progress_file: str):
        self.progress_file = Path(progress_file)
        self.completed: Set[str] = set()
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        if self.progress_file.exists():
            with open(self.progress_file, "r", encoding="utf-8") as f:
                completed = set(line.strip() for line in f if line.strip())
            with self._lock:
                self.completed = completed
            logger.info(f"已加载进度文件，已完成 {len(completed)} 个文件")

    def is_completed(self, file_id: str) -> bool:
        with self._lock:
            return file_id in self.completed

    def mark_completed(self, file_id: str):
        # 追加写：用 lock 保证 set + 文件写入一致
        with self._lock:
            if file_id in self.completed:
                return
            self.completed.add(file_id)
            with open(self.progress_file, "a", encoding="utf-8") as f:
                f.write(f"{file_id}\n")

    def get_completed_count(self) -> int:
        with self._lock:
            return len(self.completed)


class GHArchiveCollector:
    def __init__(
        self,
        target_projects: Set[str],
        output_dir: str,
        temp_dir: Optional[str] = None,
        chunk_size: int = 256 * 1024,  # 默认调大一点，减少循环次数
        retry_count: int = 3,
        retry_delay: float = 5.0,
        timeout: int = 120,
    ):
        self.target_projects = target_projects
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir) if temp_dir else self.output_dir / ".temp"
        self.chunk_size = chunk_size
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.timeout = timeout

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.progress = ProgressTracker(str(self.output_dir / ".progress"))

        self._stats_lock = threading.Lock()
        self.stats: Dict[str, int] = {
            "files_processed": 0,
            "events_total": 0,
            "events_matched": 0,
            "bytes_downloaded": 0,
            "bytes_saved": 0,
            "files_failed": 0,
        }

    def _is_target_event(self, event: Dict[str, Any]) -> bool:
        repo_name = (event.get("repo", {}) or {}).get("name", "")
        return repo_name.lower() in self.target_projects

    def _stream_download(self, url: str, dest_path: Path) -> Tuple[bool, int]:
        """下载到 dest_path；返回 (success, downloaded_bytes)"""
        for attempt in range(self.retry_count):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "OSS-Graph-Collector/1.0"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    downloaded = 0
                    with open(dest_path, "wb") as f:
                        while True:
                            chunk = resp.read(self.chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                return True, downloaded

            except urllib.error.HTTPError as e:
                if e.code == 404:
                    logger.warning(f"文件不存在: {url}")
                    return False, 0
                logger.warning(f"HTTP 错误 {e.code}，尝试 {attempt + 1}/{self.retry_count}: {url}")
            except Exception as e:
                logger.warning(f"下载错误: {e}，尝试 {attempt + 1}/{self.retry_count}: {url}")

            if attempt < self.retry_count - 1:
                time.sleep(self.retry_delay)

        return False, 0

    def _stream_filter(self, gz_path: Path, output_path: Path) -> Tuple[Dict[str, int], int]:
        """过滤 gz_path -> output_path；返回 (stats, bytes_saved)"""
        stats = {"total": 0, "matched": 0}

        with gzip.open(gz_path, "rt", encoding="utf-8", errors="ignore") as fin:
            with open(output_path, "w", encoding="utf-8") as fout:
                for line in fin:
                    stats["total"] += 1
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if self._is_target_event(event):
                        stats["matched"] += 1
                        fout.write(line)

        bytes_saved = output_path.stat().st_size if output_path.exists() else 0
        return stats, bytes_saved

    def process_hour(self, date_str: str, hour: int) -> Tuple[str, bool, Dict[str, int]]:
        """
        线程 worker：处理单个小时
        返回 (file_id, ok, per_file_stats)
        """
        file_id = f"{date_str}-{hour}"

        if self.progress.is_completed(file_id):
            return file_id, True, {"total": 0, "matched": 0, "downloaded": 0, "saved": 0, "skipped": 1}

        url = GHARCHIVE_URL_TEMPLATE.format(date=date_str, hour=hour)
        temp_gz = self.temp_dir / f"{file_id}.json.gz"
        output_file = self.output_dir / f"{file_id}-filtered.json"

        try:
            logger.info(f"下载: {url}")
            ok, downloaded = self._stream_download(url, temp_gz)
            if not ok:
                return file_id, False, {"total": 0, "matched": 0, "downloaded": 0, "saved": 0, "skipped": 0}

            logger.info(f"过滤: {file_id}")
            fstats, saved = self._stream_filter(temp_gz, output_file)

            # 清理临时文件
            if temp_gz.exists():
                temp_gz.unlink()

            # 没有匹配事件则删除空文件
            if fstats["matched"] == 0 and output_file.exists():
                output_file.unlink()
                saved = 0

            # 标记完成
            self.progress.mark_completed(file_id)

            # 聚合全局统计
            with self._stats_lock:
                self.stats["files_processed"] += 1
                self.stats["events_total"] += fstats["total"]
                self.stats["events_matched"] += fstats["matched"]
                self.stats["bytes_downloaded"] += downloaded
                self.stats["bytes_saved"] += saved

            logger.info(
                f"完成 {file_id}: 总事件={fstats['total']}, 匹配={fstats['matched']} "
                f"({fstats['matched']/max(fstats['total'], 1)*100:.2f}%)"
            )

            return file_id, True, {
                "total": fstats["total"],
                "matched": fstats["matched"],
                "downloaded": downloaded,
                "saved": saved,
                "skipped": 0,
            }

        except Exception as e:
            logger.error(f"处理失败 {file_id}: {e}")
            # 清理部分文件
            try:
                if temp_gz.exists():
                    temp_gz.unlink()
            except Exception:
                pass
            with self._stats_lock:
                self.stats["files_failed"] += 1
            return file_id, False, {"total": 0, "matched": 0, "downloaded": 0, "saved": 0, "skipped": 0}

    def _build_tasks(self, start_date: str, end_date: str, sample_mode: str) -> List[Tuple[str, int]]:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        hours = SAMPLE_MODES.get(sample_mode, [12])

        tasks: List[Tuple[str, int]] = []
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")

            should_process = True
            if sample_mode == "weekly":
                should_process = current.weekday() == 0
            elif sample_mode == "monthly":
                should_process = current.day == 1

            if should_process:
                for h in hours:
                    tasks.append((date_str, h))
            current += timedelta(days=1)

        return tasks

    def collect_parallel(
        self,
        start_date: str,
        end_date: str,
        sample_mode: str = "daily",
        workers: int = 8,
        print_every: int = 50,
    ) -> Dict[str, int]:
        tasks = self._build_tasks(start_date, end_date, sample_mode)
        total_files = len(tasks)

        logger.info(f"计划处理 {total_files} 个文件")
        logger.info(f"采样模式: {sample_mode}")
        logger.info(f"时间范围: {start_date} 到 {end_date}")
        logger.info(f"目标项目数: {len(self.target_projects)}")
        logger.info(f"并行 workers: {workers}")

        completed = 0
        failed = 0
        skipped = 0

        # 提醒：ThreadPoolExecutor 适合 I/O 密集；daily 通常下载时间占比高，线程会有明显收益
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(self.process_hour, d, h) for d, h in tasks]

            for fut in as_completed(futures):
                file_id, ok, per = fut.result()
                completed += 1
                if not ok:
                    failed += 1
                if per.get("skipped", 0) == 1:
                    skipped += 1

                if completed % print_every == 0 or completed == total_files:
                    with self._stats_lock:
                        s = dict(self.stats)
                    logger.info(
                        f"进度: {completed}/{total_files} ({completed/total_files*100:.1f}%) "
                        f"| failed={failed}, skipped={skipped} "
                        f"| matched={s['events_matched']:,}/{s['events_total']:,} "
                        f"| downloaded={s['bytes_downloaded']/1024/1024:.1f}MB"
                    )

        return self.stats

    def cleanup_temp(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            logger.info(f"已清理临时目录: {self.temp_dir}")


def _load_repo_list(repo_list_path: str) -> Set[str]:
    p = Path(repo_list_path)
    with open(p, "r", encoding="utf-8") as f:
        repos = json.load(f)
    if not isinstance(repos, list):
        raise ValueError("--repo-list 必须是 JSON 数组，例如 ['owner/repo', ...]")
    return {str(r).strip().lower() for r in repos if str(r).strip()}


def main():
    parser = argparse.ArgumentParser(description="GitHub Archive 并行数据收集器（流式下载+过滤+断点续传）")

    parser.add_argument("--start-date", type=str, required=True, help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, required=True, help="结束日期 (YYYY-MM-DD)")

    parser.add_argument(
        "--sample-mode",
        type=str,
        default="daily",
        choices=["hourly", "daily", "weekly", "monthly"],
        help="采样模式 (默认: daily)",
    )

    parser.add_argument("--output-dir", type=str, default="data/filtered/", help="输出目录")
    parser.add_argument("--repo-list", type=str, default=None, help="repo 名单 JSON 文件（['owner/repo', ...]）")
    parser.add_argument("--project-count", type=int, default=100, help="目标项目数量（仅在未传 --repo-list 时生效）")

    parser.add_argument("--workers", type=int, default=8, help="并行线程数（I/O 密集建议 4~16）")
    parser.add_argument("--chunk-size", type=int, default=256 * 1024, help="下载块大小（字节）")
    parser.add_argument("--timeout", type=int, default=120, help="单次请求超时（秒）")
    parser.add_argument("--retry-count", type=int, default=3, help="重试次数")
    parser.add_argument("--retry-delay", type=float, default=5.0, help="重试间隔（秒）")

    args = parser.parse_args()

    # 目标项目集合
    if args.repo_list:
        target_projects = _load_repo_list(args.repo_list)
    else:
        if get_project_set is None:
            raise RuntimeError("未找到 src.data_collection.representative_projects.get_project_set；请传 --repo-list")
        target_projects = get_project_set(args.project_count)

    logger.info(f"目标项目数: {len(target_projects)}")

    collector = GHArchiveCollector(
        target_projects=target_projects,
        output_dir=args.output_dir,
        chunk_size=args.chunk_size,
        retry_count=args.retry_count,
        retry_delay=args.retry_delay,
        timeout=args.timeout,
    )

    try:
        stats = collector.collect_parallel(
            start_date=args.start_date,
            end_date=args.end_date,
            sample_mode=args.sample_mode,
            workers=args.workers,
        )

        logger.info("=" * 60)
        logger.info("数据收集完成!")
        logger.info(f"输出目录: {args.output_dir}")
        logger.info(f"已处理文件: {stats['files_processed']}, 失败: {stats['files_failed']}")
        logger.info(f"总事件数: {stats['events_total']:,}, 匹配事件数: {stats['events_matched']:,}")
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.info("\n用户中断，进度已保存，可稍后继续...")

    finally:
        collector.cleanup_temp()


if __name__ == "__main__":
    main()
