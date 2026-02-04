# Research: Bus Factor 计算与分析

**Feature**: 组织参与与控制风险分析（Bus Factor）  
**Date**: 2024-12-19  
**Phase**: Phase 0 - Research

## 研究目标

确定 Bus Factor 计算与分析功能的技术实现方案，包括：
1. Bus Factor 计算算法的具体实现
2. 贡献量聚合和权重配置方案
3. 时间序列分析和趋势计算方案
4. 综合风险评分算法

## 技术决策

### 决策 1: Bus Factor 计算算法

**决策**: 使用累积贡献量方法计算 Bus Factor

**原理**: 
- 按贡献量降序排序所有贡献者
- 累积贡献量直到达到总贡献量的50%（可配置阈值）
- 返回达到阈值所需的最少贡献者数量

**实现细节**:
```python
def calculate_bus_factor(contributions: Dict[str, float], threshold: float = 0.5) -> int:
    """
    计算 Bus Factor
    
    Args:
        contributions: {contributor_id: contribution_value} 贡献量字典
        threshold: 阈值（默认0.5，即50%）
    
    Returns:
        Bus Factor 值（达到阈值所需的最少贡献者数量）
    """
    if not contributions or sum(contributions.values()) == 0:
        return 0
    
    total = sum(contributions.values())
    target = total * threshold
    
    sorted_contributors = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
    cumulative = 0.0
    count = 0
    
    for contributor_id, contribution in sorted_contributors:
        cumulative += contribution
        count += 1
        if cumulative >= target:
            return count
    
    return count  # 如果所有贡献者加起来都不够阈值，返回总数
```

**替代方案考虑**:
- 使用百分位数方法：计算贡献量分布的百分位数，但这种方法不如累积方法直观
- 使用信息熵方法：计算贡献分布的熵值，但不符合 Bus Factor 的经典定义

**选择理由**: 累积贡献量方法符合 Bus Factor 的经典定义，易于理解和验证。

---

### 决策 2: 贡献量聚合和权重配置

**决策**: 使用可配置的权重公式，基于边的统计字段动态计算贡献量

**权重配置方案**:
```python
# 默认权重配置（可在配置文件中自定义）
DEFAULT_WEIGHTS = {
    "commit_count": 1.0,      # 提交次数
    "pr_merged": 5.0,         # 合并的 PR（高价值）
    "pr_opened": 2.0,          # 打开的 PR
    "pr_closed": 1.0,          # 关闭的 PR
    "issue_opened": 1.5,       # 打开的 Issue
    "issue_closed": 2.0,       # 关闭的 Issue
    "is_comment": 0.5,         # 评论（参与度）
}

def calculate_contribution(edge_data: Dict) -> float:
    """计算单条边的贡献量"""
    contribution = 0.0
    for field, weight in DEFAULT_WEIGHTS.items():
        value = edge_data.get(field, 0)
        if isinstance(value, (int, float)):
            contribution += value * weight
    return contribution
```

**配置方式**:
- 支持通过配置文件（JSON/YAML）自定义权重
- 支持通过命令行参数覆盖默认权重
- 权重值应合理反映不同类型贡献的重要性

**替代方案考虑**:
- 硬编码权重：简单但不灵活，不符合需求
- 机器学习方法：过于复杂，需要训练数据

**选择理由**: 可配置权重方案既灵活又实用，符合"避免硬编码"的需求。

---

### 决策 3: 时间序列分析和趋势计算

**决策**: 使用线性回归和变化率方法计算趋势

**趋势计算方案**:
```python
def calculate_trend(values: List[float]) -> Dict[str, Any]:
    """
    计算时间序列趋势
    
    Args:
        values: 时间序列值列表（按时间顺序）
    
    Returns:
        {
            "direction": "上升" | "下降" | "稳定",
            "slope": float,  # 斜率
            "change_rate": float,  # 变化率（百分比）
        }
    """
    if len(values) < 2:
        return {"direction": "数据不足", "slope": 0.0, "change_rate": 0.0}
    
    # 使用线性回归计算斜率
    n = len(values)
    x = np.arange(n)
    slope = np.polyfit(x, values, 1)[0]
    
    # 计算变化率
    first_value = values[0]
    last_value = values[-1]
    if first_value == 0:
        change_rate = float('inf') if last_value > 0 else 0.0
    else:
        change_rate = ((last_value - first_value) / first_value) * 100
    
    # 判断趋势方向
    if abs(slope) < 0.1:  # 阈值可配置
        direction = "稳定"
    elif slope > 0:
        direction = "上升"
    else:
        direction = "下降"
    
    return {
        "direction": direction,
        "slope": float(slope),
        "change_rate": float(change_rate),
    }
```

**替代方案考虑**:
- 简单差分方法：不够准确，无法处理噪声
- 移动平均方法：需要更多数据点，不适合短期分析

