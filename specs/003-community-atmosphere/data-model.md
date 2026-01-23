# 数据模型：社区氛围分析

**日期**：2024-12-19  
**特性**：社区氛围分析

## 核心实体

### 1. 月度社区氛围指标（MonthlyAtmosphereMetrics）

**描述**：单个项目在单个月份的核心指标集合，是 `full_analysis.json` 中 `metrics` 列表的元素类型。

**字段**（对应 `src.models.community_atmosphere.MonthlyAtmosphereMetrics`）：
- `month` (str): 月份，格式 "YYYY-MM"，如 "2023-01"
- `repo_name` (str): 项目名称，如 "angular/angular"
- `average_emotion` (float): 平均情绪值，范围通常在-1到1之间
- `emotion_propagation_steps` (int): 情感传播步数
- `emotion_damping_factor` (float): 情感传播阻尼系数
- `global_clustering_coefficient` (float): 全局聚类系数，范围0到1
- `average_local_clustering` (float): 平均局部聚类系数
- `actor_graph_nodes` (int): 用于结构指标计算的 actor 图节点数（来源于 actor-actor 图或其无向化版本）
- `actor_graph_edges` (int): 用于结构指标计算的 actor 图边数
- `diameter` (int): 网络直径，如果图不连通则为最大连通分量的直径
- `average_path_length` (float): 平均路径长度
- `is_connected` (bool): 图是否连通
- `num_connected_components` (int): 连通分量数量
- `largest_component_size` (int): 最大连通分量的大小

**验证规则**：
- `repo_name` 和 `month` 必须非空，`month` 必须符合 "YYYY-MM" 格式
- `average_emotion` 应该在合理范围内（如-1到1）
- `global_clustering_coefficient`、`average_local_clustering` 应该在0到1之间
- `actor_graph_nodes`、`actor_graph_edges`、`largest_component_size` 必须大于等于0

### 2. 情感传播结果（EmotionPropagationResult）

**描述**：包含每个节点的最终情绪分数、传播历史记录和平均情绪值的分析结果

**字段**：
- `final_emotions` (Dict[str, float]): 每个节点的最终情绪分数，{node_id: emotion_score}
- `propagation_history` (List[Dict[str, float]]): 传播历史记录，每个元素是一个step的所有节点情绪状态
- `average_emotion` (float): 平均情绪值，范围通常在-1到1之间
- `propagation_steps` (int): 传播步数
- `damping_factor` (float): 阻尼系数

**验证规则**：
- `average_emotion` 应该在合理范围内（如-1到1）
- `propagation_steps` 必须大于0
- `damping_factor` 应该在0到1之间

### 3. 聚类系数结果（ClusteringCoefficientResult）

**描述**：包含全局聚类系数、局部聚类系数分布和平均局部聚类系数的计算结果

**字段**：
- `global_clustering_coefficient` (float): 全局聚类系数，范围0到1
- `local_clustering_coefficients` (Dict[str, float]): 每个节点的局部聚类系数，{node_id: coefficient}
- `average_local_clustering` (float): 平均局部聚类系数
- `actor_graph_nodes` (int): actor图节点数
- `actor_graph_edges` (int): actor图边数

**验证规则**：
- `global_clustering_coefficient` 应该在0到1之间
- `average_local_clustering` 应该在0到1之间
- `actor_graph_nodes` 必须大于0（至少有一个actor节点）

### 4. 网络直径结果（NetworkDiameterResult）

**描述**：包含网络直径、平均路径长度、连通性状态和连通分量数量的计算结果

**字段**：
- `diameter` (int): 网络直径，如果图不连通则为最大连通分量的直径
- `average_path_length` (float): 平均路径长度
- `is_connected` (bool): 图是否连通
- `num_connected_components` (int): 连通分量数量
- `largest_component_size` (int): 最大连通分量的大小

**验证规则**：
- `diameter` 必须大于等于0
- `average_path_length` 必须大于等于0
- 如果`is_connected`为True，`num_connected_components`应该为1
- `largest_component_size` 必须大于0

> 早期设计中还包括`时间范围分析结果（TimeRangeAnalysisResult）`等聚合实体；当前实现聚焦于**按月指标 + 基于整个时间序列的综合评分**，不再单独持久化聚合实体，但可以在后续迭代中基于 `metrics` 时间序列进行二次计算。

## 关系

### 实体关系图

```
MonthlyAtmosphereMetrics
├── EmotionPropagationResult (隐含：通过情感传播算法计算，核心字段写入average_emotion等数值)
├── ClusteringCoefficientResult (隐含：核心字段写入global_clustering_coefficient等数值)
└── NetworkDiameterResult (隐含：核心字段写入diameter、average_path_length等数值)
```

## 状态转换

### 分析流程状态

```
初始化 → 加载图文件 → 提取情感信息 → 计算指标 → 聚合结果 → 保存输出
   ↓           ↓            ↓           ↓          ↓          ↓
 错误      错误/跳过     降级处理     错误处理    错误处理   错误处理
```

## 数据持久化

### 输入数据

- **GraphML文件（讨论图）**：从`output/monthly-graphs/{repo_name}/actor-discussion/{month}.graphml`读取，标准GraphML格式，包含节点、边和`comment_body`属性（用于情感分析）
- **GraphML文件（协作图）**：从`output/monthly-graphs/{repo_name}/actor-actor/{month}.graphml`读取，标准GraphML格式，节点为Actor，边表示协作/互动关系（用于结构指标计算）

### 输出数据

- **JSON文件1：`full_analysis.json`**  
  - 路径：`output/community-atmosphere/`（或命令行指定的`--output-dir`）  
  - 结构：顶层以 `repo_name` 为键，每个项目包含：  
    - `metrics`: `MonthlyAtmosphereMetrics` 字典列表（按`month`排序，可按月增量写入/覆盖）  
    - `atmosphere_score`: 基于整条时间序列计算的综合评分对象（包含三大因子：`emotion`、`clustering`、`network_efficiency` 的值、得分和权重）  
  - 特性：分析过程中支持**按月增量更新**，断点续传时会在已有数据基础上继续填充。

- **JSON文件2：`summary.json`**  
  - 路径：同上  
  - 结构：项目级摘要列表，每个元素包含：`repo_name`、`atmosphere_score`、`level`、`months_analyzed`  
  - 特性：仅包含所有“可分析月份”均完成的项目，在项目完成分析时即时更新；再次运行分析器时会在此基础上刷新。

- **编码**：UTF-8，支持中文和emoji

## 数据验证

### 输入验证

- 图文件必须存在且可读
- 图文件必须符合GraphML格式
- 节点必须包含`node_type`属性（Actor、Issue、PullRequest）
- 边应该包含`comment_body`属性（可选）

### 输出验证

- JSON文件必须符合JSON格式规范
- 所有必需字段必须存在
- 数值字段必须在合理范围内
- 字符串字段必须非空（除非明确允许为空）

## 数据迁移

不适用。这是新功能，不涉及数据迁移。

