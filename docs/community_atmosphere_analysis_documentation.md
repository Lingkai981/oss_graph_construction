# 社区氛围分析详细文档

## 1. 概述

社区氛围分析旨在评估开源项目的社区健康度和协作氛围。通过分析情感传播、社区紧密度和网络效率三个维度，综合评估项目的社区氛围质量。

本分析器基于月度时间序列数据，计算每个项目的社区氛围指标，并生成综合评分。

## 2. 算法流程

### 2.1 整体流程

```
输入：月度 actor-discussion 图 + actor-actor 图（GraphML格式）
  ↓
1. 加载图文件
  ↓
2. 情感分析（使用 DeepSeek API）
  ↓
3. 情感传播模型计算
  ↓
4. 聚类系数计算
  ↓
5. 网络直径计算
  ↓
6. 生成月度指标
  ↓
7. 时间序列综合评分
  ↓
输出：月度指标时间序列 + 综合评分
```

### 2.2 关键步骤详解

#### 步骤1：加载图文件

**输入图类型**：

1. **actor-discussion 图**：
   - 节点类型：`Actor`、`Issue`、`PullRequest`
   - 边：从 Actor 到 Issue/PR 的参与关系
   - 边属性：`comment_body`（评论文本，用于情感分析）

2. **actor-actor 图**：
   - 节点类型：`Actor`
   - 边：Actor 之间的协作关系
   - 用于计算结构指标（聚类系数、网络直径）

**处理**：使用 NetworkX 的 `read_graphml()` 函数加载，支持 DiGraph 或 MultiDiGraph。

#### 步骤2：情感分析

**2.2.1 提取评论文本**

从 `actor-discussion` 图的边中提取 `comment_body`：

```python
for each edge in graph:
    comment_body = edge_data.get('comment_body', '')
    if comment_body and comment_body.strip():
        edges_to_process.append((edge_id, comment_body.strip()))
```

**2.2.2 调用 DeepSeek API**

使用 DeepSeek API 对每条评论进行情感分析：

```python
score = sentiment_client.analyze_sentiment(comment_body)
```

**情感分数范围**：-1 到 1
- **-1**：极度负面
- **0**：中性
- **1**：极度正面

**并发处理**：使用线程池（默认20个线程）并发调用 API，提高处理速度。

**2.2.3 情感分数映射**

将情感分数映射到边：

```python
sentiment_scores[edge_id] = score  # score ∈ [-1, 1]
```

#### 步骤3：情感传播模型

**3.1 算法原理**

使用类似 PageRank 的迭代传播模型，分析情绪如何在社区中传播。

**3.2 初始化节点情绪**

从边的情感分数初始化源节点的情绪：

```python
node_emotions = defaultdict(float)

for each edge (u → v) with sentiment_score:
    # 累加源节点的初始情绪（基于其发出的边的情感）
    node_emotions[u] += sentiment_score
```

**归一化初始情绪**：

```python
max_initial = max(abs(v) for v in node_emotions.values())
if max_initial > 0:
    for node in node_emotions:
        node_emotions[node] /= max_initial
```

**3.3 迭代传播**

进行 `propagation_steps` 步（默认5步）迭代传播：

```python
for step in range(propagation_steps):
    new_emotions = defaultdict(float)
    
    # 遍历所有边，情绪从源节点传播到目标节点
    for each edge (u → v) with sentiment_score:
        # 情绪传播：源节点的情绪 × 边的情感分数 × 阻尼系数
        propagation = node_emotions[u] * sentiment_score * damping_factor
        new_emotions[v] += propagation
    
    # 更新节点情绪（保留一部分原有情绪）
    for each node:
        node_emotions[node] = (
            damping_factor * node_emotions[node] + 
            (1 - damping_factor) * new_emotions[node]
        )
```

**参数说明**：
- `propagation_steps`：传播步数（默认5）
- `damping_factor`：阻尼系数（默认0.85），控制情绪衰减速度

