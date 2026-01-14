# 任务列表：基于 GitHub 事件的一小时时序语义图构建（002-temporal-semantic-graph）

**输入**：`specs/002-temporal-semantic-graph/` 下的规格、规划、数据模型、研究与合约文档  
**前置文档**：`spec.md`、`plan.md`、`data-model.md`、`research.md`、`contracts/README.md`、`quickstart.md`

> 说明：所有任务均使用 checklist 形式，便于逐项勾选；任务 ID 全局递增，用户故事相关任务带 `[US?]` 标记；`[P]` 表示可与其他任务并行执行（无直接依赖、改动不同文件）。

---

## 阶段 1：基础准备（Setup）

**目的**：确保目录结构与运行环境准备就绪，为后续实现打基础。

- [x] T001 创建时序语义图服务子目录 `src/services/temporal_semantic_graph/`（如不存在）并添加空的 `__init__.py`
- [x] T002 创建时序语义模型子目录 `src/models/temporal_semantic/`（如不存在）并添加空的 `__init__.py`
- [x] T003 [P] 在 `tests/unit/temporal_semantic_graph/` 下创建测试子目录与占位文件（如 `__init__.py`）
- [x] T004 [P] 在 `tests/integration/` 下新建集成测试占位文件 `tests/integration/test_temporal_semantic_graph.py`
- [x] T005 确认 `output/temporal-semantic-graph/` 输出目录存在（如不存在则在实现中确保自动创建）

---

## 阶段 2：基础设施与工具（Foundational）

**目的**：实现所有用户故事共享的核心基础能力，包括日志、时间解析、文件访问等。

> ⚠️ 在完成本阶段前，不应开始任何用户故事的核心实现工作。

- [x] T006 在 `src/utils/logger.py` 中（或相应位置）检查/扩展日志工具，确保支持中文日志消息并可在新服务中复用
- [x] T007 [P] 在 `src/utils/date_utils.py` 中新增/确认解析 GitHub `created_at` 字符串为时间戳的工具函数（如 `parse_github_datetime`）
- [x] T008 [P] 在 `src/services/temporal_semantic_graph/loader.py` 中定义基础文件读取骨架（尚可先只包含函数签名与 docstring，不实现业务细节）
- [x] T009 在 `src/services/temporal_semantic_graph/builder.py` 中定义图构建接口骨架（例如 `build_graph(events)`），暂不实现细节
- [x] T010 [P] 在 `src/services/temporal_semantic_graph/pipeline.py` 中定义高层流水线接口（例如 `run_temporal_graph_pipeline(input_path, output_dir, formats)`），仅写注释与 TODO
- [x] T011 在 `src/cli/main.py` 中预留 `temporal-semantic-graph` 子命令的路由入口（调用 `pipeline.run_temporal_graph_pipeline`），但暂可只写占位实现与参数解析结构

---

## 阶段 3：用户故事 1（US1）——从一小时事件构建基础时序语义图（优先级：P1）🎯 MVP

**目标**：从 `data/2015-01-01-15.json` 中读取所有事件，构建包含事件、开发者、仓库、提交节点及基础关系边的时序语义图（不要求所有语义属性完整，但结构正确、时间顺序可恢复）。

**独立验证方式**：在数据文件存在前提下，通过 CLI 或直接调用 pipeline，检查输出图（或统计信息）中节点和边的数量、类型，以及事件按时间顺序被处理。

### US1：测试任务（推荐，便于回归）

- [x] T012 [P] [US1] 在 `tests/unit/temporal_semantic_graph/test_loader.py` 中编写针对事件文件解析的单元测试（使用小型样例 JSON 行字符串）
- [x] T013 [P] [US1] 在 `tests/unit/temporal_semantic_graph/test_builder.py` 中编写针对基础图结构（节点/边数、类型）的单元测试
- [x] T014 [US1] 在 `tests/integration/test_temporal_semantic_graph.py` 中编写端到端测试骨架：从样例 JSON 文件构建图并断言基础统计（节点数、边数 > 0）

### US1：实现任务

- [x] T015 [P] [US1] 在 `src/services/temporal_semantic_graph/loader.py` 中实现逐行读取 `data/2015-01-01-15.json` 并解析为事件字典列表（包含错误处理与日志记录）
- [ ] T016 [P] [US1] 在 `src/models/temporal_semantic/` 中定义事件、开发者、仓库、提交的简单数据结构或辅助构造函数（可复用 `src/models/node.py` / `edge.py` 的通用模型）
- [x] T017 [US1] 在 `src/services/temporal_semantic_graph/builder.py` 中实现基础图构建逻辑：  
  使用 `networkx` 创建图，基于事件列表创建事件/开发者/仓库/提交节点与开发者→事件、事件→仓库、事件→提交等关系边
