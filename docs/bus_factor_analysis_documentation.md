# Bus Factor 分析详细文档

## 1. 概述

Bus Factor（公交因子）是衡量开源项目风险的关键指标，表示达到总贡献量50%所需的最少贡献者数量。Bus Factor 越低，说明项目越依赖少数核心贡献者，风险越高。

本分析器基于月度时间序列数据，计算每个项目的 Bus Factor 指标，并进行趋势分析和综合风险评分。

## 2. 算法流程

### 2.1 整体流程

```
输入：月度 actor-repo 图（GraphML格式）
  ↓
1. 加载图文件
  ↓
2. 聚合贡献量（按贡献者）
  ↓
3. 计算 Bus Factor
  ↓
4. 生成月度指标
  ↓
5. 时间序列分析（趋势计算）
  ↓
6. 综合风险评分
  ↓
输出：月度指标时间序列 + 趋势分析 + 风险评分
```

### 2.2 关键步骤详解

#### 步骤1：加载图文件

- **输入**：GraphML 格式的 actor-repo 图文件
- **处理**：使用 NetworkX 的 `read_graphml()` 函数加载
- **支持类型**：DiGraph 或 MultiDiGraph
- **节点类型**：
  - `actor:ID`：贡献者节点
  - `repo:NAME`：仓库节点
- **边属性**：包含贡献统计信息（见下文）

#### 步骤2：聚合贡献量

**2.2.1 Bot 账号过滤**

在聚合贡献量之前，系统会过滤掉 Bot 账号，避免将自动化操作计入贡献量。

**判断规则**：
- 登录名包含 `[bot]`
- 登录名以 `-bot`、`_bot` 结尾
- 登录名以 `bot-`、`bot_` 开头

**2.2.2 贡献量计算**

对于每条从 `actor` 到 `repo` 的边，计算其贡献量：

```python
contribution = sum(统计值 × 权重)
```

**默认权重配置**：
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

**权重说明**：
- `pr_merged` 权重最高（3.0）：合并的 PR 代表实际代码贡献
- `issue_closed` 权重较高（2.0）：关闭 Issue 代表问题解决
- `pr_opened` 权重中等（2.0）：打开的 PR 代表代码贡献意图
- `commit_count` 基础权重（1.0）：提交是基础贡献
- `is_comment` 权重最低（0.5）：评论代表参与度，但贡献价值较低

**2.2.3 贡献者聚合**

对于每个贡献者，累加其所有边的贡献量：

```python
for each edge (actor → repo):
    edge_contribution = calculate_contribution(edge_data, weights)
    contributor_total[actor_id] += edge_contribution
```

同时记录详细统计：
- `commit_count`：提交次数
- `pr_merged`：合并的 PR 数
- `pr_opened`：打开的 PR 数
- `pr_closed`：关闭的 PR 数
- `issue_opened`：打开的 Issue 数
- `issue_closed`：关闭的 Issue 数
- `comment_count`：评论数

**2.2.4 贡献占比计算**

对于每个贡献者，计算其贡献占比：

```python
contribution_ratio = contributor_total / total_contribution_all
```

#### 步骤3：计算 Bus Factor

**算法**：

1. 计算总贡献量：
   ```python
   total_contribution = sum(所有贡献者的贡献量)
   ```

2. 计算目标贡献量（阈值，默认50%）：
   ```python
   target = total_contribution × threshold  # threshold = 0.5
   ```

3. 按贡献量降序排序贡献者：
   ```python
   sorted_contributors = sorted(contributions.items(), 
                                key=lambda x: x[1], 
                                reverse=True)
   ```

4. 累加贡献量，直到达到阈值：
   ```python
   cumulative = 0.0
   count = 0
   for contributor_id, contribution in sorted_contributors:
       cumulative += contribution
       count += 1
       if cumulative >= target:
           return count  # Bus Factor
   ```

**示例**：

假设有5个贡献者，贡献量分别为：[100, 50, 30, 15, 5]

- 总贡献量 = 200
- 目标贡献量 = 200 × 0.5 = 100
- 累加过程：
  - 第1个：100 ≥ 100 ✓ → Bus Factor = 1

