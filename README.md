# OSS 社区健康度分析工具

基于 GitHub Archive 事件数据，构建多类型时序图并进行维护者倦怠（Burnout）分析的工具集。

## 功能概览

```
┌─────────────────────────────────────────────────────────────────┐
│                      OSS 社区健康度分析                          │
├─────────────────────────────────────────────────────────────────┤
│  1. 数据采集        从 GitHub Archive 下载并过滤代表性项目数据    │
│  2. 三类图构建      Actor-Actor / Actor-Repo / Actor-Discussion  │
│  3. 社区氛围分析    情感传播 + 聚类系数 + 网络直径                │
│  4. 倦怠分析        三层架构评分 + 多维度预警                     │
│  5. Bus Factor 分析 组织参与与控制风险分析                        │
│  6. 详细报告          按项目输出完整分析过程                      │
└─────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### 2. 数据采集（可选）

如果需要采集新数据：

```bash
# 方式一：按预设代表性项目列表下载（--project-count 控制数量）
python -m src.data_collection.gharchive_collector \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  --sample-mode fulldaily \
  --workers 16 \
  --output-dir data/filtered

# 方式二：按已有月度图索引中的仓库列表下载（用于扩展历史或补充数据）
python -m src.data_collection.gharchive_collector \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  --sample-mode fulldaily \
  --repos-from-index output/monthly-graphs/index.json \
  --output-dir data/filtered
```

python3 -m src.data_collection.gharchive_collector \
  --start-date 2021-07-01 --end-date 2025-12-31 \
  --sample-mode fulldaily \
  --workers 16 \
  --repos-from-index output/monthly-graphs2/index.json \
  --output-dir /Users/milk/test_data/ali2025/filtered_union_2021_2025_fulldaily

采样模式说明：`fulldaily` = 每天 24 小时全量采集，按日合并为 1 个 JSON；`daily` = 每天 1 小时；`monthly` = 每月 1 小时（数据量小）

### 3. 构建月度图

```bash
# 构建全部月份
python -m src.analysis.monthly_graph_builder \
  --data-dir data/filtered \
  --output-dir output/monthly-graphs \
  --workers 4

# 仅构建指定月份范围，并合并到已有输出目录（增量构建）
python -m src.analysis.monthly_graph_builder \
  --data-dir data/filtered \
  --output-dir output/monthly-graphs \
  --start-month YYYY-MM \
  --end-month YYYY-MM \
  --workers 4
```

### 4. 运行社区氛围分析

```bash
# 分析所有项目（使用整个时间序列）
python -m src.analysis.community_atmosphere_analyzer \
  --graphs-dir output/monthly-graphs/ \
  --output-dir output/community-atmosphere-analysis/

# 使用DeepSeek API进行情感分析（必需）
# 在项目根目录创建.env文件，添加：DEEPSEEK_API_KEY=your_api_key_here
python -m src.analysis.community_atmosphere_analyzer \
  --graphs-dir output/monthly-graphs/ \
  --output-dir output/community-atmosphere-analysis/