**3.4 计算平均情绪**

```python
average_emotion = np.mean(list(node_emotions.values()))
```

**平均情绪含义**：
- **> 0**：整体情绪偏正面
- **< 0**：整体情绪偏负面
- **≈ 0**：整体情绪中性

#### 步骤4：聚类系数计算

**4.1 图准备**

如果输入是 `actor-discussion` 二部图，需要先构建 `actor-actor` 投影图：

```python
# 对于每个 discussion（Issue/PR），将其连接的 actor 节点两两之间建立边
for each discussion:
    actors = [所有连接到该 discussion 的 actor]
    for i in range(len(actors)):
        for j in range(i + 1, len(actors)):
            actor_graph.add_edge(actors[i], actors[j])
```

如果输入是 `actor-actor` 图，直接无向化并去重：

```python
# 将 MultiDiGraph/DiGraph 折叠为无向简单图
# - 忽略边方向
# - 多重边去重
# - 忽略自环
```

**4.2 全局聚类系数**

使用 NetworkX 的 `transitivity()` 函数计算全局聚类系数：

```python
global_clustering = nx.transitivity(actor_graph)
```

**全局聚类系数定义**：
```
C_global = 3 × 三角形数量 / 连通三元组数量
```

**取值范围**：0 到 1
- **1**：完全聚类（所有邻居都相互连接）
- **0**：无聚类（没有三角形）

**4.3 局部聚类系数**

使用 NetworkX 的 `clustering()` 函数计算每个节点的局部聚类系数：

```python
local_clustering = nx.clustering(actor_graph)
```

**局部聚类系数定义**（对于节点 i）：
```
C_i = 2 × E_i / (k_i × (k_i - 1))
```

其中：
- `E_i`：节点 i 的邻居之间的边数
- `k_i`：节点 i 的度数

**4.4 平均局部聚类系数**

```python
average_local_clustering = np.mean(list(local_clustering.values()))
```

**含义**：
- **高值（> 0.5）**：社区成员之间紧密协作，形成小团体
- **低值（< 0.2）**：社区成员之间协作松散

#### 步骤5：网络直径计算

**5.1 图准备**

同步骤4.1，准备 `actor-actor` 无向图。

**5.2 连通性检查**

```python
is_connected = nx.is_connected(actor_graph)
num_components = nx.number_connected_components(actor_graph)
```

**5.3 直径计算**

如果图连通：

```python
diameter = nx.diameter(actor_graph)
average_path_length = nx.average_shortest_path_length(actor_graph)
```

如果图不连通：

```python
# 计算最大连通分量的直径
connected_components = list(nx.connected_components(actor_graph))
largest_cc = max(connected_components, key=len)
subgraph = actor_graph.subgraph(largest_cc)
diameter = nx.diameter(subgraph)
average_path_length = nx.average_shortest_path_length(subgraph)
```

**网络直径定义**：
- 所有节点对之间最短路径的最大值

**平均路径长度定义**：
- 所有节点对之间最短路径的平均值

**含义**：
- **直径小（≤ 6）**：信息传播效率高，沟通路径短
- **直径大（> 10）**：信息传播效率低，沟通路径长

#### 步骤6：生成月度指标

对于每个月份，生成 `MonthlyAtmosphereMetrics` 对象，包含：

**情感传播指标**：
- `average_emotion`：平均情绪值（-1 到 1）
- `emotion_propagation_steps`：传播步数
- `emotion_damping_factor`：阻尼系数

**聚类系数指标**：
- `global_clustering_coefficient`：全局聚类系数（0 到 1）
- `average_local_clustering`：平均局部聚类系数（0 到 1）
- `actor_graph_nodes`：actor 图节点数
- `actor_graph_edges`：actor 图边数

