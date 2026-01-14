# 时间快照式与时序语义图建模

一个用于开源项目结构与行为分析的图建模工具集，当前包含两类能力：

- **001 特性：时间快照式时序图建模** —— 从 GHTorrent SQLite 数据库中提取时间序列数据，按天粒度构建图快照；
- **002 特性：基于 GitHub 事件的一小时时序语义图建模** —— 从 GitHub 事件 JSON 行文件中构建带时间顺序与语义属性的一小时时序图。

## 功能特性

- 从 GHTorrent SQLite 数据库提取时间序列数据，按天粒度构建图快照（snapshot 模式）；
- 从 GitHub 事件 JSON 行文件构建一小时窗口的时序语义图（temporal-semantic-graph 模式）；
- 支持 GraphML 和 JSON 格式导出；
- 自动处理数据异常（记录并跳过策略）；
- 所有输出使用中文。

## 项目结构

```
oss_graph_construction/
├── src/                    # 源代码
│   ├── models/            # 数据模型（节点、边）
│   ├── services/          # 业务逻辑（数据库、提取、图构建、导出、时序语义图）
│   ├── cli/               # 命令行接口
│   └── utils/             # 工具函数（日志、日期处理）
├── tests/                 # 测试代码
│   ├── unit/              # 单元测试
│   ├── integration/       # 集成测试
│   └── contract/          # 契约测试
├── data/                  # 数据目录
│   ├── rxjs-ghtorrent.db          # GHTorrent 数据库文件
│   └── 2015-01-01-15.json         # GitHub 事件 JSON 行文件（一小时窗口示例）
├── output/                # 输出目录（自动创建）
└── logs/                  # 日志目录（自动创建）
```

## 安装步骤

### 1. 前置要求

- Python 3.8 或更高版本
- SQLite 3.x（通常随Python一起安装）

### 2. 创建虚拟环境（推荐）

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

依赖包：
- networkx>=2.8
- pytest>=7.0

### 4. 验证安装

```bash
python -c "import networkx as nx; print(f'NetworkX版本: {nx.__version__}')"
```

## 使用方法

### 基本用法（001：快照式时序图建模）

运行主程序从数据库提取数据并构建图快照：

```bash
# 方式1：使用run.py脚本（推荐）
python run.py

# 方式2：直接运行（需要设置PYTHONPATH）
# Windows PowerShell
$env:PYTHONPATH="."; python src/cli/main.py

# Linux/macOS
PYTHONPATH=. python src/cli/main.py
```

### 命令行选项（快照模式）

```bash
# 指定数据库路径（默认：data/rxjs-ghtorrent.db）
python run.py --db data/rxjs-ghtorrent.db

# 指定输出目录（默认：output/）
python run.py --output output/

# 指定日志级别（默认：INFO）
python run.py --log-level DEBUG

# 只处理特定日期范围
python run.py --start-date 2024-01-01 --end-date 2024-12-31

# 指定导出格式（graphml或json）
python run.py --format json

# 移除孤立节点（没有边的节点），使图更清晰便于分析
python run.py --remove-isolated
```

### 输出结果

程序执行后，会在 `output/` 目录下生成以下文件：

```
output/
├── snapshot_2024-01-01.graphml
├── snapshot_2024-01-02.graphml
├── snapshot_2024-01-03.graphml
└── ...
```

每个文件对应一个日期的图快照，可以使用Gephi、Cytoscape等工具打开。

### 一小时时序语义图模式（002：temporal-semantic-graph）

基于 GitHub 事件 JSON 行文件构建一小时时序语义图：

```bash
python -m src.cli.main temporal-semantic-graph \
  --input data/2015-01-01-15.json \
  --output-dir output/temporal-semantic-graph \
  --export-format json,graphml
```

参数说明：

- `--input`：GitHub 事件 JSON 行文件路径；
- `--output-dir`：时序语义图导出目录，默认 `output/temporal-semantic-graph/`；
- `--export-format`：导出格式列表（`json`、`graphml` 或两者）。

导出结果示例：

```text
output/temporal-semantic-graph/
├── temporal-graph-2015-01-01-15.json
└── temporal-graph-2015-01-01-15.graphml
```

JSON 文件遵循 `specs/002-temporal-semantic-graph/contracts/README.md` 中的结构约定：

- `meta`：包含源文件路径、生成时间、节点数、边数等元信息；
- `nodes`：节点列表（事件 / 开发者 / 仓库 / 提交），携带语义属性；
- `edges`：边列表（开发者→事件、事件→仓库、事件→提交），携带关系类型与时间属性。

## 工作流程

1. **数据提取阶段**：连接到SQLite数据库，识别所有包含时间戳的表，提取项目、贡献者、提交数据，按日期组织数据
2. **图构建阶段**：为每个日期创建NetworkX图对象，添加节点（项目、贡献者、提交）和边（贡献关系），累积节点
3. **导出阶段**：将每个图快照导出为GraphML或JSON格式，文件命名包含日期信息

## 日志查看

程序运行日志保存在 `logs/app.log`：

```bash
# 查看最新日志
tail -f logs/app.log

# 查看错误日志
grep ERROR logs/app.log
```

## 故障排除

### 问题：数据库文件不存在

**错误信息**：`数据库文件不存在或无法访问`

**解决方案**：
1. 确认 `data/rxjs-ghtorrent.db` 文件存在
2. 检查文件权限
3. 确认文件路径正确

### 问题：时间戳格式无法识别

**错误信息**：`无法解析时间戳格式`

**解决方案**：
1. 检查数据库中的时间戳格式
2. 查看日志中的警告信息
3. 系统会自动尝试多种格式，无法解析的记录会被跳过

### 问题：内存不足

**错误信息**：`内存不足`

**解决方案**：
1. 使用日期范围限制处理的数据量
2. 增加系统内存
3. 考虑分批处理数据

## 技术栈

- **Python 3.8+**: 编程语言
- **NetworkX 2.x**: 图构建和操作库
- **sqlite3**: 数据库访问（Python标准库）
- **datetime**: 时间处理（Python标准库）
- **logging**: 日志记录（Python标准库）

## 开发

### 运行测试

```bash
pytest tests/
```

### 代码结构

- `src/models/`: 数据模型定义（节点、边）
- `src/services/`: 业务逻辑服务
- `src/cli/`: 命令行接口
- `src/utils/`: 工具函数

## 许可证

[根据项目实际情况填写]

## 贡献

[根据项目实际情况填写]
