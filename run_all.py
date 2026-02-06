#!/usr/bin/env python3
"""
一键运行所有分析并生成综合报告

这是 run_analysis.py 的简化封装，自动执行完整的分析流程：
1. 构建月度图（如果需要）
2. 运行所有分析器（倦怠、新人、人员流动、社区氛围、Bus Factor 等）
3. 生成各维度报告
4. 生成综合健康度报告

使用方式：
    python run_all.py                    # 使用默认设置运行全部
    python run_all.py --workers 16       # 指定并行工作进程数
    python run_all.py --skip-toxicity    # 跳过毒性缓存生成（如已存在）
    python run_all.py --skip-graphs      # 跳过月度图构建（如已存在）
    python run_all.py --quick            # 快速模式：跳过毒性缓存和月度图构建
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(
        description="一键运行所有分析并生成综合报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
    python run_all.py                    # 完整运行
    python run_all.py --workers 16       # 使用 16 个工作进程
    python run_all.py --skip-toxicity    # 跳过毒性缓存（如已存在）
    python run_all.py --quick            # 快速模式
        """,
    )
    
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 1)),
        help=f"并行工作进程数（默认：{max(1, (os.cpu_count() or 1))}）",
    )
    
    parser.add_argument(
        "--skip-toxicity",
        action="store_true",
        help="跳过毒性缓存生成（如果 toxicity.json 已存在）",
    )
    
    parser.add_argument(
        "--skip-graphs",
        action="store_true",
        help="跳过月度图构建（如果图文件已存在）",
    )
    
    parser.add_argument(
        "--quick",
        action="store_true",
        help="快速模式：等同于 --skip-toxicity --skip-graphs",
    )
    
    parser.add_argument(
        "--data-dir",
        type=str,
        help="原始事件数据目录（默认自动检测）",
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="输出目录（默认：output）",
    )
    
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="遇到错误时继续执行后续任务",
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细错误信息",
    )
    
    args = parser.parse_args()
    
    # 构建 run_analysis.py 的参数
    run_args = ["--all", "--workers", str(args.workers)]
    
    # 处理跳过选项
    skip_list = []
    if args.quick or args.skip_toxicity:
        # 检查毒性缓存是否已存在
        toxicity_path = project_root / "output" / "community-atmosphere-analysis" / "toxicity.json"
        if toxicity_path.exists():
            skip_list.append("toxicity_cache")
            print(f"✓ 检测到已有毒性缓存：{toxicity_path}")
        else:
            print(f"⚠ 未找到毒性缓存，将执行毒性分析（需要 ToxiCR 项目）")
    
    if args.quick or args.skip_graphs:
        # 检查月度图是否已存在
        graphs_index = project_root / "output" / "monthly-graphs" / "index.json"
        if graphs_index.exists():
            skip_list.append("monthly_graphs")
            print(f"✓ 检测到已有月度图索引：{graphs_index}")
        else:
            print(f"⚠ 未找到月度图索引，将执行图构建")
    
    if skip_list:
        run_args.extend(["--skip"] + skip_list)
    
    # 其他选项
    if args.data_dir:
        run_args.extend(["--data-dir", args.data_dir])
    
    if args.output_dir and args.output_dir != "output":
        run_args.extend(["--output-dir", args.output_dir])
    
    if args.continue_on_error:
        run_args.append("--continue-on-error")
    
    if args.verbose:
        run_args.append("--verbose")
    
    # 显示执行配置
    print("\n" + "=" * 60)
    print("OSS 社区健康度分析 - 一键运行")
    print("=" * 60)
    print(f"工作进程数: {args.workers}")
    print(f"输出目录: {args.output_dir}")
    if skip_list:
        print(f"跳过步骤: {', '.join(skip_list)}")
    print("=" * 60 + "\n")
    
    # 调用 run_analysis.py 的 main 函数
    from run_analysis import main as run_analysis_main
    
    try:
        run_analysis_main(run_args)
        
        # 成功完成
        print("\n" + "=" * 60)
        print("✅ 全部分析完成！")
        print("=" * 60)
        
        # 显示报告位置
        output_path = Path(args.output_dir)
        comprehensive_report = output_path / "comprehensive_report.md"
        
        print("\n📊 生成的报告：")
        print(f"  综合报告: {comprehensive_report}")
        
        report_files = [
            ("倦怠分析", "burnout-analysis/detailed_report.txt"),
            ("新人体验", "newcomer-analysis/detailed_report.txt"),
            ("社区氛围", "community-atmosphere-analysis/detailed_report.txt"),
            ("Bus Factor", "bus-factor-analysis/detailed_report.txt"),
            ("人员流动", "personnel-flow-all/repo_yearly_status.txt"),
        ]
        
        for name, path in report_files:
            full_path = output_path / path
            if full_path.exists():
                print(f"  {name}: {full_path}")
        
        print("\n🎉 分析完成，请查看上述报告了解社区健康度详情。")
        
    except Exception as exc:
        print(f"\n❌ 运行失败：{exc}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
