"""
图导出服务单元测试
"""

import pytest
import networkx as nx
from pathlib import Path
from src.services.exporter import (
    export_graphml, export_json, generate_filename,
    ensure_output_directory, export_snapshot
)


def test_generate_filename():
    """测试生成文件名"""
    filename = generate_filename("2024-01-01", "graphml")
    assert filename == "snapshot_2024-01-01.graphml"
    
    filename = generate_filename("2024-01-01", "json")
    assert filename == "snapshot_2024-01-01.json"


def test_ensure_output_directory(tmp_path):
    """测试确保输出目录存在"""
    output_dir = tmp_path / "output"
    path = ensure_output_directory(str(output_dir))
    assert path.exists()
    assert path.is_dir()


def test_export_graphml(tmp_path):
    """测试导出GraphML"""
    graph = nx.DiGraph()
    graph.add_node("node1", name="test")
    output_path = tmp_path / "test.graphml"
    export_graphml(graph, str(output_path))
    assert output_path.exists()


def test_export_json(tmp_path):
    """测试导出JSON"""
    graph = nx.DiGraph()
    graph.add_node("node1", name="test")
    output_path = tmp_path / "test.json"
    export_json(graph, str(output_path))
    assert output_path.exists()

