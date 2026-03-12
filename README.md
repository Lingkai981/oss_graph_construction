# OSS 社区健康度分析工具

基于 GitHub Archive 事件数据，构建多类型时序图并进行开源社区健康度多维分析的工具集。

## 🎯 功能概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                      OSS 社区健康度分析系统                           │
├─────────────────────────────────────────────────────────────────────┤
│  📥 数据采集         从 GitHub Archive 下载并过滤目标项目事件数据      │
│  📊 月度图构建       Actor-Actor / Actor-Repo / Actor-Discussion     │
│  🔥 倦怠分析         核心维护者活跃度、响应时间、流失预警              │
│  👥 人员流动分析     核心成员留存率、流入流出、跨项目流向              │
│  🌡️ 社区氛围分析     毒性检测、CHAOSS 指标、网络结构评估              │
│  🌱 新人体验分析     融入距离、晋升路径、核心可达性                    │
│  📈 Bus Factor       组织参与度、关键人物风险、贡献集中度              │
│  📝 报告生成         各维度详细报告 + 综合健康度报告                   │
└─────────────────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 1. 环境安装

```bash
# Python >= 3.10
python -m venv venv
source venv/bin/activate  # Linux/macOS
# Windows: venv\Scripts\activate

pip install -r requirements.txt
```

核心依赖：`networkx`、`pandas`、`numpy`、`matplotlib`、`tqdm`。

### 2. 准备数据

项目需要 GitHub Archive 事件数据。数据存放在 `data/` 下（已被 `.gitignore` 排除），
或通过 `--data-dir` 指定外部目录。详见下方"数据采集"章节。

**月度图**（`output/monthly-graphs/`）是所有分析器的共同输入。如果图已构建好，后续分析直接复用。

### 3. 一键运行全部分析并生成报告

**方式一：使用简化脚本（推荐）**

```bash
# 完整运行：构图 + 全部分析 + 报告
python run_all.py --workers 8

# 快速模式：月度图和毒性缓存已存在时跳过
python run_all.py --quick --workers 8
```

**方式二：使用 `run_analysis.py`（更灵活）**

```bash
# 全量运行
python run_analysis.py --all --workers 8

# 跳过构图和毒性缓存（推荐：月度图已存在时）
python run_analysis.py --all --skip monthly_graphs toxicity_cache --workers 8 --continue-on-error

# 只跑四个核心分析 + 人员流动 + 全部报告
python run_analysis.py \
  --analyzers burnout newcomer community_atmosphere bus_factor personnel_flow \
  --reports burnout_report newcomer_report atmosphere_report bus_factor_report comprehensive_report \
  --continue-on-error --workers 8
```

**已验证的完整命令**（假设 `output/monthly-graphs/` 已存在）：

```bash
python run_analysis.py \
  --analyzers burnout newcomer community_atmosphere bus_factor quality_risk structure personnel_flow \
  --reports burnout_report newcomer_report bus_factor_report atmosphere_report quality_risk_report structure_report comprehensive_report \
  --skip monthly_graphs toxicity_cache \
  --continue-on-error --verbose --workers 8
```

此命令依次执行：
1. **倦怠分析** (burnout) — 核心维护者活跃度、响应时间、流失预警
2. **新人体验分析** (newcomer) — 融入距离、晋升路径、核心可达性
3. **社区氛围分析** (community_atmosphere) — CHAOSS 指标、聚类系数、网络结构
4. **Bus Factor 分析** (bus_factor) — 贡献集中度、关键人物风险
5. **质量风险分析** (quality_risk) — 可疑贡献者识别
6. **网络结构分析** (structure) — 图直径、平均距离、连通分量
7. **人员流动分析** (personnel_flow) — 留存率、跨项目流向
8. 生成各维度报告 + **综合健康度报告**

### 4. 查看结果

- 综合报告：`output/comprehensive_report.md`
- 各维度详细报告：`output/<分析类型>/detailed_report.txt`
- 完整 JSON 数据：`output/<分析类型>/full_analysis.json`

---

## 📖 分步运行指南

如果需要单独运行某个分析模块，请按以下步骤操作。

### 步骤 1：数据采集

从 GitHub Archive 下载并过滤目标项目的事件数据：

```bash
# 按代表性项目列表下载（推荐）
python -m src.data_collection.gharchive_collector \
  --start-date 2023-01-01 \
  --end-date 2025-01-01 \
  --sample-mode fulldaily \
  --workers 16 \
  --output-dir data/filtered

# 按已有月度图索引中的仓库列表下载（用于扩展历史数据）
python -m src.data_collection.gharchive_collector \
  --start-date 2021-07-01 \
  --end-date 2025-12-31 \
  --sample-mode fulldaily \
  --repos-from-index output/monthly-graphs/index.json \
  --workers 16 \
  --output-dir data/filtered
```

**采样模式说明**：
| 模式 | 说明 | 数据量 |
|------|------|--------|
| `fulldaily` | 每天 24 小时全量采集，按日合并 | 最大 |
| `daily` | 每天 1 小时（12:00 UTC） | 中等 |
| `monthly` | 每月 1 小时 | 最小 |

