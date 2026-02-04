"""
按月构建项目图（三类时序图）

功能：
1. 读取 data/filtered/ 下的日粒度数据
2. 按月聚合，按项目分组
3. 为每个项目的每个月构建三类图：
   - Actor-Actor 协作图
   - Actor-Repository 二部图
   - Actor-Discussion 二部图
4. 保存图数据供后续分析

输出结构：
output/monthly-graphs/
├── facebook-react/
│   ├── actor-actor/
│   │   ├── 2023-01.graphml
│   │   └── ...
│   ├── actor-repo/
│   │   ├── 2023-01.graphml
│   │   └── ...
│   └── actor-discussion/
│       ├── 2023-01.graphml
│       └── ...
└── ...
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import re

import networkx as nx


def sanitize_graphml_attributes(g: nx.Graph) -> None:
    """就地清洗图、节点、边属性，避免写出的 GraphML 不是合法 XML。"""
    # graph-level
    for k, v in list(g.graph.items()):
        if isinstance(v, str) or v is None:
            g.graph[k] = _sanitize_xml_text(v)
        elif isinstance(v, (dict, list)):
            g.graph[k] = _sanitize_xml_text(json.dumps(v, ensure_ascii=False))
        else:
            # numbers/bools etc are fine
            pass

    # nodes
    for n, attrs in list(g.nodes(data=True)):
        for k, v in list(attrs.items()):
            if isinstance(v, str) or v is None:
                attrs[k] = _sanitize_xml_text(v)
            elif isinstance(v, (dict, list)):
                attrs[k] = _sanitize_xml_text(json.dumps(v, ensure_ascii=False))
            else:
                pass

    # edges (MultiDiGraph compatible)
    if hasattr(g, "edges"):
        for u, v, key, attrs in list(g.edges(keys=True, data=True)):
            for k, val in list(attrs.items()):
                if isinstance(val, str) or val is None:
                    attrs[k] = _sanitize_xml_text(val)
                elif isinstance(val, (dict, list)):
                    attrs[k] = _sanitize_xml_text(json.dumps(val, ensure_ascii=False))
                else:
                    pass

from src.utils.logger import get_logger

logger = get_logger()


# ==================== 数据类 ====================

@dataclass
class ActorStats:
    """Actor 统计信息"""
    actor_id: int
    login: str
    event_count: int = 0
    event_types: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_type": "Actor",
            "actor_id": self.actor_id,
            "login": _sanitize_xml_text(self.login),
            "event_count": self.event_count,
            "event_types": json.dumps(dict(self.event_types)),
        }


@dataclass 
class RepoStats:
    """Repository 统计信息"""
    repo_id: int
    name: str
    event_count: int = 0
    event_types: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_type": "Repository",
            "repo_id": self.repo_id,
            "name": _sanitize_xml_text(self.name),
            "event_count": self.event_count,
            "event_types": json.dumps(dict(self.event_types)),
        }


@dataclass
class DiscussionStats:
    """Issue/PR 统计信息"""
    key: str  # issue:repo_id:number 或 pr:repo_id:number
    node_type: str  # Issue 或 PullRequest
    number: int
    title: str = ""
    state: str = ""
    creator_id: Optional[int] = None
    creator_login: str = ""
    comment_count: int = 0
    participants: Set[int] = field(default_factory=set)
    created_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_type": self.node_type,
            "key": _sanitize_xml_text(self.key),
            "number": self.number,
            "title": (_sanitize_xml_text(self.title)[:100] if self.title else ""),
            "state": _sanitize_xml_text(self.state),
            "creator_id": self.creator_id or 0,
            "creator_login": _sanitize_xml_text(self.creator_login),
            "comment_count": self.comment_count,
            "participants_count": len(self.participants),
            "created_at": _sanitize_xml_text(self.created_at or ""),
        }


# ==================== 数据加载 ====================

def load_filtered_data(data_dir: str) -> Dict[str, List[Dict]]:
    """加载过滤后的数据，按日期组织"""
    data_path = Path(data_dir)
    all_data = defaultdict(list)
    
    files = sorted(data_path.glob("*-filtered.json"))
    total_files = len(files)
    total_events = 0
    
    print(f"找到 {total_files} 个数据文件")
    
    for idx, file_path in enumerate(files, 1):
        filename = file_path.stem
        parts = filename.replace("-filtered", "").split("-")
        if len(parts) >= 3:
            date_str = f"{parts[0]}-{parts[1]}-{parts[2]}"
            
            file_events = 0
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            event = json.loads(line)
                            all_data[date_str].append(event)
                            file_events += 1
                        except json.JSONDecodeError:
                            continue
            
            total_events += file_events
            
            if idx % 50 == 0 or idx == total_files:
                print(f"  加载进度: {idx}/{total_files} 文件，累计 {total_events} 事件")
    
    print(f"数据加载完成: {len(all_data)} 天，{total_events} 个事件")
    return dict(all_data)


def group_by_month_and_repo(
    daily_data: Dict[str, List[Dict]]
) -> Dict[str, Dict[str, List[Dict]]]:
    """按月和项目分组"""
    result = defaultdict(lambda: defaultdict(list))
    
    for date_str, events in daily_data.items():
        month = date_str[:7]
        for event in events:
            repo_name = event.get("repo", {}).get("name", "").lower()
            if repo_name:
                result[month][repo_name].append(event)
    
    logger.info(f"按月分组后共 {len(result)} 个月")
    return {k: dict(v) for k, v in result.items()}


# ==================== 图构建函数 ====================

def _clean_text_for_xml(text: str) -> str:
    """
    清理文本中的控制字符，使其可以作为 XML 文本安全写入
    
    移除 XML 1.0 不允许的控制字符（除了 \t \n \r），保留其他所有字符。
    NetworkX/ElementTree 会自动处理 XML 转义（& < > " '），所以这里只清理控制字符。
    
    适用于所有文本字段：login, name, title, creator_login 等
    """
    if not text:
        return ""
    
    # 过滤 XML 不允许的控制字符（与 _sanitize_comment_text 使用相同的逻辑）
    return "".join(
        ch
        for ch in text
        if (
            ch == "\t"
            or ch == "\n"
            or ch == "\r"
            or 0x20 <= ord(ch) <= 0xD7FF
            or 0xE000 <= ord(ch) <= 0xFFFD
        )
    )


def _escape_xml_text(text: str) -> str:
    """
    转义 XML 特殊字符并清理控制字符
    
    先清理 XML 不允许的控制字符（除了 \t \n \r），再进行 XML 转义，
    确保生成的 XML 文件格式正确。与 _sanitize_comment_text 使用相同的控制字符过滤逻辑。
    
    注意：此函数会转义 XML 特殊字符，适用于需要手动转义的场景。
    对于 NetworkX 写入的字段，使用 _clean_text_for_xml 即可（NetworkX 会自动转义）。
    """
    if not text:
        return ""
    
    # 先清理控制字符
    cleaned = _clean_text_for_xml(text)
    
    # 然后转义 XML 特殊字符
    return (cleaned
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
            )
def _sanitize_xml_text(text: str) -> str:
    """清洗 GraphML/XML 中不合法字符，并转义 XML 特殊字符。

    主要解决：
    - XML 1.0 不允许的控制字符（会导致 not well-formed / invalid token）
    - 未转义的特殊字符 & < > ' "
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # 1) 移除 XML 1.0 不允许的字符
    # 允许：\t \n \r；以及 U+0020 以上的常规字符（并排除 surrogate 区）
    cleaned_chars = []
    for ch in text:
        code = ord(ch)
        if ch in ("\t", "\n", "\r"):
            cleaned_chars.append(ch)
            continue
        # 基本可见字符
        if 0x20 <= code <= 0xD7FF:
            cleaned_chars.append(ch)
            continue
        # 排除 surrogate：0xD800-0xDFFF
        if 0xE000 <= code <= 0xFFFD:
            cleaned_chars.append(ch)
            continue
        # 非 BMP 字符（Python 可表示）
        if 0x10000 <= code <= 0x10FFFF:
            cleaned_chars.append(ch)
            continue
        # 其它：丢弃
    text = "".join(cleaned_chars)

    # 2) 转义 XML 特殊字符（GraphML 本质是 XML）
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
            )


