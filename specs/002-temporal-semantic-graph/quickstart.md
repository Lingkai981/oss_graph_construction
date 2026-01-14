# 快速上手：基于 GitHub 事件的一小时时序语义图构建

本指南面向使用者，介绍如何在当前仓库中基于 `2015-01-01-15.json` 文件构建一张时序语义图，并导出为 JSON 与 GraphML 格式。  
示例命令与说明均使用中文，便于直接复制运行与理解。

---

## 1. 前置条件

1. 已完成项目依赖安装（通常在仓库根目录运行）：

   ```bash
   pip install -r requirements.txt
   ```

2. 确认数据文件存在：

   ```text
   data/2015-01-01-15.json
   ```

3. 确认 Python 环境可用（版本与 001 特性一致，推荐 3.10+）。

---

## 2. 目标回顾

- 从 `data/2015-01-01-15.json` 中解析一小时内的所有 GitHub 事件；
- 按**分钟粒度**构建包含事件、开发者、仓库、提交四类节点以及相应关系边的一系列有向图快照（每分钟一张或若干张）；
- 图中所有节点和边都带有来自真实数据或派生的语义属性；
- 将构建好的分钟级快照图导出到：
  - `output/temporal-semantic-graph/temporal-graph-2015-01-01-15-00.json / .graphml`
  - `output/temporal-semantic-graph/temporal-graph-2015-01-01-15-01.json / .graphml`
  - ... 依此类推，覆盖该小时内所有实际存在事件的分钟。

---

## 3. 典型使用流程（建议 CLI 形式）

> 说明：此处假设在 `src/cli/main.py` 中实现了 `temporal-semantic-graph` 子命令，实际函数名和参数解析细节以实现为准。

在仓库根目录执行：

```bash
python -m src.cli.main temporal-semantic-graph \
  --input data/2015-01-01-15.json \
  --output-dir output/temporal-semantic-graph \
  --export-format json,graphml
```

预期行为：

1. 程序检查输入文件是否存在，不存在则以中文提示错误并退出；
2. 从文件中逐行解析 GitHub 事件对象；
3. 按照 `created_at` 字段对事件排序，并为事件、开发者、仓库、提交创建对应节点；
4. 以分钟为粒度，将事件划分到对应的一分钟窗口中，为每个窗口构建一张独立的时序语义图；
5. 将每个一分钟快照图分别导出为 JSON 及 GraphML 文件；
6. 在终端输出简要统计信息（如节点数、边数、输出文件路径），并在日志中记录详细过程。

---

## 4. 输出文件查看与验证

### 4.1 JSON 文件

输出路径（示例）：

```text
output/temporal-semantic-graph/temporal-graph-2015-01-01-15-00.json
output/temporal-semantic-graph/temporal-graph-2015-01-01-15-01.json
...
```

你可以用任意 JSON 查看工具或 Python 脚本快速检查：

```bash
python - << 'PY'
import json, pathlib
p = pathlib.Path("output/temporal-semantic-graph/temporal-graph-2015-01-01-15.json")
data = json.loads(p.read_text(encoding="utf-8"))
print("节点数:", len(data.get("nodes", [])))
print("边数:", len(data.get("edges", [])))
PY
```

### 4.2 GraphML 文件

输出路径（示例）：

```text
output/temporal-semantic-graph/temporal-graph-2015-01-01-15.graphml
```

可将该文件导入到 Gephi、Cytoscape 等图分析工具中：

1. 打开 Gephi；
2. 选择“打开项目”或“导入文件”，选中上述 `.graphml` 文件；
3. 在数据表中查看节点与边的属性，例如：
   - 节点类型（Event / Actor / Repository / Commit）；
   - 事件类型、时间戳、开发者登录名、仓库名称等；
4. 根据需要在 Gephi 中做过滤、布局或时间维度可视化。

---

## 5. 与 001 特性的区分

- 001 特性侧重于“按天快照”的图构建，数据源主要是 SQLite（GHTorrent）；  
- 002 特性聚焦于“一小时事件流”的时序语义图，数据源是 JSON 行文件；  
- 两者在代码上通过 `services/temporal_semantic_graph/` 等子目录与独立测试文件进行区分，不会相互影响。

---

## 6. 常见问题（FAQ）

- **Q：如果输入文件中有部分行是损坏的 JSON 怎么办？**  
  A：程序会在日志中记录出错行号和原因，并跳过这些行，其余正常数据仍会被处理。

- **Q：能否只导出 JSON 而不导出 GraphML？**  
  A：可以在 `--export-format` 中只填写 `json`，同理如只需 GraphML 则填写 `graphml`。

- **Q：是否支持其他一小时文件？**  
  A：可以将 `--input` 参数改为其他同结构 JSON 行文件路径，只要数据格式与 GitHub 事件归档一致即可。


