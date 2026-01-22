#!/usr/bin/env python3
"""
示例：从图中提取并分析评论内容

展示如何：
1. 加载含有评论数据的图
2. 提取 COMMENTED_ISSUE 和 REVIEWED_PR 边的评论
3. 进行简单的文本分析（词频、长度统计等）
"""

import json
from pathlib import Path
from collections import Counter
from typing import List, Dict

import networkx as nx
import numpy as np


def load_graph_with_comments(graph_file: str) -> nx.MultiDiGraph:
    """加载包含评论的图"""
    if not Path(graph_file).exists():
        raise FileNotFoundError(f"图文件不存在: {graph_file}")
    
    graph = nx.read_graphml(graph_file)
    print(f"✅ 加载图: {graph_file}")
    print(f"   节点数: {graph.number_of_nodes()}")
    print(f"   边数: {graph.number_of_edges()}")
    return graph


def extract_comments_from_edges(
    graph: nx.MultiDiGraph,
    edge_types: List[str] = None,
) -> List[Dict]:
    """
    从图中提取评论数据
    
    Args:
        graph: NetworkX 图
        edge_types: 要提取的边类型，None 表示全部
    
    Returns:
        评论列表，每项包含 {source, target, edge_type, comment_body, created_at}
    """
    if edge_types is None:
        edge_types = ["COMMENTED_ISSUE", "REVIEWED_PR"]
    
    comments = []
    
    for source, target, key, attrs in graph.edges(keys=True, data=True):
        edge_type = attrs.get("edge_type")
        
        if edge_type not in edge_types:
            continue
        
        comment_body = attrs.get("comment_body", "")
        if not comment_body:
            continue
        
        comments.append({
            "source": source,
            "target": target,
            "edge_type": edge_type,
            "comment_body": comment_body,
            "created_at": attrs.get("created_at", ""),
        })
    
    return comments


def analyze_comments(comments: List[Dict]) -> Dict:
    """
    对评论进行基础统计分析
    
    Args:
        comments: 评论列表
    
    Returns:
        分析结果字典
    """
    if not comments:
        return {"total": 0}
    
    lengths = [len(c["comment_body"]) for c in comments]
    word_counts = [len(c["comment_body"].split()) for c in comments]
    
    # 统计边类型分布
    edge_types_count = Counter(c["edge_type"] for c in comments)
    
    # 词频分析（简单示例）
    all_words = []
    for comment in comments:
        words = comment["comment_body"].lower().split()
        # 过滤短词和常见词
        words = [w for w in words if len(w) > 3 and not w.startswith("@")]
        all_words.extend(words)
    
    word_freq = Counter(all_words)
    top_words = word_freq.most_common(20)
    
    return {
        "total": len(comments),
        "length": {
            "mean": float(np.mean(lengths)),
            "median": float(np.median(lengths)),
            "max": int(np.max(lengths)),
            "min": int(np.min(lengths)),
        },
        "word_count": {
            "mean": float(np.mean(word_counts)),
            "median": float(np.median(word_counts)),
            "max": int(np.max(word_counts)),
            "min": int(np.min(word_counts)),
        },
        "edge_types": dict(edge_types_count),
        "top_words": top_words,
    }


def print_analysis_report(analysis: Dict):
    """打印分析报告"""
    print("\n" + "=" * 60)
    print("评论分析报告")
    print("=" * 60)
    
    print(f"\n📊 基础统计:")
    print(f"  总评论数: {analysis['total']}")
    
    if analysis.get("length"):
        length_stats = analysis["length"]
        print(f"\n📝 评论长度（字符）:")
        print(f"  平均值: {length_stats['mean']:.1f}")
        print(f"  中位数: {length_stats['median']:.1f}")
        print(f"  范围: {length_stats['min']} ~ {length_stats['max']}")
    
    if analysis.get("word_count"):
        word_stats = analysis["word_count"]
        print(f"\n📚 评论字数（单词）:")
        print(f"  平均值: {word_stats['mean']:.1f}")
        print(f"  中位数: {word_stats['median']:.1f}")
        print(f"  范围: {word_stats['min']} ~ {word_stats['max']}")
    
    if analysis.get("edge_types"):
        print(f"\n🔗 边类型分布:")
        for edge_type, count in sorted(analysis["edge_types"].items(), key=lambda x: -x[1]):
            print(f"  {edge_type}: {count}")
    
    if analysis.get("top_words"):
        print(f"\n🏆 高频词 Top 20:")
        for i, (word, count) in enumerate(analysis["top_words"], 1):
            print(f"  {i:2d}. {word:15s} ({count:4d})")


