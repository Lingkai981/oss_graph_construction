"""
数据库服务单元测试
"""

import pytest
import sqlite3
from pathlib import Path
from src.services.database import connect_database, get_table_names


def test_connect_database_success(tmp_path):
    """测试成功连接数据库"""
    # 创建临时数据库
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
    conn.commit()
    conn.close()
    
    # 测试连接
    conn = connect_database(str(db_path))
    assert conn is not None
    conn.close()


def test_connect_database_not_found():
    """测试数据库文件不存在的情况"""
    with pytest.raises(FileNotFoundError):
        connect_database("nonexistent.db")


def test_get_table_names(tmp_path):
    """测试获取表名"""
    # 创建临时数据库
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test1 (id INTEGER)")
    conn.execute("CREATE TABLE test2 (id INTEGER)")
    conn.commit()
    conn.close()
    
    # 测试获取表名
    conn = connect_database(str(db_path))
    tables = get_table_names(conn)
    assert "test1" in tables
    assert "test2" in tables
    conn.close()

