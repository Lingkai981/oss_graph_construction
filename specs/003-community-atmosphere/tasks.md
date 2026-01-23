# 任务列表：社区氛围分析

**输入**：设计文档来自 `/specs/003-community-atmosphere/`
**前置条件**：plan.md（必需）、spec.md（用户故事必需）、research.md、data-model.md、contracts/

**测试**：以下示例包含测试任务。测试是可选的 - 仅在特性规范中明确要求时包含。

**组织方式**：任务按用户故事分组，以便每个故事可以独立实现和测试。

## 格式：`[ID] [P?] [Story] 描述`

- **[P]**：可以并行运行（不同文件，无依赖关系）
- **[Story]**：此任务属于哪个用户故事（如US1、US3）
- 描述中包含确切的文件路径

## 路径约定

- **单项目**：仓库根目录下的 `src/`、`tests/`
- 以下路径假设单项目结构 - 根据plan.md结构调整

## Phase 1: 设置（共享基础设施）

**目的**：项目初始化和基本结构

- [x] T001 创建项目目录结构（src/algorithms/、src/services/sentiment/）
- [x] T002 [P] 创建src/algorithms/__init__.py
- [x] T003 [P] 创建src/services/sentiment/目录（不需要__init__.py）
- [x] T004 [P] 更新requirements.txt添加numpy依赖（如果缺失）

---

## Phase 2: 基础（阻塞性前置条件）

**目的**：核心基础设施，必须在任何用户故事实现前完成

**⚠️ 关键**：此阶段完成前，不能开始任何用户故事工作

- [x] T005 [P] 创建数据模型MonthlyAtmosphereMetrics在src/models/community_atmosphere.py
- [x] T006 [P] 实现情感传播算法在src/algorithms/emotion_propagation.py
- [x] T007 [P] 实现聚类系数算法在src/algorithms/clustering_coefficient.py
- [x] T008 [P] 实现网络直径算法在src/algorithms/network_diameter.py
- [x] T009 实现DeepSeek API客户端在src/services/sentiment/deepseek_client.py

**检查点**：基础就绪 - 现在可以开始用户故事实现

---

## Phase 3: 用户故事1 - 分析所有项目的社区氛围指标 (Priority: P1) 🎯 MVP

**目标**：实现分析所有项目的整个时间序列，为每个项目生成月度指标时间序列和综合评分

**独立测试**：可以通过运行分析工具，验证系统能够自动加载所有项目的actor-discussion图文件，为每个项目生成月度指标时间序列，并输出综合评分

### 实现 - 用户故事1

- [x] T010 [US1] 实现CommunityAtmosphereAnalyzer类在src/analysis/community_atmosphere_analyzer.py（基础结构，参考BurnoutAnalyzer）
- [x] T011 [US1] 实现load_graph方法在src/analysis/community_atmosphere_analyzer.py
- [x] T012 [US1] 实现extract_sentiment_from_comments方法在src/analysis/community_atmosphere_analyzer.py（使用DeepSeek API）
- [x] T013 [US1] 实现compute_monthly_metrics方法在src/analysis/community_atmosphere_analyzer.py（单月分析）
- [x] T014 [US1] 集成情感传播算法到compute_monthly_metrics在src/analysis/community_atmosphere_analyzer.py
- [x] T015 [US1] 集成聚类系数算法到compute_monthly_metrics在src/analysis/community_atmosphere_analyzer.py
- [x] T016 [US1] 集成网络直径算法到compute_monthly_metrics在src/analysis/community_atmosphere_analyzer.py
- [x] T017 [US1] 实现compute_atmosphere_score方法在src/analysis/community_atmosphere_analyzer.py（计算综合评分）
- [x] T018 [US1] 实现analyze_all_repos方法在src/analysis/community_atmosphere_analyzer.py（处理整个时间序列）
- [x] T019 [US1] 实现save_results方法在src/analysis/community_atmosphere_analyzer.py（保存JSON结果，类似burnout_analyzer）
- [x] T020 [US1] 实现run方法在src/analysis/community_atmosphere_analyzer.py（主入口）
- [x] T021 [US1] 添加错误处理（图文件缺失、损坏等情况）
- [x] T022 [US1] 添加日志记录在src/analysis/community_atmosphere_analyzer.py