```

**社区氛围分析功能**：
- **情感传播模型**：分析情绪如何在社区中传播（使用DeepSeek API进行情感分析）
- **聚类系数**：衡量社区紧密度
- **网络直径**：评估社区沟通效率
- **时间序列分析**：自动处理整个时间序列，为每个项目生成月度指标时间序列
- **综合评分**：基于时间序列指标计算社区氛围综合评分

### 社区氛围分析原理与指标说明

#### 整体分析流程

- **输入数据**：
  - `actor-discussion` 图：开发者与 Issue/PR 的参与关系，边上包含 `comment_body`（评论文本），用于情感分析与情感传播；
  - `actor-actor` 图：开发者之间的协作关系网络，用于结构性指标（聚类系数、网络直径）计算；
  - `output/monthly-graphs/index.json`：索引所有项目、图类型与月份对应的 `.graphml` 文件路径。
- **逐项目、逐月份处理**：
  - 对每个项目，找到既有 `actor-discussion` 又有 `actor-actor` 图的“可分析月份集合”；
  - 对每一个可分析月份：
    1. 读取 `actor-discussion` 图，抽取评论文本并调用 DeepSeek API 得到情感分数；
    2. 在 `actor-discussion` 图上运行情感传播模型，得到本月的整体情绪氛围指标；
    3. 读取同月的 `actor-actor` 图，计算聚类系数与网络直径等结构性指标；
    4. 将本月的所有指标汇总为一条 `MonthlyAtmosphereMetrics` 记录。
- **时间序列与综合评分**：
  - 每完成一个月份的计算，就将该月份写入 `full_analysis.json`（支持断点续传）；
  - 对同一项目的所有已完成月份，按时间序列汇总，计算“社区氛围综合评分 `atmosphere_score`”；
  - 当某项目所有“可分析月份”都完成后，会把该项目的综合评分写入 `summary.json`，形成按分数排序的摘要列表。

#### 算法一：情感分析与情感传播模型

- **情感分数抽取（边级别）**：
  - 对 `actor-discussion` 图中每条包含非空 `comment_body` 的边，调用 DeepSeek API 做情感分析；
  - DeepSeek 返回的情绪分数被归一化到 \[-1, 1] 区间：
    - 数值 **> 0**：偏正向，越大表示越积极；
    - 数值 **< 0**：偏负向，绝对值越大表示越消极；
    - 数值 **≈ 0**：情绪中性或不明显；
  - 分数以 `edge_id -> score` 的形式缓存，用于后续传播（若调用失败则退化为 0.0，即中性）。

- **节点初始情绪状态**：
  - 对每条有情感分数的边，累计其源节点的情绪值：  
    - `node_emotion[u] += sentiment_score(edge u→v)`；
  - 对所有节点的初始情绪做一次归一化，避免某些高度活跃节点情绪值过大导致数值爆炸。

- **PageRank 风格情感传播（迭代 `propagation_steps` 次）**：
  - 在每一步中：
    1. 遍历所有边，将源节点的情绪乘以该边的情感分数和阻尼系数 `damping_factor` 传播到目标节点；
    2. 对每个节点，将“保留的旧情绪”和“新收到的情绪”按阻尼系数组合：
       - 新情绪 = `damping_factor * old + (1 - damping_factor) * incoming`；
  - 默认参数：
    - `propagation_steps = 5`：限制传播轮数，避免无休止扩散；
    - `damping_factor = 0.85`：类似 PageRank 的阻尼系数，控制情绪保持与更新的平衡。

- **输出指标含义**：
  - `average_emotion`：本月所有节点最终情绪值的平均数，范围约在 \[-1, 1]：
    - 趋近 **1**：整体氛围非常积极，正向反馈居多；
    - 约为 **0**：情绪总体中性或对冲；
    - 趋近 **-1**：整体氛围偏消极，需要关注讨论中的负面情绪；
  - `emotion_propagation_steps`：本次传播迭代步数（默认 5）；
  - `emotion_damping_factor`：本次传播使用的阻尼系数（默认 0.85）。

#### 算法二：聚类系数（社区紧密度）

- **Actor 图准备（投影/去重）**：
  - 若输入为 `actor-actor` 图：
    - 直接将多重、有向边折叠为 **无向简单图**（去掉自环）；
  - 若输入为 `actor-discussion` 图：
    - 先构建一个 **投影图**：
      - 若两个开发者共同参与同一个 Issue 或 PR，则在这两个 Actor 之间连一条无向边；
      - 所有 Actor 节点都会被保留，即便暂时没有边。

- **指标计算步骤**：
  - **全局聚类系数 `global_clustering_coefficient`**：
    - 采用 NetworkX 的 `transitivity`，衡量“闭合三角形（朋友的朋友也是朋友）”的比例；
    - 取值 [0, 1]，越接近 1 说明开发者之间的连接越“成团”。
  - **局部聚类系数与平均局部聚类系数**：
    - 对每个节点计算“邻居之间实际连边数 / 邻居之间可能的最大连边数”；
    - 将所有节点的局部聚类系数取平均，得到 `average_local_clustering`；
    - 该值 [0, 1] 越大，说明“典型开发者周围的小团体越紧密”。
  - 同时记录：
    - `actor_graph_nodes`：Actor 图节点数（参与社区互动的开发者规模）；
    - `actor_graph_edges`：Actor 图边数（协作关系数量）。

- **解释建议**：
  - `global_clustering_coefficient` 高 & `average_local_clustering` 高：
    - 社区具有明显的“小团体”结构，核心成员之间互相高度连通；
  - 两者都接近 0：
    - 说明协作关系稀疏，开发者之间协同较少，互动多为点对点、一次性。

#### 算法三：网络直径（沟通效率）

- **Actor 图准备**：
  - 与聚类系数相同，统一在“无向简单 Actor 图”上计算；
  - 若原图非连通，会挑出**最大连通分量**作为代表。

- **核心步骤**：
  - **连通性检查**：
    - `is_connected`：图是否整体连通；
    - `num_connected_components`：连通分量数量；
    - `largest_component_size`：最大连通分量的节点数。
  - **若图连通**：
    - `diameter`：所有节点对之间最短路径的最大值，表示“最远两点之间需要经过多少步”；
    - `average_path_length`：所有节点对之间最短路径长度的平均值，表示“典型两点之间的平均距离”。
  - **若图不连通**：
    - 在最大连通分量子图上计算 `diameter` 和 `average_path_length`，其他孤立点不参与；
  - 直观上：
    - `diameter` 越小：说明最远的两个人之间“中间需要转手的人”更少，结构更紧凑；
    - `average_path_length` 越小：说明信息在典型两点之间传播所需的“跳数”更少，沟通更高效。

#### 综合评分：社区氛围得分 `atmosphere_score`

- **时间序列聚合**：
  - 对某项目所有月份的 `MonthlyAtmosphereMetrics`：
    - 计算时间维度上的平均值：
      - `avg_emotion`：平均情绪；
      - `avg_clustering`：平均局部聚类系数；
      - `avg_diameter`：平均网络直径；
      - `avg_path_length`：平均路径长度。

- **三大因子与权重（调整后）**：
  - **情绪因子（Emotion，20 分）**：
    - 把 [-1, 1] 的 `avg_emotion` 线性映射到 [0, 1] 再乘以 20：
      - `emotion_norm = (avg_emotion + 1) / 2`（截断到 [0,1]）；
      - `emotion_score = emotion_norm * 20`；
    - **权重降低原因**：技术讨论多为中性，情绪区分度有限，因此降低权重以突出结构指标。
  - **社区紧密度因子（Clustering，40 分）**：
    - 使用**平滑增长函数**进行归一化，避免线性映射对低值过于严格：
      - 使用公式 `clustering_norm = 1 / (1 + 2.0 × (0.6 - clustering) / 0.6)`，平滑增长：
        - 聚类系数 = 0 → 0.0
        - 聚类系数 = 0.1 → 0.33
        - 聚类系数 = 0.2 → 0.5
        - 聚类系数 = 0.4 → 0.75
        - 聚类系数 ≥ 0.6 → 1.0（满分）
      - `clustering_score = clustering_norm * 40`；
    - **归一化改进原因**：使用平滑函数可以让低聚类系数（0.1-0.2）的项目得到更合理的分数，而不是被线性映射压得很低，更好地反映不同规模项目的协作紧密程度。
    - **权重提高原因**：聚类系数能有效反映社区成员间的紧密协作关系，区分度高，更能体现社区氛围质量。
  - **网络效率因子（Network Efficiency，40 分）**：
    - 使用**对数衰减函数**进行归一化，避免硬截断，适应不同规模的项目：
      - **直径分量**：使用公式 `diameter_component = 1 / (1 + 0.3 × (diameter - 1))`，平滑衰减：
        - 直径 = 1 → 1.0（满分）
        - 直径 = 6 → 0.4
        - 直径 = 10 → 0.23
        - 直径 = 20 → 0.12（大项目仍有一定分数，不会完全为0）
      - **路径长度分量**：使用公式 `path_component = 1 / (1 + 0.4 × (path_length - 1))`，平滑衰减：
        - 路径长度 = 1 → 1.0（满分）
        - 路径长度 = 3.5 → 0.5
        - 路径长度 = 5 → 0.38
        - 路径长度 = 8 → 0.22（大项目仍有一定分数，不会完全为0）
    - 再取两者平均得到 `network_norm`，乘以 40 得到 `network_score`。
    - **归一化改进原因**：大项目的网络直径和路径长度天然更大，使用对数衰减函数可以避免硬截断到0，让评分更公平地反映不同规模项目的网络效率。
    - **权重提高原因**：网络效率反映信息传播效率和社区连通性，是衡量社区氛围的重要结构指标，区分度高。

- **总分与等级**：
  - 总分范围 [0, 100]：  
    - `total_score = emotion_score + clustering_score + network_score`；
  - 等级划分（用于 `summary.json` 中的 `level` 字段）：
    - `excellent`：`total_score ≥ 80`，社区氛围非常健康；
    - `good`：`60 ≤ total_score < 80`，整体良好，局部可优化；
    - `moderate`：`40 ≤ total_score < 60`，一般，需要关注局部问题；
    - `poor`：`total_score < 40`，整体氛围偏弱或存在明显问题。

#### 结果文件与示例

- **full_analysis.json（按项目聚合的完整结果）**：
  - 结构（示意）：
  
```json
{
  "mochajs/mocha": {
    "metrics": [
      {
        "month": "2023-05",
        "repo_name": "mochajs/mocha",
        "average_emotion": -0.0308128689236111,
        "emotion_propagation_steps": 5,
        "emotion_damping_factor": 0.85,
        "global_clustering_coefficient": 0.0,
        "average_local_clustering": 0.0,
        "actor_graph_nodes": 2,
        "actor_graph_edges": 1,
        "diameter": 1,
        "average_path_length": 1.0,
        "is_connected": true,
        "num_connected_components": 1,
        "largest_component_size": 2
      }
      // ... 其他月份 ...
    ],
    "atmosphere_score": {
      "score": 50.03,
      "level": "moderate",
      "months_analyzed": 25,
      "period": "2023-05 to 2025-12",
      "factors": {
        "emotion": {
          "value": 0.055,
          "score": 13.2,
          "weight": 20
        },
        "clustering": {
          "value": 0.047,
          "score": 2.94,
          "weight": 40
        },
        "network_efficiency": {
          "value": {
            "average_diameter": 1.36,
            "average_path_length": 1.136
          },
          "score": 27.5,
          "weight": 40
        }
      }
    }
  }
}
```

- **summary.json（只包含“全部月份已分析完”的项目）**：

```json
[
  {
    "repo_name": "mochajs/mocha",
    "atmosphere_score": 50.03,
    "level": "moderate",
    "months_analyzed": 25
  },
  {
    "repo_name": "automatic1111/stable-diffusion-webui",
    "atmosphere_score": 49.02,
    "level": "moderate",
    "months_analyzed": 32
  },
  {
    "repo_name": "vercel/next.js",
    "atmosphere_score": 44.63,
    "level": "moderate",
    "months_analyzed": 37
  }
]
```

你可以通过直接查看 `output/community-atmosphere-analysis/full_analysis.json` 与 `summary.json`，来进一步探索各项目在不同月份的具体社区氛围变化趋势与结构特征。

### 5. 运行 Bus Factor 分析

```bash
# 分析所有项目（使用整个时间序列，自动使用多进程并行）
python -m src.analysis.bus_factor_analyzer \
  --graphs-dir output/monthly-graphs/ \
  --output-dir output/bus-factor-analysis/

