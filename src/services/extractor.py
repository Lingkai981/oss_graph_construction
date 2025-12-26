"""
数据提取服务

提供时间序列数据提取功能，按天粒度组织数据
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from src.services.database import (
    connect_database, extract_projects, extract_contributors,
    extract_commits_by_date, extract_contribution_edges_by_date
)
from src.utils.date_utils import parse_timestamp, extract_date
from src.utils.logger import get_logger

logger = get_logger()


def extract_all_dates(conn, table_name: str = "commits", date_column: str = "created_at") -> List[str]:
    """
    自动识别数据库中的所有唯一日期
    
    采用记录并跳过策略：记录错误到日志，跳过异常记录，继续处理其他数据
    
    Args:
        conn: SQLite连接对象
        table_name: 包含时间戳的表名（默认commits）
        date_column: 时间戳列名（默认created_at）
    
    Returns:
        唯一日期列表（YYYY-MM-DD格式），按时间顺序排序
    """
    dates = set()
    skipped_count = 0
    
    try:
        cursor = conn.cursor()
        # 查询所有时间戳
        cursor.execute(f"""
            SELECT DISTINCT {date_column}
            FROM {table_name}
            WHERE {date_column} IS NOT NULL
        """)
        
        for row in cursor.fetchall():
            timestamp = row[date_column]
            if timestamp:
                try:
                    # 解析时间戳并提取日期
                    date_str = extract_date(str(timestamp))
                    if date_str:
                        dates.add(date_str)
                    else:
                        # 记录警告并跳过
                        logger.warning(f"无法解析时间戳格式: {timestamp}，跳过该记录")
                        skipped_count += 1
                except Exception as e:
                    # 记录错误并跳过
                    logger.warning(f"解析时间戳时出错: {timestamp}, 错误: {str(e)}，跳过该记录")
                    skipped_count += 1
            else:
                # 空时间戳，跳过
                skipped_count += 1
        
        # 转换为列表并排序
        date_list = sorted(list(dates))
        if skipped_count > 0:
            logger.info(f"识别到 {len(date_list)} 个唯一日期，跳过 {skipped_count} 条无效记录")
        else:
            logger.info(f"识别到 {len(date_list)} 个唯一日期")
        return date_list
    except Exception as e:
        logger.warning(f"提取日期失败: {str(e)}，尝试降级处理")
        # 降级处理：尝试其他表或列
        try:
            # 尝试从commits表提取
            if table_name != "commits":
                return extract_all_dates(conn, "commits", "created_at")
        except Exception:
            pass
        return []


def validate_commit_data(commit: Dict[str, Any]) -> bool:
    """
    验证提交数据的必需字段
    
    Args:
        commit: 提交数据字典
    
    Returns:
        如果数据有效返回True，否则返回False
    """
    # 提交节点必须包含created_at（用于时间快照）
    if not commit.get('created_at'):
        return False
    
    # 至少需要sha或id之一
    if not commit.get('sha') and not commit.get('id'):
        return False
    
    return True


def validate_edge_data(edge: Dict[str, Any]) -> bool:
    """
    验证边数据的必需字段
    
    Args:
        edge: 边数据字典
    
    Returns:
        如果数据有效返回True，否则返回False
    """
    # 所有边必须包含source、target、edge_type和created_at
    if not edge.get('contributor_id'):
        return False
    if not edge.get('commit_sha') and not edge.get('commit_id'):
        return False
    if not edge.get('created_at'):
        return False
    
    return True


def extract_data_for_date(conn, date: str) -> Dict[str, Any]:
    """
    为指定日期提取所有相关数据（项目、贡献者、提交、关系）
    
    采用记录并跳过策略：检查必需字段，跳过无效记录并记录警告
    
    Args:
        conn: SQLite连接对象
        date: 日期字符串（YYYY-MM-DD格式）
    
    Returns:
        包含该日期所有数据的字典
    """
    data = {
        'date': date,
        'projects': [],
        'contributors': [],
        'commits': [],
        'edges': []
    }
    
    skipped_commits = 0
    skipped_edges = 0
    
    try:
        # 提取提交数据
        raw_commits = extract_commits_by_date(conn, date)
        
        # 验证并过滤提交数据
        for commit in raw_commits:
            if validate_commit_data(commit):
                data['commits'].append(commit)
            else:
                logger.warning(f"跳过无效提交记录: {commit}")
                skipped_commits += 1
        
        # 提取贡献关系
        raw_edges = extract_contribution_edges_by_date(conn, date)
        
        # 验证并过滤边数据
        for edge in raw_edges:
            if validate_edge_data(edge):
                data['edges'].append(edge)
            else:
                logger.warning(f"跳过无效边记录: {edge}")
                skipped_edges += 1
        
        # 提取相关的贡献者（从提交中获取author_id）
        contributor_ids = set()
        for commit in data['commits']:
            if commit.get('author_id'):
                contributor_ids.add(commit['author_id'])
        
        # 提取相关的项目（从边中获取project_id）
        project_ids = set()
        for edge in data['edges']:
            if edge.get('project_id'):
                project_ids.add(edge['project_id'])
        
        # 如果日期是第一天，提取所有项目和贡献者
        # 否则只提取新增的（这里简化处理，实际应该跟踪哪些是新增的）
        all_dates = extract_all_dates(conn)
        if all_dates and date == all_dates[0]:
            all_projects = extract_projects(conn)
            all_contributors = extract_contributors(conn)
            data['projects'] = all_projects
            data['contributors'] = all_contributors
        else:
            # 只提取相关的项目和贡献者
            # 这里简化处理，实际应该从数据库查询特定的ID
            pass
        
        log_msg = f"日期 {date} 提取完成: {len(data['commits'])} 个提交, {len(data['edges'])} 条关系"
        if skipped_commits > 0 or skipped_edges > 0:
            log_msg += f"（跳过 {skipped_commits} 个无效提交, {skipped_edges} 条无效边）"
        logger.info(log_msg)
        return data
    except Exception as e:
        logger.error(f"提取日期 {date} 的数据失败: {str(e)}")
        return data

