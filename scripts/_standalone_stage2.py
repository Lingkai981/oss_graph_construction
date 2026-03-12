#!/usr/bin/env python3
"""独立运行剩余 3 个阶段：社区氛围分析 + 氛围报告 + 综合报告。
人员流动已在上一轮完成，此脚本跳过。
"""
import sys
import os
import time

os.environ["PYTHONUNBUFFERED"] = "1"

ROOT = "/Users/milk/Documents/ali2025/oss_graph_construction"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

LOG = "/tmp/pf_ca_stage2.log"

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

with open(LOG, "w") as f:
    f.write("")

log("=== 开始剩余阶段 (氛围分析 + 报告) ===")

from src.utils.logger import setup_logger
setup_logger(log_level="INFO", log_file=os.path.join(ROOT, "output/report/analysis.log"))

GRAPHS_DIR = os.path.join(ROOT, "output/monthly-graphs")
OUTPUT_DIR = os.path.join(ROOT, "output/report")

# ===== 1. 社区氛围分析 =====
log(">>> 阶段1: 社区氛围分析 (community_atmosphere)")
try:
    from src.analysis.community_atmosphere_analyzer import CommunityAtmosphereAnalyzer
    ca_dir = os.path.join(OUTPUT_DIR, "community-atmosphere-analysis")
    analyzer = CommunityAtmosphereAnalyzer(
        graphs_dir=GRAPHS_DIR,
        output_dir=ca_dir,
        use_top30=False,
    )
    analyzer.run()
    log("<<< 社区氛围分析 完成!")
except Exception as e:
    log(f"!!! 社区氛围分析 失败: {e}")
    import traceback
    traceback.print_exc()

# ===== 2. 氛围报告 =====
log(">>> 阶段2: 生成氛围报告")
try:
    from pathlib import Path
    ca_dir = Path(OUTPUT_DIR) / "community-atmosphere-analysis"
    input_path = ca_dir / "full_analysis.json"
    summary_path = ca_dir / "summary.json"
    output_path = ca_dir / "detailed_report.txt"

    # 使用与 run_analysis.py 相同的 invoke_module_main 方式
    import importlib
    mod = importlib.import_module("src.analysis.generate_atmosphere_report")
    sys.argv = [
        "generate_atmosphere_report",
        "--input", str(input_path),
        "--summary", str(summary_path),
        "--output", str(output_path),
    ]
    mod.main()
    log(f"<<< 氛围报告已生成: {output_path}")
except Exception as e:
    log(f"!!! 氛围报告 失败: {e}")
    import traceback
    traceback.print_exc()

# ===== 3. 综合报告 =====
log(">>> 阶段3: 生成综合报告")
try:
    from pathlib import Path
    from src.analysis import generate_comprehensive_report as gcr

    root_dir = Path(ROOT)
    output_dir = Path(OUTPUT_DIR)
    burnout_dir = output_dir / "burnout-analysis"
    newcomer_dir = output_dir / "newcomer-analysis"
    atmosphere_dir = output_dir / "community-atmosphere-analysis"
    personnel_flow_dir = output_dir / "personnel-flow-all"
    comprehensive_path = output_dir / "comprehensive_report.md"

    gcr.ROOT_DIR = root_dir
    gcr.OUTPUT_DIR = output_dir
    gcr.BURNOUT_SUMMARY = burnout_dir / "summary.json"
    gcr.NEWCOMER_SUMMARY = newcomer_dir / "summary.json"
    gcr.ATMOSPHERE_SUMMARY = atmosphere_dir / "full_analysis.json"
    gcr.BURNOUT_FULL = burnout_dir / "full_analysis.json"
    gcr.NEWCOMER_FULL = newcomer_dir / "full_analysis.json"
    gcr.ATMOSPHERE_FULL = atmosphere_dir / "full_analysis.json"
    gcr.PERSONNEL_FILE = personnel_flow_dir / "repo_yearly_status.txt"
    gcr.FINAL_REPORT_PATH = comprehensive_path

    comprehensive_path.parent.mkdir(parents=True, exist_ok=True)
    gcr.main()
    log(f"<<< 综合报告已生成: {comprehensive_path}")
except Exception as e:
    log(f"!!! 综合报告 失败: {e}")
    import traceback
    traceback.print_exc()

log("=== 全部完成 ===")