# 指定并行工作进程数（推荐设置为 CPU 核心数）
python -m src.analysis.bus_factor_analyzer \
  --graphs-dir output/monthly-graphs/ \
  --output-dir output/bus-factor-analysis/ \
  --workers 4

# 使用单进程模式（便于调试）
python -m src.analysis.bus_factor_analyzer \
  --graphs-dir output/monthly-graphs/ \
  --output-dir output/bus-factor-analysis/ \
  --workers 1

# 单项目单月份分析（用于测试）
python -m src.analysis.bus_factor_analyzer \
  --repo angular-angular \
  --month 2023-01

# 自定义阈值和权重
python -m src.analysis.bus_factor_analyzer \
  --threshold 0.6 \
  --weights-file config/weights.json
```

**Bus Factor 分析功能**：
- **Bus Factor 计算**：计算达到总贡献量50%所需的最少贡献者数量
- **Bot 账号过滤**：自动识别并过滤 Bot 账号，避免扭曲分析结果
- **贡献量聚合**：支持可配置权重，综合考虑提交、PR、Issue、评论等贡献类型
- **时间序列分析**：自动处理整个时间序列，为每个项目生成月度指标时间序列
- **趋势分析**：使用线性回归计算 Bus Factor 的变化趋势
- **综合风险评分**：基于当前值和趋势计算综合风险评分（0-100），使用分位数归一化提高稳健性
- **断点续传**：支持中断后继续分析，自动跳过已处理的月份
- **多进程并行**：支持多进程并行处理，显著提升分析速度（默认使用 CPU 核心数）

### Bus Factor 分析原理与指标说明

#### 整体分析流程

- **输入数据**：
  - `actor-repo` 图：开发者与仓库的贡献关系，边上包含统计信息（`commit_count`, `pr_merged`, `pr_opened`, `issue_opened`, `issue_closed`, `is_comment` 等）；
  - `output/monthly-graphs/index.json`：索引所有项目、图类型与月份对应的 `.graphml` 文件路径。
- **逐项目、逐月份处理**（支持多进程并行）：
  - 对每个项目，找到所有有 `actor-repo` 图的月份；
  - **并行处理**：默认使用多进程并行处理不同项目，显著提升分析速度（可通过 `--workers` 参数控制进程数）；
  - 对每一个月份：
    1. 读取 `actor-repo` 图，遍历所有边（从 actor 到 repo 的边）；
    2. 使用权重公式聚合每个贡献者的贡献量（综合考虑提交、PR、Issue、评论等）；
    3. 按贡献量降序排序，累积贡献量直到达到总贡献量的 50%（可配置阈值）；
    4. 返回达到阈值所需的最少贡献者数量，即该月份的 Bus Factor；
    5. 将本月的所有指标汇总为一条 `MonthlyRiskMetrics` 记录。
- **时间序列与综合评分**：
  - 每完成一个月份的计算，就将该月份写入 `full_analysis.json`（支持断点续传）；
  - 对同一项目的所有已完成月份，按时间序列汇总：
    - 计算加权平均 Bus Factor（按总贡献量加权，更准确反映项目整体状况）；
    - 使用线性回归计算 Bus Factor 的变化趋势；
  - 基于当前 Bus Factor 值和趋势方向，计算综合风险评分；
  - 当某项目所有月份都完成后，会把该项目的综合评分写入 `summary.json`，形成按风险评分排序的摘要列表。

#### 算法一：Bus Factor 计算（累积贡献量方法）

- **核心原理**：
  - Bus Factor 衡量的是：如果项目中最活跃的贡献者突然离开，需要多少人来替代他们才能维持项目的正常运转。
  - 经典定义：达到总贡献量 50%（可配置阈值）所需的最少贡献者数量。
  - Bus Factor 越小，说明项目越依赖少数核心贡献者，风险越高。

- **计算步骤**：
  1. **聚合贡献量**：对每个贡献者，累加其在所有边上的贡献量（使用权重公式）；
  2. **排序**：按贡献量降序排序所有贡献者；
  3. **累积计算**：从贡献量最大的贡献者开始，累加贡献量直到达到总贡献量的 50%；
  4. **返回结果**：返回达到阈值所需的最少贡献者数量。

- **示例**：
  ```
  假设有 5 个贡献者，贡献量分别为：[100, 80, 60, 40, 20]
  总贡献量 = 300
  目标阈值 = 300 × 0.5 = 150
  
  累积过程：
  贡献者1: 100 (累积: 100 < 150，继续)
  贡献者2: 80  (累积: 180 ≥ 150，停止)
  
  Bus Factor = 2（需要前 2 个贡献者才能达到 50% 的贡献量）
  ```

- **边界情况处理**：
  - 如果总贡献量为 0，返回 `None`（表示该月份无有效数据）；
  - 如果所有贡献者加起来都不够阈值，返回贡献者总数（表示需要所有贡献者）。

#### 算法二：贡献量聚合（可配置权重）

- **权重配置**：
  - 默认权重（可在配置文件中自定义）：
    ```python
    DEFAULT_WEIGHTS = {
        "commit_count": 1.0,      # 提交次数
        "pr_merged": 3.0,         # 合并的 PR（高价值）
        "pr_opened": 2.0,         # 打开的 PR
        "pr_closed": 1.0,         # 关闭的 PR
        "issue_opened": 1.5,      # 打开的 Issue
        "issue_closed": 2.0,      # 关闭的 Issue
        "is_comment": 0.5,        # 评论（参与度）
    }
    ```
  - **权重设计理由**：
    - `pr_merged` 权重最高（3.0）：合并的 PR 代表实际被采纳的代码贡献，价值最高；
    - `pr_opened` 和 `issue_closed` 权重较高（2.0）：打开 PR 和关闭 Issue 代表主动参与；
    - `commit_count` 权重为 1.0：作为基础贡献单位；
    - `is_comment` 权重最低（0.5）：评论虽然重要，但相对代码贡献价值较低。

- **贡献量计算公式**：
  ```python
  contribution = (
      commit_count × 1.0 +
      pr_merged × 3.0 +
      pr_opened × 2.0 +
      pr_closed × 1.0 +
      issue_opened × 1.5 +
      issue_closed × 2.0 +
      is_comment × 0.5
  )
  ```

- **Bot 账号过滤**：
  - 自动识别并过滤 Bot 账号（如 `[bot]`, `-bot`, `_bot`, `bot-`, `bot_` 等）；
  - Bot 账号的贡献量不计入 Bus Factor 计算，避免扭曲分析结果；
  - 过滤后，如果总贡献量为 0，`bus_factor` 返回 `None`。

- **聚合过程**：
  - 遍历 `actor-repo` 图中所有从 actor 到 repo 的边；
  - 对每条边，检查是否为 Bot 账号，如果是则跳过；
  - 对非 Bot 账号的边，使用权重公式计算该边的贡献量；
  - 对每个贡献者，累加其所有边的贡献量，得到总贡献量。

#### 算法三：时间序列分析（加权平均 Bus Factor）

- **加权平均计算**：
  - 不使用简单平均，而是使用**按总贡献量加权**的平均值：
    ```python
    weighted_avg_bus_factor = Σ(bus_factor_i × total_contribution_i) / Σ(total_contribution_i)
    ```
  - **理由**：贡献量大的月份更能反映项目的真实状况，应该给予更高权重。
  - 这个加权平均值就是 `weighted_avg_bus_factor`，用于后续的风险评分计算。

- **数据过滤**：
  - 只考虑 `bus_factor` 不为 `None` 的月份（过滤掉无有效数据的月份）；
  - 如果所有月份都没有有效数据，返回 `None`，跳过风险评分。

#### 算法四：趋势分析（线性回归）

- **线性回归计算**：
  - 使用最小二乘法拟合 Bus Factor 时间序列的线性趋势：
    ```python
    slope = Σ(x_i - x̄)(y_i - ȳ) / Σ(x_i - x̄)²
    ```
  - 其中：
    - `x_i`：月份索引（0, 1, 2, ...）
    - `y_i`：该月份的 Bus Factor 值
    - `x̄`：月份索引的平均值
    - `ȳ`：Bus Factor 值的平均值

- **趋势方向判断**：
  - **上升**：`slope > 0.1`（Bus Factor 增加，风险降低，是好事）；
  - **下降**：`slope < -0.1`（Bus Factor 减少，风险增加，是坏事）；
  - **稳定**：`|slope| ≤ 0.1`（Bus Factor 基本不变）。

- **变化率计算**：
  ```python
  change_rate = ((last_value - first_value) / first_value) × 100
  ```
  - 表示 Bus Factor 从第一个月到最后一个月的变化百分比。

- **数据不足处理**：
  - 如果月份数少于 2 个月，标记为"数据不足"，不进行趋势分析。

#### 算法五：综合风险评分（0-100 分）

- **评分组成**：
  - **当前值得分（0-50 分）**：基于 `weighted_avg_bus_factor`（时间序列加权平均 Bus Factor）；
  - **趋势得分（0-50 分）**：基于 Bus Factor 的变化趋势。

- **当前值得分计算**：
  ```python
  # 归一化到 [0, 1]
  normalized_factor = (weighted_avg_bus_factor - min_bus_factor) / (max_bus_factor - min_bus_factor)
  normalized_factor = max(0.0, min(1.0, normalized_factor))  # 限制在 [0, 1]
  
  # 反转：Bus Factor 越小，风险越高，得分越高
  current_score = (1.0 - normalized_factor) × 50
  ```
  - `weighted_avg_bus_factor` 是基于整个时间序列的加权平均 Bus Factor（按总贡献量加权）；
  - `min_bus_factor` 和 `max_bus_factor` 使用**5% 和 95% 分位数**计算（而非最小/最大值），对极值更稳健；
  - 使用分位数的优势：避免单个极端项目影响所有项目的评分，更符合实际分布；
  - Bus Factor = 1 时，得分最高（50 分），表示风险最高；
  - Bus Factor 越大，得分越低，表示风险越低。

- **趋势得分计算**：
  ```python
  if trend_direction == "上升":
      # Bus Factor 上升是好事（风险降低），趋势得分降低
      trend_score = max(0.0, 25.0 - abs(change_rate) × 0.2)
  elif trend_direction == "下降":
      # Bus Factor 下降是坏事（风险增加），趋势得分增加
      trend_score = min(50.0, 25.0 + abs(change_rate) × 0.2)
  elif trend_direction == "稳定":
      trend_score = 25.0  # 基准分数
  else:  # 数据不足
      trend_score = 25.0  # 中等分数
  ```
  - **上升趋势**：Bus Factor 增加，风险降低，趋势得分降低（最低 0 分）；
  - **下降趋势**：Bus Factor 减少，风险增加，趋势得分增加（最高 50 分）；
  - **稳定趋势**：基准分数 25 分。

- **风险等级划分**：
  ```python
  total_score = current_score + trend_score
  
  if total_score >= 80:
      risk_level = "高"
  elif total_score >= 50:
      risk_level = "中"
  else:
      risk_level = "低"
  ```
  - **高风险（≥80 分）**：Bus Factor 很低或正在下降，项目高度依赖少数贡献者；
  - **中风险（50-79 分）**：Bus Factor 中等或趋势稳定，需要关注；
  - **低风险（<50 分）**：Bus Factor 较高或正在上升，项目健康。
  - **阈值调整说明**：从原来的 70/40 调整为 80/50，提高区分度，减少误报。

#### 结果文件与示例

- **full_analysis.json（按项目聚合的完整结果）**：
  - 结构（示意）：
  
```json
{
  "tensorflow/tensorflow": {
    "metrics": [
      {
        "month": "2023-01",
        "repo_name": "tensorflow/tensorflow",
        "bus_factor": 5,
        "total_contribution": 1234.5,
        "contributor_count": 50,
        "contributors": [
          {
            "contributor_id": 12345,
            "login": "contributor1",
            "total_contribution": 300.0,
            "contribution_ratio": 0.243,
            "commit_count": 100,
            "pr_merged": 10,
            "pr_opened": 5,
            "issue_opened": 3,
            "issue_closed": 2,
            "comment_count": 20
          }
        ],
        "node_count": 52,
        "edge_count": 150
      }
    ],
    "trend": {
      "repo_name": "tensorflow/tensorflow",
      "bus_factor_trend": {
        "direction": "下降",
        "slope": -0.2,
        "change_rate": -15.5,
        "values": [5, 4, 3, 2, 1]
      },
      "months": ["2023-01", "2023-02", "2023-03", "2023-04", "2023-05"],
      "bus_factor_values": [5, 4, 3, 2, 1]
    },
    "risk_score": {
      "repo_name": "tensorflow/tensorflow",
      "total_score": 91.67,
      "current_score": 50.0,
      "trend_score": 41.67,
      "risk_level": "高",
      "weighted_avg_bus_factor": 1,
      "trend_direction": "下降"
    }
  }
}
```

- **summary.json（按风险评分排序的摘要）**：

```json
{
  "generated_at": "2026-01-25T21:01:47.963313",
  "total_repos": 37,
  "repos": [
    {
      "repo_name": "tensorflow/tensorflow",
      "total_score": 91.67,
      "current_score": 50.0,
      "trend_score": 41.67,
      "risk_level": "高",
      "weighted_avg_bus_factor": 1,
      "trend_direction": "下降"
    },
    {
      "repo_name": "microsoft/vscode",
      "total_score": 56.58,
      "current_score": 31.58,
      "trend_score": 25.0,
      "risk_level": "中",
      "weighted_avg_bus_factor": 8,
      "trend_direction": "稳定"
    }
  ]
}
```

你可以通过直接查看 `output/bus-factor-analysis/full_analysis.json` 与 `summary.json`，来进一步探索各项目在不同月份的 Bus Factor 变化趋势与风险评分。

#### 生成详细报告

```bash
# 生成所有项目的详细报告
python -m src.analysis.generate_bus_factor_report \
  --input output/bus-factor-analysis/full_analysis.json \
  --summary output/bus-factor-analysis/summary.json \
  --output output/bus-factor-analysis/detailed_report.txt