**检查点**：此时，用户故事1应该完全功能化并可独立测试

---

## Phase 4: 用户故事3 - 使用DeepSeek大模型进行情感分析 (Priority: P3)

**目标**：集成DeepSeek API进行情感分析，系统必须使用DeepSeek API，如果API不可用，分析将失败并给出明确错误信息

**独立测试**：可以通过配置DeepSeek API key，验证系统能够调用API进行情感分析，并返回情感分数。如果API key未配置或调用失败，系统应给出明确的错误信息。

### 实现 - 用户故事3

- [x] T023 [US3] 实现DeepSeekClient类在src/services/sentiment/deepseek_client.py
- [x] T024 [US3] 实现API调用逻辑（POST请求，包含comment_body文本）
- [x] T025 [US3] 实现超时和重试机制在DeepSeekClient中
- [x] T026 [US3] 实现API可用性检测（is_available方法）
- [x] T027 [US3] 集成DeepSeekClient到CommunityAtmosphereAnalyzer中
- [x] T028 [US3] 添加环境变量读取（DEEPSEEK_API_KEY）
- [x] T029 [US3] 添加错误日志记录（记录API调用失败的情况）

**检查点**：所有用户故事现在都应该能够独立工作

---

## Phase 5: 完善与跨领域关注点

**目的**：影响多个用户故事的改进

- [x] T030 [P] 添加单元测试test_emotion_propagation.py在tests/unit/
- [x] T031 [P] 添加单元测试test_clustering_coefficient.py在tests/unit/
- [x] T032 [P] 添加单元测试test_network_diameter.py在tests/unit/
- [x] T033 代码清理和重构（确保所有代码符合项目规范，参考burnout_analyzer的风格）
- [x] T034 处理边界情况（空图、单节点图、非ASCII字符等）
- [x] T035 更新README.md添加社区氛围分析功能说明
- [x] T036 更新文档（spec.md、quickstart.md、plan.md、tasks.md）确保代码和文档对应

---

## 依赖关系与执行顺序

### 阶段依赖

- **设置（Phase 1）**：无依赖 - 可立即开始
- **基础（Phase 2）**：依赖设置完成 - 阻塞所有用户故事
- **用户故事（Phase 3+）**：都依赖基础阶段完成
  - 用户故事可以并行进行（如果有人员）
  - 或按优先级顺序依次进行（P1 → P3）
- **完善（最终阶段）**：依赖所有期望的用户故事完成

### 用户故事依赖

- **用户故事1（P1）**：基础阶段完成后可开始 - 不依赖其他故事
- **用户故事3（P3）**：基础阶段完成后可开始 - 可能集成US1但应可独立测试

### 每个用户故事内部

- 模型在服务之前
- 服务在端点之前
- 测试在实现之后

---

## 任务统计

- **总任务数**：36
- **Phase 1（设置）**：4个任务
- **Phase 2（基础）**：5个任务
- **Phase 3（用户故事1）**：13个任务
- **Phase 4（用户故事3）**：7个任务
- **Phase 5（完善）**：7个任务

### 按用户故事统计

- **用户故事1（P1）**：13个任务 - MVP核心功能
- **用户故事3（P3）**：7个任务 - DeepSeek API集成

### 并行机会

- **Phase 2**：5个任务中有4个可并行（T005-T008）
- **Phase 3**：部分任务可并行（如算法集成）
- **Phase 5**：7个任务中有3个可并行（测试任务）

---

## 独立测试标准

### 用户故事1

- 运行分析工具，自动加载所有项目的actor-discussion图文件
- 为每个项目生成月度指标时间序列
- 输出综合评分
- 处理缺失的月份
- 处理损坏的图文件

### 用户故事3

- 配置DeepSeek API key，验证系统能够调用API进行情感分析
- 如果API key未配置，系统应给出明确的错误信息
- 如果API调用失败，系统应记录错误并继续处理其他边

---

## 增量交付

1. 完成设置 + 基础 → 基础就绪
2. 添加用户故事1 → 独立测试 → 部署/演示（MVP！）
3. 添加用户故事3 → 独立测试 → 部署/演示
4. 完善阶段 → 独立测试 → 部署/演示

---

## 完成状态

所有任务已完成 ✅
