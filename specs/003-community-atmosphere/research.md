# 技术研究：社区氛围分析

**日期**：2024-12-19  
**特性**：社区氛围分析

## 研究任务

### 1. 情感传播模型算法实现

**任务**：研究如何实现情感传播模型，分析情绪如何在社区中传播

**决策**：使用类似PageRank的迭代传播算法

**理由**：
- 情感传播模型需要模拟情绪在网络中的传播过程
- PageRank算法已经验证了在网络中传播信息的有效性
- 时间复杂度O(V+E) per step符合规范要求
- 可以设置传播步数和阻尼系数来控制传播范围

**算法设计**：
1. 初始化：从边的comment_body提取情感分数，初始化源节点的情绪状态
2. 迭代传播：每个step中，情绪从源节点沿着边传播到目标节点
3. 阻尼机制：使用阻尼系数（0.85）保留部分原有情绪，避免过度传播
4. 收敛：经过指定步数（默认5步）后停止，或达到收敛条件

**替代方案考虑**：
- 线性代数方法：计算复杂度高，不适合大规模图
- 随机游走：需要更多迭代次数，性能较差

**参考**：
- PageRank算法原理：https://en.wikipedia.org/wiki/PageRank
- NetworkX图算法库文档

### 2. 聚类系数计算在二部图/协作图中的应用

**任务**：研究如何在actor-discussion二部图和actor-actor协作图中计算聚类系数

**决策**：
- 对于actor-discussion二部图：构建actor之间的投影图，然后计算聚类系数；
- 对于actor-actor协作图：直接在去重后的无向actor图上计算聚类系数（将多重边/方向折叠为简单无向边）。

**理由**：
- actor-discussion图是二部图，不能直接计算聚类系数，需要通过投影获得actor-actor视图；
- 项目中已经存在更语义化的actor-actor协作图（基于Issue回复、PR审查、合并等事件构建），在结构性指标上更贴近“真实协作网络”；
- 因此实现上优先使用actor-actor图，如果只提供actor-discussion图则回退到投影逻辑；
- NetworkX提供`clustering()`和`transitivity()`函数可以直接使用，时间复杂度O(V·d²)符合规范要求。

**实现方法**：
1. 如果输入是actor-discussion二部图：  
   1）遍历所有discussion节点，收集连接到每个discussion的actor节点；  
   2）对于每个discussion，将其连接的actor节点两两之间建立边（actor投影图）；  
2. 如果输入是actor-actor协作图：  
   1）保留所有Actor节点；  
   2）忽略边方向和多重边，将其折叠为无向简单边，去除自环；  
3. 使用NetworkX的`transitivity()`计算全局聚类系数；  
4. 使用NetworkX的`clustering()`计算局部聚类系数，并求平均值得到`average_local_clustering`。

**替代方案考虑**：
- 直接使用二部图聚类系数：需要自定义实现，复杂度高
- 使用其他紧密度指标：但规范明确要求聚类系数

**参考**：
- NetworkX聚类系数文档：https://networkx.org/documentation/stable/reference/algorithms/clustering.html
- 二部图投影方法：https://networkx.org/documentation/stable/auto_examples/algorithms/plot_bipartite.html

### 3. 网络直径计算

**任务**：研究如何在actor-actor协作网络（或从二部图投影得到的actor图）上计算网络直径，评估社区沟通效率

**决策**：使用NetworkX的`diameter()`和`average_shortest_path_length()`函数，输入为去重后的无向actor图

**理由**：
- NetworkX提供了成熟的网络直径计算函数
- 支持非连通图的处理（计算最大连通分量的直径）
- 时间复杂度O(V·E)符合规范要求
- 可以同时计算平均路径长度作为补充指标

**实现方法**：
1. 如果输入是actor-discussion二部图，则先构建actor之间的投影图（与聚类系数相同的方法）；如果输入是actor-actor图，则直接无向化并去重。  
2. 检查图的连通性。  
3. 如果连通：使用`diameter()`和`average_shortest_path_length()`。  
4. 如果不连通：找到最大连通分量，计算其直径和平均路径长度。

**边界情况处理**：
- 单节点图：直径为0
- 完全孤立节点：计算最大连通分量
- 空图：返回0或None