# 生成指定项目的报告
python -m src.analysis.generate_bus_factor_report \
  --input output/bus-factor-analysis/full_analysis.json \
  --repo "tensorflow/tensorflow,microsoft/vscode" \
  --output output/bus-factor-analysis/specific_repos_report.txt

# 只生成高风险项目（评分 ≥ 70）的报告
python -m src.analysis.generate_bus_factor_report \
  --input output/bus-factor-analysis/full_analysis.json \
  --min-risk 70 \
  --output output/bus-factor-analysis/high_risk_report.txt

# 生成前 10 个高风险项目的报告
python -m src.analysis.generate_bus_factor_report \
  --input output/bus-factor-analysis/full_analysis.json \
  --top 10 \
  --include-summary \
  --output output/bus-factor-analysis/top10_report.txt
```

**报告内容包括**：
- 综合风险评分与风险等级
- 当前状态得分与趋势得分
- 时间序列加权平均 Bus Factor
- 趋势分析（方向、斜率、变化率）
- 月度指标详情（Bus Factor、贡献者数、总贡献量等）
- 风险建议与改进方向

### 6. 运行倦怠分析

```bash
python -m src.analysis.burnout_analyzer \
  --graphs-dir output/monthly-graphs2 \
  --output-dir output/burnout-analysis2
