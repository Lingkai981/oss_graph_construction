下面我先把公式设计出来（**全时间跨度**、不按月），尽量做到：可解释、能用你现有 actor-repo / actor-discussion 图直接算（不需要改构图），且尺度稳定（用 log / 比例归一化，避免被极端活跃 repo 压死）。

我用的记号：

* 一条边/事件：(e)
* repo：(r)
* discussion：(d)
* event 的类型（构图里映射后的 `edge_type`）：(t(e))
* comment 文本长度（字符数）：(\ell(e))（没有文本则 0）
* 数据集总事件数：(|E|)
* 某 repo 的事件集合：(E_r)，某 discussion 的事件集合：(E_d)

---

## 1) 边（事件）重要性公式：语义权重 + 信息量加分

### 1.1 语义权重 $w(t)$

> 原则：能代表“协作与决策成本”的更高；纯反馈更低；极高频噪声（Push）给中等但不太高。

| edge_type                               | 建议权重 (w(t)) |
| --------------------------------------- | ----------: |
| REVIEW（PRReview / Review）               |         5.0 |
| PR（PullRequest）                         |         4.5 |
| ISSUE（Issues / IssueEvent）              |         4.0 |
| COMMENT（IssueComment / PRReviewComment） |         3.0 |
| PUSH                                    |         2.0 |
| FORK                                    |         1.5 |
| STAR / WATCH                            |         1.0 |
| 其他/未知                                   |         1.0 |

你后面可以按实验调参，但这个初始版本一般会有比较合理的排序。

### 1.2 信息量加分 (b(e))

只对有 `comment_body` 的边（评论类事件）加分；用 log 压缩长度：

$b(e) = \alpha \cdot \log(1+\ell(e))$

* $\ell(e)$：comment_body 字符数（无文本为 0）
* $\alpha$：建议 $0.2$（让文本加分是“锦上添花”，不会压过类型）

### 1.3 边的重要性 (I_e)

$\boxed{I_e = w(t(e)) \cdot (1 + \alpha \log(1+\ell(e)))}$

建议：$\alpha=0.2$

解释性很强：事件本体的“类型价值”是底座，文本长度只是放大器。

---

## 2) repo 重要性：活跃度 + 覆盖面 + 事件结构（全时间跨度）

你要“单个 repo 的重要性指标公式”，我把三部分都放进一个综合分：

$\boxed{I_r = A_r^{\lambda_A} \cdot C_r^{\lambda_C} \cdot S_r^{\lambda_S}}$

默认：$\lambda_A=\lambda_C=\lambda_S=1$（先等权）

### 2.1 活跃度项 (A_r)

用事件重要性求和，再做 log 压缩并归一：

$A_r = \frac{\log(1 + \sum_{e\in E_r} I_e)}{\max_{r'}\log(1 + \sum_{e\in E_{r'}} I_e)}$

解释：不是简单事件数，而是“加权事件量”；log 防止大 repo 一家独大。

### 2.2 覆盖面项 (C_r)

覆盖面 = 独立参与者数（unique actors）归一：

$C_r = \frac{\log(1 + |{a: (a,r)\text{有至少一条边}}|)}{\max_{r'}\log(1 + |{a: (a,r')\text{有至少一条边}}|)}$

解释：人越多，说明 repo 的组织触达越广；同样用 log 抑制极端值。

### 2.3 事件结构项 (S_r)

你想用“事件结构”，我建议用**类型分布的熵**衡量“结构丰富度/协作形态多样性”，再做 0-1 归一：

设 repo 上按 edge_type 聚合后的重要性占比：

$p_{r,k} = \frac{\sum_{e\in E_r,\ t(e)=k} I_e}{\sum_{e\in E_r} I_e}$

熵：

$H_r = -\sum_k p_{r,k}\log p_{r,k}$

归一（最大值是 $\log K$，$K$=类型数）：

$\boxed{S_r = \frac{H_r}{\log K}}$

解释：

