# 技术研究：时间快照式时序图建模

**日期**：2024-12-19  
**特性**：时间快照式时序图建模

## 研究任务

### 1. Python SQLite数据库访问

**任务**：研究Python中访问SQLite数据库的最佳实践

**决策**：使用Python标准库`sqlite3`

**理由**：
- Python标准库内置，无需额外安装
- 支持SQLite 3.x的所有功能
- 提供连接、游标、事务管理等完整功能
- 性能满足只读访问需求

**替代方案考虑**：
- SQLAlchemy：功能强大但过于复杂，对于简单的只读查询是过度设计
- aiosqlite：异步支持，但当前需求是同步处理，不需要异步

**参考**：
- Python官方文档：https://docs.python.org/3/library/sqlite3.html

### 2. NetworkX图构建库

**任务**：研究NetworkX库用于构建和操作图的最佳实践

**决策**：使用NetworkX 2.x版本

**理由**：
- Python生态系统中最成熟的图处理库
- 支持有向图和无向图
- 提供丰富的图算法和操作
- 支持多种导出格式（GraphML、JSON、GEXF等）
- 良好的文档和社区支持

**替代方案考虑**：
- igraph：性能更好但API较复杂，且需要额外安装C库
- graph-tool：功能强大但安装复杂，对最小化实现来说过于重量级

**参考**：
- NetworkX官方文档：https://networkx.org/
- NetworkX GraphML导出：https://networkx.org/documentation/stable/reference/readwrite/graphml.html

### 3. GHTorrent数据库表结构

**任务**：研究GHTorrent数据库的标准表结构

**决策**：基于GHTorrent标准表结构设计数据提取逻辑

**理由**：
- GHTorrent是GitHub数据的标准化数据库格式
- 包含项目、用户、提交、仓库等核心表
- 时间戳字段通常使用`created_at`、`updated_at`等命名
- 需要支持灵活的表结构识别和降级处理

**关键表结构（预期）**：
- `projects`：项目信息
- `users`：用户/贡献者信息
- `commits`：提交信息（包含时间戳）
- `project_commits`：项目-提交关联
- `commit_parents`：提交父子关系

**替代方案考虑**：
- 硬编码表结构：不够灵活，无法处理表结构变化
- 动态表结构识别：更灵活，但需要额外的错误处理

**参考**：
- GHTorrent文档：http://ghtorrent.org/

### 4. 时间戳解析和处理

**任务**：研究Python中处理多种时间戳格式的最佳实践

**决策**：使用`datetime`标准库，支持多种常见时间戳格式

**理由**：
- Python标准库，无需额外依赖
- `datetime.strptime()`支持多种格式解析
- `datetime.fromisoformat()`支持ISO 8601格式
- 可以处理Unix时间戳（整数）

**支持的时间戳格式**：
- ISO 8601格式：`2024-01-01T12:00:00Z`
- 标准格式：`2024-01-01 12:00:00`
- Unix时间戳：整数秒数
- 其他常见格式（通过strptime解析）

**替代方案考虑**：
- dateutil：功能更强大但需要额外安装
- arrow：更现代的API但增加了依赖

**参考**：
- Python datetime文档：https://docs.python.org/3/library/datetime.html

### 5. GraphML和JSON导出格式

**任务**：研究NetworkX导出GraphML和JSON格式的最佳实践

**决策**：使用NetworkX内置的导出功能

**理由**：
- NetworkX原生支持GraphML和JSON导出
- `nx.write_graphml()`：导出GraphML格式，兼容Gephi、Cytoscape等工具
- `nx.node_link_data()`：生成JSON格式的图数据
- 支持节点和边的属性导出

**GraphML格式**：
- 标准XML格式，广泛支持
- 可以包含节点和边的所有属性
- 兼容主流图分析工具

**JSON格式**：
- 轻量级，易于解析
- 可以包含完整的图结构信息
- 适合程序化处理

**替代方案考虑**：
- GEXF格式：Gephi原生格式，但GraphML更通用
- DOT格式：Graphviz格式，但功能有限

**参考**：
- NetworkX GraphML文档：https://networkx.org/documentation/stable/reference/readwrite/graphml.html
- NetworkX JSON文档：https://networkx.org/documentation/stable/reference/readwrite/json_graph.html

### 6. 日志记录策略

**任务**：研究Python日志记录的最佳实践

**决策**：使用Python标准库`logging`模块

**理由**：
- Python标准库，无需额外依赖
- 支持多级别日志（DEBUG、INFO、WARNING、ERROR、CRITICAL）
- 可以输出到文件和控制台
- 支持日志格式化和轮转

**日志配置**：
- 文件日志：输出到`logs/app.log`
- 控制台日志：输出到标准输出
- 日志级别：INFO（生产环境），DEBUG（开发环境）
- 日志格式：包含时间戳、级别、模块、消息

**替代方案考虑**：
- loguru：更现代的API但增加了依赖
- structlog：结构化日志但过于复杂

**参考**：
- Python logging文档：https://docs.python.org/3/library/logging.html

## 技术栈总结

| 技术 | 版本 | 用途 | 理由 |
|------|------|------|------|
| Python | 3.8+ | 编程语言 | 用户指定，生态丰富 |
| sqlite3 | 标准库 | 数据库访问 | 标准库，无需安装 |
| NetworkX | 2.x | 图构建和操作 | 成熟的图处理库 |
| datetime | 标准库 | 时间处理 | 标准库，功能足够 |
| logging | 标准库 | 日志记录 | 标准库，无需额外依赖 |
| pytest | 最新 | 测试框架 | Python标准测试工具 |

## 未解决的问题

无。所有技术选型已明确，无需进一步澄清。