```

### 5. 查看详细报告

```bash
python -m src.analysis.detailed_report \
  --input output/burnout-analysis2/full_analysis.json \
  --output my_report.txt

# 查看前 10 个高风险项目
python -m src.analysis.detailed_report --top 10

# 查看指定项目
python -m src.analysis.detailed_report --repo "kubernetes/kubernetes"
```

### 6. 人员流动分析

基于倦怠分析结果，研究各 repo 人员流动情况。支持两种分析范围：

- **核心成员（默认）**：仅分析贡献约前 50% 的核心成员
- **全部贡献者**：分析所有参与过项目的贡献者（需指定月度图目录）

```bash
# 核心成员版（默认）
python -m src.analysis.personnel_flow \
  --input output/burnout-analysis2/full_analysis.json \
  --output-dir output/personnel-flow

# 全部贡献者版（--graphs-dir 需与 burnout 分析使用的图目录一致）
python -m src.analysis.personnel_flow \
  --scope all \
  --graphs-dir output/monthly-graphs2 \
  --input output/burnout-analysis2/full_analysis.json
```

`--scope all` 时输出到 `output/personnel-flow-all/`（可用 `--output-dir` 覆盖）。

输出包括：
- **personnel_flow.json**：完整流动数据（含 flowed_to 流向信息）
- **summary_report.txt**：按关键流失排序的摘要
- **leave_events_detail.txt**：全部流失明细（每条离开事件及流向）
- **flow_statistics.txt**：Repo→Repo 流向统计（从哪流向哪的人数排序）
- **flow_by_year.txt**：按年统计流向 + 流入最多的目标 Repo 排名
- **flow_timeline.txt**：人才流动时间线（按时间顺序，每月离开明细及汇总）
- **repo_trend.txt**：Repo 流行趋势（按前半段 vs 后半段活跃度判断上升/下降/平稳）
- **cross_repo_flow.txt**：跨 repo 流向专题（有流向的关键流失明细）

分析维度：核心成员时间线、流入/流出事件、任期分布、关键流失、N 个月留存率、**跨 repo 流向**（离开后 12 个月内于其他项目成为核心）。

**「离开」含义**：某月不再处于该 repo 核心成员名单（贡献跌出前约 50%），不表示完全不参与，可能是参与减少、完全退出或角色变化。

---

## 三类图构建

系统为每个项目的每个月构建三类图：

| 图类型 | 节点 | 边 | 用途 |
|-------|------|-----|------|
| **Actor-Actor** | 开发者 | 协作/评审/回复关系 | 倦怠分析（核心成员识别、协作网络） |
| **Actor-Repo** | 开发者 + 仓库 | 贡献关系 | 贡献者分析、项目热度 |
| **Actor-Discussion** | 开发者 + Issue/PR | 参与讨论关系 | 社区互动、新人融入 |

**构建流程**：
```
GitHub Archive 事件数据
    ↓
