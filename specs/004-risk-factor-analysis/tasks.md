# 任务列表：组织参与与控制风险分析（Bus Factor）

**Feature**: 组织参与与控制风险分析（Bus Factor）  
**Branch**: `004-risk-factor-analysis`  
**Date**: 2024-12-19  
**Status**: 已完成（所有阶段已完成）

## 任务概览

- **总任务数**: 45
- **用户故事 1 (P1)**: 18 个任务
- **用户故事 2 (P2)**: 12 个任务
- **用户故事 3 (P3)**: 10 个任务
- **收尾工作**: 5 个任务

## 依赖关系

```
Phase 1 (设置) 
  ↓
Phase 2 (基础) 
  ↓
Phase 3 (用户故事 1 - P1) → 独立可测试
  ↓
Phase 4 (用户故事 2 - P2) → 依赖 US1
  ↓
Phase 5 (用户故事 3 - P3) → 依赖 US2
  ↓
Phase 6 (收尾工作)
```

## 并行执行机会

- **Phase 3 (US1)**: 数据模型、计算算法、分析器可以并行开发（不同文件）
- **Phase 4 (US2)**: 时间序列处理和断点续传可以并行开发
- **Phase 5 (US3)**: 趋势计算和风险评分可以并行开发

## 实现策略

**MVP 范围**: 仅实现用户故事 1（计算单个项目的月度风险指标）

**增量交付**:
1. **MVP**: 用户故事 1 - 能够计算单个项目的单个月份的 Bus Factor
2. **增量 1**: 用户故事 2 - 支持所有项目的时间序列分析
3. **增量 2**: 用户故事 3 - 添加趋势分析和综合评分

---

## Phase 1: 项目设置

**目标**: 初始化项目结构，创建必要的目录和文件

### 设置任务

- [x] T001 创建输出目录 `output/bus-factor-analysis/`（如果不存在）
- [x] T002 创建测试目录 `tests/unit/` 和 `tests/integration/`（如果不存在）
- [x] T003 创建日志目录 `logs/`（如果不存在）

---

## Phase 2: 基础组件

**目标**: 实现基础组件，为所有用户故事提供支持

### 数据模型

- [x] T004 [P] 创建数据模型文件 `src/models/bus_factor.py`，定义 `ContributorContribution` 数据类
- [x] T005 [P] 在 `src/models/bus_factor.py` 中实现 `ContributorContribution.to_dict()` 方法
- [x] T006 [P] 在 `src/models/bus_factor.py` 中定义 `MonthlyRiskMetrics` 数据类
- [x] T007 [P] 在 `src/models/bus_factor.py` 中实现 `MonthlyRiskMetrics.to_dict()` 方法
- [x] T008 [P] 在 `src/models/bus_factor.py` 中定义 `TrendAnalysis` 数据类
- [x] T009 [P] 在 `src/models/bus_factor.py` 中实现 `TrendAnalysis.to_dict()` 方法
- [x] T010 [P] 在 `src/models/bus_factor.py` 中定义 `RiskScore` 数据类
- [x] T011 [P] 在 `src/models/bus_factor.py` 中实现 `RiskScore.to_dict()` 方法

### 核心计算算法

- [x] T012 [P] 创建计算算法文件 `src/algorithms/bus_factor_calculator.py`，实现 `calculate_bus_factor()` 函数
- [x] T013 [P] 在 `src/algorithms/bus_factor_calculator.py` 中实现 `aggregate_contributions()` 函数，支持可配置权重
- [x] T014 [P] 在 `src/algorithms/bus_factor_calculator.py` 中定义默认权重配置 `DEFAULT_WEIGHTS`
- [x] T015 [P] 在 `src/algorithms/bus_factor_calculator.py` 中添加浮点数精度处理（使用 `math.isclose` 或 `numpy.isclose`）

---

## Phase 3: 用户故事1 - 计算单个项目的月度风险指标 (Priority: P1) 🎯 MVP

**目标**: 实现分析单个开源项目在特定月份的组织参与与控制风险，通过计算该月的 Bus Factor 来评估项目对关键贡献者的依赖程度。

**独立测试**: 可以通过加载单个项目的单个月份的 actor-repo 图文件，运行分析工具，验证系统能够正确计算该月的 Bus Factor，并输出包含详细指标信息的 JSON 结果。

### 实现 - 用户故事1