* 如果 repo 全是 PUSH（单一结构），熵低 → (S_r) 低
* 如果 repo 既有 PR/Review/Issue/Comment 等，结构更丰富 → (S_r) 高

### 2.4 最终 repo 重要性（推荐默认等权）

$\boxed{I_r = A_r \cdot C_r \cdot S_r}$

---

## 3) Discussion 重要性指标（类似 repo 的方法）

Discussion（我理解你指的是 discussion 节点 / issue / PR discussion thread 类节点，来源是 actor-discussion 图）可以用**同样三部分**，只是把集合从 repo 换成 discussion。

$\boxed{I_d = A_d \cdot C_d \cdot S_d}$

### 3.1 活跃度 (A_d)

$A_d = \frac{\log(1 + \sum_{e\in E_d} I_e)}{\max_{d'}\log(1 + \sum_{e\in E_{d'}} I_e)}$

### 3.2 覆盖面 (C_d)

$C_d = \frac{\log(1 + |{a: (a,d)\text{有至少一条边}}|)}{\max_{d'}\log(1 + |{a: (a,d')\text{有至少一条边}}|)}$

解释：参与者越多的讨论通常越重要（影响面更广）。

### 3.3 事件结构 (S_d)

同样用熵，但注意 discussion 的类型可能更集中（Comment/Review/IssueEvent 等）；仍然可用：

$p_{d,k} = \frac{\sum_{e\in E_d,\ t(e)=k} I_e}{\sum_{e\in E_d} I_e},\quad
S_d = \frac{-\sum_k p_{d,k}\log p_{d,k}}{\log K}$

### 3.4 最终 discussion 重要性

$\boxed{I_d = A_d \cdot C_d \cdot S_d}$

---

## 1) 先把“对象重要性”变成全局可用的三张表

你刚刚设计了：

* 事件重要性 (I_e)
* repo 重要性 (I_r)
* discussion 重要性 (I_d)

下一步你要做的是：在整个时间跨度上跑一遍，把它们固化成可复用的 mapping：

* `event_id -> I_e`
* `repo_id -> I_r`
* `discussion_id -> I_d`

输出建议用 `jsonl/csv` + summary（top/bottom 分布、分位数），这样你后面可以快速迭代权重表而不影响其余逻辑。

> 关键点：把归一化的分母（max、类型数K）固定在这一轮里，保持一致性。

---

## 2) 定义“低质参与者”的可疑行为画像（不要一上来就做单一分数）

你想抓的是一种“**通过低权重对象刷存在感→换取修改重要项目权限**”的策略，所以至少要有两个维度：
(1) 贡献是否低质/刷量；(2) 是否出现向高价值对象“跃迁”。

我建议先定义 4 个 actor 级指标（都能直接用你的三张表聚合得到）：

### 2.1 贡献价值（Quality-weighted contribution）

$Q(a)=\sum_{e\in E_a} I_e \cdot I_{obj(e)}$

其中 (I_{obj(e)}) 可以是 `repo` 或 `discussion` 的重要性（取能匹配的那个；actor-repo 用 repo，actor-discussion 用 discussion）。

直觉：不是看你做了多少事，而是看你在重要对象上做了多少“有分量的事”。

### 2.2 刷量倾向（Low-value ratio）

把对象重要性（repo/discussion）按分位数切“低价值集合”，比如 bottom 50% 或 bottom 30%：

$L(a)=\frac{\sum_{e\in E_a,\ obj(e)\in Low} I_e}{\sum_{e\in E_a} I_e}$

直觉：你大部分活动是不是集中在“低价值对象”。

### 2.3 行为多样性（Type entropy）

只在 actor 维度按 edge_type 统计，防止全是 STAR/简单 COMMENT：

$H(a)=-\sum_k p_{a,k}\log p_{a,k}$

低质刷量常见：类型单一、集中在低成本事件。

### 2.4 “跃迁/攀爬”信号（Jump signal）

你关心的是“先低后高”的路径。即便你不按月做主要指标，也建议你做一个最小的时间特征：**首次触达高重要对象的时间**相对其累计低重要贡献的关系。