按月聚合（YYYY-MM, ...）
    ↓
按项目分组
    ↓
为每个项目的每个月构建三类图
    ↓
导出为 GraphML 格式
```

**Actor-Actor 图边的产生规则**：
- `ISSUE_INTERACTION`：Actor A 在 Actor B 创建的 Issue 中发表评论
- `PR_REVIEW`：Actor A 在 Actor B 创建的 PR 中发表代码审查评论
- `PR_MERGE`：Actor A 合并了 Actor B 创建的 PR
- `ISSUE_CO_PARTICIPANT`：两个 Actor 都参与了同一个 Issue 的讨论

**Actor-Repo 图边的产生规则**：
- 所有 GitHub 事件（Push、PR、Issue、Comment、Review、Star、Fork 等）都会在 Actor 和 Repo 之间创建边

**Actor-Discussion 图边的产生规则**：
- Issue 相关：创建、关闭、评论 Issue
- PR 相关：创建、合并、关闭、审查 PR

---

## 倦怠分析算法详解

### 四个核心指标

对每个月的 Actor-Actor 图，提取以下四个指标：

1. **事件数（total_events）**：该月的 GitHub 事件总数，反映项目活跃度
2. **贡献者（unique_actors）**：该月参与项目的不同开发者数量，反映社区规模
3. **核心成员（core_actors）**：通过算法识别的核心维护者，反映项目维护能力
4. **协作质量（clustering_coefficient）**：平均聚类系数，反映协作网络的紧密程度（值域 [0, 1]）

### 核心成员识别

核心成员通过以下方法识别：

1. **计算加权度数**：根据边类型权重（PR_MERGE=3.0, PR_REVIEW=1.5, ISSUE_INTERACTION=0.5等）计算每个节点的加权贡献
2. **计算 k-core 值**：识别节点在网络结构中的核心位置
3. **综合得分**：`得分 = 0.5 × 归一化加权度数 + 0.5 × 归一化k-core值`
4. **动态筛选**：按得分排序，累计加权贡献达到 50% 时停止，确保核心成员覆盖主要贡献

### 三层评分架构

对每个指标的时间序列，使用三层分析计算得分（每个维度 0-25 分）：

#### 1. 长期趋势（40%权重，满分 10 分）

- **计算方法**：使用线性回归拟合整个时间序列的斜率
- **公式**：`slope = Σ(xᵢ-x̄)(yᵢ-ȳ) / Σ(xᵢ-x̄)²`
- **得分**：`得分 = -slope × 100`（斜率 < 0 时），最高 10 分
- **意义**：捕捉整体下降趋势

#### 2. 近期状态（40%权重，满分 10 分）

- **计算方法**：对比最近 3 个月均值 vs 最早 3 个月均值
- **公式**：`变化率 = (最近均值 - 最早均值) / 最早均值`
- **得分**：`得分 = -变化率 × 10`（变化率 < 0 时），最高 10 分
- **意义**：关注最近状态，捕捉突发下降

#### 3. 稳定性（20%权重，满分 5 分）

- **计算方法**：计算月度变化率的标准差（波动率）
- **公式**：`波动率 = √(Σ(变化率ᵢ - 平均变化率)² / (n-1))`
- **得分**：`得分 = (波动率 - 0.3) × 25`（波动率 > 0.3 时），最高 5 分
- **意义**：惩罚高波动性，反映不稳定性

**维度总分** = 长期趋势得分 + 近期状态得分 + 稳定性得分 = 0-25 分

### 综合倦怠评分

对四个维度分别应用三层分析，得到：

- **活跃度得分**（0-25分）：事件数趋势分析
- **贡献者得分**（0-25分）：贡献者数量趋势分析
- **核心成员得分**（0-25分）：核心成员留存率趋势分析
- **协作质量得分**（0-25分）：聚类系数趋势分析

**综合倦怠评分** = 活跃度得分 + 贡献者得分 + 核心成员得分 + 协作质量得分 = **0-100 分**

**风险等级**：
- ≥60 分：🔴 高倦怠风险
- 40-59 分：🟠 中等风险
- 20-39 分：🟡 低风险
- <20 分：🟢 健康

### 预警信号检测

系统会逐月对比相邻两个月的数据，检测以下预警信号：

#### 1. ACTIVITY_DROP（活跃度下降）

**检测方法**：
1. 对比相邻两个月的事件总数
2. 计算变化率：`变化率 = (本月事件数 - 上月事件数) / 上月事件数`
3. 触发条件：变化率 < -50%（下降超过 50%）
4. 严重程度：
   - `high`：变化率 < -70%（下降超过 70%）
   - `medium`：-70% ≤ 变化率 < -50%

**示例**：
- 上月：1000 事件
- 本月：400 事件
- 变化率：`(400-1000)/1000 = -60%`
- 触发：`medium` 级别预警

---

#### 2. CORE_MEMBER_LOSS（核心成员流失）

**检测方法**：
1. 获取上月和本月的核心成员 ID 集合
2. 计算流失成员：`流失成员 = 上月核心成员 - 本月核心成员`
3. 计算流失率：`流失率 = 流失成员数 / 上月核心成员数`
4. 触发条件：
   - 流失率 ≥ 30%，或
   - 流失绝对数量 ≥ 2 人
5. 严重程度：
   - `high`：流失率 ≥ 50% 或流失 ≥ 3 人
   - `medium`：30% ≤ 流失率 < 50% 且流失 2 人

**示例**：
- 上月核心成员：10 人（ID: [1,2,3,4,5,6,7,8,9,10]）
- 本月核心成员：6 人（ID: [1,2,3,4,5,6]）
- 流失成员：4 人（ID: [7,8,9,10]）
- 流失率：`4/10 = 40%`
- 触发：`medium` 级别预警

---

#### 3. COLLABORATION_DECLINE（协作质量下降）

**检测方法**：
1. 对比相邻两个月的聚类系数
2. 计算变化率：`变化率 = (本月聚类系数 - 上月聚类系数) / 上月聚类系数`
3. 触发条件：变化率 < -30%（下降超过 30%）
4. 严重程度：固定为 `medium`

**聚类系数说明**：
- 聚类系数衡量节点的邻居之间相互连接的程度
- 值域 [0, 1]，值越高说明协作网络越紧密
- 聚类系数下降可能意味着协作质量下降、社区分裂

**示例**：
- 上月聚类系数：0.15
- 本月聚类系数：0.09
- 变化率：`(0.09-0.15)/0.15 = -40%`
- 触发：`medium` 级别预警

---

#### 4. CONTRIBUTOR_DROP（贡献者下降）

**检测方法**：
1. 对比相邻两个月的活跃贡献者数量
2. 计算变化率：`变化率 = (本月贡献者数 - 上月贡献者数) / 上月贡献者数`
3. 触发条件：变化率 < -40%（下降超过 40%）
4. 严重程度：固定为 `medium`

**示例**：
- 上月贡献者：50 人
- 本月贡献者：25 人
- 变化率：`(25-50)/50 = -50%`
- 触发：`medium` 级别预警

---

#### 5. SUSTAINED_DECLINE（持续下降）

**检测方法**：
1. 检查最近 3 个月的事件数序列
2. 判断是否连续下降：`events[0] > events[1] > events[2]`
3. 如果连续下降，计算累计下降率：
   - `累计下降率 = (最近1月 - 3个月前) / 3个月前`
4. 触发条件：累计下降率 < -30%（累计下降超过 30%）
5. 严重程度：固定为 `high`

**示例**：
- 3 个月前：1000 事件
- 2 个月前：800 事件（环比 -20%）
- 1 个月前：600 事件（环比 -25%）
- 本月：400 事件（环比 -33%）
- 累计下降率：`(400-1000)/1000 = -60%`
- 触发：`high` 级别预警

**注意**：此预警需要至少 3 个月的数据才能检测。

---

### 综合倦怠评分计算

#### 计算流程

**步骤 1：提取四个维度的时间序列**

1. **活跃度序列**：`[month1.total_events, month2.total_events, ..., monthN.total_events]`
2. **贡献者序列**：`[month1.unique_actors, month2.unique_actors, ..., monthN.unique_actors]`
3. **核心成员流失率序列**：
   - 以首月核心成员为基准
   - 每月流失率 = `1 - (该月核心成员 ∩ 首月核心成员) / 首月核心成员数`
   - 序列：`[month1流失率, month2流失率, ..., monthN流失率]`
4. **协作质量序列**：`[month1.clustering_coefficient, month2.clustering_coefficient, ..., monthN.clustering_coefficient]`

**步骤 2：对每个维度应用三层分析**

对每个时间序列分别计算：
- 长期趋势得分（0-10分）
- 近期状态得分（0-10分）
- 稳定性得分（0-5分）

得到每个维度的总分（0-25分）。

**步骤 3：综合评分**

首先计算各维度的风险得分总和（越高越差）：
```
风险得分总和 = 活跃度风险得分 + 贡献者风险得分 + 核心成员风险得分 + 协作质量风险得分
            = (0-25) + (0-25) + (0-25) + (0-25)
            = 0-100分