- [x] T018 [US1] 在 `src/services/temporal_semantic_graph/builder.py` 中基于 `created_at` / 时间戳对事件进行排序，确保构图过程保留时间先后关系（至少通过节点属性）
- [x] T019 [P] [US1] 在 `src/services/temporal_semantic_graph/pipeline.py` 中实现流水线：调用 loader 与 builder，返回内存中的图对象
- [x] T020 [US1] 在 `src/cli/main.py` 中完善 `temporal-semantic-graph` 子命令逻辑，接收 `--input/--output-dir/--export-format` 参数并调用 pipeline
- [x] T021 [US1] 更新或新增日志输出，确保在加载、构图过程中输出关键中文日志（如事件总数、节点数、边数等）

**检查点**：完成本阶段后，即使暂未填充所有语义属性，也应能从一小时事件文件构建出结构正确的时序图，这是整个特性的 MVP。

---

## 阶段 4：用户故事 2（US2）——为节点与边填充来自真实数据的语义属性（优先级：P1）

**目标**：在已有结构正确的图基础上，为事件、开发者、仓库、提交节点及主要关系边填充来源于真实数据或其派生的语义属性，满足规格中对属性完整性与正确性的要求。

**独立验证方式**：随机抽样节点/边，对照原始 JSON 行数据，验证属性值是否一致或为清晰可解释的派生（如字符串截断、长度统计等）。

### US2：测试任务

- [x] T022 [P] [US2] 在 `tests/unit/temporal_semantic_graph/test_builder.py` 中增加针对节点属性的测试用例（验证事件/开发者/仓库/提交节点属性是否按数据模型填充）
- [x] T023 [P] [US2] 在 `tests/unit/temporal_semantic_graph/test_builder.py` 中增加针对边属性的测试用例（验证边类型与时间戳等属性）
- [x] T024 [US2] 在 `tests/integration/test_temporal_semantic_graph.py` 中增加对随机抽样事件的属性一致性检查（例如从样例文件中选几条事件做精确匹配）

### US2：实现任务

- [x] T025 [P] [US2] 按 `data-model.md` 在 `src/models/temporal_semantic/` 中完善事件节点属性映射（`event_id`, `type`, `created_at`, `created_at_ts`, `public`, `repo_id`, `actor_id`, `payload_summary` 等，为后续 `importance_score` 计算提供基础字段）
- [x] T026 [P] [US2] 在 `src/models/temporal_semantic/` 中完善开发者节点属性映射（`actor_id`, `login`, `avatar_url`, `url` 等，为后续 `influence_score` 计算提供基础字段）
- [x] T027 [P] [US2] 在 `src/models/temporal_semantic/` 中完善仓库节点属性映射（`repo_id`, `name`, `url` 等）
- [x] T028 [P] [US2] 在 `src/models/temporal_semantic/` 中完善提交节点属性映射（`commit_sha`, `message`, `author_name`, `author_email`, `distinct`, `url`, `message_length` 等）
- [ ] T029 [US2] 在 `src/services/temporal_semantic_graph/pipeline.py` 中实现基于整小时事件的语义评分预计算逻辑，生成事件重要性评分（如 `importance_score`）和开发者影响力评分（如 `influence_score`），并将结果归一化到 0～1 区间
- [ ] T030 [US2] 在 `src/services/temporal_semantic_graph/builder.py` 中将上述评分正确写入对应节点和边（如在开发者节点写入 `influence_score`、在事件节点写入 `importance_score`、在开发者→事件边写入 `contribution_strength`），确保后续导出时可见
- [x] T031 [US2] 在 `src/services/temporal_semantic_graph/loader.py` 中增强异常处理逻辑，对于 JSON 解析失败或缺失关键字段的记录，记录中文错误并跳过

**检查点**：完成本阶段后，应能通过测试与抽样验证，确认绝大部分（≥95%）节点和边的语义属性与原始 JSON 一致或为清晰派生。

---

## 阶段 5：用户故事 3（US3）——导出时序语义图为 JSON 与 GraphML（优先级：P2）

**目标**：在已有内存图基础上，支持将图结构导出为 JSON 与 GraphML 两种格式，遵循 `contracts/README.md` 中的结构与命名约定，供后续图工具与脚本消费。

**独立验证方式**：  
（1）使用 Python 脚本重新加载导出 JSON，验证节点/边数量与基本属性；  
（2）在 Gephi 等工具中导入 GraphML，确认节点/边可被识别，其属性可用于过滤与可视化。

### US3：测试任务

- [x] T032 [P] [US3] 在 `tests/unit/temporal_semantic_graph/test_pipeline.py` 中为 JSON 导出添加单元测试（使用小图，验证顶层 `meta/nodes/edges` 结构与计数）
- [x] T033 [P] [US3] 在 `tests/unit/temporal_semantic_graph/test_pipeline.py` 中为 GraphML 导出添加单元测试（通过 `networkx` 重新加载 GraphML 并比较节点/边数量）
- [x] T034 [US3] 在 `tests/integration/test_temporal_semantic_graph.py` 中增加端到端导出测试：从样例 JSON 文件构建图并生成 JSON+GraphML 文件，检查文件是否存在且可解析