### 步骤 2：构建月度图

```bash
# 构建全部月份（自动并行）
python run_analysis.py --analyzers monthly_graphs --workers 8

# 或使用原生命令
python -m src.analysis.monthly_graph_builder \
  --data-dir data/filtered \
  --output-dir output/monthly-graphs \
  --workers 8

# 仅构建指定月份范围（增量构建）
python -m src.analysis.monthly_graph_builder \
  --data-dir data/filtered \
  --output-dir output/monthly-graphs \
  --start-month 2024-01 \
  --end-month 2024-12 \
  --workers 8
```

### 步骤 3：倦怠分析

分析核心维护者的活跃度变化、响应时间和流失预警：

```bash
# 使用一站式入口
python run_analysis.py --analyzers burnout

# 生成详细报告
python run_analysis.py --reports burnout_report
```

**分析指标**：
- 度中心性变化：核心维护者的活跃度是否下降
- 响应时间变化：Issue/PR 响应是否变慢
- 活跃度变化：事件数量是否下降
- 核心成员流失：top-k 成员是否仍然活跃

**输出文件**：
- `output/burnout-analysis/full_analysis.json` - 完整分析结果
- `output/burnout-analysis/summary.json` - 摘要评分
- `output/burnout-analysis/detailed_report.txt` - 详细报告

### 步骤 4：人员流动分析

基于倦怠分析结果，研究核心成员的流入/流出、留存率和跨项目流向：

```bash
# 注意：需要先完成倦怠分析
python run_analysis.py --analyzers burnout personnel_flow
```

**分析指标**：
- 核心成员时间线：首次/末次出现、任期、活跃月份
- 流入/流出事件：谁何时成为核心、谁何时离开
- 留存率：N 个月核心成员留存曲线
- 流动率：按月/按季的流入流出统计
- 关键流失：长期核心成员离职识别
- 跨 repo 流向：离开后在哪些其他项目中成为核心

**输出文件**：
- `output/personnel-flow-all/repo_yearly_status.txt` - 年度人员状态汇总
- `output/personnel-flow-all/full_analysis.json` - 完整分析结果

### 步骤 5：社区氛围分析

分析社区的毒性水平、CHAOSS 指标和网络结构：

```bash
# 完整流程（需要 ToxiCR 项目支持毒性检测）
python run_analysis.py --analyzers toxicity_cache community_atmosphere

# 生成详细报告
python run_analysis.py --reports atmosphere_report
```

**分析指标**：
- 毒性分析：使用 ToxiCR 检测评论毒性
- CHAOSS 指标：变更请求关闭率、首次响应时间
- 聚类系数：衡量社区紧密度
- 网络直径：评估社区沟通效率

**输出文件**：
- `output/community-atmosphere-analysis/full_analysis.json` - 完整分析结果
- `output/community-atmosphere-analysis/summary.json` - 摘要评分
- `output/community-atmosphere-analysis/detailed_report.txt` - 详细报告

### 步骤 6：新人体验分析

分析新人融入社区的难度和晋升为核心成员的路径：

```bash
# 运行新人分析
python run_analysis.py --analyzers newcomer

# 生成详细报告
python run_analysis.py --reports newcomer_report
```

**分析指标**：
- 新人融入距离：新人到核心成员的平均最短路径
- 晋升路径分析：从外围成员晋升为核心的平均时间
- 核心可达性：新人能否通过网络到达核心成员

**输出文件**：
- `output/newcomer-analysis/full_analysis.json` - 完整分析结果
- `output/newcomer-analysis/summary.json` - 摘要评分
- `output/newcomer-analysis/detailed_report.txt` - 详细报告

### 步骤 7：Bus Factor 分析

评估项目对关键人物的依赖风险：

```bash
# 运行 Bus Factor 分析
python run_analysis.py --analyzers bus_factor --workers 8

# 生成详细报告
python run_analysis.py --reports bus_factor_report
```

**分析指标**：
- Bus Factor 值：达到总贡献量 50% 所需的最少贡献者数量
- 贡献集中度：Top-N 贡献者的贡献占比
- 趋势分析：Bus Factor 的变化趋势
- 综合风险评分：基于当前值和趋势计算

**输出文件**：
- `output/bus-factor-analysis/full_analysis.json` - 完整分析结果
- `output/bus-factor-analysis/summary.json` - 摘要评分
- `output/bus-factor-analysis/detailed_report.txt` - 详细报告

### 步骤 8：生成综合报告

汇总所有分析结果，生成综合健康度报告：

```bash
# 生成综合报告（需要先完成所有分析）
python run_analysis.py --reports comprehensive_report
```

**输出文件**：
- `output/comprehensive_report.md` - 综合健康度报告

---

## 🛠️ 一站式命令行工具

`run_analysis.py` 提供了一站式的命令行接口，可以灵活组合执行各种分析任务。

### 查看可用任务

```bash
python run_analysis.py --list
```

