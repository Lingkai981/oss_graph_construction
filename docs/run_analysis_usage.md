# run_analysis.py 使用说明（中文）

## 1. 脚本简介

`run_analysis.py` 是本项目的“一站式”命令行入口，用来统一调度：

- 月度图构建（构图）
- 各类健康度分析（倦怠、新人、社区氛围、Bus Factor、质量风险、网络结构、人员流动）
- 各分析对应的详细报告
- 最终综合健康报告

你可以用一条命令从“原始数据 → 构图 → 各分析 → 各类报告 → 综合报告”，也可以只选择其中一部分步骤单独运行。

---

## 2. 快速开始

### 2.1 一键运行完整流程

在项目根目录（与 `run_analysis.py` 同级）执行：

```bash
python run_analysis.py --all
```

含义：

- 按预设顺序依次执行 **全部分析器** 和 **全部报告生成器**：
  - 构图：monthly_graphs
  - 分析：burnout, newcomer, toxicity_cache（调用 ToxiCR 生成毒性缓存）, bus_factor, quality_risk, structure, personnel_flow, community_atmosphere
  - 报告：burnout_report, newcomer_report, bus_factor_report, atmosphere_report, quality_risk_report, structure_report, comprehensive_report
- 使用默认的数据路径和输出路径：
  - 数据目录：自动从 `data/filtered_union_2021_2025_daily`、`data/filtered`、`data/filtered_union_2024_fulldaily` 中“就近选取”，找不到则用 `data`。
  - 图目录：`output/monthly-graphs`
  - 各分析结果目录：挂在 `output/` 下面的子目录（见后文）。
  - 综合报告：默认写入 `output/comprehensive_report.md`。

> 建议第一次使用时直接运行 `--all`，确保所有依赖的中间结果都被正确生成。

### 2.2 只看有哪些可用任务

```bash
python run_analysis.py --list
```

- 显示所有可用的 **分析器关键字** 与 **报告关键字** 及其中文说明。
- 你在 `--analyzers`、`--reports`、`--skip` 中填写的名称，必须来自这份列表。

---

## 3. 执行流程总览

### 3.1 总体流程

脚本内部大致做了以下几件事：

1. **解析命令行参数**（由 `argparse` 完成）。
2. **根据参数选择要执行的任务**：
   - 若使用 `--all`：
     - 分析器顺序：
       - `monthly_graphs` → `burnout` → `newcomer` → `toxicity_cache` → `bus_factor` → `quality_risk` → `structure` → `personnel_flow` → `community_atmosphere`
     - 报告顺序：
       - `burnout_report` → `newcomer_report` → `bus_factor_report` → `atmosphere_report` → `quality_risk_report` → `structure_report` → `comprehensive_report`
   - 若使用 `--analyzers` / `--reports`：
     - 只执行你显式指定的任务（可配合 `--skip` 跳过部分）。
3. **解析并补全各种路径**：
   - 项目根目录、数据目录、图目录、输出根目录、各分析子目录、综合报告路径等，统统算好后放进一个上下文对象中统一管理。
4. **打印本次运行的“流水线配置”**：
   - 包括根目录、数据源、月度图目录、各分析输出路径、综合报告路径等。
5. **按顺序执行任务**：
   - 先执行选中的“分析器”列表，再执行选中的“报告”列表。
   - 每个任务开始时打印标题，结束后打印“✓ 完成任务 …”。
   - 若中途报错：
     - 默认立即中断；
     - 若加了 `--continue-on-error`，则记录错误并继续执行后续任务。

### 3.2 是否**总是**从构图开始？

- 当你使用 `--all` 时：
  - 会**固定**从 `monthly_graphs`（构图）开始，然后依次执行全部分析与报告。
- 当你只用 `--analyzers` 或 `--reports` 时：
  - **不会自动**为你加上构图步骤，也不会自动补齐上游分析任务；
  - 例如：
    - `python run_analysis.py --analyzers burnout` 不会自动执行 `monthly_graphs`，要求你已经有构图结果；
    - `python run_analysis.py --analyzers community_atmosphere` 不会自动执行构图或毒性缓存，需先有 `monthly_graphs` 和 `toxicity_cache` 结果；
    - `python run_analysis.py --reports burnout_report` 要求对应的 `burnout` 分析结果已存在，否则会因为缺少依赖文件而报错。

> 因此：
>
> - 希望“一条命令从头到尾全部跑完” → 用 `--all`。
> - 希望只重跑某一步（且你确认上游结果已存在） → 使用 `--analyzers` / `--reports` 精确指定。

---

## 4. 任务清单与依赖关系

