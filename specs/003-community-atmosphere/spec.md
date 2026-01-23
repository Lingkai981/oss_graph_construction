# Feature Specification: 社区氛围分析

**Feature Branch**: `003-community-atmosphere`  
**Created**: 2024-12-19  
**Status**: Draft  
**Input**: User description: "我现在已经有了actor-discussion的时序图@output/monthly-graphs/angular-angular/actor-discussion/2023-01.graphml ，其中也给相应的边加上了comment_body属性，然后我需要实现\"社区氛围\"的分析，图中是一些参考，然后或许需要借助大模型的协助分析，如果需要的话使用deepseek，然后通过填写环境变量的方式来配置apikey，所有生成的.md后缀的描述文件内容全部使用中文。同时，项目中也会维护actor-actor协作图，用于刻画开发者之间的结构关系。"

## Clarifications

### Session 2024-12-19

- Q: 分析方式是什么？ → A: 参考维护者倦怠分析，使用整个时间序列，自动处理所有项目，为每个项目生成月度指标时间序列和综合评分
- Q: 情感分析使用什么方法？ → A: 只使用DeepSeek大模型进行情感分析，删除关键词匹配方法
- Q: 输出格式是什么？ → A: 类似维护者倦怠分析的输出格式，包含每个项目的metrics时间序列和atmosphere_score综合评分

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 分析所有项目的社区氛围指标 (Priority: P1)

作为研究人员或社区管理者，我需要分析所有开源项目的社区氛围时间序列，以便了解各项目的社区健康度和互动质量变化趋势。

**Why this priority**: 这是核心功能，能够独立提供价值。通过分析整个时间序列，用户可以立即获得所有项目的社区氛围指标时间序列，包括情感传播、社区紧密度和沟通效率。系统自动处理所有项目和时间序列。

**Independent Test**: 可以通过运行分析工具，验证系统能够自动加载所有项目的actor-discussion和actor-actor图文件：  
- 使用actor-discussion图提取评论文本并进行情感分析  
- 使用actor-actor图计算聚类系数和网络直径  
- 为每个项目生成月度指标时间序列，并输出综合评分。该功能可以独立测试和演示。

**Acceptance Scenarios**:

1. **Given** 存在包含comment_body属性的actor-discussion图文件索引，且同一项目/月份存在对应的actor-actor图文件，**When** 用户运行分析工具，**Then** 系统应成功加载所有图文件并计算三个核心指标（情感传播、聚类系数、网络直径）的时间序列
2. **Given** 某些月份的图文件不存在，**When** 系统进行分析，**Then** 系统应跳过缺失的月份，使用可用的月份进行分析
3. **Given** 图文件中某些边没有comment_body属性，**When** 系统进行情感分析，**Then** 系统应跳过这些边，不影响其他边的分析
4. **Given** 图文件为空或损坏，**When** 系统尝试分析，**Then** 系统应跳过该文件，继续处理其他文件
5. **Given** 分析完成，**When** 系统保存结果，**Then** 系统应生成包含所有项目的时间序列指标和综合评分的JSON文件：  
   - `full_analysis.json`：按项目聚合的月度指标，支持按月增量更新（每完成一个月份就写入/覆盖）  
   - `summary.json`：仅包含“所有可分析月份均完成”的项目，在项目级别完成时更新/追加

---


---

### User Story 3 - 使用DeepSeek大模型进行情感分析 (Priority: P3)

作为需要准确情感分析的用户，我希望系统能够使用大模型（DeepSeek）来分析评论的情感倾向，以获得准确的情感分析结果。

**Why this priority**: 这是核心功能。系统必须使用DeepSeek API进行情感分析，如果API不可用，分析将失败并给出明确错误信息。

**Independent Test**: 可以通过配置DeepSeek API key，验证系统能够调用API进行情感分析，并返回情感分数。如果API key未配置或调用失败，系统应给出明确的错误信息。

**Acceptance Scenarios**:

1. **Given** 用户已在.env文件中配置DEEPSEEK_API_KEY，**When** 系统进行情感分析，**Then** 系统应使用DeepSeek API分析comment_body并返回情感分数
2. **Given** .env文件中DEEPSEEK_API_KEY未配置或无效，**When** 系统进行情感分析，**Then** 系统应给出明确的错误信息，提示需要在.env文件中配置API key
3. **Given** API调用超时或失败，**When** 系统处理，**Then** 系统应在重试后给出错误信息，记录失败的边

---

### Edge Cases