假设贡献量为：[40, 30, 20, 10, 10]

- 总贡献量 = 110
- 目标贡献量 = 110 × 0.5 = 55
- 累加过程：
  - 第1个：40 < 55
  - 第2个：40 + 30 = 70 ≥ 55 ✓ → Bus Factor = 2

#### 步骤4：生成月度指标

对于每个月份，生成 `MonthlyRiskMetrics` 对象，包含：

- `month`：月份（格式：YYYY-MM）
- `repo_name`：项目名称
- `bus_factor`：Bus Factor 值
- `total_contribution`：总贡献量
- `contributor_count`：贡献者总数
- `contributors`：贡献者列表（按贡献量降序排序）
- `node_count`：图节点数
- `edge_count`：图边数

#### 步骤5：时间序列趋势分析

**5.1 趋势计算算法**

使用线性回归和变化率计算趋势：

```python
# 1. 线性回归计算斜率
n = len(bus_factor_values)
x = np.arange(n)  # [0, 1, 2, ..., n-1]
slope = np.polyfit(x, bus_factor_values, 1)[0]

# 2. 计算变化率（首尾值的相对变化百分比）
first_value = bus_factor_values[0]
last_value = bus_factor_values[-1]
if first_value == 0:
    change_rate = inf if last_value > 0 else 0.0
else:
    change_rate = ((last_value - first_value) / first_value) * 100

# 3. 判断趋势方向（基于变化率，阈值=5%）
if abs(change_rate) < 5.0:
    direction = "稳定"
elif change_rate > 0:
    direction = "上升"
else:
    direction = "下降"
```

**趋势方向含义**：
- **上升**：Bus Factor 增加，风险降低（好事）
- **下降**：Bus Factor 减少，风险增加（坏事）
- **稳定**：Bus Factor 变化小于5%，风险稳定

**5.2 趋势分析结果**

`TrendAnalysis` 对象包含：
- `repo_name`：项目名称
- `bus_factor_trend`：趋势字典
  - `direction`：趋势方向
  - `slope`：线性回归斜率
  - `change_rate`：变化率（百分比）
  - `values`：时间序列值
- `months`：月份列表
- `bus_factor_values`：Bus Factor 值列表

#### 步骤6：综合风险评分

**6.1 加权平均 Bus Factor**

使用整个时间序列的加权平均 Bus Factor（按总贡献量加权）：

```python
# 过滤掉 bus_factor 为 None 的指标
valid_metrics = [m for m in metrics_series if m.bus_factor is not None]

# 计算加权平均
total_weights = sum(m.total_contribution for m in valid_metrics)
if total_weights > 0:
    avg_bus_factor = sum(
        m.bus_factor * m.total_contribution 
        for m in valid_metrics
    ) / total_weights
else:
    # 如果总贡献量都是0，使用简单平均
    avg_bus_factor = sum(m.bus_factor for m in valid_metrics) / len(valid_metrics)

weighted_avg_bus_factor = int(round(avg_bus_factor))
```

**6.2 风险评分计算**

综合风险评分 = 当前值得分（0-50）+ 趋势得分（0-50）

**当前值得分（0-50分）**：

基于加权平均 Bus Factor，使用归一化公式：

```python
# 归一化范围：使用所有项目的 5% 和 95% 分位数
min_bus_factor = np.percentile(all_bus_factors, 5)
max_bus_factor = np.percentile(all_bus_factors, 95)

# 归一化到 [0, 1]
normalized_factor = (weighted_avg_bus_factor - min_bus_factor) / (max_bus_factor - min_bus_factor)
normalized_factor = max(0.0, min(1.0, normalized_factor))

# 反转：Bus Factor 越小，风险越高，得分越高
current_score = (1.0 - normalized_factor) * 50
```

**趋势得分（0-50分）**：

基于 Bus Factor 的变化趋势：