### 4.1 分析器任务（ANALYZERS）

按默认顺序（`ANALYZER_ORDER`）：

1. `monthly_graphs` — 按月构建图数据快照（协作网络、仓库关系等）。
2. `burnout` — 执行维护者倦怠分析，输出全量与摘要 JSON。
3. `newcomer` — 执行新人融入与晋升路径分析，输出 full/summary JSON。
4. `toxicity_cache` — 调用同级目录的 ToxiCR 项目生成毒性缓存 `output/community-atmosphere-analysis/toxicity.json`，供社区氛围分析使用。
5. `bus_factor` — 执行 Bus Factor 风险分析，识别高度依赖少数核心开发者的模块/仓库。
6. `quality_risk` — 质量与权限滥用风险分析，识别潜在可疑行为或异常贡献模式。
7. `structure` — 协作网络结构分析，计算图直径、平均距离等结构指标。
8. `personnel_flow` — 人员流动分析，基于倦怠核心成员时间线统计离开后流向。
9. `community_atmosphere` — 执行社区氛围分析，可选仅对 top30 仓库分析，依赖构图与毒性缓存。

> 依赖关系（部分）：
>
> - 通常所有分析都依赖 **构图结果**（`monthly_graphs`）。
> - `personnel_flow` 明确依赖 `burnout` 产出的 `full_analysis.json`。
> - `community_atmosphere` 依赖 `monthly_graphs` 的图数据，以及 `toxicity_cache` 生成的 `output/community-atmosphere-analysis/toxicity.json`（若缺失会报错提示先执行毒性缓存）。

### 4.2 报告生成任务（REPORTS）

按默认顺序（`REPORT_ORDER`）：

1. `burnout_report` — 基于倦怠分析结果生成详细 markdown/txt 报告。
2. `newcomer_report` — 基于新人分析结果生成新人体验与晋升路径报告。
3. `bus_factor_report` — 基于 Bus Factor 分析的 full/summary 生成详细报告。
4. `atmosphere_report` — 基于社区氛围的 full/summary 生成说明文档。
5. `quality_risk_report` — 生成质量风险详细报告，解析可疑行为构成。
6. `structure_report` — 生成结构指标报告，对比网络结构随时间的变化。
7. `comprehensive_report` — 汇总上述多种分析/报告，输出综合健康报告。

> 报告任务均依赖于前置分析任务生成的 JSON 文件，若缺失会直接报错提示缺少哪个文件。

---

## 5. 命令行参数说明

### 5.1 **核心控制参数（必选其一）**

这三个参数中，**至少需要使用一个**，否则脚本会报错：

- `--all`
  - 类型：布尔开关
  - 作用：按固定顺序依次运行 **全部分析器** + **全部报告生成器**。
  - 适用场景：第一次完整跑全流程，或需要刷新所有结果与综合报告。

- `--analyzers 名称1 名称2 ...`
  - 类型：多值参数
  - 作用：**只运行指定的分析器**，名称来自 `--list` 显示的 ANALYZERS 表。
  - 示例：
    - `--analyzers monthly_graphs burnout`
  - 注意：
    - 不会自动补齐依赖，例如只写 `burnout` 不会自动执行 `monthly_graphs`。

- `--reports 名称1 名称2 ...`
  - 类型：多值参数
  - 作用：**只生成指定的报告**，名称来自 REPORTS 表。
  - 示例：
    - `--reports burnout_report newcomer_report`
  - 注意：
    - 要求对应分析结果已经存在，否则会因为缺少输入文件而失败。

> 你也可以同时使用 `--analyzers` 和 `--reports`，例如：
>
> ```bash
> python run_analysis.py --analyzers burnout newcomer --reports comprehensive_report
> ```
>
> 表示：只执行倦怠 + 新人分析，再生成综合报告（前提是其他需要的数据已存在或综合报告脚本可以容错）。

- `--skip 名称1 名称2 ...`
  - 类型：多值参数
  - 作用：在已经选定的任务集合中，**跳过**某些步骤。
  - 示例：
    - `python run_analysis.py --all --skip structure_report`
  - 注意：这里只是从执行队列里移除对应任务，不会自动处理依赖关系。

- `--list`
  - 类型：布尔开关
  - 作用：列出所有内置的分析器与报告关键字，然后退出，不真正执行分析。

### 5.2 路径相关参数

- `--root-dir`
  - 默认：脚本所在目录（推荐直接在项目根目录执行）。
  - 作用：指定项目根目录，其他默认路径会相对这个目录来推算。