**网络直径指标**：
- `diameter`：网络直径
- `average_path_length`：平均路径长度
- `is_connected`：图是否连通
- `num_connected_components`：连通分量数量
- `largest_component_size`：最大连通分量的大小

#### 步骤7：时间序列综合评分

**7.1 计算时间维度平均值**

```python
avg_emotion = sum(m.average_emotion for m in metrics_series) / len(metrics_series)
avg_clustering = sum(m.average_local_clustering for m in metrics_series) / len(metrics_series)
avg_diameter = sum(m.diameter for m in metrics_series) / len(metrics_series)
avg_path_length = sum(m.average_path_length for m in metrics_series) / len(metrics_series)
```

**7.2 归一化与权重设定**

综合评分 = 情绪得分（20分）+ 聚类得分（40分）+ 网络效率得分（40分）

**权重分配**：
- **情绪 20%**：技术讨论多为中性，区分度有限
- **聚类系数 40%**：反映社区成员间的紧密协作关系，区分度高
- **网络效率 40%**：反映信息传播效率和社区连通性，区分度高

**7.3 情绪得分计算（0-20分）**

```python
# 情绪：-1 ~ 1 线性映射到 0 ~ 1，再乘以 20 分
emotion_norm = max(0.0, min(1.0, (avg_emotion + 1.0) / 2.0))
emotion_score = emotion_norm * 20
```

**映射规则**：
- `avg_emotion = -1` → `emotion_norm = 0` → `emotion_score = 0`
- `avg_emotion = 0` → `emotion_norm = 0.5` → `emotion_score = 10`
- `avg_emotion = 1` → `emotion_norm = 1` → `emotion_score = 20`

**7.4 聚类得分计算（0-40分）**

使用平滑增长函数进行归一化，避免线性映射对低值过于严格：

```python
clustering_threshold = 0.6
clustering_growth_factor = 2.0

if avg_clustering <= 0.0:
    clustering_norm = 0.0
elif avg_clustering >= clustering_threshold:
    clustering_norm = 1.0
else:
    # 使用平滑增长函数
    clustering_norm = 1.0 / (1.0 + clustering_growth_factor * 
                             (clustering_threshold - avg_clustering) / 
                             clustering_threshold)
    # 确保最小值不会太小
    if avg_clustering > 0.01:
        clustering_norm = max(0.05, clustering_norm)

clustering_score = clustering_norm * 40
```

**映射示例**：
- `avg_clustering = 0` → `clustering_norm = 0` → `clustering_score = 0`
- `avg_clustering = 0.1` → `clustering_norm ≈ 0.33` → `clustering_score ≈ 13.2`
- `avg_clustering = 0.2` → `clustering_norm ≈ 0.5` → `clustering_score = 20`
- `avg_clustering = 0.4` → `clustering_norm ≈ 0.75` → `clustering_score = 30`
- `avg_clustering = 0.6` → `clustering_norm = 1.0` → `clustering_score = 40`

**7.5 网络效率得分计算（0-40分）**

基于直径和平均路径长度，使用对数衰减函数：

```python
# 直径分量
diameter_decay_factor = 0.3
if avg_diameter <= 1.0:
    diameter_component = 1.0
else:
    diameter_component = 1.0 / (1.0 + diameter_decay_factor * (avg_diameter - 1.0))
    diameter_component = max(0.05, diameter_component)

# 路径长度分量
path_decay_factor = 0.4
if avg_path_length <= 1.0:
    path_component = 1.0
else:
    path_component = 1.0 / (1.0 + path_decay_factor * (avg_path_length - 1.0))
    path_component = max(0.05, path_component)

# 综合网络效率
network_norm = 0.5 * diameter_component + 0.5 * path_component
network_score = network_norm * 40
```

**直径分量映射示例**：
- `avg_diameter = 1` → `diameter_component = 1.0`
- `avg_diameter = 6` → `diameter_component ≈ 0.4`
- `avg_diameter = 10` → `diameter_component ≈ 0.23`
- `avg_diameter = 20` → `diameter_component ≈ 0.12`

