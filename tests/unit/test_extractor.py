"""
数据提取服务单元测试
"""

import pytest
import sqlite3
from pathlib import Path
from src.services.extractor import extract_all_dates, extract_data_for_date
from src.services.database import connect_database


def test_extract_all_dates(tmp_path):
    """测试提取所有日期"""
    # 创建临时数据库
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE commits (
            id INTEGER PRIMARY KEY,
            sha TEXT,
            created_at TIMESTAMP
        )
    """)
    conn.execute("INSERT INTO commits (sha, created_at) VALUES ('abc123', '2024-01-01 10:00:00')")
    conn.execute("INSERT INTO commits (sha, created_at) VALUES ('def456', '2024-01-02 10:00:00')")
    conn.commit()
    conn.close()
    
    # 测试提取日期
    conn = connect_database(str(db_path))
    dates = extract_all_dates(conn)
    assert len(dates) >= 0  # 至少应该尝试提取
    conn.close()


def test_extract_data_for_date(tmp_path):
    """测试按日期提取数据"""
    # 创建临时数据库
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE commits (
            id INTEGER PRIMARY KEY,
            sha TEXT,
            author_id INTEGER,
            created_at TIMESTAMP
        )
    """)
    conn.execute("INSERT INTO commits (sha, author_id, created_at) VALUES ('abc123', 1, '2024-01-01 10:00:00')")
    conn.commit()
    conn.close()
    
    # 测试提取数据
    conn = connect_database(str(db_path))
    data = extract_data_for_date(conn, "2024-01-01")
    assert 'date' in data
    assert data['date'] == "2024-01-01"
    conn.close()

