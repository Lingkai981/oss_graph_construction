"""
时序语义图相关模型

封装事件、开发者、仓库、提交等节点在图中的属性映射逻辑，
便于在构图服务中保持字段命名与数据模型的一致性。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.utils.date_utils import parse_timestamp


def make_event_attributes(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据原始 GitHub 事件对象生成事件节点属性。

    对应数据模型中的事件节点字段：
    - event_id, type, created_at, created_at_ts, public, repo_id, actor_id, payload_summary
    """
    event_id = event.get("id")
    event_type = event.get("type")
    created_at = event.get("created_at")
    public = event.get("public")

    actor = event.get("actor") or {}
    repo = event.get("repo") or {}
    payload = event.get("payload") or {}

    dt = parse_timestamp(created_at) if created_at else None
    ts = dt.timestamp() if dt is not None else None

    payload_summary: Optional[str] = None
    if event_type == "PushEvent":
        commits = payload.get("commits") or []
        if commits:
            msg = commits[0].get("message")
            if isinstance(msg, str):
                payload_summary = msg[:200]

    attrs: Dict[str, Any] = {
        "node_type": "Event",
        "event_id": event_id,
        "event_type": event_type,
        "created_at": created_at,
        "created_at_ts": ts,
        "public": public,
        "repo_id": repo.get("id"),
        "actor_id": actor.get("id"),
    }
    if payload_summary is not None:
        attrs["payload_summary"] = payload_summary

    return attrs


def make_actor_attributes(actor: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据 actor 字段生成开发者节点属性。
    """
    return {
        "node_type": "Actor",
        "actor_id": actor.get("id"),
        "login": actor.get("login"),
        "avatar_url": actor.get("avatar_url"),
        "url": actor.get("url"),
        "gravatar_id": actor.get("gravatar_id"),
    }


def make_repo_attributes(repo: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据 repo 字段生成仓库节点属性。
    """
    return {
        "node_type": "Repository",
        "repo_id": repo.get("id"),
        "name": repo.get("name"),
        "url": repo.get("url"),
    }


def make_commit_attributes(commit: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据 PushEvent 中的单个 commit 字典生成提交节点属性。
    """
    sha = commit.get("sha")
    message = commit.get("message")
    author = commit.get("author") or {}

    message_length: Optional[int] = len(message) if isinstance(message, str) else None

    attrs: Dict[str, Any] = {
        "node_type": "Commit",
        "commit_sha": sha,
        "message": message,
        "author_name": author.get("name"),
        "author_email": author.get("email"),
        "distinct": commit.get("distinct"),
        "url": commit.get("url"),
    }
    if message_length is not None:
        attrs["message_length"] = message_length

    return attrs

