# Newcomer Experience 分析报告

> 本文档系统性整理本项目中 **newcomer_experience（新人体验）** 的全部设计、指标定义与评分方法说明，可作为技术文档、研究方法说明或项目分析报告的基础版本。

---

## 一、研究目标与核心问题

Newcomer Experience 模块关注的问题是：

* 新人进入项目后，**是否能够顺利接触核心贡献者**？
* 新人从外围走向核心，**路径是否清晰、成本是否过高**？
* 项目是否存在 **核心与外围成员之间的结构性断裂**？

通过对协作网络的结构与演化进行量化分析，本模块尝试刻画 OSS 项目中新人融入与成长的真实难度，衡量项目是否有吸纳新人的能力。

---

## 二、数据与建模基础

### 2.1 基础图模型

* 使用 **actor–actor 月度协作图**
* 节点：开发者（actor）
* 边：同一时间窗口内的协作关系
* 图为 **无向、简化图**（不考虑权重与方向）

### 2.2 时间粒度

* 以「月」为最小时间单位
* 所有指标均形成 **月度时间序列**

### 2.3 核心与新人定义

* **新人（Newcomer）**：某 actor 在某 repo 中首次出现的月份
* **核心成员（Core）**：在对应月份被 core-identification 模块识别为核心的 actor，相关的计算公式可以在README.md里找到。
* **外围成员（Periphery）**：当月非核心成员

---

## 三、新人体验的三大指标体系

### 3.1 指标一：新人 → 核心的人际距离（avg_shortest_path_to_core）

#### 3.1.1 指标定义

> 新人加入当月，到所有可达的核心成员的平均最短路径长度

#### 3.1.2 计算方式

* 在新人加入当月的 actor–actor 图中：

  * 计算新人到所有核心成员的最短路径
  * 仅对「可达的核心成员」取平均

```
lengths = nx.single_source_shortest_path_length(g_simple, node_id)
reachable = [lengths[t] for t in core_targets if t in lengths]
reachable_count = len(reachable)
avg_len: Optional[float] = None if reachable_count == 0 else round(sum(reachable) / reachable_count, 4)
```

#### 3.1.3 月度统计指标

* 新人人数
* 可达核心的新人数
* 平均最短路径（avg_shortest_path_to_core）

#### 3.1.4 指标含义

* 数值越大：新人距离核心越远
* 数值升高：项目核心圈层化增强，新人融入门槛变高

---

### 3.2 指标二：外围 → 核心的晋升时间（months_to_core）

#### 3.2.1 指标定义

> 核心成员从首次出现到首次成为核心所需的时间（月）
> 但额外排除数据集里**第一个月就已经出现的核心成员**，因为他们可能早就加入项目，对统计结果有一定的影响

#### 3.2.2 计算方式

* 对所有「曾成为核心」的 actor：

  * 首次在该项目中出现的月份 first_seen_month
  * 首次成为核心的月份 first_core_month
  * 核心成员从首次出现到首次成为核心所需的时间 months_to_core = first_core_month − first_seen_month

```
for node_id, core_month in first_core.items():
    seen_month = first_seen.get(node_id)
    if not seen_month:
        continue
    actor_id, login = actor_info.get(node_id, (0, node_id))
    months_to_core = _months_diff(seen_month, core_month)
```

#### 3.2.3 月度统计方式

* 以「首次成为核心的月份」为归属月
* 统计当月新晋核心人数
* 计算其平均 / 中位晋升耗时

#### 3.2.4 指标含义

* 数值越大：晋升路径越漫长，表明核心门槛高、成长路径不清晰

---

### 3.3 指标三：外围 / 新人 → 核心的可达性断裂

#### 3.3.1 指标定义

衡量非核心成员与核心成员在协作网络中的连通性，区分两种情况：

1. **ALL Core 不可达（unreachable_to_all_core_count）**
   非核心成员到所有核心成员均不可达

2. **ANY Core 不可达（unreachable_to_any_core_count）**
   非核心成员至少对一个核心成员不可达

#### 3.3.2 统计口径

* 分子：非核心成员中满足条件的人数
* 分母：当月项目中 **全部 actor 数量**
> 注：分母选择全部actor数量是因为可能存在该项目大部分参与者成为核心贡献者，少部分边缘贡献者全部游离在外，可能导致比例**反常升高**

```
unreach_all = 0
unreach_any = 0

for node_id in non_core_nodes:
    lengths = nx.single_source_shortest_path_length(g_simple, node_id)
    reachable_core = sum(1 for c in core_targets if c in lengths)

    if reachable_core == 0:
        unreach_all += 1
        unreach_any += 1
    elif reachable_core < total_core:
        unreach_any += 1
```

#### 3.3.3 指标含义