```

然后转换为健康度得分（越高越好）：
```
健康度得分 = 100 - 风险得分总和
          = 0-100分（得分越高表示项目越健康）
```

#### 评分示例

假设某项目经过 12 个月的分析，四个维度的风险得分如下：

| 维度 | 长期趋势 | 近期状态 | 稳定性 | 维度风险得分 |
|-----|---------|---------|--------|---------|
| **活跃度** | 8.5分 | 7.2分 | 4.3分 | **20.0分** |
| **贡献者** | 7.8分 | 6.5分 | 3.4分 | **17.7分** |
| **核心成员** | 1.2分 | 2.1分 | 1.7分 | **5.0分** |
| **协作质量** | 4.5分 | 3.8分 | 2.0分 | **10.3分** |
| **风险得分总和** | | | | **53.0分** |
| **健康度得分** | | | | **47.0分** (100 - 53.0) |

**解读**：
- **活跃度风险（20.0分）**：事件总数明显下降，长期和近期都有下降趋势
- **贡献者风险（17.7分）**：活跃人数下降，但波动相对较小
- **核心成员风险（5.0分）**：核心成员相对稳定，流失率较低
- **协作质量风险（10.3分）**：聚类系数下降，协作网络紧密程度下降
- **总体评价**：健康度得分 47.0 分，中等风险，主要问题是活跃度和贡献者下降

### 风险等级划分（基于健康度得分）

| 健康度得分 | 等级 | 含义 | 建议 |
|---------|------|------|------|
| <40 | 🔴 high | 高倦怠风险，需要关注 | 立即调查原因，考虑干预措施 |
| 40-59 | 🟠 medium | 中等风险，有下降趋势 | 持续监控，准备应对方案 |
| 60-79 | 🟡 low | 低风险，基本健康 | 正常监控即可 |
| ≥80 | 🟢 healthy | 健康，无明显问题 | 保持现状 |

**说明**：健康度得分 = 100 - 风险得分总和，得分越高表示项目越健康。

---

## 项目结构

```
oss_graph_construction/
├── src/
│   ├── analysis/                    # 分析模块
│   │   ├── monthly_graph_builder.py # 月度图构建
│   │   ├── burnout_analyzer.py      # 倦怠分析
│   │   ├── personnel_flow.py        # 人员流动分析
│   │   └── detailed_report.py       # 详细报告生成
│   ├── data_collection/             # 数据采集
│   │   ├── gharchive_collector.py   # GitHub Archive 下载器
│   │   └── representative_projects.py # 代表性项目列表
│   ├── models/                      # 数据模型
│   ├── services/                    # 核心服务
│   │   └── temporal_semantic_graph/ # 图构建服务
│   ├── cli/                         # 命令行接口
│   └── utils/                       # 工具函数
├── data/
│   └── filtered/                    # 过滤后的事件数据
├── output/
│   ├── monthly-graphs/              # 月度图文件
│   │   └── {owner}-{repo}/
│   │       ├── actor-actor/
│   │       ├── actor-repo/
│   │       └── actor-discussion/
│   ├── burnout-analysis/            # 倦怠分析结果
│   │   ├── summary.json             # 评分排名
│   │   ├── all_alerts.json          # 预警列表
│   │   ├── full_analysis.json       # 完整分析数据
│   │   └── detailed_report.txt      # 可读报告
│   └── personnel-flow/              # 人员流动分析结果
│       ├── personnel_flow.json      # 流动数据
│       └── summary_report.txt       # 摘要报告
│   └── bus-factor-analysis/         # Bus Factor 分析结果
│       ├── summary.json             # 评分排名
│       ├── all_alerts.json          # 预警列表
│       ├── full_analysis.json       # 完整分析数据
│       └── detailed_report.txt      # 可读报告
├── scripts/
│   ├── collect_data.sh              # 数据采集脚本
│   └── analyze_burnout.sh           # 分析运行脚本
└── requirements.txt
```

---

## 命令行参考

### 数据采集

```bash
python -m src.data_collection.gharchive_collector \
  --start-date YYYY-MM-DD \
  --end-date YYYY-MM-DD \
  --sample-mode fulldaily \    # fulldaily=每天24h合并; daily=每天1h; monthly=每月1h
  --output-dir data/filtered

