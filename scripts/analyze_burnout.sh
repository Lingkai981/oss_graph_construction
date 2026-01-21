#!/bin/bash
# 维护者倦怠分析完整流程
#
# 使用方式:
#   ./scripts/analyze_burnout.sh
#
# 流程:
#   1. 按月构建所有项目的 Actor-Actor 协作图
#   2. 对每个项目运行倦怠分析算法
#   3. 输出分析报告和预警列表

set -e

# 切换到项目根目录
cd "$(dirname "$0")/.."

# 激活虚拟环境
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

echo "=========================================="
echo "维护者倦怠分析"
echo "=========================================="

# 检查数据是否存在
if [ ! -d "data/filtered" ] || [ -z "$(ls -A data/filtered 2>/dev/null)" ]; then
    echo "错误: 未找到过滤后的数据"
    echo "请先运行数据收集脚本:"
    echo "  ./scripts/collect_data.sh daily"
    exit 1
fi

# 统计数据
FILE_COUNT=$(ls data/filtered/*-filtered.json 2>/dev/null | wc -l | tr -d ' ')
echo "已找到 $FILE_COUNT 个数据文件"

# Step 1: 构建月度图
echo ""
echo "=========================================="
echo "Step 1: 构建月度 Actor-Actor 协作图"
echo "=========================================="

python -m src.analysis.monthly_graph_builder \
    --data-dir data/filtered/ \
    --output-dir output/monthly-graphs/

# Step 2: 运行倦怠分析
echo ""
echo "=========================================="
echo "Step 2: 运行倦怠分析算法"
echo "=========================================="

python -m src.analysis.burnout_analyzer \
    --graphs-dir output/monthly-graphs/ \
    --output-dir output/burnout-analysis/

echo ""
echo "=========================================="
echo "分析完成!"
echo "=========================================="
echo ""
echo "输出文件:"
echo "  - output/monthly-graphs/          月度图数据"
echo "  - output/burnout-analysis/        分析结果"
echo "    - summary.json                  项目风险摘要（按风险排序）"
echo "    - all_alerts.json               所有预警列表"
echo "    - full_analysis.json            完整分析数据"
echo ""
echo "查看高风险项目:"
echo "  cat output/burnout-analysis/summary.json | head -50"
echo ""