- 当图文件中没有任何comment_body属性时，情感传播模型应如何处理？
- 当图只有单个节点或完全孤立时，聚类系数和网络直径应如何计算？
- 当comment_body包含非ASCII字符（如emoji、中文）时，情感分析是否正常处理？
- 当API调用达到速率限制时，系统应如何处理？
- 当图文件非常大（超过10万节点）时，算法性能是否可接受？
- 当某些月份的图文件不存在时，系统应如何处理？

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统必须能够从actor-discussion图文件中读取节点、边和comment_body属性，用于情感分析和情感传播
- **FR-001A**: 系统必须能够从actor-actor图文件中读取开发者协作关系，用于聚类系数和网络直径等结构性指标的计算
- **FR-002**: 系统必须实现情感传播模型算法，分析情绪如何在社区中传播，时间复杂度为O(V+E) per step
- **FR-003**: 系统必须实现聚类系数计算，衡量社区紧密度，时间复杂度为O(V·d²)。当输入为actor-discussion二部图时，需要先构建actor投影图；当输入为actor-actor图时，应直接在去重后的无向actor图上计算。
- **FR-004**: 系统必须实现网络直径计算，评估社区沟通效率，时间复杂度为O(V·E)。当输入为actor-discussion二部图时，需要先构建actor投影图；当输入为actor-actor图时，应直接在去重后的无向actor图上计算。
- **FR-005**: 系统必须能够从边的comment_body属性中提取情感信息（正面/负面/中性），使用DeepSeek API进行情感分析
- **FR-006**: 系统必须支持使用DeepSeek API进行情感分析，通过.env文件中的DEEPSEEK_API_KEY配置
- **FR-008**: 系统必须能够分析整个时间序列，为每个项目生成月度指标时间序列；系统应支持“按月增量保存”，即每完成一个月份的分析即可将该月份写入`full_analysis.json`。
- **FR-009**: 系统必须能够批量处理所有项目，为每个项目生成独立的分析结果和综合评分；当一个项目所有“可分析月份”（既有actor-discussion又有actor-actor的月份）完成后，应立即在`summary.json`中更新该项目的汇总记录。
- **FR-010**: 系统必须将分析结果保存为结构化数据格式，包含所有计算的指标；结果文件包括按项目聚合的`full_analysis.json`和仅包含已完成项目的`summary.json`。
- **FR-011**: 系统必须处理图文件缺失comment_body属性的情况，使用默认值或跳过
- **FR-012**: 系统必须处理非连通图的情况，计算最大连通分量的网络直径
- **FR-013**: 系统必须记录分析过程中的错误和警告，但不中断整个流程
- **FR-014**: 所有生成的Markdown文档必须使用中文编写

### Key Entities *(include if feature involves data)*

- **月度社区氛围指标（Monthly Atmosphere Metrics）**: 包含单个月的情感传播、聚类系数和网络直径指标
- **社区氛围综合评分（Atmosphere Score）**: 基于时间序列指标计算的综合评分，包含三大因子（情绪、社区紧密度、网络效率）的得分和权重
- **情感传播结果（Emotion Propagation Result）**: 包含平均情绪值、传播步数和阻尼系数的分析结果
- **聚类系数结果（Clustering Coefficient Result）**: 包含全局聚类系数、平均局部聚类系数和actor图统计的计算结果
- **网络直径结果（Network Diameter Result）**: 包含网络直径、平均路径长度、连通性状态和连通分量数量的计算结果

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 系统能够在合理时间内完成所有项目的整个时间序列分析
- **SC-002**: 系统能够成功处理至少95%的有效图文件，对于无法处理的文件应提供明确的错误信息
- **SC-003**: 当DeepSeek API可用时，情感分析能够成功处理至少90%的comment_body
- **SC-004**: 系统能够处理所有项目的整个时间序列，在合理时间内完成所有分析
- **SC-005**: 对于包含comment_body的边，系统能够提取和分析至少90%的情感信息
- **SC-006**: 分析结果文件包含所有必需的指标字段，格式规范，可以被其他工具正确解析
- **SC-007**: 当API key未配置时，系统能够给出明确的错误信息，提示需要在.env文件中配置DEEPSEEK_API_KEY
- **SC-008**: 系统能够处理包含非ASCII字符（中文、emoji等）的comment_body，不出现编码错误

## Assumptions

- actor-discussion图文件已经存在且格式符合标准，并且同一项目/月份存在对应的actor-actor图文件（至少对于需要进行结构性分析的月份）
- comment_body属性已存在于相关边的属性中，但可能不完整（某些边可能缺失）
- 用户有基本的命令行使用能力，能够配置环境变量
- 图文件大小在合理范围内（单文件不超过50万节点），算法性能可接受
- DeepSeek API服务可用且稳定，系统依赖其可用性（必须配置API key）
- 用户主要关注actor节点之间的社区氛围，discussion节点（Issue/PR）作为连接中介

## Dependencies

- 现有的actor-discussion图构建功能：依赖已生成的讨论图文件
- 现有的actor-actor图构建功能：依赖已生成的协作网络图文件
- 图数据结构和算法库：用于实现聚类系数和网络直径等算法
- DeepSeek API（必需）：用于情感分析，通过.env文件配置
- 运行环境：支持执行图分析算法

## Out of Scope

- 不包含图文件的生成功能（假设已存在）
- 不包含实时分析功能（仅支持离线分析已有图文件）
- 不包含可视化功能（仅输出结构化数据）
- 不包含其他大模型API的支持（仅支持DeepSeek）
- 不包含情感分析的训练和模型优化（使用DeepSeek API）