**路径长度分量映射示例**：
- `avg_path_length = 1` → `path_component = 1.0`
- `avg_path_length = 3.5` → `path_component ≈ 0.5`
- `avg_path_length = 5` → `path_component ≈ 0.38`
- `avg_path_length = 8` → `path_component ≈ 0.22`

**7.6 综合评分计算**

```python
total_score = emotion_score + clustering_score + network_score
```

**7.7 等级划分**

```python
if total_score >= 80:
    level = "excellent"  # 优秀
elif total_score >= 60:
    level = "good"       # 良好
elif total_score >= 40:
    level = "moderate"   # 中等
else:
    level = "poor"       # 较差
```

## 3. 指标说明

### 3.1 情感传播指标

#### 平均情绪值（Average Emotion）

- **定义**：经过情感传播模型计算后，所有节点的平均情绪值
- **取值范围**：-1 到 1
- **含义**：
  - **> 0.2**：整体情绪偏正面，社区氛围积极
  - **-0.2 到 0.2**：整体情绪中性，技术讨论为主
  - **< -0.2**：整体情绪偏负面，可能存在冲突或不满
- **计算方式**：见步骤3

#### 传播步数（Propagation Steps）

- **定义**：情感传播模型的迭代步数
- **默认值**：5
- **含义**：控制情绪传播的深度

#### 阻尼系数（Damping Factor）

- **定义**：控制情绪衰减速度的系数
- **默认值**：0.85
- **取值范围**：0 到 1
- **含义**：
  - **接近 1**：情绪衰减慢，传播范围广
  - **接近 0**：情绪衰减快，传播范围窄

### 3.2 聚类系数指标

#### 全局聚类系数（Global Clustering Coefficient）

- **定义**：图的传递性，衡量整个网络的聚类程度
- **取值范围**：0 到 1
- **计算公式**：`3 × 三角形数量 / 连通三元组数量`
- **含义**：
  - **> 0.5**：社区成员之间形成紧密的小团体
  - **0.2 到 0.5**：中等程度的聚类
  - **< 0.2**：社区成员之间协作松散

#### 平均局部聚类系数（Average Local Clustering）

- **定义**：所有节点的局部聚类系数的平均值
- **取值范围**：0 到 1
- **计算公式**：见步骤4.3
- **含义**：同全局聚类系数，但更关注局部结构

### 3.3 网络直径指标

#### 网络直径（Diameter）

- **定义**：所有节点对之间最短路径的最大值
- **取值范围**：非负整数
- **含义**：
  - **≤ 6**：信息传播效率高，沟通路径短（小世界网络特征）
  - **7 到 10**：中等效率
  - **> 10**：信息传播效率低，沟通路径长

#### 平均路径长度（Average Path Length）

- **定义**：所有节点对之间最短路径的平均值
- **取值范围**：非负浮点数
- **含义**：同网络直径，但反映平均情况

#### 连通性指标

- `is_connected`：图是否连通
- `num_connected_components`：连通分量数量
- `largest_component_size`：最大连通分量的大小

**含义**：
- **连通**：所有成员都可以通过协作网络相互联系
- **不连通**：存在孤立的成员或小团体

### 3.4 综合评分指标

#### 总分（Total Score）

- **定义**：社区氛围综合评分（0-100）
- **计算公式**：`emotion_score + clustering_score + network_score`
- **含义**：分数越高，社区氛围越好

#### 等级（Level）

- **excellent**：总分 ≥ 80，社区氛围优秀
- **good**：60 ≤ 总分 < 80，社区氛围良好
- **moderate**：40 ≤ 总分 < 60，社区氛围中等
- **poor**：总分 < 40，社区氛围较差

#### 各因子得分

- `emotion`：情绪得分（0-20）
- `clustering`：聚类得分（0-40）
- `network_efficiency`：网络效率得分（0-40）

