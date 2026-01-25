# OSS 社区健康度分析工具

基于 GitHub Archive 事件数据，构建多类型时序图并进行维护者倦怠（Burnout）分析的工具集。

## 功能概览

```
┌─────────────────────────────────────────────────────────────────┐
│                      OSS 社区健康度分析                          │
├─────────────────────────────────────────────────────────────────┤
│  1. 数据采集        从 GitHub Archive 下载并过滤代表性项目数据    │
│  2. 三类图构建      Actor-Actor / Actor-Repo / Actor-Discussion  │
│  3. 新人体验分析    新人融入路径 + 核心距离 + 晋升成本            │
│  4. 安全风险分析    低质参与 / 权限投机 / 可疑行为识别            │
│  5. 详细报告        面向项目 & 个体的可解释分析报告               │
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

### 4. 运行分析

```bash
# 新人体验分析
python -m src.analysis.newcomer_analyzer \
  --graphs-dir output/monthly-graphs \
  --output-dir output/newcomer-analysis
# 安全问题分析
python -m src.analysis.quality_risk_analyzer \
  --graphs-dir output/monthly-graphs \
  --output-dir output/quality-risk
```

### 5. 查看详细报告

```bash
# 查看前 10 个高风险项目
python -m src.analysis.newcomer_detailed_report --top 10
python -m src.analysis.quality_risk_detailed_report --top 10

# 查看指定项目
python -m src.analysis.newcomer_detailed_report --repo "kubernetes/kubernetes"
python -m src.analysis.quality_risk_detailed_report --repo "kubernetes/kubernetes"
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

## 新人体验分析算法

### 三层评分架构

每个维度（人际距离，时间距离，单不可达比例, 全不可达比例）都使用三层分析：

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
| **人际距离** | 0-25分 | `NewcomerDistanceRecord` | 新人加入时到核心成员的平均最短路径长度 |
| **时间距离** | 0-25分 | `PeripheryToCoreRecord` | 核心成员从首次出现到首次成为 core 的耗时（月） |
| **单不可达比例** | 0-25分 | `unreachable_to_any_core_count` | 非核心成员和任意核心成员之间不可达的数量统计 |
| **全不可达比例** | 0-25分 | `unreachable_to_all_core_count` | 非核心成员和所有核心成员之间不可达的数量统计 |

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
