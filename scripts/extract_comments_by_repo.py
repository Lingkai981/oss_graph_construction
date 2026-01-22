#!/usr/bin/env python3
"""
从数据文件直接提取 GitHub Issue 评论和 PR Review 评论内容（无需 API 调用）

功能：
- 遍历过滤后的事件数据
- 按仓库（repo）分组，逐个仓库提取
- 直接从 payload.comment.body 提取评论内容
- 无需调用 GitHub API，避免速率限制
- 每个仓库的评论保存到单独的 JSON 文件（{url: body} 映射）

使用：
    python scripts/extract_comments_by_repo.py --data-dir data/filtered/ --output-dir data/comments_by_repo/
"""

import json
import argparse
from pathlib import Path
from typing import Dict, Set
from collections import defaultdict
from tqdm import tqdm
import re


class CommentExtractor:
    """GitHub 评论提取器（从数据文件直接提取，无需 API）"""
    
    def __init__(self):
        """初始化提取器"""
        pass
    
    @staticmethod
    def _repo_name_to_filename(repo_name: str) -> str:
        """
        将仓库名称转换为安全的文件名
        
        Args:
            repo_name: 仓库名称，如 "denoland/deno"
        
        Returns:
            安全的文件名，如 "denoland-deno.json"
        """
        # 将 / 替换为 -，移除其他特殊字符
        safe_name = repo_name.replace("/", "-")
        # 移除其他可能不安全的字符
        safe_name = re.sub(r'[<>:"|?*]', '_', safe_name)
        return f"{safe_name}.json"
    
    def _extract_comments_by_repo(
        self,
        data_dir: str,
        existing_repos: Dict[str, Dict[str, str]]
    ) -> Dict[str, Dict[str, str]]:
        """
        按仓库提取评论内容
        
        Args:
            data_dir: 数据目录路径
            existing_repos: 已有的仓库评论映射 {repo_name: {url: body}}（用于去重）
        
        Returns:
            {repo_name: {url: body}} 字典
        """
        data_path = Path(data_dir)
        files = sorted(data_path.glob("*-filtered.json"))
        
        print(f"📁 扫描 {len(files)} 个数据文件...")
        
        repo_comments = defaultdict(dict)  # {repo_name: {url: body}}
        
        for file_path in tqdm(files, desc="扫描进度"):
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    event_type = event.get("type")
                    payload = event.get("payload", {})
                    repo = event.get("repo", {})
                    repo_name = repo.get("name", "unknown/unknown")
                    
                    # 获取该仓库已有的评论（用于去重）
                    existing_comments = existing_repos.get(repo_name, {})
                    
                    # Issue 评论
                    if event_type == "IssueCommentEvent":
                        comment = payload.get("comment", {})
                        url = comment.get("url")
                        body = comment.get("body")
                        
                        if url and body and url not in existing_comments:
                            repo_comments[repo_name][url] = body
                    
                    # PR Review 评论
                    elif event_type == "PullRequestReviewCommentEvent":
                        comment = payload.get("comment", {})
                        url = comment.get("url")
                        body = comment.get("body")
                        
                        if url and body and url not in existing_comments:
                            repo_comments[repo_name][url] = body
        
        return repo_comments
    
    def extract_comments_by_repo(
        self,
        data_dir: str,
        output_dir: str = "data/comments_by_repo/",
        resume: bool = True,
    ) -> Dict[str, Dict[str, str]]:
        """
        按仓库提取评论（从数据文件直接提取，无需 API）
        每个仓库的评论保存到单独的 JSON 文件
        
        Args:
            data_dir: 数据目录路径
            output_dir: 输出目录路径
            resume: 是否从已提取的数据恢复（追加模式）
        
        Returns:
            {repo_name: {url: body}} 映射字典
        """
        data_path = Path(data_dir)
        output_path = Path(output_dir)
        
        # 创建输出目录
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 加载已有的仓库评论（如果存在）
        existing_repos = {}
        if resume:
            # 扫描输出目录中已有的文件
            for json_file in output_path.glob("*.json"):
                if json_file.name == "index.json":  # 跳过索引文件
                    continue
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        comments = json.load(f)
                        # 从文件名恢复仓库名称（反向转换）
                        repo_name = json_file.stem.replace("-", "/")
                        existing_repos[repo_name] = comments
                except (json.JSONDecodeError, Exception) as e:
                    print(f"⚠️  跳过无效文件: {json_file.name} ({e})")
            
            if existing_repos:
                total_existing = sum(len(comments) for comments in existing_repos.values())
                print(f"✅ 已加载 {len(existing_repos)} 个仓库的 {total_existing} 条已提取评论\n")
        
        # 按仓库提取评论
        repo_comments = self._extract_comments_by_repo(data_dir, existing_repos)
        
        # 统计信息
        total_new = sum(len(comments) for comments in repo_comments.values())
        print(f"\n📊 统计信息:")
        print(f"   仓库数量: {len(repo_comments)}")
        print(f"   新提取的评论: {total_new}")
        if existing_repos:
            total_existing = sum(len(comments) for comments in existing_repos.values())
            print(f"   已有的评论: {total_existing}")
            print(f"   总计: {total_new + total_existing} 条\n")
        else:
            print(f"   总计: {total_new} 条\n")
        
        if not repo_comments:
            print("✅ 所有评论已提取完成！")
            return existing_repos
        
        # 按仓库名称排序
        sorted_repos = sorted(repo_comments.keys())
        
        print(f"⬇️  开始按仓库提取评论（无需 API 调用）\n")
        
        total_extracted = 0
        repo_index = {}  # 用于创建索引文件
        
        # 逐个仓库提取
        for repo_idx, repo_name in enumerate(sorted_repos, 1):
            comments = repo_comments[repo_name]
            
            if not comments:
                continue
            
            # 获取该仓库已有的评论（如果有）
            existing_comments = existing_repos.get(repo_name, {})
            # 合并新旧评论
            all_comments = {**existing_comments, **comments}
            
            print(f"\n{'=' * 60}")
            print(f"📦 仓库 {repo_idx}/{len(sorted_repos)}: {repo_name}")
            print(f"   新提取: {len(comments)} 条评论")
            if existing_comments:
                print(f"   已有: {len(existing_comments)} 条评论")
            print(f"   总计: {len(all_comments)} 条评论")
            print(f"{'=' * 60}\n")
            
            # 生成文件名
            filename = self._repo_name_to_filename(repo_name)
            output_file = output_path / filename
            
            # 保存该仓库的评论到单独的文件
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(all_comments, f, ensure_ascii=False, indent=2)
            
            total_extracted += len(comments)
            
            # 记录到索引
            repo_index[repo_name] = {
                "filename": filename,
                "comment_count": len(all_comments),
                "new_comments": len(comments)
            }
            
            print(f"\n✅ 仓库 {repo_name} 提取完成: {len(comments)} 条新评论，共 {len(all_comments)} 条")
            print(f"   保存到: {output_file}")
        
        # 保存索引文件
        index_file = output_path / "index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(repo_index, f, ensure_ascii=False, indent=2)
        
        # 统计
        print("\n" + "=" * 60)
        print("✅ 所有仓库提取完成统计:")
        print(f"   新提取: {total_extracted} 条")
        print(f"   处理仓库数: {len(repo_comments)}")
        print(f"   输出目录: {output_path}")
        print(f"   索引文件: {index_file}")
        print("=" * 60)
        
        # 合并所有仓库的评论返回
        all_repos = {**existing_repos}
        for repo_name, comments in repo_comments.items():
            if repo_name in all_repos:
                all_repos[repo_name].update(comments)
            else:
                all_repos[repo_name] = comments
        
        return all_repos


def main():
    parser = argparse.ArgumentParser(
        description="从数据文件直接提取 GitHub Issue 评论和 PR Review 评论（无需 API，按仓库提取，每个仓库一个文件）"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/filtered/",
        help="输入数据目录（默认: data/filtered/）"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/comments_by_repo/",
        help="输出目录路径（默认: data/comments_by_repo/）"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="从已提取数据恢复（默认启用）"
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="不从已提取数据恢复（覆盖已有文件）"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("GitHub 评论提取器（从数据文件直接提取，无需 API）")
    print("每个仓库的评论保存到单独的 JSON 文件")
    print("=" * 60)
    print(f"数据目录: {args.data_dir}")
    print(f"输出目录: {args.output_dir}")
    print(f"恢复模式: {'启用' if args.resume else '禁用'}")
    print("=" * 60)
    print()
    
    extractor = CommentExtractor()
    extractor.extract_comments_by_repo(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()

