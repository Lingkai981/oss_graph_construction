"""
命令行主入口

整合所有功能，提供命令行接口
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence
from src.services.database import connect_database
from src.services.extractor import extract_all_dates, extract_data_for_date
from src.services.graph_builder import build_all_snapshots
from src.services.exporter import export_all_snapshots
from src.services.temporal_semantic_graph.pipeline import run_temporal_graph_pipeline
from src.utils.logger import setup_logger, get_logger


def parse_arguments():
    """
    解析命令行参数
    
    Returns:
        解析后的参数对象
    """
    parser = argparse.ArgumentParser(
        description='时间快照式时序图建模工具（包含快照模式与一小时时序语义图模式）',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(
        dest="command",
        help="可用子命令"
    )

    # -------- 快照式时序图（001 特性，保持兼容） --------
    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="基于 SQLite 数据库的按天快照式时序图建模（原有功能）"
    )

    snapshot_parser.add_argument(
        '--db',
        type=str,
        default='data/rxjs-ghtorrent.db',
        help='SQLite数据库文件路径（默认: data/rxjs-ghtorrent.db）'
    )

    snapshot_parser.add_argument(
        '--output',
        type=str,
        default='output/',
        help='输出目录路径（默认: output/）'
    )

    snapshot_parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='日志级别（默认: INFO）'
    )

    snapshot_parser.add_argument(
        '--start-date',
        type=str,
        default=None,
        help='起始日期（YYYY-MM-DD格式），默认处理所有日期'
    )

    snapshot_parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='结束日期（YYYY-MM-DD格式），默认处理所有日期'
    )

    snapshot_parser.add_argument(
        '--format',
        type=str,
        default='graphml',
        choices=['graphml', 'json'],
        help='导出格式（默认: graphml）'
    )

    snapshot_parser.add_argument(
        '--remove-isolated',
        action='store_true',
        help='移除孤立节点（没有边的节点），使图更清晰便于分析'
    )

    # -------- 一小时时序语义图（002 特性） --------
    temporal_parser = subparsers.add_parser(
        "temporal-semantic-graph",
        help="基于 GitHub 事件 JSON 文件的一小时时序语义图建模"
    )

    temporal_parser.add_argument(
        '--input',
        type=str,
        default='data/2015-01-01-15.json',
        help='GitHub 事件 JSON 行文件路径（默认: data/2015-01-01-15.json）'
    )

    temporal_parser.add_argument(
        '--output-dir',
        type=str,
        default='output/temporal-semantic-graph/',
        help='输出目录路径（默认: output/temporal-semantic-graph/）'
    )

    temporal_parser.add_argument(
        '--export-format',
        type=str,
        default='json,graphml',
        help='导出格式，逗号分隔（可选: json, graphml，默认: json,graphml）'
    )

    temporal_parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='日志级别（默认: INFO）'
    )

    # 如果用户未提供子命令，则默认使用 snapshot 模式
    parser.set_defaults(command="snapshot")

    return parser.parse_args()


def filter_dates_by_range(dates: list, start_date: Optional[str], end_date: Optional[str]) -> list:
    """
    根据日期范围过滤日期列表
    
    Args:
        dates: 日期列表
        start_date: 起始日期
        end_date: 结束日期
    
    Returns:
        过滤后的日期列表
    """
    if not start_date and not end_date:
        return dates
    
    filtered = []
    for date in dates:
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue
        filtered.append(date)
    
    return filtered


def _run_snapshot_mode(args) -> None:
    """
    快照式时序图建模模式（原有实现）。
    """
    logger = setup_logger(log_level=args.log_level)
    logger.info("=" * 60)
    logger.info("开始时间快照式时序图建模（snapshot 模式）")
    logger.info("=" * 60)

    try:
        # 步骤1: 连接数据库
        logger.info("步骤1: 连接数据库...")
        conn = connect_database(args.db)

        # 步骤2: 提取所有日期
        logger.info("步骤2: 提取所有日期...")
        all_dates = extract_all_dates(conn)

        if not all_dates:
            logger.error("未找到任何日期数据，程序退出")
            sys.exit(1)

        # 过滤日期范围
        if args.start_date or args.end_date:
            all_dates = filter_dates_by_range(all_dates, args.start_date, args.end_date)
            logger.info(f"日期范围过滤后: {len(all_dates)} 个日期")

        if not all_dates:
            logger.error("日期范围过滤后没有数据，程序退出")
            sys.exit(1)

        logger.info(f"将处理 {len(all_dates)} 个日期")

        # 步骤3: 提取数据
        logger.info("步骤3: 提取数据...")
        all_data = []
        total_dates = len(all_dates)

        for idx, date in enumerate(all_dates, 1):
            logger.info(f"提取日期 {idx}/{total_dates}: {date}")
            data = extract_data_for_date(conn, date)
            all_data.append(data)

        logger.info(f"数据提取完成: {len(all_data)} 个日期的数据")

        # 步骤4: 构建图快照
        logger.info("步骤4: 构建图快照...")
        if args.remove_isolated:
            logger.info("启用移除孤立节点功能")
        snapshots = build_all_snapshots(all_data, remove_isolated=args.remove_isolated)
        logger.info(f"图快照构建完成: {len(snapshots)} 个快照")

        # 步骤5: 导出快照
        logger.info("步骤5: 导出图快照...")
        exported_files = export_all_snapshots(
            snapshots, all_dates, args.output, args.format
        )
        logger.info(f"导出完成: {len(exported_files)} 个文件")

        # 关闭数据库连接
        conn.close()

        logger.info("=" * 60)
        logger.info("处理完成！")
        logger.info(f"输出目录: {args.output}")
        logger.info(f"导出文件数: {len(exported_files)}")
        logger.info("=" * 60)

    except FileNotFoundError as e:
        logger.error(f"文件未找到: {str(e)}")
        logger.error("请检查数据库文件路径是否正确")
        sys.exit(1)
    except Exception as e:
        logger.error(f"处理过程中发生错误: {str(e)}", exc_info=True)
        sys.exit(1)


def _parse_export_formats(raw: str) -> Sequence[str]:
    """
    将逗号分隔的导出格式字符串解析为格式列表。
    """
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return ("json", "graphml")
    return parts


def _run_temporal_semantic_mode(args) -> None:
    """
    一小时时序语义图建模模式（002 特性）。
    """
    logger = setup_logger(log_level=args.log_level)
    logger.info("=" * 60)
    logger.info("开始一小时时序语义图建模（temporal-semantic-graph 模式）")
    logger.info("=" * 60)

    try:
        formats = _parse_export_formats(args.export_format)
        generated_files = run_temporal_graph_pipeline(
            input_path=args.input,
            output_dir=args.output_dir,
            export_formats=formats,
        )
        logger.info(f"导出文件数: {len(generated_files)}")
        for fp in generated_files:
            logger.info(f"导出文件: {fp}")

        logger.info("=" * 60)
        logger.info("一小时时序语义图建模完成")
        logger.info("=" * 60)
    except FileNotFoundError as e:
        logger.error(f"文件未找到: {str(e)}")
        logger.error("请检查输入事件文件路径是否正确")
        sys.exit(1)
    except Exception as e:
        logger.error(f"处理过程中发生错误: {str(e)}", exc_info=True)
        sys.exit(1)


def main():
    """
    主函数

    提供两种模式：
    - snapshot: 原有的按天快照式时序图建模（001 特性）；
    - temporal-semantic-graph: 基于 GitHub 事件的一小时时序语义图建模（002 特性）。
    """
    args = parse_arguments()

    if args.command == "temporal-semantic-graph":
        _run_temporal_semantic_mode(args)
    else:
        # 默认或显式 snapshot 命令
        _run_snapshot_mode(args)


if __name__ == '__main__':
    main()

