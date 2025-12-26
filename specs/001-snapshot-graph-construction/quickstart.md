# 快速开始指南：时间快照式时序图建模

**日期**：2024-12-19  
**特性**：时间快照式时序图建模

## 前置要求

### 系统要求

- Python 3.8 或更高版本
- SQLite 3.x（通常随Python一起安装）
- 至少 1GB 可用磁盘空间（用于输出文件）

### 数据库文件

确保 `data/rxjs-ghtorrent.db` 文件存在于项目根目录下。

## 安装步骤

### 1. 克隆或下载项目

```bash
cd oss_graph_construction
```

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

**requirements.txt 内容**：
```
networkx>=2.8
pytest>=7.0
```

### 4. 验证安装

```bash
python -c "import networkx as nx; print(f'NetworkX版本: {nx.__version__}')"
```

## 使用方法

### 基本用法

运行主程序从数据库提取数据并构建图快照：

```bash
python src/cli/main.py
```

### 命令行选项

```bash
# 指定数据库路径（默认：data/rxjs-ghtorrent.db）
python src/cli/main.py --db data/rxjs-ghtorrent.db

# 指定输出目录（默认：output/）
python src/cli/main.py --output output/

# 指定日志级别（默认：INFO）
python src/cli/main.py --log-level DEBUG

# 只处理特定日期范围（可选，默认处理所有日期）
python src/cli/main.py --start-date 2024-01-01 --end-date 2024-12-31
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

## 工作流程

### 1. 数据提取阶段

- 连接到SQLite数据库
- 识别所有包含时间戳的表
- 提取项目、贡献者、提交数据
- 按日期组织数据

### 2. 图构建阶段

- 为每个日期创建NetworkX图对象
- 添加节点（项目、贡献者、提交）
- 添加边（贡献关系）
- 累积节点（节点在所有后续快照中存在）

### 3. 导出阶段

- 将每个图快照导出为GraphML格式
- 可选：导出为JSON格式
- 文件命名包含日期信息

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

### 问题：导出文件无法打开

**错误信息**：`GraphML文件格式错误`

**解决方案**：
1. 确认NetworkX版本 >= 2.8
2. 检查图对象是否包含有效数据
3. 查看日志中的错误信息

## 示例输出

### 成功执行

```
2024-12-19 10:00:00 INFO - 开始数据提取
2024-12-19 10:00:05 INFO - 识别到 1000 个日期
2024-12-19 10:00:10 INFO - 提取完成：1000 个日期，50000 条记录
2024-12-19 10:00:15 INFO - 开始构建图快照
2024-12-19 10:05:00 INFO - 构建完成：1000 个快照
2024-12-19 10:05:05 INFO - 开始导出图快照
2024-12-19 10:10:00 INFO - 导出完成：1000 个文件
2024-12-19 10:10:00 INFO - 处理完成
```

### 部分错误（记录并跳过）

```
2024-12-19 10:00:00 INFO - 开始数据提取
2024-12-19 10:00:03 WARNING - 跳过无效时间戳记录：record_id=12345
2024-12-19 10:00:05 INFO - 识别到 1000 个日期
2024-12-19 10:00:10 INFO - 提取完成：1000 个日期，49995 条记录（跳过5条无效记录）
```

## 下一步

- 查看 [data-model.md](./data-model.md) 了解数据模型详情
- 查看 [research.md](./research.md) 了解技术选型
- 运行 `/speckit.tasks` 生成任务列表开始实现

