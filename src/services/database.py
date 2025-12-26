"""
数据库访问服务

提供SQLite数据库连接和数据提取功能
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Any
from src.utils.logger import get_logger

logger = get_logger()


def connect_database(db_path: str) -> sqlite3.Connection:
    """
    连接到SQLite数据库并处理连接错误
    
    Args:
        db_path: 数据库文件路径
    
    Returns:
        SQLite连接对象
    
    Raises:
        FileNotFoundError: 如果数据库文件不存在
        sqlite3.Error: 如果连接失败
    """
    db_file = Path(db_path)
    
    if not db_file.exists():
        error_msg = f"数据库文件不存在: {db_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)
    
    try:
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row  # 使用Row工厂，返回字典式结果
        logger.info(f"成功连接到数据库: {db_path}")
        return conn
    except sqlite3.Error as e:
        error_msg = f"连接数据库失败: {str(e)}"
        logger.error(error_msg)
        raise


def get_table_names(conn: sqlite3.Connection) -> List[str]:
    """
    识别数据库中的所有表
    
    Args:
        conn: SQLite连接对象
    
    Returns:
        表名列表
    """
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"识别到 {len(tables)} 个表: {', '.join(tables)}")
        return tables
    except sqlite3.Error as e:
        logger.error(f"获取表名失败: {str(e)}")
        raise


def extract_projects(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    从projects表提取项目数据
    
    Args:
        conn: SQLite连接对象
    
    Returns:
        项目数据列表
    """
    projects = []
    try:
        cursor = conn.cursor()
        # 尝试查询projects表
        cursor.execute("""
            SELECT id, name, url, created_at, updated_at 
            FROM projects
        """)
        
        for row in cursor.fetchall():
            project = {'id': row['id']}
            try:
                project['name'] = row['name']
            except (KeyError, IndexError):
                project['name'] = None
            try:
                project['url'] = row['url']
            except (KeyError, IndexError):
                project['url'] = None
            try:
                project['created_at'] = row['created_at']
            except (KeyError, IndexError):
                project['created_at'] = None
            try:
                project['updated_at'] = row['updated_at']
            except (KeyError, IndexError):
                project['updated_at'] = None
            projects.append(project)
        
        logger.info(f"提取到 {len(projects)} 个项目")
        return projects
    except sqlite3.Error as e:
        logger.warning(f"提取项目数据失败: {str(e)}，可能表不存在或结构不同")
        return projects


def extract_contributors(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    从users表提取贡献者数据
    
    Args:
        conn: SQLite连接对象
    
    Returns:
        贡献者数据列表
    """
    contributors = []
    try:
        cursor = conn.cursor()
        # 尝试查询users表
        cursor.execute("""
            SELECT id, login, name, created_at 
            FROM users
        """)
        
        for row in cursor.fetchall():
            contributor = {'id': row['id']}
            try:
                contributor['login'] = row['login']
            except (KeyError, IndexError):
                contributor['login'] = None
            try:
                contributor['name'] = row['name']
            except (KeyError, IndexError):
                contributor['name'] = None
            try:
                contributor['created_at'] = row['created_at']
            except (KeyError, IndexError):
                contributor['created_at'] = None
            contributors.append(contributor)
        
        logger.info(f"提取到 {len(contributors)} 个贡献者")
        return contributors
    except sqlite3.Error as e:
        logger.warning(f"提取贡献者数据失败: {str(e)}，可能表不存在或结构不同")
        return contributors


def extract_commits_by_date(conn: sqlite3.Connection, date: str) -> List[Dict[str, Any]]:
    """
    按日期从commits表提取提交数据
    
    Args:
        conn: SQLite连接对象
        date: 日期字符串（YYYY-MM-DD格式）
    
    Returns:
        提交数据列表
    """
    commits = []
    try:
        cursor = conn.cursor()
        # 先检查表结构，确定哪些列存在
        cursor.execute("PRAGMA table_info(commits)")
        columns_info = cursor.fetchall()
        available_columns = {col[1] for col in columns_info}  # col[1] 是列名
        
        # 构建查询，只选择存在的列
        select_columns = []
        if 'id' in available_columns:
            select_columns.append('id')
        if 'sha' in available_columns:
            select_columns.append('sha')
        if 'message' in available_columns:
            select_columns.append('message')
        if 'author_id' in available_columns:
            select_columns.append('author_id')
        if 'created_at' in available_columns:
            select_columns.append('created_at')
        
        if not select_columns:
            logger.warning(f"commits表没有可用的列")
            return commits
        
        # 如果created_at列不存在，无法按日期过滤
        if 'created_at' not in available_columns:
            logger.warning(f"commits表没有created_at列，无法按日期过滤")
            return commits
        
        # 构建查询语句
        query = f"""
            SELECT {', '.join(select_columns)}
            FROM commits 
            WHERE DATE(created_at) = ?
        """
        
        cursor.execute(query, (date,))
        
        for row in cursor.fetchall():
            commit = {}
            if 'id' in available_columns:
                commit['id'] = row['id']
            if 'sha' in available_columns:
                commit['sha'] = row['sha']
            if 'message' in available_columns:
                commit['message'] = row['message']
            if 'author_id' in available_columns:
                commit['author_id'] = row['author_id']
            if 'created_at' in available_columns:
                commit['created_at'] = row['created_at']
            commits.append(commit)
        
        logger.debug(f"日期 {date} 提取到 {len(commits)} 个提交")
        return commits
    except sqlite3.Error as e:
        logger.warning(f"提取提交数据失败（日期 {date}）: {str(e)}，可能表不存在或结构不同")
        return commits


def extract_contribution_edges_by_date(conn: sqlite3.Connection, date: str) -> List[Dict[str, Any]]:
    """
    通过关联users、commits和project_commits表提取贡献关系
    
    Args:
        conn: SQLite连接对象
        date: 日期字符串（YYYY-MM-DD格式）
    
    Returns:
        贡献关系数据列表
    """
    edges = []
    try:
        cursor = conn.cursor()
        # 尝试查询贡献关系，通过关联表
        cursor.execute("""
            SELECT u.id as contributor_id, c.id as commit_id, c.sha as commit_sha, 
                   c.created_at, pc.project_id
            FROM commits c
            JOIN users u ON c.author_id = u.id
            LEFT JOIN project_commits pc ON c.id = pc.commit_id
            WHERE DATE(c.created_at) = ?
        """, (date,))
        
        for row in cursor.fetchall():
            edge = {}
            try:
                edge['contributor_id'] = row['contributor_id']
            except (KeyError, IndexError):
                edge['contributor_id'] = None
            try:
                edge['commit_id'] = row['commit_id']
            except (KeyError, IndexError):
                edge['commit_id'] = None
            try:
                edge['commit_sha'] = row['commit_sha']
            except (KeyError, IndexError):
                edge['commit_sha'] = None
            try:
                edge['created_at'] = row['created_at']
            except (KeyError, IndexError):
                edge['created_at'] = None
            try:
                edge['project_id'] = row['project_id']
            except (KeyError, IndexError):
                edge['project_id'] = None
            edges.append(edge)
        
        logger.debug(f"日期 {date} 提取到 {len(edges)} 条贡献关系")
        return edges
    except sqlite3.Error as e:
        logger.warning(f"提取贡献关系失败（日期 {date}）: {str(e)}，可能表不存在或结构不同")
        return edges

