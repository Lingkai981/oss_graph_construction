"""
数据提取集成测试
"""

import pytest
import sqlite3
from pathlib import Path
from src.services.database import connect_database
from src.services.extractor import extract_all_dates, extract_data_for_date


@pytest.fixture
def sample_db(tmp_path):
    """创建示例数据库"""
    db_path = tmp_path / "sample.db"
    conn = sqlite3.connect(str(db_path))
    
    # 创建表
    conn.execute("""
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name TEXT,
            created_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            login TEXT,
            name TEXT,
            created_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE commits (
            id INTEGER PRIMARY KEY,
            sha TEXT,
            message TEXT,
            author_id INTEGER,
            created_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE project_commits (
            project_id INTEGER,
            commit_id INTEGER,
            PRIMARY KEY (project_id, commit_id)
        )
    """)
    
    # 插入测试数据
    conn.execute("INSERT INTO projects (id, name, created_at) VALUES (1, 'test-project', '2024-01-01 00:00:00')")
    conn.execute("INSERT INTO users (id, login, name, created_at) VALUES (1, 'user1', 'User One', '2024-01-01 00:00:00')")
    conn.execute("INSERT INTO commits (id, sha, message, author_id, created_at) VALUES (1, 'abc123', 'test commit', 1, '2024-01-01 10:00:00')")
    conn.execute("INSERT INTO project_commits (project_id, commit_id) VALUES (1, 1)")
    
    conn.commit()
    conn.close()
    
    return str(db_path)


def test_integration_extract_all_dates(sample_db):
    """测试集成：提取所有日期"""
    conn = connect_database(sample_db)
    dates = extract_all_dates(conn)
    assert len(dates) > 0
    conn.close()


def test_integration_extract_data_for_date(sample_db):
    """测试集成：按日期提取数据"""
    conn = connect_database(sample_db)
    data = extract_data_for_date(conn, "2024-01-01")
    assert 'date' in data
    assert 'commits' in data
    assert 'edges' in data
    conn.close()