_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _sanitize_comment_text(text: str) -> str:
    """
    清洗评论正文/日志文本，使其可以作为 GraphML 文本安全写入：
    - 去掉 ANSI 颜色控制序列（例如 [32m）
    - 去掉 XML 1.0 不允许的控制字符（除了 \t \n \r）
    其余内容原样保留，让 NetworkX/ElementTree 负责正常的 XML 转义。
    """
    if not text:
        return ""

    # 1) 去掉 ANSI 颜色控制序列
    cleaned = _ANSI_ESCAPE_RE.sub("", text)

    # 2) 过滤 XML 不允许的控制字符
    return "".join(
        ch
        for ch in cleaned
        if (
            ch == "\t"
            or ch == "\n"
            or ch == "\r"
            or 0x20 <= ord(ch) <= 0xD7FF
            or 0xE000 <= ord(ch) <= 0xFFFD
        )
    )


def build_actor_actor_graph(
    events: List[Dict],
    repo_name: str,
    month: str,
) -> nx.MultiDiGraph:
    """
    构建 Actor-Actor 协作图
    
    边类型：
    - ISSUE_INTERACTION: 在他人创建的 Issue 下评论
    - PR_REVIEW: 审查他人的 PR
    - PR_MERGE: 合并他人的 PR
    - ISSUE_CO_PARTICIPANT: 同 Issue 下的参与者
    """
    graph = nx.MultiDiGraph()
    actors: Dict[int, ActorStats] = {}
    
    issue_creators: Dict[int, int] = {}
    pr_creators: Dict[int, int] = {}
    issue_participants: Dict[int, Set[int]] = defaultdict(set)
    edges: List[Dict] = []
    
    def _ensure_actor(actor_data: Dict) -> Optional[int]:
        actor_id = actor_data.get("id")
        if actor_id is None:
            return None
        if actor_id not in actors:
            actors[actor_id] = ActorStats(
                actor_id=actor_id,
                login=_clean_text_for_xml(actor_data.get("login") or ""),
            )
        return actor_id
    
    def _update_actor_stats(actor_id: int, event_type: str, created_at: str):
        if actor_id in actors:
            actors[actor_id].event_count += 1
            actors[actor_id].event_types[event_type] = \
                actors[actor_id].event_types.get(event_type, 0) + 1
    
    # 第一遍：收集创建者
    for event in events:
        event_type = event.get("type") or ""
        payload = event.get("payload") or {}
        actor = event.get("actor") or {}
        actor_id = _ensure_actor(actor)
        
        if event_type == "IssuesEvent" and payload.get("action") == "opened":
            issue = payload.get("issue") or {}
            issue_number = issue.get("number")
            if issue_number and actor_id:
                issue_creators[issue_number] = actor_id
        
        elif event_type == "PullRequestEvent" and payload.get("action") == "opened":
            pr = payload.get("pull_request") or {}
            pr_number = pr.get("number")
            if pr_number and actor_id:
                pr_creators[pr_number] = actor_id
    
    # 第二遍：构建边
    for event in events:
        event_id = event.get("id")
        event_type = event.get("type") or ""
        created_at = event.get("created_at") or ""
        actor = event.get("actor") or {}
        actor_id = _ensure_actor(actor)
        
        if actor_id is None:
            continue
        
        _update_actor_stats(actor_id, event_type, created_at)
        payload = event.get("payload") or {}
        
        if event_type == "IssueCommentEvent":
            issue = payload.get("issue") or {}
            issue_number = issue.get("number")
            if issue_number:
                issue_participants[issue_number].add(actor_id)
                creator_id = issue_creators.get(issue_number)
                if not creator_id:
                    issue_user = issue.get("user") or {}
                    creator_id = issue_user.get("id")
                    if creator_id:
                        issue_creators[issue_number] = creator_id
                        _ensure_actor(issue_user)
                
                if creator_id and creator_id != actor_id:
                    comment = payload.get("comment") or {}
                    comment_body = _sanitize_comment_text(comment.get("body", ""))
                    edges.append({
                        "source": actor_id, "target": creator_id,
                        "edge_type": "ISSUE_INTERACTION",
                        "event_id": event_id, "created_at": created_at,
                        "comment_body": comment_body,
                    })
        
        elif event_type == "PullRequestReviewCommentEvent":
            pr = payload.get("pull_request") or {}
            pr_number = pr.get("number")
            if pr_number:
                creator_id = pr_creators.get(pr_number)
                if not creator_id:
                    pr_user = pr.get("user") or {}
                    creator_id = pr_user.get("id")
                    if creator_id:
                        pr_creators[pr_number] = creator_id
                        _ensure_actor(pr_user)
                
                if creator_id and creator_id != actor_id:
                    comment = payload.get("comment") or {}
                    comment_body = _sanitize_comment_text(comment.get("body", ""))
                    edges.append({
                        "source": actor_id, "target": creator_id,
                        "edge_type": "PR_REVIEW",
                        "event_id": event_id, "created_at": created_at,
                        "comment_body": comment_body,
                    })
        
        elif event_type == "PullRequestEvent":
            action = payload.get("action")
            pr = payload.get("pull_request") or {}
            pr_number = pr.get("number")
            
            if action == "closed" and pr.get("merged") and pr_number:
                creator_id = pr_creators.get(pr_number)
                if not creator_id:
                    pr_user = pr.get("user") or {}
                    creator_id = pr_user.get("id")
                    if creator_id:
                        pr_creators[pr_number] = creator_id
                        _ensure_actor(pr_user)
                
                if creator_id and creator_id != actor_id:
                    edges.append({
                        "source": actor_id, "target": creator_id,
                        "edge_type": "PR_MERGE",
                        "event_id": event_id, "created_at": created_at,
                    })
    
    # 添加共同参与者边
    for issue_number, participants in issue_participants.items():
        participants_list = list(participants)
        for i in range(len(participants_list)):
            for j in range(i + 1, len(participants_list)):
                a1, a2 = participants_list[i], participants_list[j]
                edges.append({
                    "source": a1, "target": a2,
                    "edge_type": "ISSUE_CO_PARTICIPANT",
                    "event_id": f"co_{issue_number}_{a1}_{a2}",
                    "created_at": "",
                })
    
    # 构建图
    actors_with_edges = set()
    for edge in edges:
        actors_with_edges.add(edge["source"])
        actors_with_edges.add(edge["target"])
    
    for actor_id in actors_with_edges:
        if actor_id in actors:
            graph.add_node(f"actor:{actor_id}", **actors[actor_id].to_dict())
    
    for edge_data in edges:
        source = f"actor:{edge_data['source']}"
        target = f"actor:{edge_data['target']}"
        edge_key = f"{edge_data['edge_type']}_{edge_data['event_id']}"
        graph.add_edge(source, target, key=edge_key,
                       edge_type=edge_data["edge_type"],
                       created_at=edge_data.get("created_at") or "",
                       comment_body=_sanitize_xml_text(edge_data.get("comment_body", "")))
    
    graph.graph["repo_name"] = _sanitize_xml_text(repo_name)
    graph.graph["month"] = _sanitize_xml_text(month)
    graph.graph["graph_type"] = "actor-actor"
    graph.graph["total_events"] = len(events)
    
    return graph


