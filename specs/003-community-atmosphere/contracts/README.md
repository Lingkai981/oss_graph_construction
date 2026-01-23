# 接口契约：社区氛围分析

**日期**：2024-12-19  
**特性**：社区氛围分析

## 概述

本文档定义了社区氛围分析系统的内部接口契约。虽然这是一个CLI工具，但定义了清晰的模块接口，便于测试和维护。

## 核心接口

### 1. 社区氛围分析器接口

**模块**：`src.analysis.community_atmosphere_analyzer.CommunityAtmosphereAnalyzer`

**主要职责（与当前实现对齐）**：

- 构造函数：
  ```python
  class CommunityAtmosphereAnalyzer:
      def __init__(
          self,
          graphs_dir: str = "output/monthly-graphs/",
          output_dir: str = "output/community-atmosphere/",
      ) -> None: ...
  ```
  - `graphs_dir`：月度图根目录（包含 `actor-discussion/` 和 `actor-actor/` 子目录）  
  - `output_dir`：输出目录，保存 `full_analysis.json` 和 `summary.json`

- 图加载：
  ```python
  def load_graph(self, graph_path: str) -> Optional[nx.MultiDiGraph]:
      """加载GraphML图文件，失败时返回None并记录日志"""
  ```

- 单月指标计算（内部接口）：
  ```python
  def compute_monthly_metrics(
      self,
      discussion_graph: nx.Graph,
      actor_actor_graph: nx.Graph,
      repo_name: str,
      month: str,
  ) -> Optional[MonthlyAtmosphereMetrics]:
      """在给定月份上计算情感传播、聚类系数和网络直径"""
  ```

- 全量分析入口：
  ```python
  def analyze_all_repos(self) -> Dict[str, Any]:
      """遍历索引，按项目/月份分析并维护断点续传状态"""
  
  def run(self) -> Dict[str, Any]:
      """CLI 主入口：调用 analyze_all_repos 并最终刷新 full_analysis / summary"""
  ```

**契约（与断点续传/图类型相关）**：
- 输入：
  - 对于每个 `repo_name` 和 `month`，若同时存在：  
    - `actor-discussion/{month}.graphml`：用于提取 `comment_body` 并执行情感传播；  
    - `actor-actor/{month}.graphml`：用于结构指标（聚类系数、网络直径）；  
    则该月份视为“可分析月份”。
  - 旧格式索引（无法区分图类型）当前实现会跳过，用日志告警。
- 断点续传：
  - `full_analysis.json` 中每个项目的 `metrics` 列表可以按月增量更新；再次运行时，已存在的月份不会重复计算，除非显式覆盖逻辑被修改。
  - 判断项目是否“完成”的标准：其所有可分析月份都已出现在 `metrics` 列表中。
- 输出：
  - `full_analysis.json`：随分析进度按月刷新；结构见 quickstart 文档。  
  - `summary.json`：仅包含已完成项目；在项目完成时和最终 `run()` 结束时刷新。

### 2. 情感传播算法接口

**模块**：`src.algorithms.emotion_propagation.analyze_emotion_propagation`

**函数签名**：

```python
def analyze_emotion_propagation(
    graph: nx.MultiDiGraph,
    sentiment_scores: Optional[Dict[str, float]] = None,
    propagation_steps: int = 5,
    damping_factor: float = 0.85,
) -> Dict[str, Any]
```

**输入契约**：
- `graph`：必须是有效的NetworkX MultiDiGraph
- `sentiment_scores`：如果为None，将从图的边属性中提取
- `propagation_steps`：必须大于0，默认5
- `damping_factor`：必须在0到1之间，默认0.85

**输出契约**：
- 返回字典包含：`final_emotions`、`propagation_history`、`average_emotion`
- `final_emotions`：键为节点ID，值为情绪分数（float）
- `propagation_history`：列表，每个元素是一个step的所有节点情绪状态
- `average_emotion`：所有节点情绪分数的平均值

**错误处理**：
- 如果图为空，返回空结果
- 如果没有任何情感分数，返回中性值（0.0）

### 3. 聚类系数算法接口

**模块**：`src.algorithms.clustering_coefficient.compute_clustering_coefficient`

**函数签名**：

```python
def compute_clustering_coefficient(
    graph: nx.MultiDiGraph,
) -> Dict[str, Any]
```

**输入契约**：
- `graph`：必须是有效的NetworkX MultiDiGraph，包含Actor和Discussion节点

**输出契约**：
- 返回字典包含：`global_clustering_coefficient`、`local_clustering_coefficients`、`average_local_clustering`、`actor_graph_nodes`、`actor_graph_edges`
- `global_clustering_coefficient`：float，范围0到1
- `local_clustering_coefficients`：字典，键为节点ID，值为局部聚类系数
- `average_local_clustering`：float，所有局部聚类系数的平均值

**错误处理**：
- 如果图为空或没有Actor节点，返回0值
- 如果图只有单个节点，返回0值

