#!/usr/bin/env python3
"""开源项目健康度一站式命令行入口。

此脚本整合了现有的各类分析器和报告生成器，允许通过命令行参数
灵活组合执行流程、控制输入输出目录，以及在失败时的行为。

示例命令：
python run_analysis.py --list
python run_analysis.py --all --workers 8
python run_analysis.py --analyzers burnout newcomer --reports comprehensive_report
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import os
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class Task:
    """表示流水线中可以执行的一个步骤，包含唯一键、说明及执行函数。"""

    key: str
    description: str
    runner: Callable[["PipelineContext"], None]


@dataclass
class PipelineContext:
    """保存一次流水线运行所需的全部路径与命令行参数，避免重复计算路径。"""

    args: argparse.Namespace
    root_dir: Path
    data_dir: Path
    graphs_dir: Path
    output_dir: Path
    burnout_dir: Path
    newcomer_dir: Path
    atmosphere_dir: Path
    bus_factor_dir: Path
    quality_risk_dir: Path
    structure_dir: Path
    personnel_flow_dir: Path
    comprehensive_path: Path


def guess_data_dir(root_dir: Path) -> Path:
    """根据常见目录结构推测数据目录，若不存在则回退到 data 根目录。"""

    candidates = [
        root_dir / "data" / "filtered_union_2021_2025_daily",
        root_dir / "data" / "filtered",
        root_dir / "data" / "filtered_union_2024_fulldaily",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return root_dir / "data"


def deduplicate(seq: Iterable[str]) -> List[str]:
    """在保持原有顺序的前提下移除重复项，确保任务列表可预测。"""

    seen: Dict[str, bool] = {}
    result: List[str] = []
    for item in seq:
        if item not in seen:
            seen[item] = True
            result.append(item)
    return result


@contextlib.contextmanager
def patched_argv(argv: Sequence[str]) -> Iterable[None]:
    """临时替换 ``sys.argv``，以便在同一进程内安全调用依赖 argparse 的旧脚本。"""

    original = sys.argv
    new_argv = list(argv)
    if not new_argv:
        new_argv = [original[0]]
    sys.argv = new_argv
    try:
        yield
    finally:
        sys.argv = original


def invoke_module_main(module_name: str, argv: Sequence[str]) -> None:
    """导入指定模块并执行其 ``main`` 函数，同时挂载临时参数列表。"""

    module = importlib.import_module(module_name)
    main_callable = getattr(module, "main", None)
    if main_callable is None:
        raise AttributeError(f"模块 {module_name} 未提供 main() 函数")

    with patched_argv([module_name, *argv]):
        try:
            main_callable()
        except SystemExit as exc:  # pragma: no cover - defensive guard
            code = exc.code or 0
            if code != 0:
                raise RuntimeError(f"模块 {module_name} 以状态码 {code} 退出") from None


def ensure_exists(path: Path, label: str) -> None:
    """在需要上游结果时提前检查文件是否存在，避免执行到中途才报错。"""

    if not path.exists():
        raise FileNotFoundError(f"缺少必要文件：{label} -> {path}")


# -----------------------
# 分析器执行封装
# -----------------------

def run_monthly_graphs(ctx: PipelineContext) -> None:
    """根据配置构建月度协作图，可按串行或并行方式运行构图流程。"""
    from src.analysis import monthly_graph_builder as mgb

    graph_types = None
    if ctx.args.graph_types:
        graph_types = [item.strip() for item in ctx.args.graph_types if item.strip()]
        if not graph_types:
            graph_types = None

    workers = ctx.args.workers
    if ctx.args.serial:
        workers = 1

    merge_index = not ctx.args.fresh_index

    if workers == 1:
        mgb.build_monthly_graphs(
            data_dir=str(ctx.data_dir),
            output_dir=str(ctx.graphs_dir),
            graph_types=graph_types,
            start_month=ctx.args.start_month,
            end_month=ctx.args.end_month,
            merge_index=merge_index,
        )
    else:
        mgb.build_monthly_graphs_parallel(
            data_dir=str(ctx.data_dir),
            output_dir=str(ctx.graphs_dir),
            graph_types=graph_types,
            workers=workers,
            start_month=ctx.args.start_month,
            end_month=ctx.args.end_month,
            merge_index=merge_index,
        )


def run_burnout_analysis(ctx: PipelineContext) -> None:
    """运行维护者倦怠分析，输出时间序列与摘要文件。"""
    from src.analysis.burnout_analyzer import BurnoutAnalyzer

    ctx.burnout_dir.mkdir(parents=True, exist_ok=True)
    analyzer = BurnoutAnalyzer(
        graphs_dir=str(ctx.graphs_dir),
        output_dir=str(ctx.burnout_dir),
    )
    analyzer.run()


def run_newcomer_analysis(ctx: PipelineContext) -> None:
    """运行新人融入与晋升路径分析，生成 full/summary 数据。"""
    from src.analysis.newcomer_analyzer import NewcomerAnalyzer

    ctx.newcomer_dir.mkdir(parents=True, exist_ok=True)
    analyzer = NewcomerAnalyzer(
        graphs_dir=str(ctx.graphs_dir),
        output_dir=str(ctx.newcomer_dir),
    )
    analyzer.run()


def run_atmosphere_analysis(ctx: PipelineContext) -> None:
    """运行社区氛围分析，可选是否限制在 Top30 仓库。"""
    from src.analysis.community_atmosphere_analyzer import CommunityAtmosphereAnalyzer

    # 社区氛围分析依赖毒性缓存（社区氛围分析器内部固定读取 output/community-atmosphere-analysis/toxicity.json）
    toxicity_cache = ctx.root_dir / "output" / "community-atmosphere-analysis" / "toxicity.json"
    ensure_exists(
        toxicity_cache,
        "社区氛围分析所需的毒性缓存 (请先运行 --analyzers toxicity_cache 或使用 --all)",
    )

    ctx.atmosphere_dir.mkdir(parents=True, exist_ok=True)
    analyzer = CommunityAtmosphereAnalyzer(
        graphs_dir=str(ctx.graphs_dir),
        output_dir=str(ctx.atmosphere_dir),
        use_top30=ctx.args.atmosphere_top30,
    )
    analyzer.run()


def run_toxicity_cache(ctx: PipelineContext) -> None:
    """调用 ToxiCR 项目生成社区氛围分析所需的毒性缓存。"""

    toxicr_root = ctx.root_dir.parent / "ToxiCR"
    if not toxicr_root.exists():
        raise FileNotFoundError(
            f"未找到 ToxiCR 项目目录: {toxicr_root}，请确保 ToxiCR 与本项目同级放置"
        )

    script_path = toxicr_root / "analyze_oss_comments.py"
    ensure_exists(script_path, "ToxiCR 毒性分析脚本")

    # 确定 Python 解释器：优先使用 ToxiCR 下的 venv/.venv/env，其次回退到系统 python。
    candidate_interpreters = [
        toxicr_root / "venv" / "Scripts" / "python.exe",
        toxicr_root / ".venv" / "Scripts" / "python.exe",
        toxicr_root / "env" / "Scripts" / "python.exe",
        toxicr_root / "venv" / "bin" / "python",
        toxicr_root / ".venv" / "bin" / "python",
        toxicr_root / "env" / "bin" / "python",
    ]
    python_exec = next((p for p in candidate_interpreters if p.exists()), None)
    if python_exec is None:
        python_exec = "python"

    # 输出路径固定为社区氛围分析器期望的位置，避免与用户自定义 output-dir 不一致。
    toxicity_output = ctx.root_dir / "output" / "community-atmosphere-analysis" / "toxicity.json"
    toxicity_output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(python_exec),
        str(script_path),
        "--graphs-dir",
        str(ctx.graphs_dir),
        "--output-file",
        str(toxicity_output),
        "--top30-file",
        str(ctx.root_dir / "top30.json"),
    ]

    if ctx.args.atmosphere_top30:
        cmd.append("--top30")

    print("调用 ToxiCR 生成毒性缓存（实时输出）...")
    try:
        process = subprocess.Popen(
            cmd,
            cwd=toxicr_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line.rstrip())
        return_code = process.wait()
    except Exception as exc:  # pragma: no cover - 防御性处理
        raise RuntimeError(f"调用 ToxiCR 失败: {exc}") from None

    if return_code != 0:
        raise RuntimeError("ToxiCR 执行失败，请查看上方输出日志。")

    print("✓ 毒性缓存生成完成")


def run_bus_factor_analysis(ctx: PipelineContext) -> None:
    """运行 Bus Factor 风险分析，支持自定义权重与并行进程数。"""
    from src.analysis.bus_factor_analyzer import BusFactorAnalyzer

    ctx.bus_factor_dir.mkdir(parents=True, exist_ok=True)

    weights = None
    if ctx.args.bus_factor_weights:
        weights_path = Path(ctx.args.bus_factor_weights)
        ensure_exists(weights_path, "Bus Factor 权重配置文件")
        with open(weights_path, "r", encoding="utf-8") as handle:
            weights = json.load(handle)

    workers = ctx.args.bus_factor_workers or ctx.args.workers
    analyzer = BusFactorAnalyzer(
        graphs_dir=str(ctx.graphs_dir),
        output_dir=str(ctx.bus_factor_dir),
        threshold=ctx.args.bus_factor_threshold,
        weights=weights,
        workers=workers,
    )
    analyzer.run(resume=not ctx.args.bus_factor_fresh)


def run_quality_risk_analysis(ctx: PipelineContext) -> None:
    """运行质量与权限滥用风险分析，输出候选可疑贡献者。"""
    from src.analysis.quality_risk_analyzer import QualityRiskAnalyzer

    ctx.quality_risk_dir.mkdir(parents=True, exist_ok=True)
    analyzer = QualityRiskAnalyzer(
        graphs_dir=str(ctx.graphs_dir),
        output_dir=str(ctx.quality_risk_dir),
    )
    analyzer.run()


def run_structure_analysis(ctx: PipelineContext) -> None:
    """运行协作网络结构指标分析，生成图直径、平均距离等指标。"""
    from src.analysis.structure_analyzer import ActorActorStructureAnalyzer

    ctx.structure_dir.mkdir(parents=True, exist_ok=True)
    analyzer = ActorActorStructureAnalyzer(
        graphs_dir=str(ctx.graphs_dir),
        output_dir=str(ctx.structure_dir),
    )
    analyzer.run()


def run_personnel_flow(ctx: PipelineContext) -> None:
    """运行人员流动分析，依赖倦怠分析产出的核心成员时间线。"""
    from src.analysis.personnel_flow import PersonnelFlowAnalyzer

    ctx.personnel_flow_dir.mkdir(parents=True, exist_ok=True)
    burnout_full = ctx.burnout_dir / "full_analysis.json"
    ensure_exists(burnout_full, "倦怠分析完整结果")

    analyzer = PersonnelFlowAnalyzer(
        input_path=str(burnout_full),
        output_dir=str(ctx.personnel_flow_dir),
        scope="all",
        graphs_dir=str(ctx.graphs_dir),
    )
    analyzer.run(flow_months_after=ctx.args.personnel_flow_months)


# -----------------------
# 报告生成封装
# -----------------------

def run_burnout_report(ctx: PipelineContext) -> None:
    """基于倦怠分析结果生成详细 markdown 报告。"""
    input_path = ctx.burnout_dir / "full_analysis.json"
    ensure_exists(input_path, "倦怠分析完整结果")
    output_path = ctx.burnout_dir / "detailed_report.txt"
    invoke_module_main(
        "src.analysis.detailed_report",
        ["--input", str(input_path), "--output", str(output_path)],
    )


def run_bus_factor_report(ctx: PipelineContext) -> None:
    """根据 Bus Factor 分析结果生成详细解读与汇总。"""
    input_path = ctx.bus_factor_dir / "full_analysis.json"
    summary_path = ctx.bus_factor_dir / "summary.json"
    ensure_exists(input_path, "Bus Factor 分析完整结果")
    ensure_exists(summary_path, "Bus Factor 分析摘要")
    output_path = ctx.bus_factor_dir / "detailed_report.txt"
    invoke_module_main(
        "src.analysis.generate_bus_factor_report",
        [
            "--input",
            str(input_path),
            "--summary",
            str(summary_path),
            "--output",
            str(output_path),
            "--include-summary",
        ],
    )


def run_atmosphere_report(ctx: PipelineContext) -> None:
    """读取社区氛围指标生成详细说明文本。"""
    input_path = ctx.atmosphere_dir / "full_analysis.json"
    summary_path = ctx.atmosphere_dir / "summary.json"
    ensure_exists(input_path, "社区氛围完整结果")
    ensure_exists(summary_path, "社区氛围摘要")
    output_path = ctx.atmosphere_dir / "detailed_report.txt"
    invoke_module_main(
        "src.analysis.generate_atmosphere_report",
        [
            "--input",
            str(input_path),
            "--summary",
            str(summary_path),
            "--output",
            str(output_path),
        ],
    )


def run_newcomer_report(ctx: PipelineContext) -> None:
    """生成新人体验与核心晋升的可读报告。"""
    input_path = ctx.newcomer_dir / "full_analysis.json"
    ensure_exists(input_path, "新人分析完整结果")
    output_path = ctx.newcomer_dir / "detailed_report.txt"
    invoke_module_main(
        "src.analysis.newcomer_detailed_report",
        ["--input", str(input_path), "--output", str(output_path)],
    )


def run_quality_risk_report(ctx: PipelineContext) -> None:
    """生成质量风险详细报告，含可疑行为构成解析。"""
    ensure_exists(ctx.quality_risk_dir / "summary.json", "质量风险摘要")
    output_path = ctx.quality_risk_dir / "detailed_report.txt"
    invoke_module_main(
        "src.analysis.quality_risk_detailed_report",
        [
            "--input-dir",
            str(ctx.quality_risk_dir),
            "--graphs-dir",
            str(ctx.graphs_dir),
            "--output",
            str(output_path),
        ],
    )


def run_structure_report(ctx: PipelineContext) -> None:
    """生成结构指标详细报告，对比不同时期的网络形态。"""
    input_path = ctx.structure_dir / "full_analysis.json"
    ensure_exists(input_path, "协作结构分析完整结果")
    output_path = ctx.structure_dir / "detailed_report.txt"
    invoke_module_main(
        "src.analysis.structure_detailed_report",
        ["--input", str(input_path), "--output", str(output_path)],
    )


def run_comprehensive_report(ctx: PipelineContext) -> None:
    """重置综合报告脚本的全局路径并调用其入口函数生成成品报告。"""
    from src.analysis import generate_comprehensive_report as gcr

    gcr.ROOT_DIR = ctx.root_dir
    gcr.OUTPUT_DIR = ctx.output_dir
    gcr.BURNOUT_SUMMARY = ctx.burnout_dir / "summary.json"
    gcr.NEWCOMER_SUMMARY = ctx.newcomer_dir / "summary.json"
    gcr.ATMOSPHERE_SUMMARY = ctx.atmosphere_dir / "full_analysis.json"
    gcr.BURNOUT_FULL = ctx.burnout_dir / "full_analysis.json"
    gcr.NEWCOMER_FULL = ctx.newcomer_dir / "full_analysis.json"
    gcr.ATMOSPHERE_FULL = ctx.atmosphere_dir / "full_analysis.json"
    gcr.PERSONNEL_FILE = ctx.personnel_flow_dir / "repo_yearly_status.txt"
    gcr.FINAL_REPORT_PATH = ctx.comprehensive_path

    ensure_exists(gcr.BURNOUT_SUMMARY, "倦怠分析摘要")
    ensure_exists(gcr.NEWCOMER_SUMMARY, "新人分析摘要")
    ensure_exists(gcr.ATMOSPHERE_SUMMARY, "社区氛围完整结果")
    ensure_exists(gcr.PERSONNEL_FILE, "人员流动汇总")

    ctx.comprehensive_path.parent.mkdir(parents=True, exist_ok=True)
    gcr.main()


ANALYZER_ORDER = [
    "monthly_graphs",
    "burnout",
    "newcomer",
    "toxicity_cache",
    "bus_factor",
    "quality_risk",
    "structure",
    "personnel_flow",
    "community_atmosphere",
]

REPORT_ORDER = [
    "burnout_report",
    "newcomer_report",
    "bus_factor_report",
    "quality_risk_report",
    "structure_report",
    "atmosphere_report",
    "comprehensive_report",
]

ANALYZERS: Dict[str, Task] = {
    "monthly_graphs": Task("monthly_graphs", "按月构建图数据快照", run_monthly_graphs),
    "burnout": Task("burnout", "执行维护者倦怠分析", run_burnout_analysis),
    "newcomer": Task("newcomer", "执行新人融入分析", run_newcomer_analysis),
    "toxicity_cache": Task("toxicity_cache", "调用 ToxiCR 生成社区氛围毒性缓存", run_toxicity_cache),
    "community_atmosphere": Task("community_atmosphere", "执行社区氛围分析", run_atmosphere_analysis),
    "bus_factor": Task("bus_factor", "执行 Bus Factor 风险分析", run_bus_factor_analysis),
    "quality_risk": Task("quality_risk", "执行质量风险分析", run_quality_risk_analysis),
    "structure": Task("structure", "执行协作网络结构分析", run_structure_analysis),
    "personnel_flow": Task("personnel_flow", "执行人员流动分析", run_personnel_flow),
}

REPORTS: Dict[str, Task] = {
    "burnout_report": Task("burnout_report", "生成倦怠详细报告", run_burnout_report),
    "newcomer_report": Task("newcomer_report", "生成新人体验报告", run_newcomer_report),
    "bus_factor_report": Task("bus_factor_report", "生成 Bus Factor 风险报告", run_bus_factor_report),
    "atmosphere_report": Task("atmosphere_report", "生成社区氛围报告", run_atmosphere_report),
    "quality_risk_report": Task("quality_risk_report", "生成质量风险报告", run_quality_risk_report),
    "structure_report": Task("structure_report", "生成结构指标报告", run_structure_report),
    "comprehensive_report": Task("comprehensive_report", "生成综合健康报告", run_comprehensive_report),
}


def list_tasks() -> None:
    """打印所有内置分析器与报告，方便用户查询可用关键字。"""

    print("可用的分析器：")
    for key in ANALYZER_ORDER:
        task = ANALYZERS[key]
        print(f"  {task.key:<22} {task.description}")
    print("\n可用的报告生成器：")
    for key in REPORT_ORDER:
        task = REPORTS[key]
        print(f"  {task.key:<22} {task.description}")


def resolve_paths(args: argparse.Namespace) -> PipelineContext:
    """解析命令行参数中的路径信息，并补全默认目录。"""
    root_dir = Path(args.root_dir).resolve() if args.root_dir else Path(__file__).resolve().parent
    data_dir = Path(args.data_dir).resolve() if args.data_dir else guess_data_dir(root_dir)
    graphs_dir = Path(args.graphs_dir).resolve() if args.graphs_dir else (root_dir / "output" / "monthly-graphs").resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else (root_dir / "output").resolve()

    burnout_dir = (output_dir / args.burnout_dir).resolve()
    newcomer_dir = (output_dir / args.newcomer_dir).resolve()
    atmosphere_dir = (output_dir / args.atmosphere_dir).resolve()
    bus_factor_dir = (output_dir / args.bus_factor_dir).resolve()
    quality_risk_dir = (output_dir / args.quality_risk_dir).resolve()
    structure_dir = (output_dir / args.structure_dir).resolve()
    personnel_flow_dir = (output_dir / args.personnel_flow_dir).resolve()

    comprehensive_path = Path(args.comprehensive_report).resolve() if args.comprehensive_report else (output_dir / "comprehensive_report.md").resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    return PipelineContext(
        args=args,
        root_dir=root_dir,
        data_dir=data_dir,
        graphs_dir=graphs_dir,
        output_dir=output_dir,
        burnout_dir=burnout_dir,
        newcomer_dir=newcomer_dir,
        atmosphere_dir=atmosphere_dir,
        bus_factor_dir=bus_factor_dir,
        quality_risk_dir=quality_risk_dir,
        structure_dir=structure_dir,
        personnel_flow_dir=personnel_flow_dir,
        comprehensive_path=comprehensive_path,
    )


def select_tasks(args: argparse.Namespace) -> Dict[str, List[str]]:
    """根据用户输入挑选要执行的分析器与报告列表，同时去重并校验。"""
    analyzers: List[str] = []
    reports: List[str] = []

    if args.all:
        analyzers.extend(ANALYZER_ORDER)
        reports.extend(REPORT_ORDER)

    if args.analyzers:
        analyzers.extend(args.analyzers)
    if args.reports:
        reports.extend(args.reports)

    analyzers = deduplicate(analyzers)
    reports = deduplicate(reports)

    skip = set(args.skip or [])
    analyzers = [name for name in analyzers if name not in skip]
    reports = [name for name in reports if name not in skip]

    invalid_analyzers = [name for name in analyzers if name not in ANALYZERS]
    invalid_reports = [name for name in reports if name not in REPORTS]
    if invalid_analyzers or invalid_reports:
        details = []
        if invalid_analyzers:
            details.append(f"未知的分析器关键字：{', '.join(invalid_analyzers)}")
        if invalid_reports:
            details.append(f"未知的报告关键字：{', '.join(invalid_reports)}")
        raise ValueError("; ".join(details))

    # 为确保执行顺序可预测，分析器始终按代码内定义的固定顺序执行，忽略命令行中的排列顺序。
    analyzer_set = set(analyzers)
    analyzers = [name for name in ANALYZER_ORDER if name in analyzer_set]

    return {"analyzers": analyzers, "reports": reports}


def run_task_sequence(tasks: List[str], registry: Dict[str, Task], ctx: PipelineContext) -> None:
    """按照顺序执行任务列表，可在失败时选择中断或继续。"""
    for name in tasks:
        task = registry[name]
        print(f"\n=== {task.description} ({task.key}) ===")
        try:
            task.runner(ctx)
            print(f"✓ 完成任务 {task.key}")
        except Exception as exc:
            print(f"✗ 任务 {task.key} 执行失败：{exc}", file=sys.stderr)
            if ctx.args.verbose:
                traceback.print_exc()
            if not ctx.args.continue_on_error:
                raise


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器，提供完整的中文帮助信息。"""
    parser = argparse.ArgumentParser(description="开源项目健康分析的一站式命令行工具")
    parser.add_argument("--all", action="store_true", help="按固定顺序依次运行全部分析器与报告生成器")
    parser.add_argument("--analyzers", nargs="+", help="仅运行指定分析器，参数为关键字", metavar="名称")
    parser.add_argument("--reports", nargs="+", help="仅生成指定报告，参数为关键字", metavar="名称")
    parser.add_argument("--skip", nargs="+", help="在选择的任务集合中跳过某些步骤", metavar="名称")
    parser.add_argument("--list", action="store_true", help="列出全部内置分析器与报告关键字")

    parser.add_argument("--root-dir", type=str, help="项目根目录（默认取脚本所在目录）")
    parser.add_argument("--data-dir", type=str, help="原始月度聚合数据目录，用于构图")
    parser.add_argument("--graphs-dir", type=str, help="月度图数据输出目录")
    parser.add_argument("--output-dir", type=str, help="所有结果的根输出目录")

    parser.add_argument("--burnout-dir", type=str, default="burnout-analysis2", help="倦怠分析输出子目录")
    parser.add_argument("--newcomer-dir", type=str, default="newcomer-analysis", help="新人分析输出子目录")
    parser.add_argument("--atmosphere-dir", type=str, default="community-atmosphere-analysis", help="社区氛围输出子目录")
    parser.add_argument("--bus-factor-dir", type=str, default="bus-factor-analysis", help="Bus Factor 输出子目录")
    parser.add_argument("--quality-risk-dir", type=str, default="quality-risk", help="质量风险输出子目录")
    parser.add_argument("--structure-dir", type=str, default="actor-actor-structure", help="网络结构输出子目录")
    parser.add_argument("--personnel-flow-dir", type=str, default="personnel-flow-all", help="人员流动输出子目录")
    parser.add_argument("--comprehensive-report", type=str, help="综合报告输出路径（默认位于 output 根目录）")

    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1)), help="并行任务默认使用的工作进程数量")
    parser.add_argument("--graph-types", nargs="+", help="构图时启用的图类型，如 actor-actor", metavar="类型")
    parser.add_argument("--start-month", type=str, help="构图起始月份（YYYY-MM）")
    parser.add_argument("--end-month", type=str, help="构图结束月份（YYYY-MM）")
    parser.add_argument("--serial", action="store_true", help="强制按单进程模式构建月度图，便于调试")
    parser.add_argument("--fresh-index", action="store_true", help="构图完成后不与旧 index 合并，直接覆盖")

    parser.add_argument("--bus-factor-threshold", type=float, default=0.5, help="Bus Factor 贡献占比阈值")
    parser.add_argument("--bus-factor-weights", type=str, help="自定义 Bus Factor 边权配置 JSON 文件路径")
    parser.add_argument("--bus-factor-workers", type=int, help="Bus Factor 专用进程数（默认沿用 --workers）")
    parser.add_argument("--bus-factor-fresh", action="store_true", help="禁用 Bus Factor 分析的断点续传功能")

    parser.add_argument("--atmosphere-top30", action="store_true", help="仅分析 top30.json 中列出的核心仓库")
    parser.add_argument("--personnel-flow-months", type=int, default=12, help="离开后跟踪去向的月份数")

    parser.add_argument("--continue-on-error", action="store_true", help="任务失败后继续执行剩余步骤")
    parser.add_argument("--verbose", action="store_true", help="失败时输出完整堆栈，便于排查")

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """脚本主入口，负责解析参数、列出任务并驱动执行。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        list_tasks()
        return

    try:
        selections = select_tasks(args)
    except ValueError as exc:
        parser.error(str(exc))
    if not selections["analyzers"] and not selections["reports"]:
        parser.error("未选择任何任务，请使用 --all、--analyzers 或 --reports（可先运行 --list 查看关键字）。")

    ctx = resolve_paths(args)

    print("流水线配置：")
    print(f"  根目录:       {ctx.root_dir}")
    print(f"  数据源:       {ctx.data_dir}")
    print(f"  月度图:       {ctx.graphs_dir}")
    print(f"  输出根:       {ctx.output_dir}")
    print(f"  倦怠目录:     {ctx.burnout_dir}")
    print(f"  新人目录:     {ctx.newcomer_dir}")
    print(f"  氛围目录:     {ctx.atmosphere_dir}")
    print(f"  BusFactor:    {ctx.bus_factor_dir}")
    print(f"  质量风险:     {ctx.quality_risk_dir}")
    print(f"  结构分析:     {ctx.structure_dir}")
    print(f"  人员流动:     {ctx.personnel_flow_dir}")
    print(f"  综合报告:     {ctx.comprehensive_path}")

    run_task_sequence(selections["analyzers"], ANALYZERS, ctx)
    run_task_sequence(selections["reports"], REPORTS, ctx)

    print("\n✅ 流水线执行完毕")


if __name__ == "__main__":
    main()