def build_actor_repo_graph(
    events: List[Dict],
    repo_name: str,
    month: str,
) -> nx.MultiDiGraph:
    """
    构建 Actor-Repository 二部图
    
    边类型：基于事件类型（PUSH, CREATE, ISSUE, PR, COMMENT 等）
    新增：边包含详细统计信息（commit_count, pr_merged 等）
    """
    graph = nx.MultiDiGraph()
    actors: Dict[int, ActorStats] = {}
    repos: Dict[int, RepoStats] = {}
    edges: List[Dict] = []
    
    for event in events:
        event_id = event.get("id")
        event_type = event.get("type") or ""
        created_at = event.get("created_at") or ""
        
        actor = event.get("actor") or {}
        actor_id = actor.get("id")
        repo = event.get("repo") or {}
        repo_id = repo.get("id")
        
        if actor_id is None or repo_id is None:
            continue
        
        # 确保 Actor 存在
        if actor_id not in actors:
            actors[actor_id] = ActorStats(
                actor_id=actor_id,
                login=_clean_text_for_xml(actor.get("login") or ""),
            )
        actors[actor_id].event_count += 1
        actors[actor_id].event_types[event_type] = \
            actors[actor_id].event_types.get(event_type, 0) + 1
        
        # 确保 Repo 存在
        if repo_id not in repos:
            repos[repo_id] = RepoStats(
                repo_id=repo_id,
                name=_clean_text_for_xml(repo.get("name") or ""),
            )
        repos[repo_id].event_count += 1
        repos[repo_id].event_types[event_type] = \
            repos[repo_id].event_types.get(event_type, 0) + 1
        
        # 简化边类型
        edge_type_map = {
            "PushEvent": "PUSH",
            "CreateEvent": "CREATE",
            "PullRequestEvent": "PR",
            "IssuesEvent": "ISSUE",
            "IssueCommentEvent": "COMMENT",
            "PullRequestReviewCommentEvent": "REVIEW",
            "WatchEvent": "STAR",
            "ForkEvent": "FORK",
            "DeleteEvent": "DELETE",
            "ReleaseEvent": "RELEASE",
        }
        edge_type = edge_type_map.get(event_type, event_type)

        # 只有"评论类事件"才有正文
        comment_body = ""
        if event_type in ("IssueCommentEvent", "PullRequestReviewCommentEvent"):
            comment = (event.get("payload") or {}).get("comment") or {}
            comment_body = _sanitize_comment_text(comment.get("body", "") or "")
        
        # 从 payload 中提取详细统计信息
        payload = event.get("payload") or {}
        commit_count = 0
        pr_merged = 0
        pr_opened = 0
        pr_closed = 0
        issue_opened = 0
        issue_closed = 0
        is_comment = 0
        
        if event_type == "PushEvent":
            commits = payload.get("commits") or []
            commit_count = len(commits)
        elif event_type == "PullRequestEvent":
            action = payload.get("action")
            pr = payload.get("pull_request") or {}
            if action == "opened":
                pr_opened = 1
            elif action == "closed":
                pr_closed = 1
                if pr.get("merged"):
                    pr_merged = 1
        elif event_type == "IssuesEvent":
            action = payload.get("action")
            if action == "opened":
                issue_opened = 1
            elif action == "closed":
                issue_closed = 1
        elif event_type in ("IssueCommentEvent", "PullRequestReviewCommentEvent"):
            is_comment = 1

        edges.append({
            "actor_id": actor_id,
            "repo_id": repo_id,
            "edge_type": edge_type,
            "event_id": event_id,
            "created_at": created_at,
            "comment_body": comment_body,
            # 新增：详细统计信息
            "commit_count": commit_count,
            "pr_merged": pr_merged,
            "pr_opened": pr_opened,
            "pr_closed": pr_closed,
            "issue_opened": issue_opened,
            "issue_closed": issue_closed,
            "is_comment": is_comment,
        })
    
    # 添加节点
    for actor_id, actor_stats in actors.items():
        graph.add_node(f"actor:{actor_id}", **actor_stats.to_dict())
    
    for repo_id, repo_stats in repos.items():
        graph.add_node(f"repo:{repo_id}", **repo_stats.to_dict())
    
    # 添加边（每条事件仍然是独立的边，但包含统计信息）
    for edge_data in edges:
        source = f"actor:{edge_data['actor_id']}"
        target = f"repo:{edge_data['repo_id']}"
        edge_key = f"{edge_data['edge_type']}_{edge_data['event_id']}"
        graph.add_edge(
            source, 
            target, 
            key=edge_key,
            edge_type=edge_data["edge_type"],
            created_at=edge_data.get("created_at") or "",
            comment_body=_sanitize_xml_text(edge_data.get("comment_body", "")),
            # 新增：统计信息
            commit_count=edge_data.get("commit_count", 0),
            pr_merged=edge_data.get("pr_merged", 0),
            pr_opened=edge_data.get("pr_opened", 0),
            pr_closed=edge_data.get("pr_closed", 0),
            issue_opened=edge_data.get("issue_opened", 0),
            issue_closed=edge_data.get("issue_closed", 0),
            is_comment=edge_data.get("is_comment", 0),
        )
    
    graph.graph["repo_name"] = _sanitize_xml_text(repo_name)
    graph.graph["month"] = _sanitize_xml_text(month)
    graph.graph["graph_type"] = "actor-repo"
    graph.graph["total_events"] = len(events)
    
    return graph


