# 快速开始：社区氛围分析

**日期**：2024-12-19  
**特性**：社区氛围分析

## 概述

社区氛围分析系统提供了三个核心图算法来分析开源社区的互动氛围：
1. **情感传播模型**：分析情绪如何在社区中传播（使用DeepSeek API进行情感分析）
2. **聚类系数**：衡量社区紧密度
3. **网络直径**：评估社区沟通效率

系统参考维护者倦怠分析的结构，自动处理整个时间序列，为每个项目生成月度指标时间序列和综合评分。

## 前置条件

### 1. 环境要求

- Python 3.8+
- 已安装项目依赖（`pip install -r requirements.txt`）
- 已生成按月三类图文件（位于`output/monthly-graphs/`），其中：  
  - `actor-discussion/`：用于情感分析和情感传播（必须包含`comment_body`属性）  
  - `actor-actor/`：用于计算聚类系数和网络直径  
- **必须配置DeepSeek API key**

### 2. 配置DeepSeek API

系统必须使用DeepSeek API进行情感分析，需要在项目根目录创建`.env`文件并配置API key：

1. 在项目根目录创建`.env`文件（如果不存在）
2. 在`.env`文件中添加以下内容：

```bash
DEEPSEEK_API_KEY=your-api-key-here
```

**注意**：
- 请将`your-api-key-here`替换为你的实际DeepSeek API key
- `.env`文件已被`.gitignore`忽略，不会提交到版本控制系统
- 如果不配置API key，系统将无法进行情感分析，会给出明确的错误信息

## 基本使用

### 分析所有项目

系统会自动处理所有项目的整个时间序列：

```bash
# 分析所有项目（使用整个时间序列）
python -m src.analysis.community_atmosphere_analyzer \
  --graphs-dir output/monthly-graphs/ \
  --output-dir output/community-atmosphere/
```

## 命令行参数

### 必需参数

无（使用默认值）

### 可选参数

- `--graphs-dir`：图文件目录（默认：`output/monthly-graphs/`）
- `--output-dir`：输出目录（默认：`output/community-atmosphere/`）

## 输出结果

### 输出文件

分析结果保存在以下文件中：

1. **`full_analysis.json`**：完整分析结果，包含所有项目的月度指标时间序列和综合评分；**在分析过程中会按月增量更新**（每完成一个月份就会写入/覆盖该项目对应月份的数据）。  
2. **`summary.json`**：摘要结果，按评分排序的项目列表；**仅包含“所有可分析月份均完成”的项目**，项目在分析完成时即时更新。

### 结果格式

#### full_analysis.json

```json
{
  "angular/angular": {
    "metrics": [
      {
        "month": "2023-01",
        "repo_name": "angular/angular",
        "average_emotion": 0.3,
        "emotion_propagation_steps": 5,
        "emotion_damping_factor": 0.85,
        "global_clustering_coefficient": 0.6,
        "average_local_clustering": 0.5,
        "actor_graph_nodes": 100,
        "actor_graph_edges": 200,
        "diameter": 5,
        "average_path_length": 2.3,
        "is_connected": true,
        "num_connected_components": 1,
        "largest_component_size": 100
      }
    ],
    "atmosphere_score": {
      "score": 75.5,
      "level": "good",
      "months_analyzed": 12,
      "period": "2023-01 to 2023-12",
      "factors": {
        "emotion": {
          "value": 0.3,
          "score": 26.0,
          "weight": 40
        },
        "clustering": {
          "value": 0.5,
          "score": 15.0,
          "weight": 30
        },
        "diameter": {
          "value": 5,
          "score": 15.0,
          "weight": 20
        },
        "path_length": {
          "value": 2.3,
          "score": 7.7,
          "weight": 10
        }
      }
    }
  }
}
```

#### summary.json

```json
[
  {
    "repo_name": "angular/angular",
    "atmosphere_score": 75.5,
    "level": "good",
    "months_analyzed": 12
  }
]
```

### 结果解读

- **月度指标（metrics）**：
  - `average_emotion`：平均情绪值，范围约为-1到1，正值表示正面情绪，负值表示负面情绪
  - `global_clustering_coefficient`：全局聚类系数，范围0到1，值越大表示社区越紧密
  - `average_local_clustering`：平均局部聚类系数
  - `diameter`：网络直径，值越小表示沟通效率越高
  - `average_path_length`：平均路径长度，值越小表示信息传播越快
  - `is_connected`：图是否连通，True表示所有节点都可以相互到达

- **综合评分（atmosphere_score）**：
  - `score`：综合评分，范围0-100，分数越高表示社区氛围越好
  - `level`：评分等级（excellent/good/moderate/poor）
  - `factors`：各因子得分和权重（当前版本仅保留三大类）：  
  - `emotion`：情绪因子（权重20%），由时间平均的`average_emotion`经 [-1,1] → [0,1] 线性归一化得到；  
  - `clustering`：社区紧密度因子（权重40%），基于时间平均的`average_local_clustering`，使用平滑增长函数进行归一化（避免线性映射对低值过于严格）：
    - 公式：`clustering_norm = 1 / (1 + 2.0 × (0.6 - clustering) / 0.6)`
    - 聚类系数 = 0 → 0.0, 0.1 → 0.33, 0.2 → 0.5, 0.4 → 0.75, ≥0.6 → 1.0  
  - `network_efficiency`：网络效率因子（权重40%），综合时间平均的 `diameter` 和 `average_path_length`，使用对数衰减函数进行归一化（避免硬截断，适应不同规模项目）：
    - 直径分量：`diameter_component = 1 / (1 + 0.3 × (diameter - 1))`，平滑衰减
    - 路径长度分量：`path_component = 1 / (1 + 0.4 × (path_length - 1))`，平滑衰减
    - 两者平均后乘以 40 得到网络效率得分

## 常见问题

### Q1: 如何知道分析是否使用了DeepSeek API？

查看日志输出，如果看到"DeepSeek API key未配置"警告，说明需要配置API key。

### Q2: 如果某些月份的图文件缺失怎么办？

系统会自动跳过缺失的月份，使用可用的月份进行分析。

### Q3: 分析结果中的数值如何解读？

- **情感传播**：正值表示正面情绪，负值表示负面情绪，绝对值越大表示情绪越强烈
- **聚类系数**：值越大表示社区成员之间的连接越紧密，社区越团结
- **网络直径**：值越小表示信息传播路径越短，沟通效率越高
- **综合评分**：分数越高表示社区氛围越好

### Q4: 如何提高分析速度？

- 确保DeepSeek API响应速度正常
- 对于大项目，分析时间会相应增加

## 下一步

- 查看[数据模型文档](./data-model.md)了解详细的数据结构
- 查看[接口契约文档](./contracts/README.md)了解API接口
- 查看[研究文档](./research.md)了解算法实现细节
