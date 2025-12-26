# 数据模型：时间快照式时序图建模

**日期**：2024-12-19  
**特性**：时间快照式时序图建模

## 实体定义

### 节点（Node）

图中的实体，最小化实现包含三种类型：

#### 1. 项目节点（Project Node）

**类型标识**：`project`

**属性**：
- `node_id` (string, 必需)：节点唯一标识符，格式：`project_{project_id}`
- `node_type` (string, 必需)：节点类型，固定值：`project`
- `name` (string, 可选)：项目名称
- `created_at` (datetime, 可选)：项目创建时间
- `updated_at` (datetime, 可选)：项目更新时间

**来源**：GHTorrent数据库的`projects`表

#### 2. 贡献者节点（Contributor Node）

**类型标识**：`contributor`

**属性**：
- `node_id` (string, 必需)：节点唯一标识符，格式：`contributor_{user_id}`
- `node_type` (string, 必需)：节点类型，固定值：`contributor`
- `login` (string, 可选)：贡献者登录名
- `name` (string, 可选)：贡献者显示名称
- `created_at` (datetime, 可选)：账户创建时间

**来源**：GHTorrent数据库的`users`表

#### 3. 提交节点（Commit Node）

**类型标识**：`commit`

**属性**：
- `node_id` (string, 必需)：节点唯一标识符，格式：`commit_{commit_sha}`
- `node_type` (string, 必需)：节点类型，固定值：`commit`
- `sha` (string, 可选)：提交SHA哈希值
- `message` (string, 可选)：提交消息（截断到前200字符）
- `created_at` (datetime, 必需)：提交时间（用于时间快照）

**来源**：GHTorrent数据库的`commits`表

### 边（Edge）

节点之间的关系，最小化实现包含贡献关系边：

#### 贡献关系边（Contribution Edge）

**类型标识**：`contributes`

**属性**：
- `source` (string, 必需)：源节点ID（贡献者节点）
- `target` (string, 必需)：目标节点ID（提交节点）
- `edge_type` (string, 必需)：边类型，固定值：`contributes`
- `created_at` (datetime, 必需)：关系创建时间（提交时间）
- `project_id` (string, 可选)：关联的项目ID

**来源**：通过关联`users`、`commits`和`project_commits`表构建

## 数据验证规则

### 节点验证

1. **必需字段检查**：
   - 所有节点必须包含`node_id`和`node_type`
   - 提交节点必须包含`created_at`（用于时间快照）

2. **唯一性检查**：
   - `node_id`必须在图中唯一
   - 同一类型的节点不能有重复的ID

3. **类型验证**：
   - `node_type`必须是以下值之一：`project`、`contributor`、`commit`
   - `edge_type`必须是：`contributes`

### 边验证

1. **必需字段检查**：
   - 所有边必须包含`source`、`target`、`edge_type`和`created_at`

2. **节点存在性检查**：
   - `source`和`target`节点必须在图中存在
   - 贡献关系边：`source`必须是贡献者节点，`target`必须是提交节点

3. **时间一致性**：
   - 边的时间戳必须在对应时间快照的日期范围内

## 时间快照模型

### 快照结构

每个时间快照是一个独立的NetworkX图对象，包含：

- **快照日期**：快照对应的日期（YYYY-MM-DD格式）
- **节点集合**：该日期及之前的所有节点（累积）
- **边集合**：该日期及之前的所有边（累积）

### 快照构建规则

1. **节点累积**：节点一旦创建就存在于所有后续快照中
2. **边累积**：边一旦创建就存在于所有后续快照中
3. **完整图状态**：每个快照反映到该日期为止的完整图状态，包括所有历史节点和历史边
4. **空快照处理**：如果某天没有新数据，仍会创建包含历史节点和边的快照（保持图的连续性）

## 数据库表映射

### 预期表结构

基于GHTorrent标准格式：

```sql
-- 项目表
projects (
    id INTEGER PRIMARY KEY,
    name TEXT,
    url TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)

-- 用户表
users (
    id INTEGER PRIMARY KEY,
    login TEXT,
    name TEXT,
    created_at TIMESTAMP
)

-- 提交表
commits (
    id INTEGER PRIMARY KEY,
    sha TEXT,
    message TEXT,
    author_id INTEGER,  -- 关联users.id
    created_at TIMESTAMP
)

-- 项目-提交关联表
project_commits (
    project_id INTEGER,  -- 关联projects.id
    commit_id INTEGER,   -- 关联commits.id
    PRIMARY KEY (project_id, commit_id)
)
```

### 数据提取查询

```sql
-- 提取项目节点
SELECT id, name, created_at, updated_at FROM projects;

-- 提取贡献者节点
SELECT id, login, name, created_at FROM users;

-- 提取提交节点（按日期）
SELECT id, sha, message, author_id, created_at 
FROM commits 
WHERE DATE(created_at) = ?;

-- 提取贡献关系（按日期）
SELECT u.id as contributor_id, c.id as commit_id, c.created_at
FROM commits c
JOIN users u ON c.author_id = u.id
JOIN project_commits pc ON c.id = pc.commit_id
WHERE DATE(c.created_at) = ?;
```

## 状态转换

### 节点生命周期

1. **创建**：节点首次出现在数据库中
2. **更新**：节点属性发生变化（在当前实现中不跟踪更新）
3. **持久化**：节点在所有后续快照中保持存在

### 边生命周期

1. **创建**：提交发生时创建贡献关系边
2. **快照包含**：边只出现在其创建日期对应的快照中
3. **不删除**：边一旦创建就不会从历史快照中删除

## 数据一致性

### 时间一致性

- 所有时间戳必须能够解析为有效的datetime对象
- 时间戳格式不一致时，尝试多种格式解析
- 无法解析的时间戳记录警告并跳过

### 引用完整性

- 边的`source`和`target`必须引用存在的节点
- 如果节点不存在，创建边时自动创建缺失的节点（基于数据库数据）

### 数据质量

- 缺失必需字段的记录跳过并记录警告
- 无效数据（如空字符串、NULL值）使用默认值或跳过
- 所有数据质量问题记录到日志