def build_actor_discussion_graph(
    events: List[Dict],
    repo_name: str,
    month: str,
) -> nx.MultiDiGraph:
    """
    构建 Actor-Discussion 二部图（Issue/PR 讨论图）
    
    节点：Actor, Issue, PullRequest
    边：CREATED, COMMENTED, REVIEWED, CLOSED, MERGED
    """
    graph = nx.MultiDiGraph()
    actors: Dict[int, ActorStats] = {}
    discussions: Dict[str, DiscussionStats] = {}
    edges: List[Dict] = []
    
    def _ensure_actor(actor_data: Dict) -> Optional[int]:
        actor_id = actor_data.get("id")
        if actor_id is None:
            return None
        if actor_id not in actors:
            actors[actor_id] = ActorStats(
                actor_id=actor_id,
                login=_clean_text_for_xml(actor_data.get("login") or ""),
            )
        return actor_id
    
    def _update_actor(actor_id: int, event_type: str, created_at: str):
        if actor_id in actors:
            actors[actor_id].event_count += 1
            actors[actor_id].event_types[event_type] = \
                actors[actor_id].event_types.get(event_type, 0) + 1
    
    for event in events:
        event_id = event.get("id")
        event_type = event.get("type") or ""
        created_at = event.get("created_at") or ""
        
        actor = event.get("actor") or {}
        actor_id = _ensure_actor(actor)
        if actor_id is None:
            continue
        
        _update_actor(actor_id, event_type, created_at)
        
        repo = event.get("repo") or {}
        repo_id = repo.get("id")
        payload = event.get("payload") or {}
        
        if event_type == "IssuesEvent":
            action = payload.get("action")
            issue = payload.get("issue") or {}
            issue_number = issue.get("number")
            
            if issue_number and repo_id:
                key = f"issue:{repo_id}:{issue_number}"
                
                if key not in discussions:
                    issue_user = issue.get("user") or {}
                    discussions[key] = DiscussionStats(
                        key=key,
                        node_type="Issue",
                        number=issue_number,
                        title=_sanitize_xml_text(_clean_text_for_xml(issue.get("title") or "")),
                        state=issue.get("state") or "",
                        creator_id=issue_user.get("id"),
                        creator_login=_clean_text_for_xml(issue_user.get("login") or ""),
                        created_at=issue.get("created_at"),
                    )
                
                discussions[key].participants.add(actor_id)
                
                edge_type = "CREATED_ISSUE" if action == "opened" else "CLOSED_ISSUE"
                edges.append({
                    "actor_id": actor_id,
                    "discussion_key": key,
                    "edge_type": edge_type,
                    "event_id": event_id,
                    "created_at": created_at,
                })
        
        elif event_type == "IssueCommentEvent":
            issue = payload.get("issue") or {}
            issue_number = issue.get("number")
            
            if issue_number and repo_id:
                key = f"issue:{repo_id}:{issue_number}"
                
                if key not in discussions:
                    issue_user = issue.get("user") or {}
                    discussions[key] = DiscussionStats(
                        key=key,
                        node_type="Issue",
                        number=issue_number,
                        title=_sanitize_xml_text(_clean_text_for_xml(issue.get("title") or "")),
                        state=issue.get("state") or "",
                        creator_id=issue_user.get("id"),
                        creator_login=_clean_text_for_xml(issue_user.get("login") or ""),
                        created_at=issue.get("created_at"),
                    )
                
                discussions[key].comment_count += 1
                discussions[key].participants.add(actor_id)
                
                # 确保创建者也是 actor
                issue_user = issue.get("user") or {}
                if issue_user.get("id"):
                    _ensure_actor(issue_user)
                
                # 获取评论正文（直接从事件数据中提取）
                comment = payload.get("comment") or {}
                comment_body = _sanitize_comment_text(comment.get("body", ""))

                edges.append({
                    "actor_id": actor_id,
                    "discussion_key": key,
                    "edge_type": "COMMENTED_ISSUE",
                    "event_id": event_id,
                    "created_at": created_at,
                    "comment_body": comment_body,
                })
        
        elif event_type == "PullRequestEvent":
            action = payload.get("action")
            pr = payload.get("pull_request") or {}
            pr_number = pr.get("number")
            
            if pr_number and repo_id:
                key = f"pr:{repo_id}:{pr_number}"
                
                if key not in discussions:
                    pr_user = pr.get("user") or {}
                    discussions[key] = DiscussionStats(
                        key=key,
                        node_type="PullRequest",
                        number=pr_number,
                        title=_sanitize_xml_text(_clean_text_for_xml(pr.get("title") or "")),
                        state=pr.get("state") or "",
                        creator_id=pr_user.get("id"),
                        creator_login=_clean_text_for_xml(pr_user.get("login") or ""),
                        created_at=pr.get("created_at"),
                    )
                
                discussions[key].participants.add(actor_id)
                
                if action == "opened":
                    edge_type = "CREATED_PR"
                elif action == "closed" and pr.get("merged"):
                    edge_type = "MERGED_PR"
                elif action == "closed":
                    edge_type = "CLOSED_PR"
                else:
                    edge_type = "PR_ACTION"
                
                edges.append({
                    "actor_id": actor_id,
                    "discussion_key": key,
                    "edge_type": edge_type,
                    "event_id": event_id,
                    "created_at": created_at,
                })
        
        elif event_type == "PullRequestReviewCommentEvent":
            pr = payload.get("pull_request") or {}
            pr_number = pr.get("number")
            
            if pr_number and repo_id:
                key = f"pr:{repo_id}:{pr_number}"
                
                if key not in discussions:
                    pr_user = pr.get("user") or {}
                    discussions[key] = DiscussionStats(
                        key=key,
                        node_type="PullRequest",
                        number=pr_number,
                        title=_sanitize_xml_text(_clean_text_for_xml(pr.get("title") or "")),
                        state=pr.get("state") or "",
                        creator_id=pr_user.get("id"),
                        creator_login=_clean_text_for_xml(pr_user.get("login") or ""),
                        created_at=pr.get("created_at"),
                    )
                
                discussions[key].comment_count += 1
                discussions[key].participants.add(actor_id)
                
                # 确保创建者也是 actor
                pr_user = pr.get("user") or {}
                if pr_user.get("id"):
                    _ensure_actor(pr_user)
                
                # 获取评论正文（直接从事件数据中提取）
                comment = payload.get("comment") or {}
                comment_body = _sanitize_comment_text(comment.get("body", ""))
                edges.append({
                    "actor_id": actor_id,
                    "discussion_key": key,
                    "edge_type": "REVIEWED_PR",
                    "event_id": event_id,
                    "created_at": created_at,
                    "comment_body": comment_body,
                })
    
    # 添加节点
    for actor_id, actor_stats in actors.items():
        graph.add_node(f"actor:{actor_id}", **actor_stats.to_dict())
    
    for key, disc_stats in discussions.items():
        graph.add_node(key, **disc_stats.to_dict())
    
    # 添加边
    for edge_data in edges:
        source = f"actor:{edge_data['actor_id']}"
        target = edge_data["discussion_key"]
        edge_key = f"{edge_data['edge_type']}_{edge_data['event_id']}"
        graph.add_edge(source, target, key=edge_key,
                       edge_type=edge_data["edge_type"],
                       created_at=edge_data.get("created_at") or "",
                       comment_body=_sanitize_xml_text(edge_data.get("comment_body", "")))
    
    graph.graph["repo_name"] = _sanitize_xml_text(repo_name)
    graph.graph["month"] = _sanitize_xml_text(month)
    graph.graph["graph_type"] = "actor-discussion"
    graph.graph["total_events"] = len(events)
    
    return graph