# 从已有月度图索引指定仓库列表
# --repos-from-index output/monthly-graphs/index.json
# python -m src.data_collection.gharchive_collector --start-date 2024-01-01 --end-date 2024-12-31 --sample-mode fulldaily --workers 32 --output-dir data/filtered_union_2024_fulldaily --repos-from-index output/monthly-graphs2/index.json
```

### 月度图构建

```bash
python -m src.analysis.monthly_graph_builder \
  --data-dir data/filtered \
  --output-dir output/monthly-graphs \
  --workers 4                  # 并行进程数

# 仅构建指定月份范围（增量构建，自动合并到已有索引）
# --start-month YYYY-MM --end-month YYYY-MM
```

### Bus Factor 分析

```bash
# 完整分析（所有项目，自动多进程并行）
python -m src.analysis.bus_factor_analyzer

# 指定并行工作进程数
python -m src.analysis.bus_factor_analyzer --workers 4

# 单项目单月份测试
python -m src.analysis.bus_factor_analyzer \
  --repo angular-angular \
  --month 2023-01
```

### 倦怠分析

```bash
python -m src.analysis.burnout_analyzer \
  --graphs-dir output/monthly-graphs \
  --output-dir output/burnout-analysis
```

### 人员流动分析

```bash
# 核心成员（默认）
python -m src.analysis.personnel_flow \
  --input output/burnout-analysis/full_analysis.json \
  --output-dir output/personnel-flow

# 全部贡献者（需指定 --graphs-dir）
python -m src.analysis.personnel_flow --scope all \
  --graphs-dir output/monthly-graphs2 \
  --input output/burnout-analysis/full_analysis.json
```

### 详细报告

```bash
# 查看前 N 个高风险项目
python -m src.analysis.detailed_report --top 10

# 查看指定项目
python -m src.analysis.detailed_report --repo "kubernetes/kubernetes,facebook/react"

# 只看高风险项目（评分 ≥ 60）
python -m src.analysis.detailed_report --min-score 60

# 指定输出文件
python -m src.analysis.detailed_report --output my_report.txt
```

---

## 输出示例

### 详细报告片段

```
================================================================================
📊 项目: kubernetes/kubernetes
================================================================================

🎯 综合倦怠评分: 35.42 / 100
   风险等级: 🟡 低风险
   分析周期: 2023-01 to 2025-12 (36 个月)

--------------------------------------------------------------------------------
📈 各因子详细分析（三层架构：长期趋势40% + 近期状态40% + 稳定性20%）
--------------------------------------------------------------------------------

【1. 活跃度】(0-25分)
   📊 数据概览:
      首月: 1250.00 事件  →  末月: 890.00 事件
   📉 长期趋势 (40%权重):
      线性回归斜率: -2.15%/月
      ⚠️ 每月平均下降 2.2%
      → 趋势得分: 2.15
   📅 近期状态 (40%权重):
      早期3月均值: 1180.33  →  近期3月均值: 920.67
      变化率: -22.0%
      → 近期得分: 2.20
   📊 稳定性 (20%权重):
      月度波动率: 18.5%
      ✅ 波动可控 (≤30%)
      → 稳定性扣分: 0.00
   ➡️ 维度总分: 4.35 / 25
```

---

## 技术栈

- **Python 3.8+**
- **NetworkX**: 图构建与算法
- **tqdm**: 进度显示
- **multiprocessing**: 并行处理

## 许可证

MIT License
