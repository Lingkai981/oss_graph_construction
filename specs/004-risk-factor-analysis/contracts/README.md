# API Contracts: Bus Factor 分析

**Feature**: 组织参与与控制风险分析（Bus Factor）  
**Date**: 2024-12-19  
**Phase**: Phase 1 - Design

## 概述

本文档定义了 Bus Factor 分析功能的 API 契约。由于这是一个命令行工具（而非 Web API），这里的"API"指的是模块接口和命令行接口。

## 模块接口

### 1. BusFactorCalculator（核心计算模块）

**位置**: `src/algorithms/bus_factor_calculator.py`

#### calculate_bus_factor

计算 Bus Factor 值。

**签名**:
```python
def calculate_bus_factor(
    contributions: Dict[int, float],
    threshold: float = 0.5,
) -> int:
    """
    计算 Bus Factor（达到阈值所需的最少贡献者数量）
    
    Args:
        contributions: {contributor_id: contribution_value} 贡献量字典
        threshold: 阈值（默认0.5，即50%）
    
    Returns:
        Bus Factor 值（达到阈值所需的最少贡献者数量）
    
    Raises:
        ValueError: 如果 contributions 为空或 threshold 不在 [0, 1] 范围内
    """
```

**前置条件**:
- `contributions` 不为空
- `threshold` 在 [0.0, 1.0] 范围内
- 所有贡献量值 >= 0

**后置条件**:
- 返回值 >= 0
- 返回值 <= len(contributions)

**测试用例**:
- 正常情况：多个贡献者，贡献量不同
- 边界情况：所有贡献者贡献量相同
- 边界情况：只有一个贡献者
- 边界情况：贡献量总和为 0

---

#### aggregate_contributions

聚合图的边统计信息，计算每个贡献者的总贡献量。

**签名**:
```python
def aggregate_contributions(
    graph: nx.MultiDiGraph,
    weights: Dict[str, float] = None,
) -> Dict[int, ContributorContribution]:
    """
    从图中聚合贡献量
    
    Args:
        graph: actor-repo 图
        weights: 权重配置（如果为 None，使用默认权重）
    
    Returns:
        {contributor_id: ContributorContribution} 贡献量字典
    """
```

**前置条件**:
- `graph` 不为 None
- `weights` 中的所有键必须是有效的边属性名
- `weights` 中的所有值 >= 0

**后置条件**:
- 返回字典不为空（如果图中有边）
- 所有贡献量值 >= 0

---

### 2. BusFactorAnalyzer（主分析器）

**位置**: `src/analysis/bus_factor_analyzer.py`

#### __init__

初始化分析器。

**签名**:
```python
def __init__(
    self,
    graphs_dir: str = "output/monthly-graphs/",
    output_dir: str = "output/bus-factor-analysis/",
    threshold: float = 0.5,
    weights: Dict[str, float] = None,
):
    """
    初始化 Bus Factor 分析器
    
    Args:
        graphs_dir: 图文件目录
        output_dir: 输出目录
        threshold: Bus Factor 计算阈值（默认0.5）
        weights: 贡献权重配置（如果为 None，使用默认权重）
    """
```

---

#### load_graph

加载图文件。

**签名**:
```python
def load_graph(self, graph_path: str) -> Optional[nx.MultiDiGraph]:
    """
    加载图文件
    
    Args:
        graph_path: 图文件路径
    
    Returns:
        图对象，如果加载失败返回 None
    """
```

**前置条件**:
- `graph_path` 不为空
- 文件存在且可读

**后置条件**:
- 如果文件格式正确，返回有效的图对象
- 如果文件格式错误或不存在，返回 None

---

#### compute_monthly_metrics

计算单个月份的风险指标。

**签名**:
```python
def compute_monthly_metrics(
    self,
    graph: nx.MultiDiGraph,
    repo_name: str,
    month: str,
) -> Optional[MonthlyRiskMetrics]:
    """
    计算单个月份的风险指标
    
    Args:
        graph: actor-repo 图
        repo_name: 项目名称
        month: 月份（格式：YYYY-MM）
    
    Returns:
        月度风险指标，如果计算失败返回 None
    """
```

**前置条件**:
- `graph` 不为 None
- `repo_name` 不为空
- `month` 符合 "YYYY-MM" 格式

**后置条件**:
- 如果图中有边，返回有效的 `MonthlyRiskMetrics` 对象
- 如果图中没有边，返回 None

---

#### analyze_all_repos

分析所有项目的整个时间序列。

**签名**:
```python
def analyze_all_repos(
    self,
    resume: bool = True,
) -> Dict[str, List[MonthlyRiskMetrics]]:
    """
    分析所有项目的整个时间序列
    
    Args:
        resume: 是否支持断点续传（默认 True）
    
    Returns:
        {repo_name: [MonthlyRiskMetrics, ...]} 所有项目的月度指标
    """
```