## 4. 输出格式

### 4.1 月度指标（MonthlyAtmosphereMetrics）

```json
{
  "month": "2023-01",
  "repo_name": "angular/angular",
  "average_emotion": 0.15,
  "emotion_propagation_steps": 5,
  "emotion_damping_factor": 0.85,
  "global_clustering_coefficient": 0.35,
  "average_local_clustering": 0.42,
  "actor_graph_nodes": 200,
  "actor_graph_edges": 500,
  "diameter": 6,
  "average_path_length": 3.5,
  "is_connected": true,
  "num_connected_components": 1,
  "largest_component_size": 200
}
```

### 4.2 综合评分（Atmosphere Score）

```json
{
  "score": 72.5,
  "level": "good",
  "months_analyzed": 12,
  "period": "2023-01 to 2023-12",
  "factors": {
    "emotion": {
      "value": 0.15,
      "score": 11.5,
      "weight": 20
    },
    "clustering": {
      "value": 0.42,
      "score": 28.0,
      "weight": 40
    },
    "network_efficiency": {
      "value": {
        "average_diameter": 6.0,
        "average_path_length": 3.5
      },
      "score": 33.0,
      "weight": 40
    }
  }
}
```

### 4.3 完整分析结果（full_analysis.json）

```json
{
  "angular/angular": {
    "metrics": [
      { /* MonthlyAtmosphereMetrics */ },
      ...
    ],
    "atmosphere_score": { /* Atmosphere Score */ }
  },
  ...
}
```

### 4.4 摘要（summary.json）

```json
[
  {
    "repo_name": "angular/angular",
    "atmosphere_score": 72.5,
    "level": "good",
    "months_analyzed": 12
  },
  ...
]
```

## 5. 使用说明

### 5.1 环境配置

**必需**：DeepSeek API Key

在项目根目录创建 `.env` 文件：

```
DEEPSEEK_API_KEY=your_api_key_here
```

### 5.2 命令行参数

```bash
python -m src.analysis.community_atmosphere_analyzer \
  --graphs-dir output/monthly-graphs/ \
  --output-dir output/community-atmosphere-analysis/
```

**参数说明**：
- `--graphs-dir`：图文件目录（默认：`output/monthly-graphs/`）
- `--output-dir`：输出目录（默认：`output/community-atmosphere/`）

### 5.3 断点续传

默认支持断点续传：
- 自动检测已处理的月份，跳过已分析的数据
- 按月增量保存，每完成一个月就保存结果
- 按项目完成时更新摘要

### 5.4 并发处理

情感分析使用线程池并发处理（默认20个线程），提高 API 调用效率。

## 6. 算法复杂度

### 6.1 时间复杂度

- **情感分析**：O(E)，E 为边数（API 调用）
- **情感传播**：O(E × S)，S 为传播步数（默认5）
- **聚类系数**：O(V × d²)，V 为节点数，d 为平均度
- **网络直径**：O(V × E)
- **总体**：O(E × S + V × d² + V × E)

### 6.2 空间复杂度

- **情感分数字典**：O(E)
- **节点情绪字典**：O(V)
- **月度指标列表**：O(M)
- **总体**：O(E + V + M)

## 7. 注意事项

1. **DeepSeek API**：必需配置 API Key，否则情感分析将失败
2. **图文件要求**：需要同时存在 `actor-discussion` 和 `actor-actor` 图
3. **评论数据**：只有包含 `comment_body` 的边才会进行情感分析
4. **API 调用限制**：注意 API 调用频率限制，避免超出配额
5. **网络效率**：对于大型项目，网络直径计算可能较慢

## 8. 参考文献

- 情感传播模型：基于 PageRank 的迭代传播算法
- 聚类系数：衡量网络的小世界特征
- 网络直径：衡量信息传播效率
- 小世界网络：Watts-Strogatz 模型