**参考**：
- NetworkX直径计算文档：https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html

### 4. DeepSeek API集成

**任务**：研究如何集成DeepSeek API进行情感分析

**决策**：使用requests库调用DeepSeek API，通过环境变量配置API key

**理由**：
- DeepSeek提供RESTful API接口，易于集成
- 使用环境变量配置API key符合安全最佳实践
- requests库是Python标准HTTP库，稳定可靠
- 支持超时和重试机制，确保系统健壮性

**API调用设计**：
1. 从环境变量`DEEPSEEK_API_KEY`读取API key
2. 构建API请求（POST请求，包含comment_body文本）
3. 设置合理的超时时间（如10秒）
4. 处理API响应，提取情感分数
5. 如果API调用失败，降级到关键词匹配方法

**降级策略**：
- API key未配置：直接使用关键词匹配
- API调用超时：记录警告，使用关键词匹配
- API返回错误：记录错误，使用关键词匹配
- 速率限制：实现重试机制，超过重试次数后降级

**参考**：
- DeepSeek API文档（需要查阅最新文档）
- requests库文档：https://requests.readthedocs.io/

### 5. 图合并策略

**任务**：研究如何合并多个月份的图文件

**决策**：保留所有节点，根据comment_body是否相同决定是否合并边

**理由**：
- 保留所有节点确保不丢失任何参与者信息
- 根据comment_body判断是否合并边，确保不丢失评论内容
- 如果comment_body相同，合并边并累加权重（事件数量），反映整体活跃度
- 如果comment_body不同，保留为多条边，保留每条评论的独立信息

**合并算法**：
1. 遍历所有月份的图文件
2. 对于每个节点：直接添加到合并图中（NetworkX会自动去重）
3. 对于每条边：
   - 检查是否已存在相同的(source, target, comment_body)组合
   - 如果存在：累加权重（如事件数量）
   - 如果不存在：添加新边
4. 保留所有边的属性（created_at等）

**性能考虑**：
- 使用字典缓存已存在的边，提高查找效率
- 对于大时间范围（>12个月），考虑分批合并或使用近似算法

**参考**：
- NetworkX图合并方法：https://networkx.org/documentation/stable/reference/classes/graph.html

### 6. 加权平均聚合方法

**任务**：研究如何对多个月份的指标进行加权平均聚合

**决策**：按各月的事件数量或节点数量进行加权平均

**理由**：
- 加权平均能够反映不同月份的活跃度差异
- 活跃度高的月份应该对最终指标有更大影响
- 使用事件数量或节点数量作为权重，客观反映社区活跃度
- 简单易懂，计算效率高

**聚合公式**：
```
加权平均 = Σ(指标_i × 权重_i) / Σ(权重_i)
其中权重_i = 事件数量_i 或 节点数量_i
```

**实现方法**：
1. 分别计算每个月的三个核心指标
2. 获取每个月的权重（事件数量或节点数量）
3. 对每个指标（情感传播、聚类系数、网络直径）分别计算加权平均
4. 保留月度指标序列，便于趋势分析

**替代方案考虑**：
- 简单平均：忽略了活跃度差异，不够准确
- 中位数：对异常值更稳健，但可能丢失重要信息
- 时间序列分析：可以提供趋势信息，但复杂度高，可作为未来扩展

**参考**：
- 加权平均算法：标准统计学方法
- numpy库的加权平均函数：`numpy.average(weights=...)`

## 技术选型总结

| 技术选择 | 选型 | 理由 |
|---------|------|------|
| 情感传播算法 | PageRank式迭代传播 | 时间复杂度符合要求，易于实现 |
| 聚类系数计算 | NetworkX + 投影图 | 成熟库，支持二部图投影 |
| 网络直径计算 | NetworkX diameter函数 | 标准算法，支持非连通图 |
| API集成 | requests库 | Python标准HTTP库，稳定可靠 |
| 图合并 | 基于comment_body的边合并 | 保留评论信息，累加权重 |
| 聚合方法 | 加权平均 | 反映活跃度差异，计算简单 |

## 未解决的问题

无。所有技术选型已明确，可以进入设计阶段。

