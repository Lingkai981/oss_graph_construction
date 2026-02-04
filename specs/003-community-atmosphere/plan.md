# 实现计划：社区氛围分析

**分支**：`003-community-atmosphere` | **日期**：2024-12-19 | **规范**：[spec.md](./spec.md)
**输入**：特性规范来自 `/specs/003-community-atmosphere/spec.md`

**注意**：此模板由 `/speckit.plan` 命令填写。执行工作流请参见 `.specify/templates/commands/plan.md`。

## 摘要

实现一个社区氛围分析系统，从actor-discussion图文件中提取评论数据，使用三个核心图算法（情感传播模型、聚类系数、网络直径）分析社区氛围。系统参考维护者倦怠分析的结构，自动处理整个时间序列，为每个项目生成月度指标时间序列和综合评分。情感分析必须使用DeepSeek API。系统采用Python实现，所有代码注释和文档使用中文。

## 技术上下文

**语言/版本**：Python 3.8+  
**主要依赖**：NetworkX（图算法）、requests（API调用）、numpy（数值计算）、python-dotenv（环境变量管理）  
**存储**：文件系统（读取GraphML图文件，输出JSON结果文件）  
**测试**：pytest  
**目标平台**：跨平台（Windows/Linux/macOS）  
**项目类型**：单项目（命令行工具，与现有分析模块集成）  
**性能目标**：系统能够在合理时间内完成所有项目的整个时间序列分析  
**约束**：所有输出使用中文，必须使用DeepSeek API进行情感分析（通过.env文件配置），处理非ASCII字符（中文、emoji）  
**规模/范围**：处理actor-discussion图文件，自动处理所有项目的整个时间序列，单文件不超过50万节点

## Constitution Check

*GATE: 必须在Phase 0研究前通过。Phase 1设计后重新检查。*

由于constitution文件是模板格式，当前项目遵循以下原则：
- 代码质量：使用Python标准库和成熟第三方库（NetworkX、requests）
- 文档：所有注释和文档使用中文
- 测试：使用pytest进行单元测试和集成测试
- 错误处理：采用记录并跳过策略，确保系统健壮性
- API集成：必须使用DeepSeek API进行情感分析

## 项目结构

### 文档（此特性）

```text
specs/003-community-atmosphere/
├── plan.md              # 本文件（/speckit.plan命令输出）
├── research.md          # Phase 0输出（/speckit.plan命令）
├── data-model.md        # Phase 1输出（/speckit.plan命令）
├── quickstart.md        # Phase 1输出（/speckit.plan命令）
├── contracts/           # Phase 1输出（/speckit.plan命令）
└── tasks.md             # Phase 2输出（/speckit.tasks命令 - 不由/speckit.plan创建）
```

### 源代码（仓库根目录）

```text
src/
├── analysis/            # 分析模块（已存在）
│   ├── __init__.py
│   ├── burnout_analyzer.py      # 倦怠分析器（已存在）
│   ├── monthly_graph_builder.py # 月度图构建器（已存在）
│   └── community_atmosphere_analyzer.py  # 社区氛围分析器（新增）
├── services/            # 服务模块（已存在）
│   └── sentiment/       # 情感分析服务（新增）
│       └── deepseek_client.py   # DeepSeek API客户端
├── algorithms/          # 图算法模块（新增）
│   ├── __init__.py
│   ├── emotion_propagation.py   # 情感传播模型
│   ├── clustering_coefficient.py # 聚类系数计算
│   └── network_diameter.py       # 网络直径计算
├── models/              # 数据模型（已存在）
│   └── community_atmosphere.py  # 社区氛围指标模型（新增）

tests/
├── unit/                # 单元测试（已存在）
│   ├── test_emotion_propagation.py
│   ├── test_clustering_coefficient.py
│   └── test_network_diameter.py

output/                  # 输出目录（已存在）
└── community-atmosphere/  # 社区氛围分析结果（新增）
    ├── full_analysis.json  # 完整分析结果
    └── summary.json        # 摘要结果
```

**结构决策**：采用单项目结构，与现有的分析模块（burnout_analyzer）保持一致的组织方式和代码风格。新增的社区氛围分析器放在`src/analysis/`目录下，参考burnout_analyzer的结构，使用整个时间序列分析。图算法独立为`algorithms/`模块便于复用和测试，情感分析服务使用DeepSeek API客户端。

## 复杂度跟踪

> **仅在Constitution Check有需要证明的违规时填写**

无违规情况。