一个简单可用的定义（不需要月度聚合，用事件时间戳排序即可）：

* 定义高重要 repo 集合 High（比如 top 10% 的 $I_r$）
* 找到 actor 第一次对 High 里的 repo 产生事件的时间 $t^*(a)$
* 计算在 $t^*(a)$ 之前，actor 对 Low repo 的累计贡献量 $Q_{low,pre}(a)$

如果一个人：

* $Q_{low,pre}$ 很大（长期刷低价值）
* $t^*$ 很早/突然（很快就触达高价值）
* 且在 High 上贡献很浅（例如只有少量低成本事件）

就很可疑。

---

## 3) 先做“规则型可疑分数”，再考虑模型

别急着上复杂模型。你要的是“能解释给别人听”的判定。

我建议做一个 **Suspicion Score**（可疑分）：

$S(a) = z(L(a)) + z(\text{LowTypeShare}(a)) + z(\text{Jumpiness}(a)) - z(Q(a))$

* $L(a)$：低价值占比高 → 可疑加分
* LowTypeShare：低成本事件（STAR/简单 COMMENT）占比高 → 可疑加分
* Jumpiness：突然接触高价值对象但贡献浅 → 可疑加分
* $Q(a)$：在高价值对象上的加权贡献越大 → 可疑减分

这里用 z-score 是为了让量纲稳定、不同 repo 规模差异不致压死。

---

## 4) 验证：你要证明“这个分数抓到了你想抓的事”

没有 ground truth 的情况下，你可以做三种验证：

### 4.1 人工抽样审阅（最有效）

* 取 S(a) 最高的前 50
* 取 S(a) 最低的前 50
* 随机取 50
  看他们的行为轨迹（事件类型、对象重要性分布、是否突然进入高重要 repo）。

### 4.2 反事实检查

高可疑者是否满足你假设的路径：

* 低重要对象占比极高
* 进入高重要对象的事件类型偏低成本（比如 comment/star）
  而不是正常成长型（先小贡献→逐渐 PR/review→进入核心）。

### 4.3 与“正常成长”对比

把 newcomer_analyzer 的“晋核耗时/新人到核心距离”等作为对照标签：

* 真正成长型往往在重要对象上逐渐增加、有 review/pr 等高成本事件
* 低质刷量型在重要对象上贡献稀薄但触达很快

---

## 5) 工程落地建议（你下一步直接做什么）

你现在最该做的是写一个**并列于 newcomer_analyzer 的新分析器**（比如 `quality_risk_analyzer.py`），输出以下内容：

1. `repo_importance.json`（repo_id -> I_r）
2. `discussion_importance.json`（discussion_id -> I_d）
3. `actor_quality.json`（每个 actor 的 Q(a)、L(a)、H(a)、Jump signal、S(a)）
4. `top_suspects.csv`（高可疑者前 N，附解释字段）

并且在报告里必须带“可解释字段”，比如：

* actor 的 low/high repo 贡献占比
* top contributing repos（按 I_r 加权）
* 高价值 repo 上做了哪些类型事件（PR/Review/Comment/Star）

---

## 一个重要提醒：避免“误伤”的两个边界条件

1. **新手正常路径**：很多人会从低价值 repo 开始学习，这是合理的；你要抓的是“长期刷低价值 + 高价值上贡献浅 + 行为类型低成本”的组合。
2. **大 repo 的外围贡献**：有些人只做 issues/comment 也可能很有价值（高信息量讨论）。所以你引入 comment length 加分是对的；另外可以在 high repo 上把 COMMENT 的权重稍微抬一点（或者加一个“高信息 comment”的额外特征）。

---

如果你愿意，我可以下一步直接帮你把这个 `quality_risk_analyzer.py` 的骨架写出来（读取 index.json，扫全量 graphml，聚合 I_e/I_r/I_d，再聚合 actor 指标，输出 top suspects），并把配置（权重表、high/low 分位阈值、alpha）都做成命令行参数，方便你快速试几组设定看效果。
