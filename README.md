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
│  5. 详细报告        按项目输出完整分析过程                        │
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
# 下载 2023-2025 年数据（月采样模式，约 36GB）
python -m src.data_collection.gharchive_collector \
  --start-date 2023-01-01 \
  --end-date 2025-12-31 \
  --sample-mode monthly \
  --output-dir data/filtered
```

### 3. 构建月度图

```bash
python -m src.analysis.monthly_graph_builder \
  --data-dir data/filtered \
  --output-dir output/monthly-graphs \
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

- **三大因子与权重**：
  - **情绪因子（Emotion，40 分）**：
    - 把 [-1, 1] 的 `avg_emotion` 线性映射到 [0, 1] 再乘以 40：
      - `emotion_norm = (avg_emotion + 1) / 2`（截断到 [0,1]）；
      - `emotion_score = emotion_norm * 40`；
    - 情绪越正向、越稳定，得分越高。
  - **社区紧密度因子（Clustering，30 分）**：
    - 将 `avg_clustering` 以 0.6 作为“非常紧密”的上限做归一化：
      - `clustering_norm = min(1, avg_clustering / 0.6)`；
      - `clustering_score = clustering_norm * 30`；
    - 当社区局部聚类系数长期处于 0.6 以上时，视为满分。
  - **网络效率因子（Network Efficiency，30 分）**：
    - 预设“合理范围”：
      - 直径 `avg_diameter` 约落在 [1, 6]；
      - 平均路径 `avg_path_length` 约落在 [1, 3.5]；
    - 在各自区间内将“越小越好”映射到 [0,1]：
      - 直径分量：`diameter_component`，从 1（非常紧凑）到 0（非常松散）；
      - 路径分量：`path_component`，从 1（平均路径最短）到 0（平均路径很长）；
    - 再取两者平均得到 `network_norm`，乘以 30 得到 `network_score`。

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
          "score": 21.1,
          "weight": 40
        },
        "clustering": {
          "value": 0.047,
          "score": 1.42,
          "weight": 30
        },
        "diameter": {
          "value": 1.36,
          "score": 18.64,
          "weight": 20
        },
        "path_length": {
          "value": 1.136,
          "score": 8.86,
          "weight": 10
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

### 5. 运行倦怠分析

```bash
python -m src.analysis.burnout_analyzer \
  --graphs-dir output/monthly-graphs \
  --output-dir output/burnout-analysis
```

### 5. 查看详细报告

```bash
# 查看前 10 个高风险项目
python -m src.analysis.detailed_report --top 10

# 查看指定项目
python -m src.analysis.detailed_report --repo "kubernetes/kubernetes"
```

---

## 三类图构建

### 图类型说明

| 图类型 | 节点 | 边 | 适用分析 |
|-------|------|-----|---------|
| **Actor-Actor** | 开发者 | 协作/评审/回复关系 | 核心成员识别、协作网络 |
| **Actor-Repo** | 开发者 + 仓库 | 贡献关系 | 贡献者分析、项目热度 |
| **Actor-Discussion** | 开发者 + Issue/PR | 参与讨论关系 | 社区互动、新人融入 |

### Actor-Actor 图

捕捉开发者之间的直接协作关系：

```
Developer A ──PR_REVIEW──> Developer B
Developer A ──ISSUE_REPLY──> Developer C
Developer A ──SHARED_REPO──> Developer D
```

**边类型**：
- `ISSUE_REPLY`: 在同一 Issue 中回复
- `PR_REVIEW_COMMENT`: PR 代码审查评论
- `PR_MERGE`: 合并他人的 PR

**用途**：
- k-core 分解识别核心成员
- 度中心性分析协作活跃度
- 社区结构分析

### Actor-Repo 图

二部图，连接开发者与仓库。**每个事件对应一条独立边**：

```
Developer A ──PUSH (event_1)──> Repository X
Developer A ──PR (event_2)──> Repository X
Developer B ──ISSUE (event_3)──> Repository X
```

**边类型**：
- `PUSH`: 代码推送
- `PR`: Pull Request 操作
- `ISSUE`: Issue 操作
- `COMMENT`: Issue/PR 评论
- `REVIEW`: PR 代码审查
- `STAR` / `FORK` / `CREATE` / `DELETE` / `RELEASE`

**边属性**：
- `edge_type`: 边类型
- `created_at`: 事件发生时间
- `key`: 唯一标识（`{type}_{event_id}`）

**用途**：
- 贡献者活跃度分析
- 事件时序分析

### Actor-Discussion 图

二部图，连接开发者与 Issue/PR：

```
Developer A ──AUTHOR──> Issue #123
Developer B ──PARTICIPANT──> Issue #123
Developer C ──PARTICIPANT──> Issue #123
```

**边类型**：
- `AUTHOR`: 创建者
- `PARTICIPANT`: 参与讨论者

**用途**：
- 讨论参与度分析
- 新人融入轨迹

---

## 倦怠分析算法

### 三层评分架构

每个维度（活跃度、贡献者、核心成员、协作密度）都使用三层分析：

```
┌─────────────────────────────────────────────────────┐
│                   单个维度 (25分)                    │
├─────────────────────────────────────────────────────┤
│  📉 长期趋势 (40%)                                  │
│     线性回归拟合整个时间序列的斜率                    │
│     公式: slope = Σ(xᵢ-x̄)(yᵢ-ȳ) / Σ(xᵢ-x̄)²         │
│     得分: max(0, min(10, -slope × 100))             │
├─────────────────────────────────────────────────────┤
│  📅 近期状态 (40%)                                  │
│     最近3个月均值 vs 最早3个月均值                   │
│     change = (recent_avg - early_avg) / early_avg   │
│     得分: max(0, min(10, -change × 10))             │
├─────────────────────────────────────────────────────┤
│  📊 稳定性 (20%)                                    │
│     月度变化率的标准差                               │
│     volatility = std(monthly_changes)               │
│     得分: max(0, min(5, (volatility - 0.3) × 25))   │
└─────────────────────────────────────────────────────┘
```

### 四个评估维度

| 维度 | 权重 | 数据来源 | 说明 |
|-----|------|---------|------|
| **活跃度** | 0-25分 | `total_events` | 月度事件总数变化 |
| **贡献者** | 0-25分 | `unique_actors` | 月度活跃人数变化 |
| **核心成员** | 0-25分 | `core_actors` 留存率 | 核心成员流失情况 |
| **协作密度** | 0-25分 | `density` | 网络密度变化 |

### 核心成员识别算法

使用 **k-core + 贡献量** 双信号融合：

```python
# 1. 计算 k-core 分解
core_numbers = nx.core_number(graph.to_undirected())

# 2. 计算综合得分
score = 0.6 × (degree / degree_max) + 0.4 × (kcore / max_k)

# 3. 三重约束筛选
停止条件：
  - 累计贡献 ≥ 70% 总交互量
  - 核心成员 ≥ 30% 总人数
  - 得分 < 平均得分（且已有 ≥3 人）
```

### 预警信号类型

| 预警类型 | 触发条件 | 严重程度 |
|---------|---------|---------|
| `ACTIVITY_DROP` | 事件数环比下降 >50% | medium/high |
| `CORE_MEMBER_LOSS` | 核心成员流失 ≥30% 或 ≥2人 | medium/high |
| `COLLABORATION_DECLINE` | 网络密度环比下降 >30% | medium |
| `CONTRIBUTOR_DROP` | 活跃贡献者环比下降 >40% | medium |
| `SUSTAINED_DECLINE` | 连续3个月活跃度下降，累计 >30% | high |

### 风险等级划分

| 分数区间 | 等级 | 含义 |
|---------|------|------|
| ≥60 | 🔴 high | 高倦怠风险，需要关注 |
| 40-59 | 🟠 medium | 中等风险，有下降趋势 |
| 20-39 | 🟡 low | 低风险，基本健康 |
| <20 | 🟢 healthy | 健康，无明显问题 |

---

## 指标计算详解

### 基础网络指标

```python
# 节点数和边数
node_count = graph.number_of_nodes()
edge_count = graph.number_of_edges()

# 有向图密度
density = edge_count / (node_count × (node_count - 1))
```

### 度中心性统计

```python
degrees = dict(graph.degree())  # 每个节点的度数

degree_mean = Σdᵢ / n           # 平均度数
degree_max = max(dᵢ)            # 最大度数
degree_std = √(Σ(dᵢ-μ)² / n)    # 标准差
```

### 线性回归斜率

```python
def linear_regression_slope(values):
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    
    numerator = Σ(i - x_mean)(values[i] - y_mean)
    denominator = Σ(i - x_mean)²
    
    return numerator / denominator
```

### 波动率计算

```python
def compute_volatility(values):
    # 计算月度环比变化率
    changes = [(v[i] - v[i-1]) / v[i-1] for i in range(1, n)]
    
    # 返回标准差
    return std(changes)
```

---

## 项目结构

```
oss_graph_construction/
├── src/
│   ├── analysis/                    # 分析模块
│   │   ├── monthly_graph_builder.py # 月度图构建
│   │   ├── burnout_analyzer.py      # 倦怠分析
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
│   └── burnout-analysis/            # 分析结果
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
  --start-date 2023-01-01 \
  --end-date 2025-12-31 \
  --sample-mode monthly \      # daily/weekly/monthly
  --output-dir data/filtered \
  --resume                     # 断点续传
```

### 月度图构建

```bash
python -m src.analysis.monthly_graph_builder \
  --data-dir data/filtered \
  --output-dir output/monthly-graphs \
  --workers 4                  # 并行进程数
```

### 倦怠分析

```bash
python -m src.analysis.burnout_analyzer \
  --graphs-dir output/monthly-graphs \
  --output-dir output/burnout-analysis
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