```python
if trend_direction == "数据不足":
    trend_score = 25.0  # 中等分数
elif trend_direction == "上升":
    # Bus Factor 上升是好事（风险降低），趋势得分应该降低
    trend_score = max(0.0, 25.0 - trend_change_rate * 0.2)
elif trend_direction == "下降":
    # Bus Factor 下降是坏事（风险增加），趋势得分应该增加
    trend_score = min(50.0, 25.0 + abs(trend_change_rate) * 0.2)
else:  # 稳定
    trend_score = 25.0  # 基准分数
```

**总分计算**：

```python
total_score = current_score + trend_score
```

**风险等级划分**：

```python
if total_score >= 80:
    risk_level = "高"
elif total_score >= 50:
    risk_level = "中"
else:
    risk_level = "低"
```

## 3. 指标说明

### 3.1 核心指标

#### Bus Factor

- **定义**：达到总贡献量50%所需的最少贡献者数量
- **取值范围**：正整数（≥1）
- **含义**：
  - **Bus Factor = 1**：单个贡献者贡献了50%以上，风险极高
  - **Bus Factor = 2-3**：少数核心贡献者，风险较高
  - **Bus Factor = 4-10**：中等风险
  - **Bus Factor > 10**：贡献分布较均匀，风险较低
- **计算方式**：见步骤3

#### 总贡献量（Total Contribution）

- **定义**：所有贡献者的加权贡献量总和
- **取值范围**：非负浮点数
- **含义**：反映项目的活跃度
- **计算方式**：所有贡献者贡献量的总和

#### 贡献者数量（Contributor Count）

- **定义**：参与项目的贡献者总数（不包括 Bot）
- **取值范围**：非负整数
- **含义**：反映项目的参与度

### 3.2 贡献者详细指标

对于每个贡献者，记录：

- `contributor_id`：贡献者 ID
- `login`：登录名
- `total_contribution`：总贡献量（加权后）
- `contribution_ratio`：贡献占比（0.0-1.0）
- `commit_count`：提交次数
- `pr_merged`：合并的 PR 数
- `pr_opened`：打开的 PR 数
- `pr_closed`：关闭的 PR 数
- `issue_opened`：打开的 Issue 数
- `issue_closed`：关闭的 Issue 数
- `comment_count`：评论数

### 3.3 趋势指标

#### 趋势方向（Trend Direction）

- **上升**：Bus Factor 增加，风险降低
- **下降**：Bus Factor 减少，风险增加
- **稳定**：Bus Factor 变化小于5%
- **数据不足**：少于2个月的数据

#### 变化率（Change Rate）

- **定义**：首尾值的相对变化百分比
- **计算公式**：`((last_value - first_value) / first_value) * 100`
- **含义**：反映 Bus Factor 的变化幅度

#### 斜率（Slope）

- **定义**：线性回归的斜率
- **含义**：反映 Bus Factor 的平均变化速度

### 3.4 风险评分指标

#### 总分（Total Score）

- **定义**：综合风险评分（0-100）
- **计算公式**：`current_score + trend_score`
- **含义**：分数越高，风险越高

#### 当前值得分（Current Score）

- **定义**：基于加权平均 Bus Factor 的得分（0-50）
- **计算公式**：见6.2节
- **含义**：反映当前风险水平

#### 趋势得分（Trend Score）

- **定义**：基于趋势方向的得分（0-50）
- **计算公式**：见6.2节
- **含义**：反映风险变化趋势

#### 风险等级（Risk Level）

- **高**：总分 ≥ 80
- **中**：50 ≤ 总分 < 80
- **低**：总分 < 50

## 4. 输出格式

### 4.1 月度指标（MonthlyRiskMetrics）

```json
{
  "month": "2023-01",
  "repo_name": "angular/angular",
  "bus_factor": 5,
  "total_contribution": 1234.5,
  "contributor_count": 150,
  "contributors": [
    {
      "contributor_id": 12345,
      "login": "contributor1",
      "total_contribution": 200.5,
      "contribution_ratio": 0.1624,
      "commit_count": 50,
      "pr_merged": 10,
      "pr_opened": 15,
      "pr_closed": 5,
      "issue_opened": 20,
      "issue_closed": 15,
      "comment_count": 100
    },
    ...
  ],
  "node_count": 200,
  "edge_count": 500
}
```