* ALL 不可达：核心与外围存在结构性割裂
* ANY 不可达：核心群体内部本身存在分裂

---

## 四、三层分析评分机制（Three-layer Analysis）

为避免仅凭单点或短期现象判断，每一项指标的月度时间序列都会经过 **三层分析**。

所有指标均遵循：**数值越大，问题越严重**（increase_is_bad = True）

---

### 4.1 第一层：长期趋势（Trend Analysis）

**4.1.1 问题关注点**：

> 该指标是否在长期持续恶化？

**4.1.2 方法**：

* 对月度序列进行线性回归
* 提取斜率 slope

**4.1.3 评分逻辑**：

* slope > 0（长期变差） → 产生惩罚得分
* slope ≤ 0 → 不加分
```
def _linear_regression_slope(values: List[float]) -> float:
    """简单线性回归斜率（x=0..n-1）。"""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = 0.0
    den = 0.0
    for i, y in enumerate(values):
        dx = i - x_mean
        dy = y - y_mean
        num += dx * dy
        den += dx * dx
    return num / den if den != 0 else 0.0

slope = _linear_regression_slope(normalized)
trend_score = max(0.0, min(max_score * 0.4, slope * max_score * 4))
```
---

### 4.2 第二层：近期状态（Recent Change Analysis）

**4.2.1 问题关注点**：

> 最近一段时间是否出现明显恶化？

**4.2.2 方法**：

* 将序列划分为 early window 与 recent window
* 分别计算平均值
* 计算变化率：

```
change_rate = (recent_avg - early_avg) / |early_avg|
```

**4.2.3 评分逻辑**：

* change_rate > 0 → 近期变差 → 加分
* change_rate ≤ 0 → 不加分
```
early_avg = sum(clean[:w]) / w
recent_avg = sum(clean[-w:]) / w
change = (recent_avg - early_avg) / early_avg if early_avg != 0 else 0.0

recent_score = max(0.0, min(max_score * 0.4, change * max_score * 0.4))
```
---

### 4.3 第三层：稳定性（Volatility Analysis）

**4.3.1 问题关注点**：

> 指标是否存在剧烈波动、不稳定现象？

**4.3.2 方法**：

* 计算月度环比变化率
* 计算其标准差（volatility）
* 与预设阈值比较

**4.3.3 评分逻辑**：

* volatility > threshold → 加分
* volatility ≤ threshold → 不加分
```
def _compute_volatility(values: List[float]) -> float:
    """环比变化率标准差；跳过 prev<=0。"""
    if len(values) < 3:
        return 0.0
    changes: List[float] = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        cur = values[i]
        if prev is None or cur is None:
            continue
        if prev <= 0:
            continue
        changes.append((cur - prev) / prev)
    if len(changes) < 2:
        return 0.0
    mean = sum(changes) / len(changes)
    var = sum((c - mean) ** 2 for c in changes) / len(changes)
    return math.sqrt(var)
stability_score = max(0.0, min(max_score * 0.2, (volatility - volatility_threshold) * max_score))

volatility = _compute_volatility(clean)
```
---

### 4.4 单项指标总得分

```
single_metric_score = trend_score + recent_score + volatility_score
```

---

## 五、项目总得分与预警等级

### 5.1 项目总得分

> **项目总得分 = 4 个单项指标的得分之和**

对应指标：

1. 新人 → 核心平均最短路径
2. 外围 → 核心晋升时间
3. ALL Core 不可达比例
4. ANY Core 不可达比例

---

### 5.2 预警等级划分

| 总得分区间 | 预警等级        |
| ----- | ----------- |
| ≥ 60  | High（高风险）   |
| 40–59 | Medium（中风险） |
| 20–39 | Low（低风险）    |
| < 20  | Healthy（健康） |

> 得分越高，表示新人体验结构性问题越严重。

---

## 六、问题来源解释（用于报告解读）

当某一单项指标得分 **严格大于 15** 时，会在报告中进行单独说明：

* **新人 → 核心距离高**
  → 新人和核心贡献者联系不够紧密，缺少直接沟通

* **晋升时间得分高**
  → 新人需要较长时间或其他成本才能成为核心

* **ALL Core 不可达得分高**
  → 新人和核心贡献者之间可达性断裂（完全不可达）

* **ANY Core 不可达得分高**
  → 新人和核心贡献者之间可达性断裂（部分不可达）

---

## 七、总结

Newcomer Experience 模块通过 **结构距离、时间成本与可达性断裂** 三个维度，结合 **趋势 / 近期 / 稳定性** 的三层分析机制，对 OSS 项目中新人融入与成长的难度进行了系统量化。

该方法不仅能够刻画静态差异，还能够识别 **逐步恶化、短期异常与系统性不稳定** 等多种风险模式，为项目治理和社区健康评估提供量化依据。
