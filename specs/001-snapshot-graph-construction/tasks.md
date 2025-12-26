# 任务列表：时间快照式时序图建模

**输入**：设计文档来自 `/specs/001-snapshot-graph-construction/`
**前置条件**：plan.md（必需）, spec.md（必需，用于用户故事）, research.md, data-model.md, contracts/

**测试**：以下示例包含测试任务。测试是可选的 - 仅在特性规范中明确要求时包含。

**组织方式**：任务按用户故事分组，以便每个故事可以独立实现和测试。

## 格式：`[ID] [P?] [Story] 描述`

- **[P]**: 可以并行运行（不同文件，无依赖关系）
- **[Story]**: 此任务属于哪个用户故事（例如，US1、US2、US3）
- 描述中包含确切的文件路径

## 路径约定

- **单项目**：仓库根目录下的 `src/`、`tests/`
- 以下路径假设为单项目结构 - 根据plan.md中的结构进行调整

## Phase 1: 设置（共享基础设施）

**目的**：项目初始化和基本结构

- [x] T001 创建项目结构，按照实现计划在仓库根目录创建src/、tests/、data/、output/、logs/目录
- [x] T002 初始化Python项目，创建requirements.txt文件，包含networkx>=2.8和pytest>=7.0依赖
- [x] T003 [P] 创建src/models/__init__.py、src/services/__init__.py、src/cli/__init__.py、src/utils/__init__.py空文件
- [x] T004 [P] 创建tests/unit/、tests/integration/、tests/contract/目录结构

---

## Phase 2: 基础（阻塞性前置条件）

**目的**：核心基础设施，必须在任何用户故事实现之前完成

**⚠️ 关键**：此阶段完成前，不能开始任何用户故事工作

- [x] T005 实现日志配置工具，创建src/utils/logger.py，配置logging模块，支持文件和控制台输出，所有日志消息使用中文
- [x] T006 实现日期处理工具，创建src/utils/date_utils.py，包含时间戳解析函数，支持多种日期格式（ISO 8601、标准格式、Unix时间戳）
- [x] T007 实现数据库连接服务，创建src/services/database.py，包含connect_database()函数，连接到SQLite数据库并处理连接错误
- [x] T008 创建基础节点模型，创建src/models/node.py，定义Node基类和节点类型常量（PROJECT、CONTRIBUTOR、COMMIT）
- [x] T009 创建基础边模型，创建src/models/edge.py，定义Edge基类和边类型常量（CONTRIBUTES）

**检查点**：基础就绪 - 用户故事实现现在可以并行开始

---

## Phase 3: 用户故事 1 - 从GHTorrent数据库提取时间快照数据（优先级：P1）🎯 MVP

**目标**：从rxjs-ghtorrent.db SQLite数据库中提取时间序列数据，按天粒度组织数据，为每个日期准备图构建所需的数据

**独立测试**：运行数据提取脚本，验证能够从数据库中读取时间序列数据，输出为结构化格式，验证数据的时间顺序正确性，以及关键实体的识别准确性

### 用户故事1的实现

- [x] T010 [US1] 实现数据库表结构识别，在src/services/database.py中添加get_table_names()函数，识别数据库中的所有表
- [x] T011 [US1] 实现项目数据提取，在src/services/database.py中添加extract_projects()函数，从projects表提取项目数据
- [x] T012 [US1] 实现贡献者数据提取，在src/services/database.py中添加extract_contributors()函数，从users表提取贡献者数据
- [x] T013 [US1] 实现提交数据提取，在src/services/database.py中添加extract_commits_by_date()函数，按日期从commits表提取提交数据
- [x] T014 [US1] 实现贡献关系提取，在src/services/database.py中添加extract_contribution_edges_by_date()函数，通过关联users、commits和project_commits表提取贡献关系
- [x] T015 [US1] 实现日期识别服务，在src/services/extractor.py中创建extract_all_dates()函数，自动识别数据库中的所有唯一日期
- [x] T016 [US1] 实现按日期数据提取，在src/services/extractor.py中创建extract_data_for_date()函数，为指定日期提取所有相关数据（项目、贡献者、提交、关系）
- [x] T017 [US1] 实现错误处理逻辑，在src/services/extractor.py中添加时间戳解析错误处理，采用记录并跳过策略，记录警告到日志
- [x] T018 [US1] 实现数据验证，在src/services/extractor.py中添加数据验证逻辑，检查必需字段，跳过无效记录并记录警告

