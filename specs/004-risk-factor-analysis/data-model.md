# Data Model: Bus Factor 分析

**Feature**: 组织参与与控制风险分析（Bus Factor）  
**Date**: 2024-12-19  
**Phase**: Phase 1 - Design

## 数据模型概览

Bus Factor 分析功能涉及以下核心数据模型：

1. **ContributorContribution**: 单个贡献者的贡献量信息
2. **MonthlyRiskMetrics**: 单个月份的风险指标
3. **TrendAnalysis**: 时间序列趋势分析结果
4. **RiskScore**: 综合风险评分

## 实体定义

### 1. ContributorContribution（贡献者贡献量）

**用途**: 存储单个贡献者的贡献量信息

**字段**:
```python
@dataclass
class ContributorContribution:
    """单个贡献者的贡献量信息"""
    contributor_id: int
    """贡献者 ID（Actor ID）"""
    
    login: str
    """贡献者登录名"""
    
    total_contribution: float
    """总贡献量（加权后的值）"""
    
    contribution_ratio: float
    """贡献占比（0.0-1.0）"""
    
    # 详细贡献统计（可选）
    commit_count: int = 0
    pr_merged: int = 0
    pr_opened: int = 0
    pr_closed: int = 0
    issue_opened: int = 0
    issue_closed: int = 0
    comment_count: int = 0
```

**验证规则**:
- `contribution_ratio` 必须在 [0.0, 1.0] 范围内
- `total_contribution` 必须 >= 0
- `contributor_id` 必须 > 0

**序列化**:
```python
def to_dict(self) -> Dict[str, Any]:
    return {
        "contributor_id": self.contributor_id,
        "login": self.login,
        "total_contribution": round(self.total_contribution, 2),
        "contribution_ratio": round(self.contribution_ratio, 4),
        "commit_count": self.commit_count,
        "pr_merged": self.pr_merged,
        "pr_opened": self.pr_opened,
        "pr_closed": self.pr_closed,
        "issue_opened": self.issue_opened,
        "issue_closed": self.issue_closed,
        "comment_count": self.comment_count,
    }
```

---

### 2. MonthlyRiskMetrics（月度风险指标）

**用途**: 存储单个项目在单个月份的风险指标

**字段**:
```python
@dataclass
class MonthlyRiskMetrics:
    """单个月份的风险指标"""
    month: str
    """月份，格式 "YYYY-MM"，如 "2023-01" """
    
    repo_name: str
    """项目名称，如 "angular/angular" """
    
    bus_factor: int
    """Bus Factor 值（达到50%贡献所需的最少贡献者数量）"""
    
    total_contribution: float
    """总贡献量"""
    
    contributor_count: int
    """贡献者总数"""
    
    contributors: List[ContributorContribution] = field(default_factory=list)
    """贡献者贡献量列表（按贡献量降序排序）"""
    
    # 图统计信息（可选）
    node_count: int = 0
    """图节点数"""
    
    edge_count: int = 0
    """图边数"""
```

**验证规则**:
- `month` 必须符合 "YYYY-MM" 格式
- `bus_factor` 必须 >= 0
- `total_contribution` 必须 >= 0
- `contributor_count` 必须 >= 0
- `bus_factor` 必须 <= `contributor_count`（如果 `contributor_count` > 0）

**序列化**:
```python
def to_dict(self) -> Dict[str, Any]:
    return {
        "month": self.month,
        "repo_name": self.repo_name,
        "bus_factor": self.bus_factor,
        "total_contribution": round(self.total_contribution, 2),
        "contributor_count": self.contributor_count,
        "contributors": [c.to_dict() for c in self.contributors],
        "node_count": self.node_count,
        "edge_count": self.edge_count,
    }
```

---

### 3. TrendAnalysis（趋势分析结果）

**用途**: 存储基于时间序列的趋势分析结果

**字段**:
```python
@dataclass
class TrendAnalysis:
    """趋势分析结果"""
    repo_name: str
    """项目名称"""
    
    bus_factor_trend: Dict[str, Any]
    """Bus Factor 趋势"""
    # {
    #     "direction": "上升" | "下降" | "稳定" | "数据不足",
    #     "slope": float,  # 斜率
    #     "change_rate": float,  # 变化率（百分比）
    #     "values": List[float],  # 时间序列值
    # }
    
    months: List[str]
    """月份列表（按时间顺序）"""
    
    bus_factor_values: List[int]
    """Bus Factor 值列表（按时间顺序）"""
```