**前置条件**:
- `graphs_dir` 存在且包含 `index.json` 文件

**后置条件**:
- 返回字典包含所有成功分析的项目
- 失败的项目会被记录在日志中，但不会中断处理

---

#### compute_trends

计算时间序列趋势。

**签名**:
```python
def compute_trends(
    self,
    repo_metrics: Dict[str, List[MonthlyRiskMetrics]],
) -> Dict[str, TrendAnalysis]:
    """
    计算所有项目的趋势分析
    
    Args:
        repo_metrics: {repo_name: [MonthlyRiskMetrics, ...]} 月度指标
    
    Returns:
        {repo_name: TrendAnalysis} 趋势分析结果
    """
```

---

#### compute_risk_scores

计算综合风险评分。

**签名**:
```python
def compute_risk_scores(
    self,
    repo_metrics: Dict[str, List[MonthlyRiskMetrics]],
    trends: Dict[str, TrendAnalysis],
) -> Dict[str, RiskScore]:
    """
    计算所有项目的综合风险评分
    
    Args:
        repo_metrics: {repo_name: [MonthlyRiskMetrics, ...]} 月度指标
        trends: {repo_name: TrendAnalysis} 趋势分析结果
    
    Returns:
        {repo_name: RiskScore} 风险评分
    """
```

---

#### save_results

保存分析结果。

**签名**:
```python
def save_results(
    self,
    repo_metrics: Dict[str, List[MonthlyRiskMetrics]],
    trends: Dict[str, TrendAnalysis],
    risk_scores: Dict[str, RiskScore],
) -> None:
    """
    保存分析结果到 JSON 文件
    
    Args:
        repo_metrics: {repo_name: [MonthlyRiskMetrics, ...]} 月度指标
        trends: {repo_name: TrendAnalysis} 趋势分析结果
        risk_scores: {repo_name: RiskScore} 风险评分
    """
```

**前置条件**:
- `output_dir` 存在或可创建

**后置条件**:
- 生成 `full_analysis.json` 和 `summary.json` 文件
- JSON 格式有效

---

#### run

主入口方法。

**签名**:
```python
def run(self, resume: bool = True) -> None:
    """
    运行完整分析流程
    
    Args:
        resume: 是否支持断点续传（默认 True）
    """
```

---

## 命令行接口

### 主命令

**位置**: `src/analysis/bus_factor_analyzer.py`（作为模块运行）

**用法**:
```bash
python -m src.analysis.bus_factor_analyzer \
  --graphs-dir output/monthly-graphs/ \
  --output-dir output/bus-factor-analysis/ \
  [选项]
```

**参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--graphs-dir` | str | `output/monthly-graphs/` | 图文件目录 |
| `--output-dir` | str | `output/bus-factor-analysis/` | 输出目录 |
| `--threshold` | float | `0.5` | Bus Factor 计算阈值（0.0-1.0） |
| `--weights-file` | str | None | 权重配置文件路径（JSON/YAML） |
| `--no-resume` | flag | False | 禁用断点续传 |
| `--verbose` | flag | False | 详细输出 |

**示例**:
```bash
# 使用默认配置
python -m src.analysis.bus_factor_analyzer

# 自定义阈值和权重
python -m src.analysis.bus_factor_analyzer \
  --threshold 0.6 \
  --weights-file config/weights.json

# 禁用断点续传
python -m src.analysis.bus_factor_analyzer --no-resume
```

---

## 配置文件格式

### 权重配置文件（JSON）

**位置**: 用户指定（通过 `--weights-file` 参数）

**格式**:
```json
{
  "commit_count": 1.0,
  "pr_merged": 5.0,
  "pr_opened": 2.0,
  "pr_closed": 1.0,
  "issue_opened": 1.5,
  "issue_closed": 2.0,
  "is_comment": 0.5
}
```

**验证规则**:
- 所有值必须是数字
- 所有值必须 >= 0
- 键名必须匹配边的属性名

---

## 错误处理

### 异常类型

1. **FileNotFoundError**: 图文件不存在
2. **ValueError**: 参数无效（如阈值不在 [0, 1] 范围内）
3. **KeyError**: 图中缺少必需的属性
4. **json.JSONDecodeError**: JSON 文件格式错误

### 错误处理策略

- 图文件加载失败：记录警告，跳过该文件，继续处理
- 计算失败：记录错误，返回 None，继续处理其他项目
- 配置错误：抛出异常，终止程序

---

## 测试契约

### 单元测试

- 测试 `calculate_bus_factor` 的各种边界情况
- 测试 `aggregate_contributions` 的权重计算
- 测试数据模型的验证规则

### 集成测试

- 测试完整的分析流程（从图文件到 JSON 输出）
- 测试断点续传功能
- 测试错误处理（缺失文件、损坏文件等）

---

## 版本历史

- **v1.0** (2024-12-19): 初始版本

