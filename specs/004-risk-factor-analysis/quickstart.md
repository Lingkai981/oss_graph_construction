# 快速开始：Bus Factor 分析

**Feature**: 组织参与与控制风险分析（Bus Factor）  
**Date**: 2024-12-19

## 概述

Bus Factor（公交因子）分析用于评估开源项目对关键贡献者的依赖程度。Bus Factor 值表示达到总贡献量50%所需的最少贡献者数量。值越小，表示项目越依赖少数关键贡献者，风险越高。

## 前置条件

1. **Python 环境**: Python 3.11+
2. **依赖包**: 已安装 `requirements.txt` 中的所有依赖
3. **图数据**: 已构建 actor-repo 图文件（位于 `output/monthly-graphs/`）

### 检查图数据

确保图数据已构建：

```bash
# 检查图文件目录
ls output/monthly-graphs/

# 应该看到类似结构：
# angular-angular/
#   actor-repo/
#     2023-01.graphml
#     2023-02.graphml
#     ...
# index.json
```

如果图数据不存在，请先运行图构建：

```bash
python -m src.analysis.monthly_graph_builder \
  --data-dir data/filtered \
  --output-dir output/monthly-graphs \
  --graph-types actor-repo \
  --workers 4
```

## 基本使用

### 1. 使用默认配置运行分析

```bash
python -m src.analysis.bus_factor_analyzer
```

这将：
- 从 `output/monthly-graphs/` 读取所有项目的 actor-repo 图文件
- 计算每个项目的每个月的 Bus Factor
- 生成时间序列趋势分析
- 计算综合风险评分
- 保存结果到 `output/bus-factor-analysis/`

### 2. 自定义输出目录

```bash
python -m src.analysis.bus_factor_analyzer \
  --output-dir output/my-bus-factor-analysis/
```

### 3. 自定义阈值

默认阈值为 50%（0.5）。可以自定义：

```bash
python -m src.analysis.bus_factor_analyzer \
  --threshold 0.6  # 使用 60% 作为阈值
```

## 高级配置

### 自定义贡献权重

默认权重配置：
- `commit_count`: 1.0（提交次数）
- `pr_merged`: 5.0（合并的 PR，高价值）
- `pr_opened`: 2.0（打开的 PR）
- `pr_closed`: 1.0（关闭的 PR）
- `issue_opened`: 1.5（打开的 Issue）
- `issue_closed`: 2.0（关闭的 Issue）
- `is_comment`: 0.5（评论）

创建权重配置文件 `config/weights.json`：

```json
{
  "commit_count": 1.0,
  "pr_merged": 6.0,
  "pr_opened": 2.5,
  "pr_closed": 1.0,
  "issue_opened": 1.5,
  "issue_closed": 2.0,
  "is_comment": 0.5
}
```

使用自定义权重：

```bash
python -m src.analysis.bus_factor_analyzer \
  --weights-file config/weights.json
```

## 输出结果

### 输出文件结构

```
output/bus-factor-analysis/
├── full_analysis.json    # 完整分析结果
└── summary.json          # 摘要（按风险评分排序）
```

### full_analysis.json 格式

```json
{
  "angular/angular": {
    "metrics": [
      {
        "month": "2023-01",
        "repo_name": "angular/angular",
        "bus_factor": 5,
        "total_contribution": 1234.5,
        "contributor_count": 50,
        "contributors": [
          {
            "contributor_id": 12345,
            "login": "contributor1",
            "total_contribution": 300.0,
            "contribution_ratio": 0.243,
            "commit_count": 100,
            "pr_merged": 10,
            ...
          },
          ...
        ]
      },
      ...
    ],
    "trend": {
      "repo_name": "angular/angular",
      "bus_factor_trend": {
        "direction": "上升",
        "slope": 0.5,
        "change_rate": 10.0
      },
      "months": ["2023-01", "2023-02", ...],
      "bus_factor_values": [5, 6, ...]
    },
    "risk_score": {
      "repo_name": "angular/angular",
      "total_score": 65.5,
      "current_score": 35.0,
      "trend_score": 30.5,
      "risk_level": "中",
      "current_bus_factor": 5,
      "trend_direction": "上升"
    }
  },
  ...
}
```

### summary.json 格式

```json
{
  "summary": [
    {
      "repo_name": "project1",
      "risk_score": {
        "total_score": 75.0,
        "risk_level": "高",
        ...
      },
      "current_bus_factor": 3,
      "trend_direction": "上升"
    },
    ...
  ],
  "sorted_by": "risk_score"
}
```

## 断点续传

分析支持断点续传。如果分析过程中断，重新运行相同命令会自动跳过已处理的月份：

```bash
# 第一次运行（处理所有月份）
python -m src.analysis.bus_factor_analyzer

# 如果中断，再次运行会自动跳过已处理的月份
python -m src.analysis.bus_factor_analyzer
```

要禁用断点续传（重新开始）：

```bash
python -m src.analysis.bus_factor_analyzer --no-resume
```

## 常见问题

### Q: 分析时间过长怎么办？

A: 分析时间取决于项目数量和月份数量。可以：
1. 使用 `--workers` 参数（如果支持并行处理）
2. 分批处理项目（修改代码过滤特定项目）
3. 使用断点续传功能，分多次运行

### Q: 如何只分析特定项目？

A: 当前版本不支持命令行参数过滤项目。可以：
1. 修改 `index.json`，只保留需要分析的项目
2. 修改代码，添加项目过滤逻辑

### Q: 如何理解 Bus Factor 值？

A: 
- **Bus Factor = 1**: 项目完全依赖一个贡献者（高风险）
- **Bus Factor = 5**: 项目依赖 5 个贡献者达到 50% 贡献（中等风险）
- **Bus Factor = 20**: 项目依赖 20 个贡献者达到 50% 贡献（低风险）

值越小，风险越高。

### Q: 如何理解风险评分？

A: 风险评分范围 0-100，分数越高风险越高：
- **0-40**: 低风险（绿色）
- **40-70**: 中等风险（黄色）
- **70-100**: 高风险（红色）

评分综合考虑：
- 当前 Bus Factor 值（50分）
- 变化趋势（50分）

## 下一步

1. **查看详细文档**: 阅读 `data-model.md` 了解数据模型
2. **查看 API 文档**: 阅读 `contracts/README.md` 了解接口定义
3. **运行测试**: 运行单元测试和集成测试
4. **自定义分析**: 根据需要调整权重配置和阈值

## 参考

- **规范文档**: `spec.md`
- **实现计划**: `plan.md`
- **研究文档**: `research.md`
- **数据模型**: `data-model.md`
- **API 契约**: `contracts/README.md`

