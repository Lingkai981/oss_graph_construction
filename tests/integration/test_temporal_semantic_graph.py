"""
时序语义图构建集成测试

验证从小型 GitHub 事件 JSON 文件到图构建与导出的端到端流程。
"""

from pathlib import Path
import json

from src.services.temporal_semantic_graph.pipeline import run_temporal_graph_pipeline


def test_temporal_semantic_graph_end_to_end(tmp_path):
    """
    使用一个包含两条事件的临时 JSON 行文件，验证端到端流程：
    - 能够成功构建图；
    - 能够按要求在输出目录中生成 JSON/GraphML 文件。
    """
    content = '\n'.join(
        [
            '{"id": "1", "type": "CreateEvent", "created_at": "2015-01-01T15:00:00Z", '
            '"actor": {"id": 1, "login": "user1"}, '
            '"repo": {"id": 100, "name": "owner/repo1", "url": "https://api.github.com/repos/owner/repo1"}, '
            '"payload": {}}',
            '{"id": "2", "type": "PushEvent", "created_at": "2015-01-01T15:00:10Z", '
            '"actor": {"id": 2, "login": "user2"}, '
            '"repo": {"id": 200, "name": "owner/repo2", "url": "https://api.github.com/repos/owner/repo2"}, '
            '"payload": {"commits": [{"sha": "abc123", "message": "test", '
            '"author": {"name": "user2", "email": "user2@example.com"}, '
            '"distinct": true, "url": "https://api.github.com/repos/owner/repo2/commits/abc123"}]}}',
        ]
    )
    input_file = tmp_path / "2015-01-01-15.json"
    input_file.write_text(content, encoding="utf-8")

    output_dir = tmp_path / "out"
    files = run_temporal_graph_pipeline(
        input_path=str(input_file),
        output_dir=str(output_dir),
        export_formats=("json", "graphml"),
    )

    # 至少应生成两个导出文件（JSON + GraphML），且文件名包含分钟信息
    assert len(files) == 2
    for fp in files:
        assert Path(fp).exists()

    # 读取 JSON 导出文件，验证 meta 与部分节点属性与原始事件一致
    json_files = [fp for fp in files if fp.endswith(".json")]
    assert json_files
    data = json.loads(Path(json_files[0]).read_text(encoding="utf-8"))

    assert data["meta"]["source_file"] == str(input_file)
    assert data["meta"]["node_count"] >= 2
    assert data["meta"]["edge_count"] >= 1

    node_map = {n["id"]: n for n in data["nodes"]}
    ev1 = node_map.get("event:1")
    assert ev1 is not None
    assert ev1["type"] == "Event"
    assert ev1["attributes"]["event_id"] == "1"
    assert ev1["attributes"]["event_type"] == "CreateEvent"

    # 语义评分字段存在且在合理范围内
    imp1 = ev1["attributes"].get("importance_score")
    assert imp1 is not None
    assert 0.0 <= imp1 <= 1.0