**检查点**：此时，用户故事1应该完全功能化并可独立测试

---

## Phase 4: 用户故事 2 - 构建时间快照图（优先级：P2）

**目标**：根据提取的时间序列数据，在指定的日期创建图结构，包括节点（实体）和边（关系）。每个快照代表该日期的项目状态

**独立测试**：提供预定义的时间点数据，验证系统能够构建对应的图结构。验证节点和边的正确性，以及图的基本属性（节点数、边数、连通性等）

### 用户故事2的实现

- [x] T019 [US2] 实现项目节点创建，在src/models/node.py中创建create_project_node()函数，根据项目数据创建项目节点，格式为project_{project_id}
- [x] T020 [US2] 实现贡献者节点创建，在src/models/node.py中创建create_contributor_node()函数，根据贡献者数据创建贡献者节点，格式为contributor_{user_id}
- [x] T021 [US2] 实现提交节点创建，在src/models/node.py中创建create_commit_node()函数，根据提交数据创建提交节点，格式为commit_{commit_sha}
- [x] T022 [US2] 实现贡献关系边创建，在src/models/edge.py中创建create_contribution_edge()函数，根据贡献关系数据创建边，连接贡献者节点和提交节点
- [x] T023 [US2] 实现图构建服务，在src/services/graph_builder.py中创建build_snapshot()函数，接受日期数据，创建NetworkX有向图，添加节点和边
- [x] T024 [US2] 实现节点添加逻辑，在src/services/graph_builder.py中创建add_nodes()函数，将节点添加到图中，包含所有节点属性
- [x] T025 [US2] 实现边添加逻辑，在src/services/graph_builder.py中创建add_edges()函数，将边添加到图中，包含所有边属性
- [x] T026 [US2] 实现节点累积逻辑，在src/services/graph_builder.py中实现节点累积机制，节点一旦创建就存在于所有后续快照中
- [x] T027 [US2] 实现空快照处理，在src/services/graph_builder.py中添加空快照处理逻辑，如果某天没有数据，创建空图
- [x] T028 [US2] 实现多日期快照构建，在src/services/graph_builder.py中创建build_all_snapshots()函数，为所有日期构建图快照

**检查点**：此时，用户故事1和用户故事2都应该能够独立工作

---

## Phase 5: 用户故事 3 - 导出和可视化图快照（优先级：P3）

**目标**：提供基本的图导出功能（GraphML、JSON格式），将构建的图快照导出为标准格式文件

**独立测试**：构建一个图快照，然后导出为指定格式，验证导出文件的正确性和完整性。验证导出的图可以被标准图工具（如Gephi、Cytoscape）读取

### 用户故事3的实现

- [x] T029 [US3] 实现GraphML导出，在src/services/exporter.py中创建export_graphml()函数，使用NetworkX的write_graphml()函数导出图
- [x] T030 [US3] 实现JSON导出，在src/services/exporter.py中创建export_json()函数，使用NetworkX的node_link_data()函数导出为JSON格式
- [x] T031 [US3] 实现文件命名逻辑，在src/services/exporter.py中创建generate_filename()函数，生成包含日期的文件名（如snapshot_2024-01-01.graphml）
- [x] T032 [US3] 实现输出目录管理，在src/services/exporter.py中添加output目录创建逻辑，确保output/目录存在
- [x] T033 [US3] 实现批量导出，在src/services/exporter.py中创建export_all_snapshots()函数，为所有快照生成导出文件
- [x] T034 [US3] 实现导出格式选择，在src/services/exporter.py中添加格式参数支持，允许选择GraphML或JSON格式

**检查点**：所有用户故事现在应该能够独立功能化

---

## Phase 6: 命令行接口

**目的**：创建命令行入口，整合所有功能

- [x] T035 实现命令行主入口，创建src/cli/main.py，使用argparse实现命令行参数解析（--db、--output、--log-level、--start-date、--end-date、--format）
- [x] T036 实现主流程编排，在src/cli/main.py中实现main()函数，按顺序调用数据提取、图构建、导出服务
- [x] T037 实现错误处理，在src/cli/main.py中添加全局错误处理，确保所有错误都被记录到日志
- [x] T038 实现进度输出，在src/cli/main.py中添加进度信息输出，使用中文显示处理进度

---

## Phase 7: 完善与跨领域关注点

**目的**：影响多个用户故事的改进