def find_most_active_discussants(graph: nx.MultiDiGraph) -> List[Dict]:
    """
    找出最活跃的讨论参与者
    
    Returns:
        参与者列表，每项包含 {actor, discussion_count, comment_count}
    """
    actor_stats = {}
    
    for source, target, key, attrs in graph.edges(keys=True, data=True):
        edge_type = attrs.get("edge_type")
        
        # 只计算评论类边
        if edge_type not in ["COMMENTED_ISSUE", "REVIEWED_PR"]:
            continue
        
        if source not in actor_stats:
            actor_stats[source] = {
                "actor": source,
                "discussion_count": 0,
                "comment_count": 0,
                "has_comments": 0,
            }
        
        actor_stats[source]["discussion_count"] += 1
        
        if attrs.get("comment_body"):
            actor_stats[source]["comment_count"] += 1
            actor_stats[source]["has_comments"] += 1
    
    # 排序
    result = sorted(
        actor_stats.values(),
        key=lambda x: x["comment_count"],
        reverse=True
    )
    
    return result[:10]  # 返回 Top 10


def print_active_discussants(discussants: List[Dict]):
    """打印活跃讨论者"""
    if not discussants:
        print("未找到活跃讨论者")
        return
    
    print("\n" + "=" * 60)
    print("最活跃讨论者 Top 10")
    print("=" * 60)
    print(f"{'排名':<5} {'Actor':<30} {'讨论数':<10} {'有评论':<10}")
    print("-" * 60)
    
    for i, d in enumerate(discussants, 1):
        actor = d["actor"][:28]  # 截断长名称
        print(f"{i:<5} {actor:<30} {d['discussion_count']:<10} {d['has_comments']:<10}")


def export_comments_to_csv(comments: List[Dict], output_file: str):
    """导出评论到 CSV 文件"""
    import csv
    
    if not comments:
        print("没有评论可导出")
        return
    
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["source", "target", "edge_type", "created_at", "comment_body"]
        )
        writer.writeheader()
        writer.writerows(comments)
    
    print(f"✅ 已导出 {len(comments)} 条评论到: {output_file}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="分析图中的评论内容")
    parser.add_argument(
        "--graph",
        type=str,
        default="output/monthly-graphs/facebook-react/actor-discussion/2023-01.graphml",
        help="图文件路径"
    )
    parser.add_argument(
        "--export-csv",
        type=str,
        default=None,
        help="导出评论到 CSV 文件"
    )
    parser.add_argument(
        "--show-samples",
        type=int,
        default=5,
        help="显示前 N 条评论样本"
    )
    
    args = parser.parse_args()
    
    try:
        # 加载图
        graph = load_graph_with_comments(args.graph)
        
        # 提取评论
        print("\n正在提取评论...")
        comments = extract_comments_from_edges(graph)
        print(f"✅ 提取了 {len(comments)} 条评论")
        
        # 分析
        print("\n正在分析评论...")
        analysis = analyze_comments(comments)
        print_analysis_report(analysis)
        
        # 活跃讨论者
        print("\n正在分析活跃讨论者...")
        discussants = find_most_active_discussants(graph)
        print_active_discussants(discussants)
        
        # 显示样本
        if comments and args.show_samples > 0:
            print(f"\n评论样本（前 {args.show_samples} 条）:")
            print("-" * 60)
            for i, comment in enumerate(comments[:args.show_samples], 1):
                print(f"\n{i}. {comment['source']} → {comment['target']}")
                print(f"   类型: {comment['edge_type']}")
                print(f"   时间: {comment['created_at']}")
                body = comment["comment_body"]
                if len(body) > 200:
                    body = body[:200] + "..."
                print(f"   内容: {body}")
        
        # 导出
        if args.export_csv:
            export_comments_to_csv(comments, args.export_csv)
        
        print("\n✅ 分析完成！")
    
    except Exception as e:
        print(f"❌ 错误: {e}")
        raise


if __name__ == "__main__":
    main()
