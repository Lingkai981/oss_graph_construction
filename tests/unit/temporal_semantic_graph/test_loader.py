"""
loader 模块单元测试

主要验证从 JSON 行文件中正确解析事件列表，以及对错误行的容错行为。
"""

from pathlib import Path

from src.services.temporal_semantic_graph.loader import load_events_from_file


def test_load_events_from_file_basic(tmp_path):
    """
    使用一个包含两行事件（其中一行无效 JSON）的临时文件进行测试。
    """
    content = '\n'.join(
        [
            # 有效事件
            '{"id": "1", "type": "PushEvent", "created_at": "2015-01-01T15:00:00Z"}',
            # 无效 JSON 行
            '{"id": "broken", "type": ',
        ]
    )
    file_path = tmp_path / "events.json"
    file_path.write_text(content, encoding="utf-8")

    events = load_events_from_file(str(file_path))

    assert len(events) == 1
    ev = events[0]
    assert ev["id"] == "1"
    assert ev["type"] == "PushEvent"
    assert ev["created_at"] == "2015-01-01T15:00:00Z"