- [x] T016 [US1] 创建分析器文件 `src/analysis/bus_factor_analyzer.py`，定义 `BusFactorAnalyzer` 类（基础结构，参考 `BurnoutAnalyzer`）
- [x] T017 [US1] 在 `BusFactorAnalyzer.__init__()` 中初始化参数（graphs_dir, output_dir, threshold, weights）
- [x] T018 [US1] 在 `BusFactorAnalyzer` 中实现 `load_graph()` 方法，加载 GraphML 文件
- [x] T019 [US1] 在 `BusFactorAnalyzer` 中实现 `compute_monthly_metrics()` 方法，计算单个月份的风险指标
- [x] T020 [US1] 在 `compute_monthly_metrics()` 中集成 `aggregate_contributions()` 计算贡献量
- [x] T021 [US1] 在 `compute_monthly_metrics()` 中集成 `calculate_bus_factor()` 计算 Bus Factor
- [x] T022 [US1] 在 `compute_monthly_metrics()` 中处理边界情况（空图、贡献量为0等）
- [x] T023 [US1] 在 `BusFactorAnalyzer` 中添加错误处理和日志记录（使用 `get_logger()`）
- [x] T024 [US1] 实现命令行入口，在 `src/analysis/bus_factor_analyzer.py` 中添加 `if __name__ == "__main__"` 块
- [x] T025 [US1] 在命令行入口中添加参数解析（--graphs-dir, --output-dir, --threshold, --weights-file）
- [x] T026 [US1] 在命令行入口中实现单项目单月份分析模式（用于测试）
- [x] T027 [US1] 在 `BusFactorAnalyzer` 中实现 `save_single_result()` 方法，保存单个月份的分析结果到 JSON
- [x] T028 [US1] 添加数据验证：验证 `MonthlyRiskMetrics` 的所有字段
- [x] T029 [US1] 添加边界情况处理：当图文件中没有边时返回合理的默认值
- [x] T030 [US1] 添加边界情况处理：当所有贡献者的贡献量完全相同时正确处理
- [x] T031 [US1] 添加边界情况处理：当贡献量总和为0时返回合理的默认值
- [x] T032 [US1] 添加边界情况处理：当图文件损坏或格式不正确时捕获异常并记录错误
- [x] T033 [US1] 添加浮点数精度处理：在阈值计算中使用 `math.isclose` 确保准确判断是否达到50%阈值

**检查点**: 此时，用户故事1应该完全功能化并可独立测试。可以通过运行 `python -m src.analysis.bus_factor_analyzer --repo angular-angular --month 2023-01` 来测试单项目单月份的分析。

---

## Phase 4: 用户故事2 - 分析所有项目的月度风险指标时间序列 (Priority: P2)

**目标**: 实现分析所有项目在整个时间序列上的风险指标变化，为每个项目生成月度指标时间序列，以便观察项目风险的变化趋势。

**独立测试**: 可以通过运行分析工具，验证系统能够自动加载所有项目的 actor-repo 图文件，为每个项目生成完整的月度指标时间序列，并输出包含所有月份数据的 JSON 结果。

### 实现 - 用户故事2

- [x] T034 [US2] 在 `BusFactorAnalyzer` 中实现 `load_index()` 方法，从 `index.json` 加载项目索引
- [x] T035 [US2] 在 `BusFactorAnalyzer` 中实现 `analyze_all_repos()` 方法，遍历所有项目和月份
- [x] T036 [US2] 在 `analyze_all_repos()` 中为每个项目生成月度指标时间序列
- [x] T037 [US2] 在 `analyze_all_repos()` 中处理缺失月份：跳过缺失的月份，在日志中记录缺失信息
- [x] T038 [US2] 在 `analyze_all_repos()` 中实现错误处理：当某个项目或月份的计算失败时，记录错误但继续处理其他项目
- [x] T039 [US2] 在 `BusFactorAnalyzer` 中实现 `save_results()` 方法，保存完整分析结果到 `full_analysis.json`
- [x] T040 [US2] 在 `save_results()` 中实现增量保存：每完成一个月份就写入文件（支持断点续传）
- [x] T041 [US2] 在 `analyze_all_repos()` 中实现断点续传：检查已存在的 `full_analysis.json`，跳过已处理的月份
- [x] T042 [US2] 在命令行入口中添加 `--no-resume` 参数，允许禁用断点续传
- [x] T043 [US2] 在 `analyze_all_repos()` 中添加进度显示（使用 `tqdm` 或类似工具）
- [x] T044 [US2] 在 `analyze_all_repos()` 中处理边界情况：当某个项目的所有月份都缺失时跳过该项目
- [x] T045 [US2] 优化内存使用：及时释放不需要的图对象，避免内存泄漏

