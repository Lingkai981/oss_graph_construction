#!/usr/bin/env python3
"""独立运行 personnel_flow + community_atmosphere 分析。
直接调用分析器，不经过 run_analysis.py 的终端。
所有输出写入 /tmp/pf_ca_standalone.log
"""
import sys
import os
import time

# 确保 unbuffered
os.environ["PYTHONUNBUFFERED"] = "1"

# 设置工作目录
ROOT = "/Users/milk/Documents/ali2025/oss_graph_construction"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

LOG = "/tmp/pf_ca_standalone.log"

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

# 清空日志
with open(LOG, "w") as f:
    f.write("")

log("=== 开始独立分析脚本 ===")

# 初始化 logger
from src.utils.logger import setup_logger
setup_logger(log_level="INFO", log_file=os.path.join(ROOT, "output/report/analysis.log"))

GRAPHS_DIR = os.path.join(ROOT, "output/monthly-graphs")
OUTPUT_DIR = os.path.join(ROOT, "output/report")

# ===== 1. 人员流动分析 =====
log(">>> 阶段1: 人员流动分析 (personnel_flow)")
try:
    from src.analysis.personnel_flow import PersonnelFlowAnalyzer
    pf_dir = os.path.join(OUTPUT_DIR, "personnel-flow-all")
    burnout_full = os.path.join(OUTPUT_DIR, "burnout-analysis/full_analysis.json")
    
    analyzer = PersonnelFlowAnalyzer(
        input_path=burnout_full,
        output_dir=pf_dir,
        scope="all",
        graphs_dir=GRAPHS_DIR,
    )
    analyzer.run(flow_months_after=12)
    log("<<< 人员流动分析 完成!")
except Exception as e:
    log(f"!!! 人员流动分析 失败: {e}")
    import traceback
    traceback.print_exc()

# ===== 2. 社区氛围分析 =====
log(">>> 阶段2: 社区氛围分析 (community_atmosphere)")
try:
    from src.analysis.community_atmosphere import CommunityAtmosphereAnalyzer
    ca_dir = os.path.join(OUTPUT_DIR, "community-atmosphere-analysis")
    
    ca = CommunityAtmosphereAnalyzer(
        graphs_dir=GRAPHS_DIR,
        output_dir=ca_dir,
        workers=8,
    )
    ca.run()
    log("<<< 社区氛围分析 完成!")
except Exception as e:
    log(f"!!! 社区氛围分析 失败: {e}")
    import traceback
    traceback.print_exc()

# ===== 3. 氛围报告 =====
log(">>> 阶段3: 生成氛围报告")
try:
    from src.services.atmosphere_report import generate_atmosphere_report
    ca_dir = os.path.join(OUTPUT_DIR, "community-atmosphere-analysis")
    report_path = os.path.join(OUTPUT_DIR, "atmosphere_report.md")
    generate_atmosphere_report(ca_dir, report_path)
    log(f"<<< 氛围报告已生成: {report_path}")
except Exception as e:
    log(f"!!! 氛围报告 失败: {e}")
    import traceback
    traceback.print_exc()

# ===== 4. 综合报告 =====
log(">>> 阶段4: 生成综合报告")
try:
    from src.services.comprehensive_report import generate_comprehensive_report
    report_path = os.path.join(OUTPUT_DIR, "comprehensive_report.md")
    generate_comprehensive_report(OUTPUT_DIR, report_path)
    log(f"<<< 综合报告已生成: {report_path}")
except Exception as e:
    log(f"!!! 综合报告 失败: {e}")
    import traceback
    traceback.print_exc()

log("=== 全部完成 ===")