- `--data-dir`
  - 默认：按顺序尝试：
    - `root_dir/data/filtered`
    - `root_dir/data/filtered_union_2024_fulldaily`
    - `root_dir/data/filtered_union_2021_2025_daily`
    - 若以上都不存在，则使用 `root_dir/data`。
  - 作用：提供 **用于构图的原始月度聚合数据** 所在目录。

- `--graphs-dir`
  - 默认：`root_dir/output/monthly-graphs`
  - 作用：存放构建出来的 **月度图数据**（actor-actor、actor-repo 等）。

- `--output-dir`
  - 默认：`root_dir/output`
  - 作用：所有分析结果与报告的 **根输出目录**。

各分析输出子目录（相对 `--output-dir`）：

- `--burnout-dir`
  - 默认：`burnout-analysis2`
  - 含义：倦怠分析输出子目录。

- `--newcomer-dir`
  - 默认：`newcomer-analysis`
  - 含义：新人分析输出子目录。

- `--atmosphere-dir`
  - 默认：`community-atmosphere-analysis`
  - 含义：社区氛围分析输出子目录。

- `--bus-factor-dir`
  - 默认：`bus-factor-analysis`
  - 含义：Bus Factor 分析输出子目录。

- `--quality-risk-dir`
  - 默认：`quality-risk`
  - 含义：质量风险分析输出子目录。

- `--structure-dir`
  - 默认：`actor-actor-structure`
  - 含义：协作网络结构分析输出子目录。

- `--personnel-flow-dir`
  - 默认：`personnel-flow-all`
  - 含义：人员流动分析输出子目录。

- `--comprehensive-report`
  - 默认：`output/comprehensive_report.md`
  - 含义：最终综合健康报告的输出路径。

### 5.3 构图与性能相关参数

- `--workers`
  - 默认：机器 CPU 核心数（至少为 1）。
  - 作用：构图和部分分析的**默认并行进程数**。

- `--graph-types 类型1 类型2 ...`
  - 类型：多值参数
  - 示例：`--graph-types actor-actor actor-repo`
  - 作用：指定构图时启用的图类型；若不指定则使用默认配置（由内部脚本决定）。

- `--start-month`
  - 格式：`YYYY-MM`
  - 含义：构图的起始月份（含）。

- `--end-month`
  - 格式：`YYYY-MM`
  - 含义：构图的结束月份（含）。

- `--serial`
  - 类型：布尔开关
  - 作用：强制按 **单进程** 模式构建月度图（忽略 `--workers`），便于调试。

- `--fresh-index`
  - 类型：布尔开关
  - 作用：构图完成后 **不与旧 index 合并**，而是直接覆盖旧索引。

### 5.4 Bus Factor 专用参数

仅在你执行 `bus_factor` 分析时生效：

- `--bus-factor-threshold`
  - 默认：`0.5`
  - 含义：Bus Factor 贡献占比阈值，用于判断“高度集中”的风险水平。

- `--bus-factor-weights`
  - 类型：字符串（文件路径）
  - 作用：提供一个 JSON 配置文件，自定义计算 Bus Factor 时不同边/事件的权重。
  - 脚本会在使用前检查该文件是否存在。

- `--bus-factor-workers`
  - 类型：整数
  - 默认：沿用 `--workers` 的值。
  - 作用：专门为 Bus Factor 分析设置的进程数。

- `--bus-factor-fresh`
  - 类型：布尔开关
  - 作用：禁用 Bus Factor 分析的 **断点续传** 功能，每次都从头重新计算。

### 5.5 其他分析相关参数

- `--atmosphere-top30`
  - 类型：布尔开关
  - 作用：社区氛围分析时，仅针对 `top30.json` 中列出的核心仓库进行分析。

- `--personnel-flow-months`
  - 默认：`12`
  - 含义：在人员流动分析中，成员“离开后”的追踪窗口大小（单位：月）。

### 5.6 运行行为控制

- `--continue-on-error`
  - 类型：布尔开关
  - 默认：关闭
  - 作用：当某个任务失败时：
    - 关闭（默认）：立即中断整个流水线；
    - 开启：记录错误并继续尝试执行后续任务。

- `--verbose`
  - 类型：布尔开关
  - 作用：当任务失败时，是否输出完整的 Python 堆栈信息，便于排查。

---

## 6. 常见使用场景与命令示例

### 场景 1：第一次完整跑全流程

**目标**：从原始数据开始，构图 + 所有分析 + 所有报告 + 综合报告。

```bash
python run_analysis.py --all
```

可选增强：利用多核并行提升速度，例如：

```bash
python run_analysis.py --all --workers 16
```

### 场景 2：仅重跑构图与倦怠分析

**目标**：

