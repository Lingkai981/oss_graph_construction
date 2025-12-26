"""
图导出集成测试
"""

import pytest
import networkx as nx
from pathlib import Path
from src.services.exporter import export_snapshot, export_all_snapshots


def test_integration_export_snapshot(tmp_path):
    """测试集成：导出单个快照"""
    graph = nx.DiGraph()
    graph.add_node("node1", name="test")
    graph.graph['date'] = '2024-01-01'
    
    output_dir = str(tmp_path / "output")
    file_path = export_snapshot(graph, "2024-01-01", output_dir, "graphml")
    
    assert Path(file_path).exists()
    assert "snapshot_2024-01-01.graphml" in file_path


def test_integration_export_all_snapshots(tmp_path):
    """测试集成：批量导出快照"""
    snapshots = []
    dates = []
    
    for i in range(3):
        graph = nx.DiGraph()
        graph.add_node(f"node{i}", name=f"test{i}")
        graph.graph['date'] = f'2024-01-0{i+1}'
        snapshots.append(graph)
        dates.append(f'2024-01-0{i+1}')
    
    output_dir = str(tmp_path / "output")
    exported_files = export_all_snapshots(snapshots, dates, output_dir, "graphml")
    
    assert len(exported_files) == 3
    for file_path in exported_files:
        assert Path(file_path).exists()