### 4.2 趋势分析（TrendAnalysis）

```json
{
  "repo_name": "angular/angular",
  "bus_factor_trend": {
    "direction": "上升",
    "slope": 0.15,
    "change_rate": 12.5,
    "values": [4, 4, 5, 5, 5, 6]
  },
  "months": ["2023-01", "2023-02", "2023-03", "2023-04", "2023-05", "2023-06"],
  "bus_factor_values": [4, 4, 5, 5, 5, 6]
}
```

### 4.3 风险评分（RiskScore）

```json
{
  "repo_name": "angular/angular",
  "total_score": 45.2,
  "current_score": 20.5,
  "trend_score": 24.7,
  "risk_level": "低",
  "weighted_avg_bus_factor": 5,
  "trend_direction": "上升"
}
```

### 4.4 完整分析结果（full_analysis.json）

```json
{
  "angular/angular": {
    "metrics": [
      { /* MonthlyRiskMetrics */ },
      ...
    ],
    "trend": { /* TrendAnalysis */ },
    "risk_score": { /* RiskScore */ }
  },
  ...
}
```

### 4.5 摘要（summary.json）

```json
{
  "generated_at": "2024-01-01T00:00:00",
  "total_repos": 100,
  "repos": [
    {
      "repo_name": "project1",
      "total_score": 85.5,
      "current_score": 45.0,
      "trend_score": 40.5,
      "risk_level": "高",
      "weighted_avg_bus_factor": 2,
      "trend_direction": "下降"
    },
    ...
  ]
}
```

## 5. 使用说明

### 5.1 命令行参数

```bash
python -m src.analysis.bus_factor_analyzer \
  --graphs-dir output/monthly-graphs/ \
  --output-dir output/bus-factor-analysis/ \
  --threshold 0.5 \
  --weights-file weights.json \
  --workers 4 \
  --no-resume
```

**参数说明**：
- `--graphs-dir`：图文件目录（默认：`output/monthly-graphs/`）
- `--output-dir`：输出目录（默认：`output/bus-factor-analysis/`）
- `--threshold`：Bus Factor 计算阈值（默认：0.5，即50%）
- `--weights-file`：权重配置文件路径（JSON格式，可选）
- `--workers`：并行工作进程数（默认：CPU核心数，设置为1使用单进程）
- `--no-resume`：禁用断点续传

### 5.2 权重配置文件格式

```json
{
  "commit_count": 1.0,
  "pr_merged": 3.0,
  "pr_opened": 2.0,
  "pr_closed": 1.0,
  "issue_opened": 1.5,
  "issue_closed": 2.0,
  "is_comment": 0.5
}
```

### 5.3 断点续传

默认启用断点续传功能：
- 自动检测已处理的月份，跳过已分析的数据
- 支持增量保存，每完成一个项目就保存结果
- 使用原子写入（临时文件+重命名）防止文件损坏

## 6. 算法复杂度

### 6.1 时间复杂度

- **贡献量聚合**：O(E)，E 为边数
- **Bus Factor 计算**：O(V log V)，V 为贡献者数（排序）
- **趋势分析**：O(M)，M 为月份数
- **风险评分**：O(M)
- **总体**：O(E + V log V + M)

### 6.2 空间复杂度

- **贡献量字典**：O(V)
- **月度指标列表**：O(M)
- **总体**：O(V + M)

## 7. 注意事项

1. **Bot 账号过滤**：默认过滤 Bot 账号，确保只计算真实贡献者的贡献量
2. **权重配置**：可以根据项目特点自定义权重配置
3. **阈值调整**：默认阈值为0.5（50%），可以根据需要调整
4. **数据质量**：确保图文件包含完整的贡献统计信息
5. **多进程模式**：对于大型项目，建议使用多进程模式加速分析

## 8. 参考文献

- Bus Factor 概念：衡量项目对关键人员的依赖程度
- 贡献量加权：基于不同类型贡献的价值差异
- 时间序列分析：使用线性回归和变化率分析趋势

