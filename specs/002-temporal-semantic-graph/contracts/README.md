# 合约说明：时序语义图构建 CLI 与输出格式

本文件用于描述与“基于 GitHub 事件的一小时时序语义图构建”相关的外部合约，包括：

- 命令行入口与参数约定；
- 输入输出文件路径与命名约定；
- 导出 JSON 与 GraphML 的基础结构约定（面向使用者，而非精确 schema）。

> 注意：本仓库当前更偏向脚本/CLI 风格，而非对外暴露 HTTP API，因此此处的“合约”主要指 CLI 使用契约与文件格式契约。

---

## 1. 命令行接口约定（CLI Contract）

### 1.1 入口形式（建议）

在 `src/cli/main.py` 中，为本特性预留一个子命令，例如：

```text
python -m src.cli.main temporal-semantic-graph \
  --input data/2015-01-01-15.json \
  --output-dir output/temporal-semantic-graph \
  --export-format json,graphml
```

> 具体参数解析可以使用 `argparse` 等库实现，这里只规定外部行为。

### 1.2 参数约定

- `--input`（必需）  
  - 含义：输入的 GitHub 事件 JSON 行文件路径。  
  - 默认值：无，必须显式提供。  
  - 验证：文件必须存在且可读，否则给出中文错误提示并退出。

- `--output-dir`（可选）  
  - 含义：输出目录路径，用于存放导出的 JSON / GraphML 文件。  
  - 默认值：`output/temporal-semantic-graph`。  
  - 行为：如目录不存在，程序应尝试自动创建；创建失败时给出中文错误提示。

- `--export-format`（可选）  
  - 含义：导出格式，允许多个，以逗号分隔，例如 `json`、`graphml` 或 `json,graphml`。  
  - 默认值：`json,graphml`（即两种格式都导出）。  
  - 验证：若传入不支持的格式值，应提示可选项，并以中文错误信息退出。

（后续如引入更多参数，如事件过滤、日志级别等，可在本文件中继续扩展说明。）

---

## 2. 输入 / 输出约定

### 2.1 输入文件约定

- 格式：每行一个完整 JSON 对象，结构与 GitHub Archive 事件格式一致。
- 关键字段：
  - 顶层字段：`id`, `type`, `actor`, `repo`, `payload`, `public`, `created_at` 等；
  - 嵌套字段：`actor.id`, `actor.login`, `repo.id`, `repo.name`, `payload.commits[*].sha` 等。
- 出错处理：
  - 解析失败的行：记录到日志并跳过；
  - 缺失关键字段的行：按数据模型中的规则处理（如缺失 `id`/`created_at` 则整行跳过）。

### 2.2 输出文件命名

- 输出目录：默认为 `output/temporal-semantic-graph/`。
- 命名规则（示例，按分钟快照）：
  - JSON：`temporal-graph-2015-01-01-15-00.json`
  - GraphML：`temporal-graph-2015-01-01-15-00.graphml`
- 说明：
  - 文件名中应包含时间窗口信息和分钟信息（如 `2015-01-01-15-23`），便于区分同一小时内不同分钟产生的快照结果。

---

## 3. 导出 JSON 结构约定（面向分析者）

> 这里给出的是“逻辑结构约定”，实现时可以选择更具体的 key 命名，只要确保语义对应即可。

建议的 JSON 顶层结构示例：

```json
{
  "meta": {
    "source_file": "data/2015-01-01-15.json",
    "generated_at": "2026-01-14T12:00:00Z",
    "node_count": 12345,
    "edge_count": 67890
  },
  "nodes": [
    {
      "id": "event:2489651051",
      "type": "Event",
      "attributes": {
        "event_id": "2489651051",
        "event_type": "PushEvent",
        "created_at": "2015-01-01T15:00:01Z",
        "...": "..."
      }
    }
  ],
  "edges": [
    {
      "id": "actor:665991->event:2489651051",
      "type": "ACTOR_TRIGGERED_EVENT",
      "source": "actor:665991",
      "target": "event:2489651051",
      "attributes": {
        "created_at": "2015-01-01T15:00:01Z"
      }
    }
  ]
}
```

约定要点：

- `nodes` 与 `edges` 均为数组；
- 每个节点有：
  - `id`：在全图内唯一，可组合前缀（如 `event:`、`actor:` 等）；
  - `type`：节点类型（`Event` / `Actor` / `Repository` / `Commit`）；
  - `attributes`：包含来自原始数据或派生的语义属性。
- 每条边有：
  - `id`：在全图内唯一，可由 `source` 与 `target` 拼接；
  - `type`：边类型，如 `"ACTOR_TRIGGERED_EVENT"` 等；
  - `source` / `target`：引用节点的 `id`；
  - `attributes`：包含边级别的属性，如时间戳等。

---

## 4. 导出 GraphML 结构约定（面向图工具）

GraphML 是 XML 格式，这里不展开全部细节，只约定核心原则：

- 所有节点与边都应携带一个 `type` 属性，用来区分节点/边的业务类型；
- 关键语义属性（如事件类型、时间戳、开发者登录名、仓库名称等）应作为 GraphML 的 `data` 元素输出；
- 节点与边的 ID 应与 JSON 导出中的 ID 保持一致，便于跨格式对照。

使用者可以在常见图分析工具（如 Gephi）中：

- 通过 `type` 字段筛选不同的节点/边；
- 按 `created_at` 等时间字段进行布局或动态可视化；
- 结合节点/边属性进行过滤与统计。

---

## 5. 错误与退出码约定（建议）

- 正常完成：退出码 `0`。
- 输入文件不存在或不可读：退出码非 0，并在标准错误输出中文说明。
- 输出目录不可写：退出码非 0，并在标准错误输出中文说明。
- 解析过程中出现部分错误（但整体完成）：仍返回 `0`，但在日志中记录警告与错误详情。

> 具体退出码细分可以在实现阶段进一步约定，只要保持“有错误必有中文提示”和“非 0 代表致命错误”的基本原则即可。


