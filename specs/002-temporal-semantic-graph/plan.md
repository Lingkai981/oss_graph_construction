# 实现规划：基于 GitHub 事件的一小时时序语义图构建（002-temporal-semantic-graph）

**分支**：`002-temporal-semantic-graph`  
**日期**：2026-01-14  
**规格文档**：`specs/002-temporal-semantic-graph/spec.md`

## 摘要

本特性在现有快照式图构建能力（001 特性）的基础上，增加对 GitHub 事件一小时窗口数据（`2015-01-01-15.json`）的时序语义图建模能力。  
实现目标是：从该 JSON 行式事件文件中解析出事件、开发者、仓库、提交等实体，构建带时间顺序与语义属性的有向图，并支持导出为 JSON 与 GraphML，两种图构建实现通过源码子目录与 001 特性进行清晰隔离。

## 技术上下文（Technical Context）

- **语言 / 版本**：Python 3.x（复用当前项目环境，默认与 001 特性一致）  
- **主要依赖**：  
  - `networkx`：图结构建模与导出 GraphML  
  - `pandas` / 标准库 `json`：按行解析 GitHub 事件 JSON 文件  
  - 项目内已有工具：`src/utils/logger.py`, `src/utils/date_utils.py` 等  
- **存储方式**：  
  - 输入：文件系统中的 JSON 行文件 `data/2015-01-01-15.json`  
  - 输出：文件系统中的 JSON / GraphML 文件，位于 `output/temporal-semantic-graph/`  
  - 不引入额外数据库，仅在内存中构建图  
- **测试**：  
  - 单元测试：使用现有 `pytest` 基础，新增单元测试文件，放在 `tests/unit/temporal_semantic_graph/` 子目录中  
  - 集成测试：在 `tests/integration/` 下新增针对端到端“从 JSON 构图并导出”的测试  
- **目标运行环境**：本地命令行（Windows + WSL / Linux 环境），通过 `run.py` 或 CLI 子命令触发  
- **项目类型**：单一后端/脚本型项目（无前端），通过 CLI 驱动  
- **性能目标**：针对单个一小时文件，在普通开发机器上**整体处理时间不超过 5 分钟**，内存占用在可接受范围内（不做硬性数值约束）  
- **约束条件**：  
  - 所有对用户可见的输出（日志、错误、文档）均为中文  
  - 语义属性必须基于真实数据字段或其派生，不允许虚构默认语义  
  - 与 001 特性代码在源码层面通过子目录进行清晰区分，避免逻辑耦合  
- **规模 / 范围**：  
  - 范围限定在**单个一小时** GitHub 事件文件的图构建与导出  
  - 事件覆盖该小时内所有仓库，不限定单一项目  
  - 不处理跨多小时/多天的演化对比与高级图分析

## 宪章检查（Constitution Check）

> 由于当前 `.specify/memory/constitution.md` 仍为占位模板，未给出具体不可违背的原则与强制性质量门槛，本特性在规划阶段暂不引入额外复杂度或多项目结构，遵循“保持简单、可测试、可观察”的一般工程原则。

- 代码结构保持在现有 `src/` 与 `tests/` 体系内，通过**子目录划分**与 001 特性区分，未新增额外独立项目或仓库，复杂度可控。
- 计划在实现前补充或扩展单元 / 集成测试，保证新增时序图构建逻辑可独立验证。
- 所有新文档与 CLI 输出统一使用中文，满足当前仓库的文档一致性约束。

结论：在当前抽象宪章前提下，本规划未发现明显违背高层原则的设计，可进入 Phase 0 研究与 Phase 1 设计。

## 项目结构规划（Project Structure）

### 文档结构（本特性）

```text
specs/002-temporal-semantic-graph/
├── spec.md          # 特性规格说明（已完成）
├── plan.md          # 本文件：实现规划（/speckit.plan 输出）
├── research.md      # Phase 0：研究与设计决策记录
├── data-model.md    # Phase 1：数据模型与图实体设计
├── quickstart.md    # Phase 1：使用说明与运行示例
├── contracts/       # Phase 1：接口/CLI 合约（以文档/伪接口形式记录）
└── tasks.md         # Phase 2：实现任务分解（由 /speckit.tasks 生成）
```

### 源码结构（与 001 特性通过子目录区分）

```text
src/
├── cli/
│   ├── __init__.py
│   ├── main.py
│   └── temporal_semantic_graph_cli.py      # 新增：时序语义图相关 CLI 入口（可选）
├── models/
│   ├── __init__.py
│   ├── node.py                             # 复用：节点与属性的通用建模
│   ├── edge.py                             # 复用：边与属性的通用建模
│   └── temporal_semantic/                  # 新增子目录：时序语义图专用模型扩展（如事件/提交节点封装）
├── services/
│   ├── __init__.py
│   ├── extractor.py                        # 001 相关：从数据库等抽取
│   ├── graph_builder.py                    # 001 相关：快照式图构建
│   ├── exporter.py                         # 复用：图导出基础能力
│   ├── database.py                         # 001 相关：数据库访问
│   └── temporal_semantic_graph/            # 新增子目录：时序语义图构建流水线
│       ├── __init__.py
│       ├── loader.py                       # 负责按行读取 2015-01-01-15.json 并解析事件对象
│       ├── builder.py                      # 负责根据事件构建 networkx 图（事件/开发者/仓库/提交节点与边）
│       └── pipeline.py                     # 负责编排：加载 → 构图 → 导出（JSON/GraphML）
├── utils/
│   ├── __init__.py
│   ├── logger.py
│   └── date_utils.py

tests/
├── unit/
│   ├── test_graph_builder.py               # 001 相关
│   ├── test_extractor.py                   # 001 相关
│   ├── temporal_semantic_graph/            # 新增：时序语义图单元测试
│   │   ├── test_loader.py                  # 测试事件文件解析
│   │   ├── test_builder.py                 # 测试图结构与属性生成
│   │   └── test_pipeline.py                # 测试整体流程控制（不触及真实文件系统可用 mock）
├── integration/
│   ├── test_data_extraction.py             # 001 相关
│   ├── test_graph_building.py              # 001 相关
│   └── test_temporal_semantic_graph.py     # 新增：端到端测试，从真实/样例 JSON 构建并导出图
└── contract/
    └── （如后续需要可补充 CLI/接口 合约测试）
```

**结构决策说明**：

- 通过在 `services/` 与 `models/` 下引入 `temporal_semantic_*` 子目录，将时序语义图逻辑与 001 快照式逻辑解耦，避免后续扩展时互相干扰。
- 复用通用的节点/边模型与导出逻辑（例如 GraphML/JSON 导出部分），尽量避免重复造轮子。
- 测试目录中为本特性单独创建子目录，保证测试命名与职责清晰、不会混淆两种图构建模式。

## 复杂度跟踪（Complexity Tracking）

目前规划中未引入额外项目、进程或复杂架构模式，仅通过子目录拆分逻辑模块，复杂度增加有限，无需单独列出复杂度违例。若后续在实现中需要新增更复杂的流水线或多进程处理，再在此处补充说明与权衡理由。