**检查点**: 此时，用户故事2应该完全功能化并可独立测试。可以通过运行 `python -m src.analysis.bus_factor_analyzer` 来测试所有项目的时间序列分析。

---

## Phase 5: 用户故事3 - 计算跨月趋势和综合风险评分 (Priority: P3)

**目标**: 实现基于月度指标时间序列计算跨月趋势，并生成综合风险评分，以便快速识别高风险项目。

**独立测试**: 可以通过运行分析工具，验证系统能够基于月度指标时间序列计算趋势指标（如 Bus Factor 的变化趋势），并生成综合风险评分。

### 实现 - 用户故事3

- [x] T046 [US3] 在 `BusFactorAnalyzer` 中实现 `calculate_trend()` 函数，使用线性回归计算趋势
- [x] T047 [US3] 在 `calculate_trend()` 中判断趋势方向（上升/下降/稳定）
- [x] T048 [US3] 在 `calculate_trend()` 中计算变化率（百分比）
- [x] T049 [US3] 在 `BusFactorAnalyzer` 中实现 `compute_trends()` 方法，为所有项目计算趋势分析
- [x] T050 [US3] 在 `compute_trends()` 中处理数据不足的情况：当项目只有1-2个月的数据时标记为"数据不足"
- [x] T051 [US3] 在 `BusFactorAnalyzer` 中实现 `calculate_risk_score()` 函数，计算综合风险评分
- [x] T052 [US3] 在 `calculate_risk_score()` 中计算当前值得分（基于 Bus Factor 值）
- [x] T053 [US3] 在 `calculate_risk_score()` 中计算趋势得分（基于趋势方向）
- [x] T054 [US3] 在 `calculate_risk_score()` 中确定风险等级（低/中/高）
- [x] T055 [US3] 在 `BusFactorAnalyzer` 中实现 `compute_risk_scores()` 方法，为所有项目计算风险评分
- [x] T056 [US3] 在 `save_results()` 中保存趋势分析和风险评分到 `full_analysis.json`
- [x] T057 [US3] 在 `BusFactorAnalyzer` 中实现 `save_summary()` 方法，生成 `summary.json`（按风险评分排序）
- [x] T058 [US3] 在 `save_summary()` 中按风险评分降序排序项目
- [x] T059 [US3] 在命令行入口中集成趋势分析和风险评分计算

**检查点**: 此时，用户故事3应该完全功能化并可独立测试。可以通过运行完整分析流程来验证趋势分析和风险评分功能。

---

## Phase 6: 收尾工作

**目标**: 完善功能，添加文档和测试

### 文档和测试

- [x] T060 更新 `README.md`，添加 Bus Factor 分析的使用说明
- [x] T061 在 `quickstart.md` 中添加实际使用示例（如果尚未完成）
- [x] T062 创建单元测试文件 `tests/unit/test_bus_factor_calculator.py`，测试核心计算算法
- [x] T063 创建单元测试文件 `tests/unit/test_bus_factor_analyzer.py`，测试分析器功能
- [x] T064 创建集成测试文件 `tests/integration/test_bus_factor_integration.py`，测试完整流程

---

## 任务统计

- **Phase 1 (设置)**: 3 个任务
- **Phase 2 (基础)**: 12 个任务
- **Phase 3 (US1)**: 18 个任务
- **Phase 4 (US2)**: 12 个任务
- **Phase 5 (US3)**: 14 个任务
- **Phase 6 (收尾)**: 5 个任务
- **总计**: 64 个任务

## 注意事项

1. **并行开发**: 标记为 `[P]` 的任务可以并行开发（不同文件，无依赖）
2. **用户故事标签**: 所有用户故事阶段的任务都标记了 `[US1]`, `[US2]`, `[US3]`
3. **文件路径**: 每个任务都包含了明确的文件路径
4. **MVP 范围**: 建议先完成 Phase 1-3（用户故事1），这是 MVP 范围
5. **测试**: 每个用户故事完成后都应该进行独立测试

## 下一步

1. 开始实现 Phase 1 和 Phase 2 的基础组件
2. 实现 Phase 3 的用户故事1（MVP）
3. 测试 MVP 功能
4. 继续实现 Phase 4 和 Phase 5
5. 完成 Phase 6 的收尾工作