输出：
```
可用的分析器：
  monthly_graphs         按月构建图数据快照
  burnout                执行维护者倦怠分析
  newcomer               执行新人融入分析
  toxicity_cache         调用 ToxiCR 生成社区氛围毒性缓存
  bus_factor             执行 Bus Factor 风险分析
  quality_risk           执行质量风险分析
  structure              执行协作网络结构分析
  personnel_flow         执行人员流动分析
  community_atmosphere   执行社区氛围分析

可用的报告生成器：
  burnout_report         生成倦怠详细报告
  newcomer_report        生成新人体验报告
  bus_factor_report      生成 Bus Factor 风险报告
  atmosphere_report      生成社区氛围报告
  quality_risk_report    生成质量风险报告
  structure_report       生成结构指标报告
  comprehensive_report   生成综合健康报告
```

### 常用命令

```bash
# 运行全部分析和报告
python run_analysis.py --all --workers 8

# 只运行指定分析器
python run_analysis.py --analyzers burnout newcomer personnel_flow

# 只生成指定报告
python run_analysis.py --reports burnout_report comprehensive_report

# 跳过某些步骤
python run_analysis.py --all --skip toxicity_cache community_atmosphere

# 遇到错误继续执行
python run_analysis.py --all --continue-on-error

# 显示详细错误信息
python run_analysis.py --all --verbose
```

### 高级选项

```bash
# 自定义目录
python run_analysis.py --all \
  --data-dir /path/to/data \
  --graphs-dir /path/to/graphs \
  --output-dir /path/to/output

# 指定月份范围（构图时）
python run_analysis.py --analyzers monthly_graphs \
  --start-month 2024-01 \
  --end-month 2024-12

# Bus Factor 自定义选项
python run_analysis.py --analyzers bus_factor \
  --bus-factor-threshold 0.6 \
  --bus-factor-workers 16

# 人员流动跟踪时长
python run_analysis.py --analyzers personnel_flow \
  --personnel-flow-months 24
```

---

## 📁 输出目录结构

```
output/
├── monthly-graphs/                    # 月度图数据
│   ├── index.json                     # 图索引文件
│   └── <repo>/<type>/<month>.graphml  # GraphML 图文件
├── burnout-analysis/                  # 倦怠分析
│   ├── full_analysis.json
│   ├── summary.json
│   └── detailed_report.txt
├── newcomer-analysis/                 # 新人体验分析
│   ├── full_analysis.json
│   ├── summary.json
│   └── detailed_report.txt
├── community-atmosphere-analysis/     # 社区氛围分析
│   ├── toxicity.json                  # 毒性缓存
│   ├── full_analysis.json
│   ├── summary.json
│   └── detailed_report.txt
├── bus-factor-analysis/               # Bus Factor 分析
│   ├── full_analysis.json
│   ├── summary.json
│   └── detailed_report.txt
├── personnel-flow-all/                # 人员流动分析
│   ├── full_analysis.json
│   └── repo_yearly_status.txt
├── quality-risk/                      # 质量风险分析
│   ├── full_analysis.json
│   ├── summary.json
│   └── detailed_report.txt
├── actor-actor-structure/             # 网络结构分析
│   ├── full_analysis.json
│   └── detailed_report.txt
└── comprehensive_report.md            # 综合健康度报告
```

---

## 📊 分析指标说明

### 倦怠风险评分

评分范围 0-100，越高表示风险越大：
- 🟢 0-30：低风险，社区健康活跃
- 🟡 30-60：中等风险，需要关注
- 🔴 60-100：高风险，需要干预

### 新人体验评分

评分范围 0-100，越高表示体验越好：
- 🟢 70-100：优秀，新人容易融入
- 🟡 40-70：一般，存在改进空间
- 🔴 0-40：较差，新人融入困难

### 社区氛围评分

评分范围 0-100，越高表示氛围越好：
- 🟢 80-100：卓越，社区氛围非常健康
- 🟢 60-80：良好，整体良好
- 🟡 40-60：中等，需要关注局部问题
- 🔴 0-40：较差，存在明显问题

### Bus Factor 风险

Bus Factor 值表示达到总贡献量 50% 所需的最少贡献者数量：
- 🔴 1-2：极高风险，高度依赖个别人
- 🟡 3-5：中等风险，需要扩大贡献者群体
- 🟢 6+：低风险，贡献分布较均匀

---

## 🔧 配置说明

### 环境变量

在项目根目录创建 `.env` 文件：

```bash
# DeepSeek API（用于 LLM 评分，可选）
DEEPSEEK_API_KEY=your_api_key_here

# 或使用其他 LLM 提供商
OPENAI_API_KEY=your_api_key_here
```

### ToxiCR 配置

社区氛围分析的毒性检测功能需要 ToxiCR 项目支持。请确保 ToxiCR 与本项目同级放置：

```
parent_dir/
├── oss_graph_construction/  # 本项目
└── ToxiCR/                  # ToxiCR 项目
```

---

## 📚 详细文档

- [run_analysis.py 使用指南](docs/run_analysis_usage.md)
- [Bus Factor 分析文档](docs/bus_factor_analysis_documentation.md)
- [社区氛围分析文档](docs/community_atmosphere_analysis_documentation.md)

---

## 📄 License

MIT License
