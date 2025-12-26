"""
命令行主入口

整合所有功能，提供命令行接口
"""

import argparse
import sys
from pathlib import Path
from typing import Optional
from src.services.database import connect_database
from src.services.extractor import extract_all_dates, extract_data_for_date
from src.services.graph_builder import build_all_snapshots
from src.services.exporter import export_all_snapshots
from src.utils.logger import setup_logger, get_logger


def parse_arguments():
    """
    解析命令行参数
    
    Returns:
        解析后的参数对象
    """
    parser = argparse.ArgumentParser(
        description='时间快照式时序图建模工具',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--db',
        type=str,
        default='data/rxjs-ghtorrent.db',
        help='SQLite数据库文件路径（默认: data/rxjs-ghtorrent.db）'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='output/',
        help='输出目录路径（默认: output/）'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='日志级别（默认: INFO）'
    )
    
    parser.add_argument(
        '--start-date',
        type=str,
        default=None,
        help='起始日期（YYYY-MM-DD格式），默认处理所有日期'
    )
    
    parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='结束日期（YYYY-MM-DD格式），默认处理所有日期'
    )
    
    parser.add_argument(
        '--format',
        type=str,
        default='graphml',
        choices=['graphml', 'json'],
        help='导出格式（默认: graphml）'
    )
    
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


def main():
    """
    主函数
    
    按顺序调用数据提取、图构建、导出服务
    """
    args = parse_arguments()
    
    # 设置日志
    logger = setup_logger(log_level=args.log_level)
    logger.info("=" * 60)
    logger.info("开始时间快照式时序图建模")
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
        snapshots = build_all_snapshots(all_data)
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


if __name__ == '__main__':
    main()

