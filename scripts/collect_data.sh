#!/bin/bash
# GitHub Archive 数据收集脚本
# 
# 使用方式:
#   ./scripts/collect_data.sh [采样模式]
#
# 采样模式:
#   daily   - 每天1小时（默认，约730个文件/年）
#   weekly  - 每周1小时（约104个文件/年）
#   monthly - 每月1小时（约24个文件/年）

set -e

# 默认参数
SAMPLE_MODE=${1:-daily}
START_DATE="2023-01-01"
END_DATE="2025-01-20"
OUTPUT_DIR="data/filtered"
PROJECT_COUNT=100

# 切换到项目根目录
cd "$(dirname "$0")/.."

# 激活虚拟环境
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

echo "=========================================="
echo "GitHub Archive 数据收集"
echo "=========================================="
echo "时间范围: $START_DATE 到 $END_DATE"
echo "采样模式: $SAMPLE_MODE"
echo "项目数量: $PROJECT_COUNT"
echo "输出目录: $OUTPUT_DIR"
echo "=========================================="

# 预估数据量
case $SAMPLE_MODE in
    hourly)
        echo "预估文件数: ~17,500"
        echo "预估下载量: ~700 GB"
        echo "预估过滤后: ~10-50 GB"
        ;;
    daily)
        echo "预估文件数: ~730"
        echo "预估下载量: ~30 GB"
        echo "预估过滤后: ~0.5-2 GB"
        ;;
    weekly)
        echo "预估文件数: ~104"
        echo "预估下载量: ~4 GB"
        echo "预估过滤后: ~50-200 MB"
        ;;
    monthly)
        echo "预估文件数: ~24"
        echo "预估下载量: ~1 GB"
        echo "预估过滤后: ~10-50 MB"
        ;;
esac

echo "=========================================="
echo "按 Ctrl+C 可随时中断，进度会自动保存"
echo "再次运行相同命令可从断点继续"
echo "=========================================="
echo ""

read -p "确认开始? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

# 运行收集器
python -m src.data_collection.gharchive_collector \
    --start-date "$START_DATE" \
    --end-date "$END_DATE" \
    --sample-mode "$SAMPLE_MODE" \
    --output-dir "$OUTPUT_DIR" \
    --project-count "$PROJECT_COUNT"

echo ""
echo "=========================================="
echo "数据收集完成!"
echo "输出目录: $OUTPUT_DIR"
echo "=========================================="