**选择理由**: 线性回归方法简单有效，适合分析短期趋势（3个月以上）。

---

### 决策 4: 综合风险评分算法

**决策**: 使用加权评分方法，综合考虑当前 Bus Factor 值和变化趋势

**评分算法**:
```python
def calculate_risk_score(
    current_bus_factor: float,
    trend_direction: str,
    trend_change_rate: float,
    min_bus_factor: float = 1.0,
    max_bus_factor: float = 50.0,
) -> Dict[str, Any]:
    """
    计算综合风险评分（0-100，分数越高风险越高）
    
    Args:
        current_bus_factor: 当前 Bus Factor 值
        trend_direction: 趋势方向（"上升" | "下降" | "稳定"）
        trend_change_rate: 变化率（百分比）
        min_bus_factor: 最小 Bus Factor 值（用于归一化）
        max_bus_factor: 最大 Bus Factor 值（用于归一化）
    
    Returns:
        {
            "total_score": float,  # 总分（0-100）
            "current_score": float,  # 当前值得分（0-50）
            "trend_score": float,   # 趋势得分（0-50）
            "risk_level": str,      # 风险等级（"低" | "中" | "高"）
        }
    """
    # 当前值得分（0-50）：Bus Factor 越小，风险越高
    normalized_factor = (current_bus_factor - min_bus_factor) / (max_bus_factor - min_bus_factor)
    normalized_factor = max(0.0, min(1.0, normalized_factor))  # 限制在 [0, 1]
    current_score = (1.0 - normalized_factor) * 50  # 反转：值越小得分越高
    
    # 趋势得分（0-50）：上升趋势风险高，下降趋势风险低
    if trend_direction == "上升":
        trend_score = min(50.0, 30.0 + abs(trend_change_rate) * 0.5)
    elif trend_direction == "下降":
        trend_score = max(0.0, 20.0 - abs(trend_change_rate) * 0.3)
    else:  # 稳定
        trend_score = 25.0
    
    total_score = current_score + trend_score
    
    # 风险等级
    if total_score >= 70:
        risk_level = "高"
    elif total_score >= 40:
        risk_level = "中"
    else:
        risk_level = "低"
    
    return {
        "total_score": round(total_score, 2),
        "current_score": round(current_score, 2),
        "trend_score": round(trend_score, 2),
        "risk_level": risk_level,
    }
```

**替代方案考虑**:
- 简单平均方法：不考虑权重，不够准确
- 机器学习方法：需要训练数据，过于复杂

**选择理由**: 加权评分方法简单有效，能够综合考虑当前值和趋势，符合业务需求。

---

## 参考实现

### 1. BurnoutAnalyzer 实现模式

**参考点**:
- 使用 `MonthlyMetrics` 数据类存储单月指标
- 使用 `analyze_all_repos` 方法处理整个时间序列
- 使用 `save_results` 方法保存 JSON 结果
- 支持断点续传（通过检查已存在的输出文件）

**可复用代码**:
- 图加载逻辑：`load_graph` 方法
- 时间序列处理：`analyze_all_repos` 方法
- 结果保存：`save_results` 方法

### 2. CommunityAtmosphereAnalyzer 实现模式

**参考点**:
- 使用 `MonthlyAtmosphereMetrics` 数据类
- 使用 `compute_monthly_metrics` 方法计算单月指标
- 使用 `compute_atmosphere_score` 方法计算综合评分
- 支持多图类型（actor-discussion 和 actor-actor）

**可复用代码**:
- 指标计算模式：单月指标 → 时间序列 → 综合评分
- 错误处理模式：捕获异常，记录日志，继续处理

---

## 技术风险与缓解

### 风险 1: 浮点数精度问题

**风险**: 阈值计算（50%）可能出现浮点数精度问题

**缓解措施**:
- 使用 `math.isclose` 或 `numpy.isclose` 进行浮点数比较
- 使用相对误差而非绝对误差
- 在测试中覆盖边界情况

### 风险 2: 大型图文件内存占用

**风险**: 处理大型图文件（数万个节点和边）可能导致内存不足

**缓解措施**:
- 使用 NetworkX 的流式处理（如果可能）
- 及时释放不需要的图对象
- 分批处理多个项目

### 风险 3: 贡献权重配置不合理

**风险**: 默认权重可能不符合实际业务需求

**缓解措施**:
- 提供合理的默认权重（基于经验值）
- 支持通过配置文件自定义权重
- 在文档中说明权重设置原则

---

## 总结

所有技术决策已确定，无需要进一步澄清的问题。实现方案：
1. ✅ Bus Factor 计算算法：累积贡献量方法
2. ✅ 贡献量聚合：可配置权重公式
3. ✅ 趋势计算：线性回归方法
4. ✅ 风险评分：加权评分方法

可以进入 Phase 1 设计阶段。

