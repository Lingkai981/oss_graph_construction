"""
投影图构建器

将原始事件数据投影为两类分析友好的图结构：
1. Actor-Repository 二分图：Actor 与 Repository 直接连边，Event 作为边属性
2. Actor-Actor 协作图：基于共同仓库贡献、Issue 回复、PR 审查等隐含关系

保留详细的节点和边属性，便于后续分析算法使用。
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from src.utils.logger import get_logger
from src.utils.date_utils import parse_timestamp

logger = get_logger()


# ==================== 数据结构定义 ====================

@dataclass
class ActorInfo:
    """Actor 节点信息"""
    actor_id: int
    login: str
    avatar_url: Optional[str] = None
    url: Optional[str] = None
    gravatar_id: Optional[str] = None
    # 统计属性
    total_events: int = 0
    event_types: Dict[str, int] = field(default_factory=dict)
    first_event_time: Optional[str] = None
    last_event_time: Optional[str] = None
    repos_contributed: Set[int] = field(default_factory=set)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_type": "Actor",
            "actor_id": self.actor_id,
            "login": self.login,
            "avatar_url": self.avatar_url,
            "url": self.url,
            "gravatar_id": self.gravatar_id,
            "total_events": self.total_events,
            "event_types": dict(self.event_types),
            "first_event_time": self.first_event_time,
            "last_event_time": self.last_event_time,
            "repos_count": len(self.repos_contributed),
        }


@dataclass
class RepoInfo:
    """Repository 节点信息"""
    repo_id: int
    name: str
    url: Optional[str] = None
    # 统计属性
    total_events: int = 0
    event_types: Dict[str, int] = field(default_factory=dict)
    contributors: Set[int] = field(default_factory=set)
    first_event_time: Optional[str] = None
    last_event_time: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_type": "Repository",
            "repo_id": self.repo_id,
            "name": self.name,
            "url": self.url,
            "total_events": self.total_events,
            "event_types": dict(self.event_types),
            "contributors_count": len(self.contributors),
            "first_event_time": self.first_event_time,
            "last_event_time": self.last_event_time,
        }


@dataclass
class ActorRepoEdge:
    """Actor-Repository 边信息"""
    actor_id: int
    repo_id: int
    # 详细的事件统计
    event_count: int = 0
    event_types: Dict[str, int] = field(default_factory=dict)
    event_ids: List[str] = field(default_factory=list)
    first_event_time: Optional[str] = None
    last_event_time: Optional[str] = None
    # 提交统计（仅 PushEvent）
    commit_count: int = 0
    commit_shas: List[str] = field(default_factory=list)
    # PR 统计
    pr_opened: int = 0
    pr_closed: int = 0
    pr_merged: int = 0
    # Issue 统计
    issue_opened: int = 0
    issue_closed: int = 0
    issue_comments: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_type": "CONTRIBUTED_TO",
            "event_count": self.event_count,
            "event_types": dict(self.event_types),
            "event_ids": self.event_ids[:100],  # 限制存储的事件 ID 数量
            "first_event_time": self.first_event_time,
            "last_event_time": self.last_event_time,
            "commit_count": self.commit_count,
            "pr_opened": self.pr_opened,
            "pr_closed": self.pr_closed,
            "pr_merged": self.pr_merged,
            "issue_opened": self.issue_opened,
            "issue_closed": self.issue_closed,
            "issue_comments": self.issue_comments,
        }


@dataclass
class ActorActorEdge:
    """Actor-Actor 边信息（协作关系）"""
    actor1_id: int
    actor2_id: int
    # 关系类型统计
    shared_repos: Set[int] = field(default_factory=set)  # 共同贡献的仓库
    issue_replies: int = 0  # actor1 回复了 actor2 的 Issue
    pr_reviews: int = 0  # actor1 审查了 actor2 的 PR
    pr_merges: int = 0  # actor1 合并了 actor2 的 PR
    # 详细记录
    interactions: List[Dict[str, Any]] = field(default_factory=list)
    first_interaction_time: Optional[str] = None
    last_interaction_time: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        # 计算关系强度
        relationship_strength = (
            len(self.shared_repos) * 1.0 +
            self.issue_replies * 2.0 +
            self.pr_reviews * 3.0 +
            self.pr_merges * 4.0
        )
        
        return {
            "edge_type": "COLLABORATED_WITH",
            "shared_repos_count": len(self.shared_repos),
            "shared_repos": list(self.shared_repos)[:50],  # 限制数量
            "issue_replies": self.issue_replies,
            "pr_reviews": self.pr_reviews,
            "pr_merges": self.pr_merges,
            "relationship_strength": relationship_strength,
            "interaction_count": len(self.interactions),
            "interactions": self.interactions[:50],  # 限制存储的交互记录
            "first_interaction_time": self.first_interaction_time,
            "last_interaction_time": self.last_interaction_time,
        }


# ==================== 事件解析辅助函数 ====================

def _extract_issue_author(event: Dict[str, Any]) -> Optional[int]:
    """从 IssueCommentEvent 或 IssuesEvent 中提取 Issue 作者 ID"""
    payload = event.get("payload") or {}
    issue = payload.get("issue") or {}
    user = issue.get("user") or {}
    return user.get("id")


def _extract_pr_author(event: Dict[str, Any]) -> Optional[int]:
    """从 PullRequestEvent 或 PullRequestReviewCommentEvent 中提取 PR 作者 ID"""
    payload = event.get("payload") or {}
    pr = payload.get("pull_request") or {}
    user = pr.get("user") or {}
    return user.get("id")


def _extract_pr_merger(event: Dict[str, Any]) -> Optional[int]:
    """从 PullRequestEvent 中提取合并者 ID（如果是合并操作）"""
    payload = event.get("payload") or {}
    action = payload.get("action")
    pr = payload.get("pull_request") or {}
    
    if action == "closed" and pr.get("merged"):
        merged_by = pr.get("merged_by") or {}
        return merged_by.get("id")
    return None


def _update_time_range(
    current_first: Optional[str],
    current_last: Optional[str],
    new_time: str
) -> Tuple[Optional[str], Optional[str]]:
    """更新时间范围"""
    if current_first is None or new_time < current_first:
        current_first = new_time
    if current_last is None or new_time > current_last:
        current_last = new_time
    return current_first, current_last


# ==================== 投影图构建函数 ====================

def build_actor_repo_graph(
    events: List[Dict[str, Any]],
    include_watch_events: bool = False,
    include_fork_events: bool = True,
) -> nx.DiGraph:
    """
    构建 Actor-Repository 二分投影图。
    
    将原始事件投影为 Actor → Repository 的直接边，
    边上聚合了所有相关事件的统计信息。
    
    Args:
        events: 事件列表
        include_watch_events: 是否包含 WatchEvent（Star 行为，非实质贡献）
        include_fork_events: 是否包含 ForkEvent
    
    Returns:
        NetworkX 有向图，节点类型为 Actor 和 Repository
    """
    logger.info("开始构建 Actor-Repository 投影图...")
    
    # 收集节点和边信息
    actors: Dict[int, ActorInfo] = {}
    repos: Dict[int, RepoInfo] = {}
    edges: Dict[Tuple[int, int], ActorRepoEdge] = {}
    
    # 需要排除的事件类型
    excluded_types = set()
    if not include_watch_events:
        excluded_types.add("WatchEvent")
    if not include_fork_events:
        excluded_types.add("ForkEvent")
    
    for ev in events:
        event_id = ev.get("id")
        event_type = ev.get("type") or ""
        created_at = ev.get("created_at") or ""
        
        if not event_id or not created_at:
            continue
        
        if event_type in excluded_types:
            continue
        
        actor = ev.get("actor") or {}
        actor_id = actor.get("id")
        repo = ev.get("repo") or {}
        repo_id = repo.get("id")
        
        if actor_id is None or repo_id is None:
            continue
        
        # 更新 Actor 信息
        if actor_id not in actors:
            actors[actor_id] = ActorInfo(
                actor_id=actor_id,
                login=actor.get("login") or "",
                avatar_url=actor.get("avatar_url"),
                url=actor.get("url"),
                gravatar_id=actor.get("gravatar_id"),
            )
        actor_info = actors[actor_id]
        actor_info.total_events += 1
        actor_info.event_types[event_type] = actor_info.event_types.get(event_type, 0) + 1
        actor_info.repos_contributed.add(repo_id)
        actor_info.first_event_time, actor_info.last_event_time = _update_time_range(
            actor_info.first_event_time, actor_info.last_event_time, created_at
        )
        
        # 更新 Repository 信息
        if repo_id not in repos:
            repos[repo_id] = RepoInfo(
                repo_id=repo_id,
                name=repo.get("name") or "",
                url=repo.get("url"),
            )
        repo_info = repos[repo_id]
        repo_info.total_events += 1
        repo_info.event_types[event_type] = repo_info.event_types.get(event_type, 0) + 1
        repo_info.contributors.add(actor_id)
        repo_info.first_event_time, repo_info.last_event_time = _update_time_range(
            repo_info.first_event_time, repo_info.last_event_time, created_at
        )
        
        # 更新边信息
        edge_key = (actor_id, repo_id)
        if edge_key not in edges:
            edges[edge_key] = ActorRepoEdge(actor_id=actor_id, repo_id=repo_id)
        edge_info = edges[edge_key]
        edge_info.event_count += 1
        edge_info.event_types[event_type] = edge_info.event_types.get(event_type, 0) + 1
        edge_info.event_ids.append(event_id)
        edge_info.first_event_time, edge_info.last_event_time = _update_time_range(
            edge_info.first_event_time, edge_info.last_event_time, created_at
        )
        
        # 事件类型特定的统计
        payload = ev.get("payload") or {}
        
        if event_type == "PushEvent":
            commits = payload.get("commits") or []
            edge_info.commit_count += len(commits)
            for commit in commits:
                sha = commit.get("sha")
                if sha:
                    edge_info.commit_shas.append(sha)
        
        elif event_type == "PullRequestEvent":
            action = payload.get("action")
            pr = payload.get("pull_request") or {}
            if action == "opened":
                edge_info.pr_opened += 1
            elif action == "closed":
                edge_info.pr_closed += 1
                if pr.get("merged"):
                    edge_info.pr_merged += 1
        
        elif event_type == "IssuesEvent":
            action = payload.get("action")
            if action == "opened":
                edge_info.issue_opened += 1
            elif action == "closed":
                edge_info.issue_closed += 1
        
        elif event_type == "IssueCommentEvent":
            edge_info.issue_comments += 1
    
    # 构建 NetworkX 图
    graph = nx.DiGraph()
    
    # 添加 Actor 节点
    for actor_id, actor_info in actors.items():
        node_id = f"actor:{actor_id}"
        graph.add_node(node_id, **actor_info.to_dict())
    
    # 添加 Repository 节点
    for repo_id, repo_info in repos.items():
        node_id = f"repo:{repo_id}"
        graph.add_node(node_id, **repo_info.to_dict())
    
    # 添加边
    for (actor_id, repo_id), edge_info in edges.items():
        source = f"actor:{actor_id}"
        target = f"repo:{repo_id}"
        graph.add_edge(source, target, **edge_info.to_dict())
    
    logger.info(
        f"Actor-Repository 投影图构建完成: "
        f"Actor 数={len(actors)}, Repository 数={len(repos)}, 边数={len(edges)}"
    )
    
    return graph


def build_actor_actor_graph(
    events: List[Dict[str, Any]],
    include_shared_repo_edges: bool = True,
    min_shared_repos: int = 1,
) -> nx.MultiDiGraph:
    """
    构建 Actor-Actor 协作投影图（多重有向图）。
    
    从事件中提取人与人之间的隐含关系，每个交互操作都是独立的边：
    1. 共同仓库贡献：两个 Actor 都对同一 Repository 有贡献（聚合边）
    2. Issue 回复：Actor A 回复了 Actor B 创建的 Issue（独立边）
    3. PR 审查：Actor A 审查/评论了 Actor B 的 PR（独立边）
    4. PR 合并：Actor A 合并了 Actor B 的 PR（独立边）
    
    Args:
        events: 事件列表
        include_shared_repo_edges: 是否包含基于共同仓库的协作边
        min_shared_repos: 至少共同贡献多少个仓库才建立边
    
    Returns:
        NetworkX 多重有向图，节点类型为 Actor，每个交互是独立的边
    """
    logger.info("开始构建 Actor-Actor 协作图（多重边模式）...")
    
    # 收集信息
    actors: Dict[int, ActorInfo] = {}
    repo_contributors: Dict[int, Set[int]] = defaultdict(set)  # repo_id -> set of actor_ids
    # 独立边列表：每个交互操作一条边
    interaction_edges: List[Dict[str, Any]] = []
    # 共同仓库关系（仍然聚合）
    shared_repo_pairs: Dict[Tuple[int, int], Set[int]] = defaultdict(set)
    
    def _get_pair_key(a1: int, a2: int) -> Tuple[int, int]:
        """确保配对的键是有序的"""
        return (min(a1, a2), max(a1, a2))
    
    def _ensure_actor(actor_data: Dict[str, Any]) -> Optional[ActorInfo]:
        """获取或创建 Actor"""
        actor_id = actor_data.get("id")
        if actor_id is None:
            return None
        if actor_id not in actors:
            actors[actor_id] = ActorInfo(
                actor_id=actor_id,
                login=actor_data.get("login") or "",
                avatar_url=actor_data.get("avatar_url"),
                url=actor_data.get("url"),
                gravatar_id=actor_data.get("gravatar_id"),
            )
        return actors[actor_id]
    
    # 遍历事件，收集所有 Actor 和交互关系
    for ev in events:
        event_id = ev.get("id")
        event_type = ev.get("type") or ""
        created_at = ev.get("created_at") or ""
        
        actor = ev.get("actor") or {}
        actor_id = actor.get("id")
        repo = ev.get("repo") or {}
        repo_id = repo.get("id")
        repo_name = repo.get("name") or ""
        
        if actor_id is None:
            continue
        
        actor_info = _ensure_actor(actor)
        if actor_info:
            actor_info.total_events += 1
            actor_info.event_types[event_type] = actor_info.event_types.get(event_type, 0) + 1
            if repo_id is not None:
                actor_info.repos_contributed.add(repo_id)
            actor_info.first_event_time, actor_info.last_event_time = _update_time_range(
                actor_info.first_event_time, actor_info.last_event_time, created_at
            )
        
        if repo_id is not None:
            repo_contributors[repo_id].add(actor_id)
        
        # 提取隐含的人与人关系 - 每个交互创建独立的边
        payload = ev.get("payload") or {}
        
        # IssueCommentEvent: 评论者 -> Issue 作者
        if event_type == "IssueCommentEvent":
            issue_author_id = _extract_issue_author(ev)
            if issue_author_id is not None and issue_author_id != actor_id:
                # 确保 Issue 作者也被记录
                issue = payload.get("issue") or {}
                issue_user = issue.get("user") or {}
                target_actor = _ensure_actor(issue_user)
                target_login = target_actor.login if target_actor else issue_user.get("login", "")
                
                # 提取更多上下文信息
                issue_title = issue.get("title") or ""
                issue_number = issue.get("number")
                comment = payload.get("comment") or {}
                comment_body = comment.get("body") or ""
                
                interaction_edges.append({
                    "edge_type": "ISSUE_REPLY",
                    "source_actor_id": actor_id,
                    "source_login": actor_info.login if actor_info else "",
                    "target_actor_id": issue_author_id,
                    "target_login": target_login,
                    "event_id": event_id,
                    "created_at": created_at,
                    "repo_id": repo_id,
                    "repo_name": repo_name,
                    "issue_number": issue_number,
                    "issue_title": issue_title,
                    "comment_body": comment_body[:500] if comment_body else "",  # 截断
                })
        
        # PullRequestReviewCommentEvent: 审查者 -> PR 作者
        elif event_type == "PullRequestReviewCommentEvent":
            pr_author_id = _extract_pr_author(ev)
            if pr_author_id is not None and pr_author_id != actor_id:
                # 确保 PR 作者也被记录
                pr = payload.get("pull_request") or {}
                pr_user = pr.get("user") or {}
                target_actor = _ensure_actor(pr_user)
                target_login = target_actor.login if target_actor else pr_user.get("login", "")
                
                # 提取更多上下文信息
                pr_title = pr.get("title") or ""
                pr_number = pr.get("number")
                comment = payload.get("comment") or {}
                comment_body = comment.get("body") or ""
                
                interaction_edges.append({
                    "edge_type": "PR_REVIEW_COMMENT",
                    "source_actor_id": actor_id,
                    "source_login": actor_info.login if actor_info else "",
                    "target_actor_id": pr_author_id,
                    "target_login": target_login,
                    "event_id": event_id,
                    "created_at": created_at,
                    "repo_id": repo_id,
                    "repo_name": repo_name,
                    "pr_number": pr_number,
                    "pr_title": pr_title,
                    "comment_body": comment_body[:500] if comment_body else "",
                })
        
        # PullRequestEvent (closed + merged): 合并者 -> PR 作者
        elif event_type == "PullRequestEvent":
            action = payload.get("action")
            pr = payload.get("pull_request") or {}
            
            if action == "closed" and pr.get("merged"):
                pr_author_id = _extract_pr_author(ev)
                if pr_author_id is not None and pr_author_id != actor_id:
                    pr_user = pr.get("user") or {}
                    target_actor = _ensure_actor(pr_user)
                    target_login = target_actor.login if target_actor else pr_user.get("login", "")
                    
                    pr_title = pr.get("title") or ""
                    pr_number = pr.get("number")
                    
                    interaction_edges.append({
                        "edge_type": "PR_MERGE",
                        "source_actor_id": actor_id,
                        "source_login": actor_info.login if actor_info else "",
                        "target_actor_id": pr_author_id,
                        "target_login": target_login,
                        "event_id": event_id,
                        "created_at": created_at,
                        "repo_id": repo_id,
                        "repo_name": repo_name,
                        "pr_number": pr_number,
                        "pr_title": pr_title,
                    })
    
    # 基于共同仓库贡献建立协作边
    if include_shared_repo_edges:
        for repo_id, contributor_set in repo_contributors.items():
            contributors = list(contributor_set)
            for i in range(len(contributors)):
                for j in range(i + 1, len(contributors)):
                    a1, a2 = contributors[i], contributors[j]
                    key = _get_pair_key(a1, a2)
                    shared_repo_pairs[key].add(repo_id)
    
    # 构建 NetworkX 多重有向图
    graph = nx.MultiDiGraph()
    
    # 收集所有需要添加的 Actor
    connected_actors = set()
    for edge in interaction_edges:
        connected_actors.add(edge["source_actor_id"])
        connected_actors.add(edge["target_actor_id"])
    
    # 添加共同仓库关系的 Actor（如果达到阈值）
    if include_shared_repo_edges:
        for (a1, a2), repos in shared_repo_pairs.items():
            if len(repos) >= min_shared_repos:
        connected_actors.add(a1)
        connected_actors.add(a2)
    
    # 添加节点
    for actor_id in connected_actors:
        if actor_id in actors:
            node_id = f"actor:{actor_id}"
            graph.add_node(node_id, **actors[actor_id].to_dict())
    
    # 添加独立的交互边（每个交互一条边，使用 event_id 作为 key 确保唯一）
    for edge_data in interaction_edges:
        source = f"actor:{edge_data['source_actor_id']}"
        target = f"actor:{edge_data['target_actor_id']}"
        event_id = edge_data["event_id"]
        
        # 使用 event_id 作为边的 key，确保唯一性
        edge_key = f"{edge_data['edge_type']}_{event_id}"
        
        # 构建边属性
        edge_attrs = {
            "edge_type": edge_data["edge_type"],
            "event_id": event_id,
            "created_at": edge_data["created_at"],
            "repo_id": edge_data["repo_id"],
            "repo_name": edge_data["repo_name"],
            "source_login": edge_data["source_login"],
            "target_login": edge_data["target_login"],
        }
        
        # 添加类型特定的属性
        if edge_data["edge_type"] == "ISSUE_REPLY":
            edge_attrs["issue_number"] = edge_data.get("issue_number")
            edge_attrs["issue_title"] = edge_data.get("issue_title", "")
            edge_attrs["comment_body"] = edge_data.get("comment_body", "")
        elif edge_data["edge_type"] == "PR_REVIEW_COMMENT":
            edge_attrs["pr_number"] = edge_data.get("pr_number")
            edge_attrs["pr_title"] = edge_data.get("pr_title", "")
            edge_attrs["comment_body"] = edge_data.get("comment_body", "")
        elif edge_data["edge_type"] == "PR_MERGE":
            edge_attrs["pr_number"] = edge_data.get("pr_number")
            edge_attrs["pr_title"] = edge_data.get("pr_title", "")
        
        graph.add_edge(source, target, key=edge_key, **edge_attrs)
    
    # 添加共同仓库协作边（聚合边，无向关系用双向边表示）
    if include_shared_repo_edges:
        for (a1, a2), repos in shared_repo_pairs.items():
            if len(repos) >= min_shared_repos:
        source = f"actor:{a1}"
        target = f"actor:{a2}"
                edge_attrs = {
                    "edge_type": "SHARED_REPO",
                    "shared_repos_count": len(repos),
                    "shared_repos": list(repos)[:50],
                    "created_at": None,  # 聚合边没有单一时间
                }
                # 使用唯一的 key，包含双方 actor id
                edge_key_forward = f"SHARED_REPO_{a1}_{a2}"
                edge_key_backward = f"SHARED_REPO_{a2}_{a1}"
                # 添加双向边表示无向关系
                graph.add_edge(source, target, key=edge_key_forward, **edge_attrs)
                graph.add_edge(target, source, key=edge_key_backward, **edge_attrs)
    
    # 统计信息
    direct_interaction_count = len(interaction_edges)
    shared_repo_edge_count = sum(1 for repos in shared_repo_pairs.values() if len(repos) >= min_shared_repos) * 2
    
    logger.info(
        f"Actor-Actor 协作图构建完成: "
        f"Actor 数={graph.number_of_nodes()}, "
        f"总边数={graph.number_of_edges()} "
        f"(直接交互={direct_interaction_count}, 共同仓库={shared_repo_edge_count})"
    )
    
    return graph


def build_actor_discussion_graph(
    events: List[Dict[str, Any]],
) -> nx.MultiDiGraph:
    """
    构建 Actor-Discussion 二部图（Issue/PR 讨论图）。
    
    节点类型：
    - Actor：参与讨论的用户
    - Issue：Issue 讨论主题
    - PullRequest：PR 讨论主题
    
    边类型：
    - CREATED_ISSUE：Actor 创建了 Issue
    - COMMENTED_ISSUE：Actor 评论了 Issue
    - CREATED_PR：Actor 创建了 PR
    - REVIEWED_PR：Actor 审查/评论了 PR
    - MERGED_PR：Actor 合并了 PR
    
    每条边都是独立的，包含完整的时间戳和上下文信息。
    
    Args:
        events: 事件列表
    
    Returns:
        NetworkX 多重有向图
    """
    logger.info("开始构建 Actor-Discussion 二部图...")
    
    # 收集节点信息
    actors: Dict[int, ActorInfo] = {}
    issues: Dict[str, Dict[str, Any]] = {}  # issue_key -> issue_info
    pull_requests: Dict[str, Dict[str, Any]] = {}  # pr_key -> pr_info
    
    # 收集边信息（每个交互独立）
    edges: List[Dict[str, Any]] = []
    
    def _ensure_actor(actor_data: Dict[str, Any]) -> Optional[ActorInfo]:
        """获取或创建 Actor"""
        actor_id = actor_data.get("id")
        if actor_id is None:
            return None
        if actor_id not in actors:
            actors[actor_id] = ActorInfo(
                actor_id=actor_id,
                login=actor_data.get("login") or "",
                avatar_url=actor_data.get("avatar_url"),
                url=actor_data.get("url"),
                gravatar_id=actor_data.get("gravatar_id"),
            )
        return actors[actor_id]
    
    def _get_issue_key(repo_id: int, issue_number: int) -> str:
        return f"issue:{repo_id}:{issue_number}"
    
    def _get_pr_key(repo_id: int, pr_number: int) -> str:
        return f"pr:{repo_id}:{pr_number}"
    
    # 遍历事件
    for ev in events:
        event_id = ev.get("id")
        event_type = ev.get("type") or ""
        created_at = ev.get("created_at") or ""
        
        actor = ev.get("actor") or {}
        actor_id = actor.get("id")
        repo = ev.get("repo") or {}
        repo_id = repo.get("id")
        repo_name = repo.get("name") or ""
        
        if actor_id is None or repo_id is None:
            continue
        
        actor_info = _ensure_actor(actor)
        if actor_info:
            actor_info.total_events += 1
            actor_info.event_types[event_type] = actor_info.event_types.get(event_type, 0) + 1
            actor_info.first_event_time, actor_info.last_event_time = _update_time_range(
                actor_info.first_event_time, actor_info.last_event_time, created_at
            )
        
        payload = ev.get("payload") or {}
        
        # IssuesEvent: 创建 Issue
        if event_type == "IssuesEvent":
            action = payload.get("action")
            issue = payload.get("issue") or {}
            issue_number = issue.get("number")
            
            if issue_number is not None:
                issue_key = _get_issue_key(repo_id, issue_number)
                
                # 记录 Issue 节点信息
                if issue_key not in issues:
                    issues[issue_key] = {
                        "node_type": "Issue",
                        "issue_key": issue_key,
                        "repo_id": repo_id,
                        "repo_name": repo_name,
                        "issue_number": issue_number,
                        "title": issue.get("title") or "",
                        "state": issue.get("state") or "",
                        "labels": [l.get("name") for l in (issue.get("labels") or [])],
                        "creator_id": (issue.get("user") or {}).get("id"),
                        "creator_login": (issue.get("user") or {}).get("login") or "",
                        "created_at": issue.get("created_at"),
                        "comments_count": 0,
                        "participants": set(),
                    }
                
                issues[issue_key]["participants"].add(actor_id)
                
                if action == "opened":
                    edges.append({
                        "edge_type": "CREATED_ISSUE",
                        "source_actor_id": actor_id,
                        "source_login": actor_info.login if actor_info else "",
                        "target_key": issue_key,
                        "target_type": "Issue",
                        "event_id": event_id,
                        "created_at": created_at,
                        "repo_id": repo_id,
                        "repo_name": repo_name,
                        "issue_number": issue_number,
                        "title": issue.get("title") or "",
                    })
                elif action == "closed":
                    edges.append({
                        "edge_type": "CLOSED_ISSUE",
                        "source_actor_id": actor_id,
                        "source_login": actor_info.login if actor_info else "",
                        "target_key": issue_key,
                        "target_type": "Issue",
                        "event_id": event_id,
                        "created_at": created_at,
                        "repo_id": repo_id,
                        "repo_name": repo_name,
                        "issue_number": issue_number,
                        "title": issue.get("title") or "",
                    })
        
        # IssueCommentEvent: 评论 Issue
        elif event_type == "IssueCommentEvent":
            issue = payload.get("issue") or {}
            issue_number = issue.get("number")
            comment = payload.get("comment") or {}
            
            if issue_number is not None:
                issue_key = _get_issue_key(repo_id, issue_number)
                
                # 确保 Issue 节点存在
                if issue_key not in issues:
                    issues[issue_key] = {
                        "node_type": "Issue",
                        "issue_key": issue_key,
                        "repo_id": repo_id,
                        "repo_name": repo_name,
                        "issue_number": issue_number,
                        "title": issue.get("title") or "",
                        "state": issue.get("state") or "",
                        "labels": [l.get("name") for l in (issue.get("labels") or [])],
                        "creator_id": (issue.get("user") or {}).get("id"),
                        "creator_login": (issue.get("user") or {}).get("login") or "",
                        "created_at": issue.get("created_at"),
                        "comments_count": 0,
                        "participants": set(),
                    }
                
                issues[issue_key]["comments_count"] += 1
                issues[issue_key]["participants"].add(actor_id)
                
                # 确保 Issue 创建者也被记录为 Actor
                issue_creator = issue.get("user") or {}
                if issue_creator.get("id"):
                    _ensure_actor(issue_creator)
                
                edges.append({
                    "edge_type": "COMMENTED_ISSUE",
                    "source_actor_id": actor_id,
                    "source_login": actor_info.login if actor_info else "",
                    "target_key": issue_key,
                    "target_type": "Issue",
                    "event_id": event_id,
                    "created_at": created_at,
                    "repo_id": repo_id,
                    "repo_name": repo_name,
                    "issue_number": issue_number,
                    "title": issue.get("title") or "",
                    "comment_body": (comment.get("body") or "")[:500],
                    "comment_id": comment.get("id"),
                })
        
        # PullRequestEvent: 创建/合并 PR
        elif event_type == "PullRequestEvent":
            action = payload.get("action")
            pr = payload.get("pull_request") or {}
            pr_number = pr.get("number")
            
            if pr_number is not None:
                pr_key = _get_pr_key(repo_id, pr_number)
                
                # 记录 PR 节点信息
                if pr_key not in pull_requests:
                    pull_requests[pr_key] = {
                        "node_type": "PullRequest",
                        "pr_key": pr_key,
                        "repo_id": repo_id,
                        "repo_name": repo_name,
                        "pr_number": pr_number,
                        "title": pr.get("title") or "",
                        "state": pr.get("state") or "",
                        "merged": pr.get("merged") or False,
                        "creator_id": (pr.get("user") or {}).get("id"),
                        "creator_login": (pr.get("user") or {}).get("login") or "",
                        "created_at": pr.get("created_at"),
                        "additions": pr.get("additions") or 0,
                        "deletions": pr.get("deletions") or 0,
                        "changed_files": pr.get("changed_files") or 0,
                        "comments_count": 0,
                        "participants": set(),
                    }
                
                pull_requests[pr_key]["participants"].add(actor_id)
                
                # 确保 PR 创建者也被记录为 Actor
                pr_creator = pr.get("user") or {}
                if pr_creator.get("id"):
                    _ensure_actor(pr_creator)
                
                if action == "opened":
                    edges.append({
                        "edge_type": "CREATED_PR",
                        "source_actor_id": actor_id,
                        "source_login": actor_info.login if actor_info else "",
                        "target_key": pr_key,
                        "target_type": "PullRequest",
                        "event_id": event_id,
                        "created_at": created_at,
                        "repo_id": repo_id,
                        "repo_name": repo_name,
                        "pr_number": pr_number,
                        "title": pr.get("title") or "",
                        "additions": pr.get("additions") or 0,
                        "deletions": pr.get("deletions") or 0,
                    })
                elif action == "closed":
                    if pr.get("merged"):
                        edges.append({
                            "edge_type": "MERGED_PR",
                            "source_actor_id": actor_id,
                            "source_login": actor_info.login if actor_info else "",
                            "target_key": pr_key,
                            "target_type": "PullRequest",
                            "event_id": event_id,
                            "created_at": created_at,
                            "repo_id": repo_id,
                            "repo_name": repo_name,
                            "pr_number": pr_number,
                            "title": pr.get("title") or "",
                        })
                        pull_requests[pr_key]["merged"] = True
                    else:
                        edges.append({
                            "edge_type": "CLOSED_PR",
                            "source_actor_id": actor_id,
                            "source_login": actor_info.login if actor_info else "",
                            "target_key": pr_key,
                            "target_type": "PullRequest",
                            "event_id": event_id,
                            "created_at": created_at,
                            "repo_id": repo_id,
                            "repo_name": repo_name,
                            "pr_number": pr_number,
                            "title": pr.get("title") or "",
                        })
        
        # PullRequestReviewCommentEvent: 审查 PR
        elif event_type == "PullRequestReviewCommentEvent":
            pr = payload.get("pull_request") or {}
            pr_number = pr.get("number")
            comment = payload.get("comment") or {}
            
            if pr_number is not None:
                pr_key = _get_pr_key(repo_id, pr_number)
                
                # 确保 PR 节点存在
                if pr_key not in pull_requests:
                    pull_requests[pr_key] = {
                        "node_type": "PullRequest",
                        "pr_key": pr_key,
                        "repo_id": repo_id,
                        "repo_name": repo_name,
                        "pr_number": pr_number,
                        "title": pr.get("title") or "",
                        "state": pr.get("state") or "",
                        "merged": pr.get("merged") or False,
                        "creator_id": (pr.get("user") or {}).get("id"),
                        "creator_login": (pr.get("user") or {}).get("login") or "",
                        "created_at": pr.get("created_at"),
                        "additions": pr.get("additions") or 0,
                        "deletions": pr.get("deletions") or 0,
                        "changed_files": pr.get("changed_files") or 0,
                        "comments_count": 0,
                        "participants": set(),
                    }
                
                pull_requests[pr_key]["comments_count"] += 1
                pull_requests[pr_key]["participants"].add(actor_id)
                
                # 确保 PR 创建者也被记录为 Actor
                pr_creator = pr.get("user") or {}
                if pr_creator.get("id"):
                    _ensure_actor(pr_creator)
                
                edges.append({
                    "edge_type": "REVIEWED_PR",
                    "source_actor_id": actor_id,
                    "source_login": actor_info.login if actor_info else "",
                    "target_key": pr_key,
                    "target_type": "PullRequest",
                    "event_id": event_id,
                    "created_at": created_at,
                    "repo_id": repo_id,
                    "repo_name": repo_name,
                    "pr_number": pr_number,
                    "title": pr.get("title") or "",
                    "comment_body": (comment.get("body") or "")[:500],
                    "comment_id": comment.get("id"),
                    "path": comment.get("path"),  # 代码文件路径
                    "line": comment.get("line"),  # 代码行号
                })
    
    # 构建 NetworkX 多重有向图
    graph = nx.MultiDiGraph()
    
    # 添加 Actor 节点
    for actor_id, actor_info in actors.items():
        node_id = f"actor:{actor_id}"
        graph.add_node(node_id, **actor_info.to_dict())
    
    # 添加 Issue 节点
    for issue_key, issue_info in issues.items():
        node_attrs = {k: v for k, v in issue_info.items()}
        # 将 set 转为 list（JSON 序列化需要）
        node_attrs["participants"] = list(node_attrs["participants"])
        node_attrs["participants_count"] = len(node_attrs["participants"])
        graph.add_node(issue_key, **node_attrs)
    
    # 添加 PullRequest 节点
    for pr_key, pr_info in pull_requests.items():
        node_attrs = {k: v for k, v in pr_info.items()}
        node_attrs["participants"] = list(node_attrs["participants"])
        node_attrs["participants_count"] = len(node_attrs["participants"])
        graph.add_node(pr_key, **node_attrs)
    
    # 添加边
    for edge_data in edges:
        source = f"actor:{edge_data['source_actor_id']}"
        target = edge_data["target_key"]
        event_id = edge_data["event_id"]
        edge_type = edge_data["edge_type"]
        
        # 使用 event_id 作为边的 key，确保唯一性
        edge_key = f"{edge_type}_{event_id}"
        
        # 构建边属性
        edge_attrs = {
            "edge_type": edge_type,
            "event_id": event_id,
            "created_at": edge_data["created_at"],
            "repo_id": edge_data["repo_id"],
            "repo_name": edge_data["repo_name"],
            "source_login": edge_data["source_login"],
        }
        
        # 添加类型特定的属性
        if "issue_number" in edge_data:
            edge_attrs["issue_number"] = edge_data["issue_number"]
        if "pr_number" in edge_data:
            edge_attrs["pr_number"] = edge_data["pr_number"]
        if "title" in edge_data:
            edge_attrs["title"] = edge_data["title"]
        if "comment_body" in edge_data:
            edge_attrs["comment_body"] = edge_data["comment_body"]
        if "comment_id" in edge_data:
            edge_attrs["comment_id"] = edge_data["comment_id"]
        if "path" in edge_data:
            edge_attrs["path"] = edge_data["path"]
        if "line" in edge_data:
            edge_attrs["line"] = edge_data["line"]
        if "additions" in edge_data:
            edge_attrs["additions"] = edge_data["additions"]
        if "deletions" in edge_data:
            edge_attrs["deletions"] = edge_data["deletions"]
        
        graph.add_edge(source, target, key=edge_key, **edge_attrs)
    
    # 统计信息
    actor_count = len(actors)
    issue_count = len(issues)
    pr_count = len(pull_requests)
    edge_count = len(edges)
    
    logger.info(
        f"Actor-Discussion 二部图构建完成: "
        f"Actor 数={actor_count}, Issue 数={issue_count}, PR 数={pr_count}, "
        f"总节点数={graph.number_of_nodes()}, 总边数={edge_count}"
    )
    
    return graph


def build_all_projection_graphs(
    events: List[Dict[str, Any]],
    include_watch_events: bool = False,
    include_fork_events: bool = True,
    include_shared_repo_edges: bool = True,
    min_shared_repos: int = 1,
) -> Dict[str, nx.Graph]:
    """
    构建所有投影图。
    
    Args:
        events: 事件列表
        include_watch_events: Actor-Repo 图是否包含 WatchEvent
        include_fork_events: Actor-Repo 图是否包含 ForkEvent
        include_shared_repo_edges: Actor-Actor 图是否包含共同仓库边
        min_shared_repos: Actor-Actor 图中共同仓库边的最小仓库数
    
    Returns:
        字典，包含 "actor_repo" 和 "actor_actor" 两个图
    """
    return {
        "actor_repo": build_actor_repo_graph(
            events,
            include_watch_events=include_watch_events,
            include_fork_events=include_fork_events,
        ),
        "actor_actor": build_actor_actor_graph(
            events,
            include_shared_repo_edges=include_shared_repo_edges,
            min_shared_repos=min_shared_repos,
        ),
    }
