"""
pipeline / 导出相关单元测试

主要验证：
- export_temporal_graph_to_json 生成的 JSON 结构符合 contracts/README.md 约定；
- export_temporal_graph_to_graphml 生成的 GraphML 文件可被 NetworkX 重新加载。
"""

import json
from pathlib import Path

import networkx as nx

from src.services.exporter import (
    export_temporal_graph_to_json,
    export_temporal_graph_to_graphml,
)


def _make_small_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("event:1", node_type="Event", event_id="1", event_type="PushEvent")
    g.add_node("actor:1", node_type="Actor", actor_id=1, login="user1")
    g.add_edge(
        "actor:1",
        "event:1",
        type="ACTOR_TRIGGERED_EVENT",
        created_at="2015-01-01T15:00:00Z",
    )
    return g


def test_export_temporal_graph_to_json_structure(tmp_path):
    graph = _make_small_graph()
    output = tmp_path / "temporal.json"

    export_temporal_graph_to_json(graph, str(output), source_file="data/sample.json")

    data = json.loads(output.read_text(encoding="utf-8"))

    assert "meta" in data
    assert "nodes" in data
    assert "edges" in data

    assert data["meta"]["source_file"] == "data/sample.json"
    assert data["meta"]["node_count"] == 2
    assert data["meta"]["edge_count"] == 1

    node_ids = {n["id"] for n in data["nodes"]}
    assert "event:1" in node_ids
    assert "actor:1" in node_ids

    edge = data["edges"][0]
    assert edge["type"] == "ACTOR_TRIGGERED_EVENT"
    assert edge["source"] == "actor:1"
    assert edge["target"] == "event:1"


def test_export_temporal_graph_to_graphml_roundtrip(tmp_path):
    graph = _make_small_graph()
    output = tmp_path / "temporal.graphml"

    export_temporal_graph_to_graphml(graph, str(output))

    assert output.exists()

    loaded = nx.read_graphml(str(output))
    # GraphML 加载后节点/边数量应一致
    assert len(loaded.nodes) == len(graph.nodes)
    assert len(loaded.edges) == len(graph.edges)


