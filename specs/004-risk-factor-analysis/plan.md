# Implementation Plan: 组织参与与控制风险分析（Bus Factor）

**Branch**: `004-risk-factor-analysis` | **Date**: 2024-12-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-risk-factor-analysis/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

实现 Bus Factor（公交因子）计算与分析功能，用于评估开源项目对关键贡献者的依赖程度。系统需要：
1. 从 actor-repo 图文件中加载图数据并计算每个贡献者的贡献量
2. 计算 Bus Factor（达到50%贡献所需的最少贡献者数量）
3. 为每个项目的每个月生成月度风险指标时间序列
4. 计算跨月趋势和综合风险评分
5. 支持断点续传和可配置的贡献权重公式

技术方法：参考现有的 `burnout_analyzer.py` 和 `community_atmosphere_analyzer.py` 的实现模式，使用 NetworkX 处理图数据，采用时间序列分析方法。

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: NetworkX（图处理）、dataclasses（数据模型）、pathlib（文件操作）、json（数据序列化）  
**Storage**: JSON 文件（输出分析结果）  
**Testing**: pytest（单元测试和集成测试）  
**Target Platform**: Linux/macOS/Windows（跨平台 Python 应用）  
**Project Type**: 单项目（命令行工具）  
**Performance Goals**: 能够处理至少100个项目的分析任务，每个项目至少包含12个月的指标数据，整个分析过程在合理时间内完成（不超过2小时）  
**Constraints**: 
- 内存使用：需要能够处理大型图文件（可能包含数万个节点和边）
- 浮点数精度：确保阈值计算（50%）的准确性
- 错误处理：必须能够处理图文件缺失、损坏等异常情况，记录错误信息但继续处理其他文件
**Scale/Scope**: 
- 输入：多个项目的多个月份的 actor-repo 图文件（通过 `index.json` 索引）
- 输出：每个项目的月度指标时间序列、趋势分析和综合评分（JSON 格式）
- 支持断点续传，能够识别已处理的月份并跳过

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**检查项**：
- ✅ 功能范围明确：仅实现 Bus Factor，暂不实现 Elephant Factor（已在 spec 中明确说明）
- ✅ 技术栈一致：使用与现有项目相同的 Python + NetworkX 技术栈
- ✅ 代码结构一致：参考现有的 `burnout_analyzer.py` 和 `community_atmosphere_analyzer.py` 的实现模式
- ✅ 输出格式一致：使用 JSON 格式输出，与现有分析器保持一致
- ✅ 错误处理完善：必须能够处理各种边界情况和异常情况

**无违反项，可以继续。**

## Project Structure

### Documentation (this feature)

```text
specs/004-risk-factor-analysis/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── analysis/
│   ├── bus_factor_analyzer.py      # Bus Factor 分析器主类（新增）
│   ├── burnout_analyzer.py          # 参考实现
│   └── community_atmosphere_analyzer.py  # 参考实现
├── models/
│   └── bus_factor.py                # Bus Factor 数据模型（新增）
├── algorithms/
│   └── bus_factor_calculator.py     # Bus Factor 计算算法（新增）
└── utils/
    └── logger.py                     # 日志工具（已存在）

output/
└── bus-factor-analysis/              # 分析结果输出目录（新增）
    ├── full_analysis.json            # 完整分析结果（所有项目的所有月份）
    └── summary.json                  # 摘要（按风险评分排序）

tests/
├── unit/
│   ├── test_bus_factor_calculator.py    # 单元测试
│   └── test_bus_factor_analyzer.py      # 分析器测试
└── integration/
    └── test_bus_factor_integration.py   # 集成测试
```

**Structure Decision**: 采用单项目结构，与现有的 `burnout_analyzer` 和 `community_atmosphere_analyzer` 保持一致。新增 `bus_factor_analyzer.py` 作为主分析器，`bus_factor.py` 作为数据模型，`bus_factor_calculator.py` 作为核心计算算法。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 无 | - | - |