# ==================== 主流程 ====================

def _filter_months(
    monthly_repo_data: Dict[str, Dict[str, List[Dict]]],
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
) -> Dict[str, Dict[str, List[Dict]]]:
    """按月份范围过滤"""
    if not start_month and not end_month:
        return monthly_repo_data
    filtered = {}
    for month, repos in monthly_repo_data.items():
        if start_month and month < start_month:
            continue
        if end_month and month > end_month:
            continue
        filtered[month] = repos
    return filtered


def build_monthly_graphs(
    data_dir: str = "data/filtered/",
    output_dir: str = "output/monthly-graphs/",
    graph_types: List[str] = None,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    merge_index: bool = True,
) -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    构建所有项目的月度图（三类）
    
    Args:
        data_dir: 输入数据目录
        output_dir: 输出目录
        graph_types: 要构建的图类型，默认全部 ["actor-actor", "actor-repo", "actor-discussion"]
        start_month: 只构建该月及之后的图 (YYYY-MM)
        end_month: 只构建该月及之前的图 (YYYY-MM)
        merge_index: 若输出目录已有 index.json，是否合并而非覆盖
    
    Returns:
        {repo_name: {graph_type: {month: graph_path}}}
    """
    if graph_types is None:
        graph_types = ["actor-actor", "actor-repo", "actor-discussion"]
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 图构建函数映射
    builder_map = {
        "actor-actor": build_actor_actor_graph,
        "actor-repo": build_actor_repo_graph,
        "actor-discussion": build_actor_discussion_graph,
    }
    
    # 加载数据
    print("加载过滤后的数据...")
    daily_data = load_filtered_data(data_dir)
    
    # 按月和项目分组
    print("按月和项目分组...")
    monthly_repo_data = group_by_month_and_repo(daily_data)
    
    # 按月份范围过滤
    if start_month or end_month:
        monthly_repo_data = _filter_months(monthly_repo_data, start_month, end_month)
        print(f"月份过滤: {start_month or '不限'} ~ {end_month or '不限'}，共 {len(monthly_repo_data)} 个月")
    
    # 统计
    total_combos = sum(len(repos) for repos in monthly_repo_data.values())
    total_graphs = total_combos * len(graph_types)
    print(f"将构建约 {total_graphs} 个图（{len(monthly_repo_data)} 个月 × 多个项目 × {len(graph_types)} 种图）")
    
    result = defaultdict(lambda: defaultdict(dict))
    graph_count = 0
    skipped_count = 0
    error_count = 0
    
    # 计算总任务数
    months_list = sorted(monthly_repo_data.keys())
    total_months = len(months_list)
    
    for month_idx, month in enumerate(months_list, 1):
        repos = monthly_repo_data[month]
        repos_in_month = len(repos)
        
        print(f"")
        print(f"{'='*60}")
        print(f"处理月份: {month} ({month_idx}/{total_months})")
        print(f"该月份包含 {repos_in_month} 个项目")
        print(f"{'='*60}")
        
        for repo_idx, (repo_name, events) in enumerate(repos.items(), 1):
            if len(events) < 3:  # 跳过事件太少的
                skipped_count += 1
                continue
            
            safe_repo_name = repo_name.replace("/", "-")
            repo_dir = output_path / safe_repo_name
            
            graphs_built_for_repo = []
            
            for graph_type in graph_types:
                builder = builder_map.get(graph_type)
                if not builder:
                    continue
                
                # 创建图类型目录
                type_dir = repo_dir / graph_type
                type_dir.mkdir(parents=True, exist_ok=True)
                
                # 构建图
                try:
                    import sys
                    sys.stdout.write(f"\r    构建 {graph_type}...")
                    sys.stdout.flush()
                    graph = builder(events, repo_name, month)
                except Exception as e:
                    print(f"\n    警告: 构建图失败 {repo_name}/{graph_type}/{month}: {e}")
                    error_count += 1
                    continue
                
                # 跳过空图
                if graph.number_of_nodes() < 2:
                    skipped_count += 1
                    continue
                
                # 保存
                graph_file = type_dir / f"{month}.graphml"
                try:
                    sanitize_graphml_attributes(graph)
                    nx.write_graphml(graph, str(graph_file))

                    result[repo_name][graph_type][month] = str(graph_file)
                    graph_count += 1
                    graphs_built_for_repo.append(graph_type)

                except Exception as e:
                    print(f"\n    警告: 保存图失败 {graph_file}: {e}")
                    error_count += 1
                    continue

            
            # 每处理一个项目输出进度
            if graphs_built_for_repo:
                # 清除当前行并打印完成信息
                print(
                    f"\r  [{repo_idx}/{repos_in_month}] {repo_name}: "
                    f"{len(events)} 事件 → {', '.join(graphs_built_for_repo)}          "
                )
        
        # 每个月结束时输出统计
        print(f"月份 {month} 处理完成，累计: {graph_count} 个图")
    
    print("")
    print("=" * 60)
    print("构建完成统计:")
    print(f"  成功构建: {graph_count} 个图")
    print(f"  跳过: {skipped_count} 个（事件太少或空图）")
    print(f"  错误: {error_count} 个")
    print(f"  涉及项目: {len(result)} 个")
    print("=" * 60)
    
    # 保存索引（若已有则合并）
    index_file = output_path / "index.json"
    to_save = {k: dict(v) for k, v in result.items()}
    if merge_index and index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            existing = json.load(f)
        for repo, graph_types_dict in to_save.items():
            if repo not in existing:
                existing[repo] = {}
            for gt, months in graph_types_dict.items():
                existing[repo].setdefault(gt, {}).update(months)
        to_save = existing
        print(f"已合并到现有索引")
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)
    
    print(f"索引已保存: {index_file}")
    
    return dict(result)


def _process_single_repo(args_tuple):
    """处理单个项目（用于并行）"""
    repo_name, events, month, graph_types, output_path = args_tuple
    
    builder_map = {
        "actor-actor": build_actor_actor_graph,
        "actor-repo": build_actor_repo_graph,
        "actor-discussion": build_actor_discussion_graph,
    }
    
    safe_repo_name = repo_name.replace("/", "-")
    repo_dir = output_path / safe_repo_name
    
    results = []
    
    for graph_type in graph_types:
        builder = builder_map.get(graph_type)
        if not builder:
            continue
        
        type_dir = repo_dir / graph_type
        type_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            graph = builder(events, repo_name, month)
        except Exception as e:
            continue
        
        if graph.number_of_nodes() < 2:
            continue
        
        graph_file = type_dir / f"{month}.graphml"
        try:
            sanitize_graphml_attributes(graph)
            nx.write_graphml(graph, str(graph_file))
            results.append((repo_name, graph_type, month, str(graph_file)))
        except:
            continue

    
    return results


def build_monthly_graphs_parallel(
    data_dir: str = "data/filtered/",
    output_dir: str = "output/monthly-graphs/",
    graph_types: List[str] = None,
    workers: int = 4,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    merge_index: bool = True,
) -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    并行构建所有项目的月度图
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed
    
    if graph_types is None:
        graph_types = ["actor-actor", "actor-repo", "actor-discussion"]
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print("加载过滤后的数据...")
    daily_data = load_filtered_data(data_dir)
    
    print("按月和项目分组...")
    monthly_repo_data = group_by_month_and_repo(daily_data)
    
    # 按月份范围过滤
    if start_month or end_month:
        monthly_repo_data = _filter_months(monthly_repo_data, start_month, end_month)
        print(f"月份过滤: {start_month or '不限'} ~ {end_month or '不限'}，共 {len(monthly_repo_data)} 个月")
    
    # 准备所有任务
    tasks = []
    for month in sorted(monthly_repo_data.keys()):
        repos = monthly_repo_data[month]
        for repo_name, events in repos.items():
            if len(events) >= 3:
                tasks.append((repo_name, events, month, graph_types, output_path))
    
    total_tasks = len(tasks)
    print(f"共 {total_tasks} 个任务，使用 {workers} 个进程并行处理")
    
    result = defaultdict(lambda: defaultdict(dict))
    completed = 0
    graph_count = 0
    
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_process_single_repo, task): task for task in tasks}
        
        for future in as_completed(futures):
            completed += 1
            try:
                results = future.result()
                for repo_name, graph_type, month, path in results:
                    result[repo_name][graph_type][month] = path
                    graph_count += 1
            except Exception as e:
                pass
            
            if completed % 20 == 0 or completed == total_tasks:
                print(f"进度: {completed}/{total_tasks} ({completed*100//total_tasks}%), 已生成 {graph_count} 个图")
    
    print("")
    print("=" * 60)
    print("构建完成统计:")
    print(f"  成功构建: {graph_count} 个图")
    print(f"  涉及项目: {len(result)} 个")
    print("=" * 60)
    
    # 保存索引（若已有则合并）
    index_file = output_path / "index.json"
    to_save = {k: dict(v) for k, v in result.items()}
    if merge_index and index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            existing = json.load(f)
        for repo, graph_types_dict in to_save.items():
            if repo not in existing:
                existing[repo] = {}
            for gt, months in graph_types_dict.items():
                existing[repo].setdefault(gt, {}).update(months)
        to_save = existing
        print(f"已合并到现有索引")
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)
    
    print(f"索引已保存: {index_file}")
    
    return dict(result)


if __name__ == "__main__":
    import argparse
    import logging
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    parser = argparse.ArgumentParser(description="按月构建项目图（三类时序图）")
    parser.add_argument("--data-dir", type=str, default="data/filtered/", help="输入数据目录")
    parser.add_argument("--output-dir", type=str, default="output/monthly-graphs/", help="输出目录")
    parser.add_argument(
        "--graph-types",
        type=str,
        default="actor-actor,actor-repo,actor-discussion",
        help="要构建的图类型，逗号分隔（默认全部）"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="并行进程数（默认: 4）"
    )
    parser.add_argument(
        "--serial",
        action="store_true",
        help="使用串行模式（默认使用并行）"
    )
    parser.add_argument(
        "--start-month",
        type=str,
        default=None,
        help="只构建该月及之后的图 (YYYY-MM，如 2020-01)"
    )
    parser.add_argument(
        "--end-month",
        type=str,
        default=None,
        help="只构建该月及之前的图 (YYYY-MM，如 2020-12)"
    )
    parser.add_argument(
        "--no-merge-index",
        action="store_true",
        help="不合并到现有索引，直接覆盖（默认会合并）"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("开始构建月度时序图")
    print(f"数据目录: {args.data_dir}")
    print(f"输出目录: {args.output_dir}")
    print(f"图类型: {args.graph_types}")
    print(f"月份范围: {args.start_month or '不限'} ~ {args.end_month or '不限'}")
    print(f"模式: {'串行' if args.serial else f'并行 ({args.workers} 进程)'}")
    print("=" * 60)
    
    graph_types = [t.strip() for t in args.graph_types.split(",")]
    merge_index = not args.no_merge_index
    
    if args.serial:
        build_monthly_graphs(
            data_dir=args.data_dir,
            output_dir=args.output_dir,
            graph_types=graph_types,
            start_month=args.start_month,
            end_month=args.end_month,
            merge_index=merge_index,
        )
    else:
        build_monthly_graphs_parallel(
            data_dir=args.data_dir,
            output_dir=args.output_dir,
            graph_types=graph_types,
            workers=args.workers,
            start_month=args.start_month,
            end_month=args.end_month,
            merge_index=merge_index,
        )