- [x] T039 [P] 创建README.md文档，在项目根目录创建README.md，包含项目介绍、安装步骤、使用方法
- [x] T040 [P] 创建单元测试，在tests/unit/目录创建test_database.py、test_extractor.py、test_graph_builder.py、test_exporter.py
- [x] T041 [P] 创建集成测试，在tests/integration/目录创建test_data_extraction.py、test_graph_building.py、test_export.py
- [x] T042 代码清理和重构，检查所有代码文件，确保注释和文档字符串使用中文
- [x] T043 性能优化，优化数据提取和图构建性能，确保满足5分钟内提取1000天数据的要求
- [x] T044 运行quickstart.md验证，按照quickstart.md中的步骤验证系统功能

---

## 依赖关系与执行顺序

### 阶段依赖

- **设置（Phase 1）**：无依赖 - 可以立即开始
- **基础（Phase 2）**：依赖于设置完成 - 阻塞所有用户故事
- **用户故事（Phase 3+）**：都依赖于基础阶段完成
  - 用户故事可以并行进行（如果有人员配置）
  - 或按优先级顺序进行（P1 → P2 → P3）
- **完善（最后阶段）**：依赖于所有期望的用户故事完成

### 用户故事依赖

- **用户故事 1 (P1)**：可以在基础（Phase 2）完成后开始 - 不依赖其他故事
- **用户故事 2 (P2)**：可以在基础（Phase 2）完成后开始 - 可能使用US1的组件但应该独立可测试
- **用户故事 3 (P3)**：可以在基础（Phase 2）完成后开始 - 可能使用US1/US2的组件但应该独立可测试

### 每个用户故事内部

- 模型在服务之前
- 服务在端点之前
- 核心实现在集成之前
- 故事完成后再进入下一个优先级

### 并行机会

- 所有标记为[P]的设置任务可以并行运行
- 所有标记为[P]的基础任务可以并行运行（在Phase 2内）
- 基础阶段完成后，所有用户故事可以并行开始（如果团队容量允许）
- 用户故事内的模型任务标记为[P]可以并行运行
- 不同用户故事可以由不同团队成员并行工作

---

## 并行示例：用户故事1

```bash
# 用户故事1中的模型可以并行创建（虽然当前没有标记[P]，因为它们有依赖关系）
# 但数据提取函数可以并行实现（不同表）：
Task: "实现项目数据提取，在src/services/database.py中添加extract_projects()函数"
Task: "实现贡献者数据提取，在src/services/database.py中添加extract_contributors()函数"
Task: "实现提交数据提取，在src/services/database.py中添加extract_commits_by_date()函数"
```

---

## 实现策略

### MVP优先（仅用户故事1）

1. 完成Phase 1：设置
2. 完成Phase 2：基础（关键 - 阻塞所有故事）
3. 完成Phase 3：用户故事1
4. **停止并验证**：独立测试用户故事1
5. 如果准备就绪，部署/演示

### 增量交付

1. 完成设置 + 基础 → 基础就绪
2. 添加用户故事1 → 独立测试 → 部署/演示（MVP！）
3. 添加用户故事2 → 独立测试 → 部署/演示
4. 添加用户故事3 → 独立测试 → 部署/演示
5. 每个故事在不破坏先前故事的情况下增加价值

### 并行团队策略

有多名开发人员时：

1. 团队一起完成设置 + 基础
2. 基础完成后：
   - 开发者A：用户故事1
   - 开发者B：用户故事2
   - 开发者C：用户故事3
3. 故事独立完成和集成

---

## 任务统计

- **总任务数**：44
- **Phase 1（设置）**：4个任务
- **Phase 2（基础）**：5个任务
- **Phase 3（用户故事1）**：9个任务
- **Phase 4（用户故事2）**：10个任务
- **Phase 5（用户故事3）**：6个任务
- **Phase 6（命令行接口）**：4个任务
- **Phase 7（完善）**：6个任务

### 按用户故事的任务数

- **用户故事1（P1）**：9个任务
- **用户故事2（P2）**：10个任务
- **用户故事3（P3）**：6个任务

### 并行机会

- **Phase 1**：2个并行任务（T003, T004）
- **Phase 2**：无并行任务（有依赖关系）
- **Phase 7**：3个并行任务（T039, T040, T041）

---

## 注意事项

- [P] 任务 = 不同文件，无依赖关系
- [Story] 标签将任务映射到特定用户故事以便追溯
- 每个用户故事应该可以独立完成和测试
- 每个任务或逻辑组后提交
- 在任何检查点停止以独立验证故事
- 避免：模糊任务、同一文件冲突、破坏独立性的跨故事依赖