### 4. 网络直径算法接口

**模块**：`src.algorithms.network_diameter.compute_network_diameter`

**函数签名**：

```python
def compute_network_diameter(
    graph: nx.MultiDiGraph,
) -> Dict[str, Any]
```

**输入契约**：
- `graph`：必须是有效的NetworkX MultiDiGraph

**输出契约**：
- 返回字典包含：`diameter`、`average_path_length`、`is_connected`、`num_connected_components`、`largest_component_size`
- `diameter`：int，网络直径
- `average_path_length`：float，平均路径长度
- `is_connected`：bool，图是否连通

**错误处理**：
- 如果图为空，返回0值
- 如果图不连通，计算最大连通分量的直径
- 如果图只有单个节点，直径为0

### 5. 情感分析服务接口

**模块**：`src.services.sentiment`

**接口1：DeepSeek客户端**

```python
class DeepSeekClient:
    def __init__(self, api_key: Optional[str] = None) -> None
    
    def analyze_sentiment(self, text: str) -> float
    """分析文本情感，返回-1到1之间的分数"""
    
    def is_available(self) -> bool
    """检查API是否可用"""
```

**接口2：关键词匹配器**

```python
class KeywordMatcher:
    def analyze_sentiment(self, text: str) -> float
    """使用关键词匹配分析情感，返回-1到1之间的分数"""
```

**接口3：情感分析服务（统一接口）**

```python
class SentimentAnalyzer:
    def __init__(self) -> None
    
    def analyze(self, text: str) -> float
    """分析文本情感，自动选择DeepSeek或关键词匹配"""
    
    def get_method(self) -> str
    """返回当前使用的方法（'deepseek'或'keyword'）"""
```

**契约**：
- `analyze`：如果DeepSeek不可用，自动降级到关键词匹配
- 返回的情感分数应该在-1到1之间
- 如果文本为空，返回0.0（中性）

### 6. 图合并服务接口

**模块**：`src.services.graph_merger.merge_graphs`

**函数签名**：

```python
def merge_graphs(
    graphs: List[nx.MultiDiGraph],
    months: List[str],
) -> nx.MultiDiGraph
```

**输入契约**：
- `graphs`：图文件列表，每个图对应一个月份
- `months`：月份列表，与graphs一一对应

**输出契约**：
- 返回合并后的MultiDiGraph
- 所有节点都被保留
- 如果边(source, target, comment_body)相同，合并并累加权重
- 如果边(source, target)相同但comment_body不同，保留为多条边

**错误处理**：
- 如果graphs为空，返回空图
- 如果某些图文件损坏，跳过并记录警告

## 数据契约

### 输入数据格式

**GraphML文件结构**：
- 根元素：`<graphml>`
- 图元素：`<graph>`，属性`edgedefault="directed"`
- 节点：`<node id="...">`，包含`node_type`属性
- 边：`<edge source="..." target="...">`，包含`comment_body`属性（可选）

### 输出数据格式

**JSON文件结构**：
```json
[
  {
    "repo_name": "angular/angular",
    "month": "2023-01",
    "time_range": null,
    "analysis_mode": "single",
    "emotion_propagation": {
      "final_emotions": {"actor:123": 0.5, ...},
      "average_emotion": 0.3,
      "propagation_steps": 5
    },
    "clustering_coefficient": {
      "global_clustering_coefficient": 0.6,
      "average_local_clustering": 0.5
    },
    "network_diameter": {
      "diameter": 5,
      "average_path_length": 2.3,
      "is_connected": true
    }
  }
]
```

## 错误处理契约

### 错误级别

1. **ERROR**：严重错误，导致分析无法继续
   - 图文件格式完全错误
   - API key配置错误且无法降级
   
2. **WARNING**：警告，分析可以继续但结果可能不完整
   - 某些边缺失comment_body
   - 某些月份图文件缺失
   - API调用失败，降级到关键词匹配

3. **INFO**：信息，正常流程中的提示
   - 分析开始/完成
   - 处理进度

### 错误处理策略

- **记录并跳过**：对于单个图文件错误，记录并继续处理其他文件
- **降级处理**：对于API错误，降级到备用方法
- **默认值**：对于缺失数据，使用合理的默认值（如中性情感分数0.0）

## 性能契约

### 时间性能

- 单个1000节点图文件分析：≤5分钟
- 6个月合并图分析：≤15分钟
- 6个月分别计算再聚合分析：≤20分钟
- API降级检测：≤3秒

### 空间性能

- 内存使用：与图大小成正比，单文件不超过50万节点
- 磁盘使用：输出JSON文件大小与结果数量成正比

## 测试契约

### 单元测试要求

- 每个算法函数必须有对应的单元测试
- 测试覆盖率≥80%
- 必须测试边界情况（空图、单节点图等）

### 集成测试要求

- 测试完整分析流程
- 测试时间范围分析
- 测试批量分析
- 测试错误处理和降级机制

