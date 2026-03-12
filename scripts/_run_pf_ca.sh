#!/bin/bash
cd /Users/milk/Documents/ali2025/oss_graph_construction
exec python3 -u run_analysis.py \
  --analyzers personnel_flow community_atmosphere \
  --reports atmosphere_report comprehensive_report \
  --graphs-dir output/monthly-graphs \
  --output-dir output/report \
  --workers 8 \
  --continue-on-error