**验证规则**:
- `months` 和 `bus_factor_values` 长度必须一致
- `direction` 必须是有效值之一
- `slope` 和 `change_rate` 必须是浮点数

**序列化**:
```python
def to_dict(self) -> Dict[str, Any]:
    return {
        "repo_name": self.repo_name,
        "bus_factor_trend": self.bus_factor_trend,
        "months": self.months,
        "bus_factor_values": self.bus_factor_values,
    }
```

---

### 4. RiskScore（综合风险评分）

**用途**: 存储基于当前值和趋势的综合风险评分

**字段**:
```python
@dataclass
class RiskScore:
    """综合风险评分"""
    repo_name: str
    """项目名称"""
    
    total_score: float
    """总分（0-100，分数越高风险越高）"""
    
    current_score: float
    """当前值得分（0-50）"""
    
    trend_score: float
    """趋势得分（0-50）"""
    
    risk_level: str
    """风险等级（"低" | "中" | "高"）"""
    
    current_bus_factor: int
    """当前 Bus Factor 值"""
    
    trend_direction: str
    """趋势方向"""
```

**验证规则**:
- `total_score` 必须在 [0.0, 100.0] 范围内
- `current_score` 必须在 [0.0, 50.0] 范围内
- `trend_score` 必须在 [0.0, 50.0] 范围内
- `risk_level` 必须是 "低"、"中"、"高" 之一
- `total_score` 应该等于 `current_score + trend_score`（允许小的浮点误差）

**序列化**:
```python
def to_dict(self) -> Dict[str, Any]:
    return {
        "repo_name": self.repo_name,
        "total_score": round(self.total_score, 2),
        "current_score": round(self.current_score, 2),
        "trend_score": round(self.trend_score, 2),
        "risk_level": self.risk_level,
        "current_bus_factor": self.current_bus_factor,
        "trend_direction": self.trend_direction,
    }
```

---

## 数据流

### 输入数据

1. **图文件**: `output/monthly-graphs/{repo_name}/actor-repo/{month}.graphml`
   - 节点：Actor（包含 `actor_id`, `login` 等属性）
   - 节点：Repository（包含 `repo_id`, `name` 等属性）
   - 边：包含统计信息（`commit_count`, `pr_merged`, `pr_opened`, `issue_opened`, `issue_closed`, `is_comment` 等）

2. **索引文件**: `output/monthly-graphs/index.json`
   - 格式：`{repo_name: {graph_type: {month: graph_path}}}`
   - 用于遍历所有项目和月份

### 处理流程

1. **加载图文件** → 提取节点和边
2. **聚合贡献量** → 计算每个 Actor 的总贡献量（使用权重公式）
3. **计算 Bus Factor** → 按贡献量降序排序，累积到50%阈值
4. **生成月度指标** → 创建 `MonthlyRiskMetrics` 对象
5. **时间序列分析** → 对同一项目的多个月份，计算趋势
6. **综合评分** → 基于当前值和趋势计算 `RiskScore`

### 输出数据

1. **完整分析结果**: `output/bus-factor-analysis/full_analysis.json`
   ```json
   {
     "repo_name": {
       "metrics": [MonthlyRiskMetrics, ...],
       "trend": TrendAnalysis,
       "risk_score": RiskScore
     }
   }
   ```

2. **摘要**: `output/bus-factor-analysis/summary.json`
   ```json
   {
     "summary": [
       {
         "repo_name": "...",
         "risk_score": RiskScore,
         "current_bus_factor": int,
         "trend_direction": str
       },
       ...
     ],
     "sorted_by": "risk_score"  // 按风险评分降序排序
   }
   ```

---

## 数据验证

### 输入验证

- 图文件必须存在且可读
- 图文件格式必须正确（GraphML）
- 节点和边必须包含必需的属性

### 计算验证

- 贡献量总和必须 >= 0
- Bus Factor 必须 <= 贡献者总数
- 贡献占比总和应该接近 1.0（允许小的浮点误差）

### 输出验证

- JSON 格式必须有效
- 所有必需字段必须存在
- 数值字段必须在合理范围内

---

## 数据模型文件位置

所有数据模型定义在 `src/models/bus_factor.py` 中：

```python
# src/models/bus_factor.py
from dataclasses import dataclass, field
from typing import Dict, List, Any

@dataclass
class ContributorContribution:
    # ... 定义 ...

@dataclass
class MonthlyRiskMetrics:
    # ... 定义 ...

@dataclass
class TrendAnalysis:
    # ... 定义 ...

@dataclass
class RiskScore:
    # ... 定义 ...
```