### US3：实现任务

- [x] T035 [P] [US3] 在 `src/services/exporter.py` 中复用或扩展现有导出工具，新增将通用 `networkx` 图导出为约定 JSON 结构的函数（例如 `export_temporal_graph_to_json(graph, path)`）
- [x] T036 [P] [US3] 在 `src/services/exporter.py` 中新增或复用 GraphML 导出函数（例如 `export_temporal_graph_to_graphml(graph, path)`），确保节点/边类型与属性写入 GraphML
- [x] T037 [US3] 在 `src/services/temporal_semantic_graph/pipeline.py` 中集成导出逻辑：根据 `--export-format` 参数决定导出 JSON、GraphML 或两者，并写入 `output/temporal-semantic-graph/` 目录
- [x] T038 [US3] 在 `src/cli/main.py` 中完善错误处理与中文提示：输入文件不存在、输出目录不可写、导出异常时给出友好信息并返回非 0 退出码
- [x] T039 [US3] 按 `contracts/README.md` 约定，确保导出 JSON 的顶层结构包含 `meta/nodes/edges`，并在 `meta` 中填入源文件路径、生成时间、节点数与边数
- [x] T040 [US3] 按 `contracts/README.md` 约定，确保 GraphML 中节点/边的 `type` 与关键语义属性以 `data` 元素形式输出

**检查点**：完成本阶段后，应能稳定从一小时事件文件生成带语义属性的 JSON 与 GraphML 文件，并被外部工具成功加载。

---

## 阶段 6：打磨与横切关注点（Polish & Cross-Cutting）

**目的**：在所有主要用户故事完成后，统一进行文档完善、性能检查、代码整理与快速上手验证。

- [x] T041 [P] 根据实际实现更新 `specs/002-temporal-semantic-graph/quickstart.md` 中的示例命令与输出说明，确保与 CLI 行为一致
- [x] T042 [P] 在 `README.md` 或相关顶层文档中简要添加“时序语义图构建（002）”的使用入口说明
- [x] T043 对 `src/services/temporal_semantic_graph/` 与 `src/models/temporal_semantic/` 中代码进行适度重构与注释补充，提升可读性（不改变对外合约）
- [ ] T044 [P] 运行全部单元测试与集成测试（`pytest`），修复与本特性相关的失败用例（当前在未设置PYTHONPATH为项目根目录时，`tests` 下部分用例会出现 `ModuleNotFoundError: No module named 'src'`，建议在本地运行测试时使用 `PYTHONPATH=.` 或等效方式）
- [ ] T045 通过一轮人工抽样检查（对比原始 JSON 与图结构），确认整体结果满足规格中的成功标准（SC-201 ~ SC-206）

---

## 依赖关系与执行顺序

### 阶段依赖

- **阶段 1（Setup）**：无依赖，可立即开始；
- **阶段 2（Foundational）**：依赖阶段 1 完成，是所有用户故事的前置条件；
- **阶段 3（US1）**：在阶段 2 完成后即可开始，是整个特性的 MVP；
- **阶段 4（US2）**：依赖阶段 3 提供的基础图结构，但可以与阶段 5（US3）的部分准备任务并行；
- **阶段 5（US3）**：依赖阶段 3 完成基本构图能力，导出结构则同时依赖阶段 4 中的属性设计；
- **阶段 6（Polish）**：依赖所有希望完成的用户故事阶段。

### 用户故事依赖

- **US1（P1）**：仅依赖 Setup + Foundational，可独立实现与验证；
- **US2（P1）**：基于 US1 的图结构，聚焦语义属性填充，测试可独立于导出进行；
- **US3（P2）**：基于 US1+US2 的完整图数据结构，实现导出能力，可通过文件与外部工具独立验证。

### 并行执行机会

- 标记为 `[P]` 的任务一般可在不同文件中并行推进（如 loader 与 builder 的部分实现、单元测试与集成测试骨架编写等）；
- 在阶段 2 完成后，可以由不同开发者分别负责 US1、US2、US3 的子集任务，但需遵守上述依赖关系；
- 测试代码（`tests/unit/...` 与 `tests/integration/...`）的编写也可以与部分实现并行，只需保证最终在合并前测试通过。

---

## 实施策略建议

- **MVP 优先**：首先集中完成 US1 相关任务（尤其是 T015 ~ T021），让从一小时事件到基础时序图的最小链路跑通。  
- **渐进增强**：在 MVP 可用后，再依次完成 US2 的语义属性填充与 US3 的导出能力，使图既有结构又有语义并可被外部工具消费。  
- **持续验证**：每个阶段结束前运行测试与简单人工抽样检查，避免问题积累到后期才暴露。  
- **严格中文输出**：在实现和测试中留意所有用户可见文本，确保保持中文一致性。  

