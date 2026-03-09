#!/bin/bash
# 维护者倦怠分析完整流程
#
# 使用方式:
#   ./scripts/analyze_burnout.sh
#
# 流程:
#   1. 检查 Kuzu 数据库是否存在
#   2. 对每个项目运行倦怠分析算法（从 Kuzu 查询）
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

# 检查 Kuzu 数据库
if [ ! -f "output/kuzu_db.kuzu" ]; then
    echo "错误: 未找到 Kuzu 数据库 output/kuzu_db.kuzu"
    echo "请先准备 Kuzu 数据库（例如先执行 CSV 导入脚本）"
    exit 1
fi

# Step 1: 运行倦怠分析
echo ""
echo "=========================================="
echo "Step 1: 运行倦怠分析算法（Kuzu）"
echo "=========================================="

python -m src.analysis.burnout_analyzer \
    --db-path output/kuzu_db.kuzu \
    --output-dir output/burnout-analysis/

echo ""
echo "=========================================="
echo "分析完成!"
echo "=========================================="
echo ""
echo "输出文件:"
echo "  - output/burnout-analysis/        分析结果"
echo "    - summary.json                  项目风险摘要（按风险排序）"
echo "    - all_alerts.json               所有预警列表"
echo "    - full_analysis.json            完整分析数据"
echo ""
echo "查看高风险项目:"
echo "  cat output/burnout-analysis/summary.json | head -50"
echo ""