- 数据更新后，重新构建月度图；
- 只重跑倦怠分析；
- 不生成其他分析与报告。

```bash
python run_analysis.py \
  --analyzers monthly_graphs burnout \
  --workers 8
```

### 场景 3：在已有图的基础上，跑新人分析并生成报告

**前提**：

- `output/monthly-graphs` 中已经存在构图结果（你可能之前跑过 `--all` 或 `monthly_graphs`）。

**命令**：

```bash
python run_analysis.py \
  --analyzers newcomer \
  --reports newcomer_report
```

如果图数据不在默认位置，需要指定：

```bash
python run_analysis.py \
  --graphs-dir path/to/your/graphs \
  --output-dir path/to/output \
  --analyzers newcomer \
  --reports newcomer_report
```

### 场景 4：只生成若干报告，不重跑分析

**前提**：

- 对应分析结果已经存在于 `output/` 结构中。

**命令**：

```bash
python run_analysis.py \
  --reports burnout_report newcomer_report bus_factor_report
```

如果你只想在已有结果基础上刷新综合报告：

```bash
python run_analysis.py --reports comprehensive_report
```

### 场景 5：限定构图时间范围 + 自定义图类型

**目标**：

- 只对 2022-01 到 2023-12 期间的数据构图；
- 仅构建 actor-actor 和 actor-repo 图；
- 完整跑全流程。

```bash
python run_analysis.py \
  --all \
  --graph-types actor-actor actor-repo \
  --start-month 2022-01 \
  --end-month 2023-12
```

### 场景 6：Bus Factor 分析使用自定义权重

**前提**：

- 准备好一个 JSON 文件（例如 `bus_factor_weights.json`），定义不同事件或边的权重。

**命令**：

```bash
python run_analysis.py \
  --all \
  --bus-factor-weights bus_factor_weights.json \
  --bus-factor-threshold 0.6
```

或仅跑 Bus Factor 分析与报告：

```bash
python run_analysis.py \
  --analyzers monthly_graphs bus_factor \
  --reports bus_factor_report \
  --bus-factor-weights bus_factor_weights.json
```

### 场景 7：社区氛围只分析 top30 仓库

```bash
python run_analysis.py \
  --all \
  --atmosphere-top30
```

或只重跑社区氛围相关分析 + 报告：

```bash
python run_analysis.py \
  --analyzers community_atmosphere \
  --reports atmosphere_report \
  --atmosphere-top30

### 场景 8：仅生成/刷新毒性缓存（供社区氛围分析使用）

**目标**：在不同环境下运行 ToxiCR，生成社区氛围依赖的 `toxicity.json`，并将其写入本项目的 `output/community-atmosphere-analysis/`。

```bash
python run_analysis.py \
  --analyzers monthly_graphs toxicity_cache \
  --graphs-dir output/monthly-graphs \
  --output-dir output \
  --atmosphere-top30   # 若希望只针对 top30 仓库生成毒性缓存，可添加此开关
```

说明：

- `toxicity_cache` 会通过 `subprocess` 调用同级目录下的 `ToxiCR/analyze_oss_comments.py`，优先使用 ToxiCR 项目的虚拟环境（若存在），并实时输出日志到终端。
- 输出文件固定写到 `output/community-atmosphere-analysis/toxicity.json`，以匹配社区氛围分析器的硬编码读取路径。
```

---

## 7. 注意事项与建议

- **任务选择**：
  - `--all` 会自动保证正确的先后顺序（从构图到综合报告）。
  - 单独使用 `--analyzers`、`--reports` 时，你需要自行确认上游依赖是否已经存在；且分析器的实际执行顺序会按照代码内的固定顺序（忽略命令行排列）。
  - 社区氛围分析需确保：构图结果已存在、毒性缓存已生成（可通过 `toxicity_cache` 任务提前生成）。

- **路径一致性**：
  - 建议始终在项目根目录下运行命令，避免路径混乱；
  - 如果你改变了某些目录结构，记得用 `--root-dir`、`--data-dir`、`--graphs-dir`、`--output-dir` 等参数显式指定。

- **性能调优**：
  - 大部分 CPU 密集型任务都可以通过 `--workers` 提升速度；
  - 若遇到问题，可以加上 `--serial`（单进程构图）和 `--verbose`（打印堆栈）来排查。

- **错误处理**：
  - 默认遇到错误会中断，以避免产生不完整或混杂的数据；
  - 如果你希望“尽量跑完能跑的部分”，可以使用 `--continue-on-error`。

如需进一步了解每个分析器内部的具体算法和指标含义，可以查看 `src/analysis/` 目录下对应的 Python 文件及 `docs/` 里的专题文档。
