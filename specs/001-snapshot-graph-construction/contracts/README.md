# API契约：时间快照式时序图建模

**日期**：2024-12-19  
**特性**：时间快照式时序图建模

## 概述

本特性是一个命令行工具，不提供REST API或GraphQL接口。所有功能通过命令行参数调用。

## 命令行接口

### 主程序入口

**程序**：`src/cli/main.py`

**调用方式**：
```bash
python src/cli/main.py [选项]
```

### 命令行参数

| 参数 | 类型 | 必需 | 默认值 | 描述 |
|------|------|------|--------|------|
| `--db` | string | 否 | `data/rxjs-ghtorrent.db` | SQLite数据库文件路径 |
| `--output` | string | 否 | `output/` | 输出目录路径 |
| `--log-level` | string | 否 | `INFO` | 日志级别（DEBUG/INFO/WARNING/ERROR） |
| `--start-date` | string | 否 | 无（处理所有日期） | 起始日期（YYYY-MM-DD格式） |
| `--end-date` | string | 否 | 无（处理所有日期） | 结束日期（YYYY-MM-DD格式） |
| `--format` | string | 否 | `graphml` | 导出格式（graphml/json） |

### 返回值

- **退出码 0**：成功执行
- **退出码 1**：数据库文件不存在或无法访问
- **退出码 2**：数据提取错误
- **退出码 3**：图构建错误
- **退出码 4**：导出错误

### 输出格式

#### GraphML格式

文件扩展名：`.graphml`

示例文件名：`snapshot_2024-01-01.graphml`

格式：标准GraphML XML格式，包含所有节点和边的属性

#### JSON格式

文件扩展名：`.json`

示例文件名：`snapshot_2024-01-01.json`

格式：NetworkX node-link格式的JSON

```json
{
  "directed": true,
  "multigraph": false,
  "graph": {},
  "nodes": [
    {
      "id": "project_1",
      "node_type": "project",
      "name": "rxjs"
    }
  ],
  "links": [
    {
      "source": "contributor_1",
      "target": "commit_abc123",
      "edge_type": "contributes"
    }
  ]
}
```

## 内部服务接口

### 数据库服务

**模块**：`src/services/database.py`

**主要函数**：
- `connect_database(db_path: str) -> sqlite3.Connection`
- `get_table_names(conn: sqlite3.Connection) -> List[str]`
- `extract_projects(conn: sqlite3.Connection) -> List[Dict]`
- `extract_contributors(conn: sqlite3.Connection) -> List[Dict]`
- `extract_commits_by_date(conn: sqlite3.Connection, date: str) -> List[Dict]`

### 数据提取服务

**模块**：`src/services/extractor.py`

**主要函数**：
- `extract_all_dates(conn: sqlite3.Connection) -> List[str]`
- `extract_data_for_date(conn: sqlite3.Connection, date: str) -> Dict`

### 图构建服务

**模块**：`src/services/graph_builder.py`

**主要函数**：
- `build_snapshot(data: Dict, previous_snapshot: nx.DiGraph = None) -> nx.DiGraph`
- `add_nodes(graph: nx.DiGraph, nodes: List[Dict]) -> None`
- `add_edges(graph: nx.DiGraph, edges: List[Dict]) -> None`

### 导出服务

**模块**：`src/services/exporter.py`

**主要函数**：
- `export_graphml(graph: nx.DiGraph, output_path: str) -> None`
- `export_json(graph: nx.DiGraph, output_path: str) -> None`

## 错误处理

所有错误通过日志记录，不抛出异常（除非是致命错误）。

错误级别：
- **DEBUG**：调试信息
- **INFO**：正常执行信息
- **WARNING**：警告（如跳过无效记录）
- **ERROR**：错误（如数据库连接失败）

## 数据契约

### 输入数据

- SQLite数据库文件（只读访问）
- 符合GHTorrent标准表结构

### 输出数据

- GraphML文件（标准格式）
- JSON文件（NetworkX node-link格式）
- 日志文件（文本格式）

## 版本信息

- **API版本**：1.0
- **最后更新**：2024-12-19

