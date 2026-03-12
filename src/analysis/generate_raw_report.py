"""
Generate comprehensive report using RAW (non-normalized) scores.

Difference from generate_comprehensive_report.py:
- Skips the cross-repo Min-Max normalization step
- Uses each dimension's raw score directly (all nominally 0-100)
- Total score = simple average of 4 raw dimension scores
- Scores are absolute, not relative to other repos in the sample
"""

import json
import re
import math
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import defaultdict

# ==========================================
# Paths
# ==========================================
ROOT_DIR = Path("/Users/milk/Documents/ali2025/oss_graph_construction")
OUTPUT_DIR = ROOT_DIR / "output"

BURNOUT_SUMMARY = OUTPUT_DIR / "burnout-analysis/summary.json"
NEWCOMER_SUMMARY = OUTPUT_DIR / "newcomer-analysis/summary.json"
ATMOSPHERE_FULL = OUTPUT_DIR / "community-atmosphere-analysis/full_analysis.json"
PERSONNEL_FILE = OUTPUT_DIR / "personnel-flow-all/repo_yearly_status.txt"

BURNOUT_FULL = OUTPUT_DIR / "burnout-analysis/full_analysis.json"
NEWCOMER_FULL = OUTPUT_DIR / "newcomer-analysis/full_analysis.json"

# Output to a separate file
FINAL_REPORT_PATH = OUTPUT_DIR / "report" / "comprehensive_report_raw.md"

# ==========================================
# Shared utilities (identical to normalized version)
# ==========================================

def load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_level(score: float) -> str:
    if score >= 85: return "🟢 卓越"
    if score >= 70: return "🟢 良好"
    if score >= 60: return "🟡 中等"
    if score >= 50: return "🟡 及格"
    return "🔴 较差"

# ==========================================
# NO normalize() function — that's the whole point
# ==========================================

# ==========================================
# Two-layer scoring helpers (50% trend + 50% stability)
# Used to recalculate scores from existing full_analysis.json
# without re-running the analysis pipeline.
# ==========================================

EXCLUDE_MONTHS = {"2026-03"}   # 数据不完整的月份

def _lr_slope(values: List[float]) -> float:
    """线性回归斜率 (x=0..n-1)"""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0.0


def _volatility(values: List[float]) -> float:
    """月度环比变化率的标准差"""
    if len(values) < 2:
        return 0.0
    changes = []
    for i in range(1, len(values)):
        if values[i - 1] > 0:
            changes.append((values[i] - values[i - 1]) / values[i - 1])
    if len(changes) < 2:
        return 0.0
    mu = sum(changes) / len(changes)
    var = sum((c - mu) ** 2 for c in changes) / len(changes)
    return var ** 0.5


def _score_dim(values: List[float], max_score: float = 25.0, reverse: bool = False) -> float:
    """两层维度评分：50% 长期趋势(线性回归) + 50% 稳定性惩罚(波动率)"""
    n = len(values)
    if n < 2 or all(v == 0 for v in values):
        return 0.0
    first_nz = next((v for v in values if v > 0), 1)
    normalized = [v / first_nz for v in values]
    slope = _lr_slope(normalized)
    if reverse:
        trend_score = max(0.0, min(max_score * 0.5, slope * max_score * 5))
    else:
        trend_score = max(0.0, min(max_score * 0.5, -slope * max_score * 5))
    vol = _volatility(values)
    stab_score = max(0.0, min(max_score * 0.5, vol * max_score))
    return round(trend_score + stab_score, 2)


def _newcomer_dim(values: List[Optional[float]], max_score: float = 25.0) -> float:
    """Newcomer 两层维度评分 (increase_is_bad=True)"""
    clean = [v for v in values if v is not None]
    n = len(clean)
    if n < 2:
        return 0.0
    base = next((v for v in clean if v != 0), None)
    norm = clean[:] if base is None else [v / base for v in clean]
    slope = _lr_slope(norm)
    trend_score = max(0.0, min(max_score * 0.5, slope * max_score * 5))
    vol = _volatility(clean)
    stab_score = max(0.0, min(max_score * 0.5, vol * max_score))
    return round(trend_score + stab_score, 4)


# --- Burnout ---
def recalculate_burnout_scores(full_data: Dict) -> Dict[str, float]:
    """从 full_analysis.json 重新计算 burnout 健康分 (新公式, 排除不完整月份)"""
    scores = {}
    for repo, rd in full_data.items():
        metrics = [m for m in rd.get('metrics', []) if m.get('month') not in EXCLUDE_MONTHS]
        metrics.sort(key=lambda m: m['month'])
        n = len(metrics)
        if n < 2:
            scores[repo] = 50.0
            continue

        event_vals = [m.get('total_events', 0) for m in metrics]
        actor_vals = [m.get('unique_actors', 0) or m.get('node_count', 0) for m in metrics]
        clust_vals = [m.get('clustering_coefficient', 0) for m in metrics]

        # core stability → churn
        core_series = []
        for m in metrics:
            ca = m.get('core_actors', [])
            ids = set()
            if ca:
                for item in ca:
                    if isinstance(item, list) and len(item) >= 1:
                        ids.add(str(item[0]))
                    elif isinstance(item, (str, int)):
                        ids.add(str(item))
            core_series.append(ids)

        if core_series[0]:
            init = core_series[0]
            retention = [len(init & core_series[i]) / len(init) for i in range(n)]
        else:
            retention = [1.0] * n
        churn = [1 - r for r in retention]

        s_act = _score_dim(event_vals, 25.0, reverse=False)
        s_con = _score_dim(actor_vals, 25.0, reverse=False)
        s_cor = _score_dim(churn, 25.0, reverse=True)
        s_col = _score_dim(clust_vals, 25.0, reverse=False)

        risk = s_act + s_con + s_cor + s_col
        scores[repo] = round(max(0, 100 - risk), 2)
    return scores


def load_burnout_scores_raw() -> Dict[str, float]:
    """Fallback: read pre-computed scores from summary.json"""
    data = load_json(BURNOUT_SUMMARY)
    if isinstance(data, list):
        return {item["repo_name"]: float(item.get("burnout_score", 0)) for item in data}
    return {}

def load_burnout_monthly_full(repo: str, full_data: Dict) -> Dict[str, Dict]:
    monthly = {}
    if repo not in full_data: return monthly
    metrics = full_data[repo].get("metrics", [])
    for m in metrics:
        month = m.get("month")
        if not month or month in EXCLUDE_MONTHS: continue
        monthly[month] = {
            "events": m.get("total_events", 0),
            "users": m.get("node_count", 0),
            "core": m.get("core_actor_count", 0),
            "clust": round(m.get("clustering_coefficient", 0), 3)
        }
    return monthly

# --- Newcomer ---
def recalculate_newcomer_scores(full_data: Dict) -> Dict[str, float]:
    """从 full_analysis.json 重新计算 newcomer 健康分 (新公式, 排除不完整月份)"""
    scores = {}
    for repo, rd in full_data.items():
        nd_ms = rd.get('newcomer_distance', {}).get('monthly_summary', []) or []
        p2c_ms = rd.get('periphery_to_core', {}).get('monthly_summary', []) or []
        cr_ms = rd.get('core_reachability', {}).get('monthly_summary', []) or []

        def _filter(ms, key):
            return [m.get(key) for m in ms if m.get('month') not in EXCLUDE_MONTHS]

        s1 = _newcomer_dim(_filter(nd_ms, 'avg_shortest_path_to_core'), 25.0)
        s2 = _newcomer_dim(_filter(p2c_ms, 'avg_months_to_core'), 25.0)
        s3 = _newcomer_dim(_filter(cr_ms, 'unreachable_to_all_core_rate'), 25.0)
        s4 = _newcomer_dim(_filter(cr_ms, 'unreachable_to_any_core_rate'), 25.0)

        risk = s1 + s2 + s3 + s4
        scores[repo] = round(max(0, 100 - risk), 2)
    return scores


def load_newcomer_scores_raw() -> Dict[str, float]:
    """Fallback: read pre-computed scores from summary.json"""
    data = load_json(NEWCOMER_SUMMARY)
    if isinstance(data, list):
        return {item["repo_name"]: float(item.get("health_score", 0)) for item in data}
    return {}

def load_newcomer_monthly_full(repo: str, full_data: Dict) -> Dict[str, Dict]:
    monthly = defaultdict(lambda: {
        "count": 0, "dist": "-",
        "new_core": 0, "time_core": "-",
        "unr_all": 0, "unr_any": 0
    })
    if repo not in full_data: return monthly
    repo_data = full_data[repo]

    keys_to_check = ["core_reachability", "periphery_to_core", "newcomer_distance"]
    for k in keys_to_check:
        section = repo_data.get(k, {})
        ms = section.get("monthly_summary", [])
        if not ms: continue
        for record in ms:
            m = record.get("month")
            if not m or m in EXCLUDE_MONTHS: continue
            if "newcomers" in record:
                monthly[m]["count"] = record["newcomers"]
            if "avg_shortest_path_to_core" in record:
                val = record["avg_shortest_path_to_core"]
                if val is not None: monthly[m]["dist"] = round(val, 2)
            if "new_core_count" in record:
                monthly[m]["new_core"] = record["new_core_count"]
            if "avg_months_to_core" in record:
                val = record["avg_months_to_core"]
                if val is not None: monthly[m]["time_core"] = round(val, 1)
            if "unreachable_to_all_core_rate" in record:
                val = record["unreachable_to_all_core_rate"]
                if val is not None: monthly[m]["unr_all"] = f"{round(val*100, 1)}%"
            if "unreachable_to_any_core_rate" in record:
                val = record["unreachable_to_any_core_rate"]
                if val is not None: monthly[m]["unr_any"] = f"{round(val*100, 1)}%"
    return monthly

# --- Atmosphere ---
def load_atmosphere_scores_raw() -> Dict[str, float]:
    full = load_json(ATMOSPHERE_FULL)
    scores = {}
    for repo, data in full.items():
        metrics = data.get("metrics", [])
        metrics = [m for m in metrics if m.get('month') not in EXCLUDE_MONTHS]
        if not metrics:
            scores[repo] = 0.0
            continue

        vals_t, vals_r, vals_c = [], [], []
        for m in metrics:
            t = m.get("toxicity_ratio")
            if t is None: t = m.get("toxic_rate_0_5", 0)
            vals_t.append(t)
            r = m.get("avg_response_time")
            if r is None: r = m.get("time_to_first_response_mean", 0)
            vals_r.append(r)
            c = m.get("closing_rate")
            if c is None: c = m.get("change_request_closure_ratio", 0)
            vals_c.append(c)

        avg_t = sum(vals_t)/len(vals_t) if vals_t else 0
        avg_r = sum(vals_r)/len(vals_r) if vals_r else 0
        avg_c = sum(vals_c)/len(vals_c) if vals_c else 0

        W = 100.0 / 3.0  # 三项各占 1/3
        s1 = max(0.0, 1.0 - avg_t/0.05) * W
        s2 = (1.0 / (1.0 + avg_r/48.0)) * W
        s3 = min(1.0, avg_c) * W
        scores[repo] = s1 + s2 + s3
    return scores

def load_atmosphere_monthly_full(repo: str, full_data: Dict) -> Dict[str, Dict]:
    monthly = {}
    if repo not in full_data: return monthly
    metrics = full_data[repo].get("metrics", [])
    for m in metrics:
        month = m.get("month")
        if not month or month in EXCLUDE_MONTHS: continue
        tox = m.get("toxicity_ratio")
        if tox is None: tox = m.get("toxic_rate_0_5", 0)
        resp = m.get("avg_response_time")
        if resp is None: resp = m.get("time_to_first_response_mean", 0)
        close = m.get("closing_rate")
        if close is None: close = m.get("change_request_closure_ratio", 0)
        monthly[month] = {
            "tox": round(tox, 4),
            "resp": round(resp, 1),
            "close": f"{round(close*100, 1)}%"
        }
    return monthly

# --- Personnel ---
def load_personnel_data() -> Dict[str, Dict[str, float]]:
    data = defaultdict(dict)
    if not PERSONNEL_FILE.exists(): return data
    with open(PERSONNEL_FILE, "r") as f: lines = f.readlines()
    yr_pat = re.compile(r"\[\s*(\d{4})")
    repo_pat = re.compile(r"^\s+([a-zA-Z0-9\-\_\./]+)\s+:\s+净(?:[增流])?\s*([+\-]?\d+\.?\d*)%")
    curr_yr = None
    for line in lines:
        ym = yr_pat.search(line)
        if ym:
            curr_yr = ym.group(1)
            continue
        rm = repo_pat.search(line)
        if rm and curr_yr:
            repo = rm.group(1).strip()
            val = float(rm.group(2))
            data[repo][curr_yr] = val
    return data

def calc_personnel_score_raw(data: Dict[str, float]) -> float:
    """人员流动评分 (0-100)
    
    PART 1  长期均值 (50 分): 历年平均净增长率，以 0 为中轴 (50 分)
    PART 2  时序变化 (50 分): 趋势斜率 (25 分) + 稳定性 (25 分)
    """
    if not data: return 50.0
    sorted_years = sorted(data.keys())
    vals = [data[y] for y in sorted_years]
    n = len(vals)
    if n == 0: return 50.0

    # Cap first-year extreme values to 30% to avoid data pollution
    vals = [min(v, 30.0) for v in vals]

    # ---- PART 1: 长期均值 (50 分) ----
    mean_rate = sum(vals) / n
    score_mean = max(0.0, min(100.0, 50.0 + mean_rate * 2.5))

    if n > 1:
        # ---- PART 2A: 趋势斜率 (25 分) ----
        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = mean_rate
        numerator = sum((xs[i] - x_mean) * (vals[i] - y_mean) for i in range(n))
        denominator = sum((xs[i] - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0.0
        score_slope = max(0.0, min(100.0, 50.0 + slope * 5.0))

        # ---- PART 2B: 稳定性 (25 分) ----
        std_dev = (sum((v - mean_rate) ** 2 for v in vals) / n) ** 0.5
        score_stab = max(0.0, min(100.0, 100.0 - std_dev * 2.0))
    else:
        score_slope = 50.0
        score_stab = 100.0

    # Final: Mean(0.5) + Slope(0.25) + Stab(0.25)
    final_score = score_mean * 0.50 + score_slope * 0.25 + score_stab * 0.25
    return final_score

# ==========================================
# Statistics
# ==========================================

def mean(data: List[float]) -> float:
    return sum(data) / len(data) if data else 0.0

def pearson_r(x: List[float], y: List[float]) -> float:
    n = len(x)
    if n < 2 or n != len(y): return 0.0
    mu_x = mean(x)
    mu_y = mean(y)
    numerator = sum((xi - mu_x) * (yi - mu_y) for xi, yi in zip(x, y))
    sum_sq_x = sum((xi - mu_x) ** 2 for xi in x)
    sum_sq_y = sum((yi - mu_y) ** 2 for yi in y)
    denominator = (sum_sq_x * sum_sq_y) ** 0.5
    if denominator == 0: return 0.0
    return numerator / denominator

def get_significance(r: float, n: int) -> str:
    if abs(r) >= 1.0: return "***"
    if n <= 2: return ""
    t_stat = abs(r) * ((n - 2) ** 0.5) / ((1 - r ** 2) ** 0.5)
    if t_stat > 3.5: return "***"
    if t_stat > 2.68: return "**"
    if t_stat > 2.01: return "*"
    return ""

# ==========================================
# Main — RAW version (no cross-repo normalization)
# ==========================================

def main():
    print("⏳ Loading full datasets (RAW mode)...")
    f_burn = load_json(BURNOUT_FULL)
    f_new = load_json(NEWCOMER_FULL)
    f_atm = load_json(ATMOSPHERE_FULL)
    d_flow = load_personnel_data()

    # Recalculate burnout & newcomer scores from full data (new formula, excl 2026-03)
    print("🔄 Recalculating burnout scores (50% trend + 50% stability, excl 2026-03)...")
    r_burn = recalculate_burnout_scores(f_burn)
    print("🔄 Recalculating newcomer scores (50% trend + 50% stability, excl 2026-03)...")
    r_new = recalculate_newcomer_scores(f_new)
    r_atm = load_atmosphere_scores_raw()
    r_per = {r: calc_personnel_score_raw(d_flow.get(r, {}))
             for r in (set(r_burn)|set(r_new)|set(r_atm)|set(d_flow))}

    # ---- Distribution stats for methodology section ----
    def dist_stats(scores: Dict[str, float]):
        vals = list(scores.values())
        if not vals: return {}
        vals_sorted = sorted(vals)
        return {
            "min": vals_sorted[0],
            "max": vals_sorted[-1],
            "mean": sum(vals)/len(vals),
            "median": vals_sorted[len(vals)//2],
            "std": (sum((v - sum(vals)/len(vals))**2 for v in vals) / len(vals)) ** 0.5
        }

    stats_burn = dist_stats(r_burn)
    stats_new = dist_stats(r_new)
    stats_atm = dist_stats(r_atm)
    stats_per = dist_stats(r_per)

    # Build items — use raw scores directly
    items = []
    all_repos = sorted(list(r_per.keys()))
    for repo in all_repos:
        rb = r_burn.get(repo, 0)
        rn = r_new.get(repo, 0)
        ra = r_atm.get(repo, 0)
        rp = r_per.get(repo, 50)
        total = (rb + rn + ra + rp) / 4.0

        mb = load_burnout_monthly_full(repo, f_burn)
        mn = load_newcomer_monthly_full(repo, f_new)
        ma = load_atmosphere_monthly_full(repo, f_atm)
        months = sorted(set(mb.keys()) | set(mn.keys()) | set(ma.keys()), reverse=True)

        items.append({
            "repo": repo,
            "total": total,
            "raw": {"b": rb, "n": rn, "a": ra, "p": rp},
            "flow": d_flow.get(repo, {}),
            "months": months,
            "data": {"b": mb, "n": mn, "a": ma}
        })

    items.sort(key=lambda x: x["total"], reverse=True)

    # ==========================================
    # Write Markdown
    # ==========================================
    md = []
    md.append("# 📈 OSS 项目全维度深度健康报告（原始分版本）")
    md.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append("")
    md.append("本报告采用 **原始评分 (Raw Scores)**，未经跨项目 Min-Max 归一化。")
    md.append("每个维度的分数反映项目的**绝对健康水平**，不受其他项目的最高/最低分影响。")
    md.append("")
    md.append("> **与归一化版本的区别**：归一化版本中，每个维度的最高分被拉至 100、最低分被压至 0，")
    md.append("> 适合看**相对排位**；本报告的原始分保留了真实分布，适合看**绝对水平**。")
    md.append("> 两个版本的排名可能不同，因为各维度的原始分布范围不一致。")
    md.append("")

    # ---- Econometric Analysis ----
    md.append("## 📈 计量分析 (Econometric Analysis)")

    vec_total = [x['total'] for x in items]
    vec_maint = [x['raw']['b'] for x in items]
    vec_ncomer = [x['raw']['n'] for x in items]
    vec_atmos = [x['raw']['a'] for x in items]
    vec_flow = [x['raw']['p'] for x in items]
    n_samples = len(vec_total)

    md.append(f"基于 **N={n_samples}** 个样本项目的 Pearson 相关性分析（原始分）。")
    md.append("")

    def fmt_corr(v1, v2):
        r = pearson_r(v1, v2)
        sig = get_significance(r, n_samples)
        return f"{r:.3f}{sig}"

    md.append("| 变量 (Variables) | 总分 (Total) | 🧠 维护 | 🌱 新人 | 💬 氛围 | 🌊 流动 |")
    md.append("|---|---|---|---|---|---|")
    md.append(f"| **总分 (Total)** | 1.000 | {fmt_corr(vec_total, vec_maint)} | {fmt_corr(vec_total, vec_ncomer)} | {fmt_corr(vec_total, vec_atmos)} | {fmt_corr(vec_total, vec_flow)} |")
    md.append(f"| **🧠 维护 (Maint)** | {fmt_corr(vec_maint, vec_total)} | 1.000 | {fmt_corr(vec_maint, vec_ncomer)} | {fmt_corr(vec_maint, vec_atmos)} | {fmt_corr(vec_maint, vec_flow)} |")
    md.append(f"| **🌱 新人 (Newcomer)** | {fmt_corr(vec_ncomer, vec_total)} | {fmt_corr(vec_ncomer, vec_maint)} | 1.000 | {fmt_corr(vec_ncomer, vec_atmos)} | {fmt_corr(vec_ncomer, vec_flow)} |")
    md.append(f"| **💬 氛围 (Atmos)** | {fmt_corr(vec_atmos, vec_total)} | {fmt_corr(vec_atmos, vec_maint)} | {fmt_corr(vec_atmos, vec_ncomer)} | 1.000 | {fmt_corr(vec_atmos, vec_flow)} |")
    md.append(f"| **🌊 流动 (Flow)** | {fmt_corr(vec_flow, vec_total)} | {fmt_corr(vec_flow, vec_maint)} | {fmt_corr(vec_flow, vec_ncomer)} | {fmt_corr(vec_flow, vec_atmos)} | 1.000 |")
    md.append("")
    md.append("**显著性水平:** `*** p<0.001`, `** p<0.01`, `* p<0.05`")
    md.append("")

    # ---- Automated Insights ----
    corrs = [
        ("维护 (Maint)", pearson_r(vec_total, vec_maint)),
        ("新人 (Newcomer)", pearson_r(vec_total, vec_ncomer)),
        ("氛围 (Atmos)", pearson_r(vec_total, vec_atmos)),
        ("流动 (Flow)", pearson_r(vec_total, vec_flow))
    ]
    corrs.sort(key=lambda x: x[1], reverse=True)
    md.append("**💡 关键发现 (Raw Score版):**")
    md.append(f"1. **{corrs[0][0]}** 与总得分的相关性最高 (r={corrs[0][1]:.3f})。")

    dim_pairs = [
        ("维护", "新人", vec_maint, vec_ncomer),
        ("维护", "氛围", vec_maint, vec_atmos),
        ("维护", "流动", vec_maint, vec_flow),
        ("新人", "氛围", vec_ncomer, vec_atmos),
        ("新人", "流动", vec_ncomer, vec_flow),
        ("氛围", "流动", vec_atmos, vec_flow)
    ]
    for n1, n2, v1, v2 in dim_pairs:
        r_val = pearson_r(v1, v2)
        if r_val < -0.1:
            md.append(f"2. **{n1}** 与 **{n2}** 呈现负相关 (r={r_val:.3f})，暗示权衡关系。")
            break
    else:
        md.append("2. 各子维度之间普遍呈正相关或弱相关。")
    md.append("")

    # ---- Raw Score Distribution ----
    md.append("## 📊 原始分分布统计")
    md.append("")
    md.append("展示各维度原始分的实际分布范围，帮助理解归一化前的数据特征。")
    md.append("")
    md.append("| 维度 | 最小值 | 最大值 | 均值 | 中位数 | 标准差 | 实际范围宽度 |")
    md.append("|---|---|---|---|---|---|---|")
    for name, st in [("🧠 维护", stats_burn), ("🌱 新人", stats_new),
                      ("💬 氛围", stats_atm), ("🌊 流动", stats_per)]:
        width = st['max'] - st['min']
        md.append(f"| {name} | {st['min']:.1f} | {st['max']:.1f} | {st['mean']:.1f} | {st['median']:.1f} | {st['std']:.1f} | {width:.1f} |")
    md.append("")
    md.append("> **解读**：范围宽度差异越大，说明归一化对该维度的拉伸/压缩越明显。")
    md.append("> 例如，若「维护」的原始范围是 [5, 95]（宽度 90），而「氛围」是 [60, 90]（宽度 30），")
    md.append("> 归一化后「氛围」的微小差异会被放大 3 倍。这正是原始分版本要解决的信息损失问题。")
    md.append("")

    # ---- Methodology ----
    md.append("## 📐 评分模型说明")
    md.append("总分由四大维度构成 (**各占 25%**)。")
    md.append("**⚠️ 本报告不做跨项目归一化**：各维度的原始分直接参与加权平均。")
    md.append("")
    md.append("### 各维度原始分含义")
    md.append("| 维度 | 原始分来源 | 名义范围 | 含义 |")
    md.append("|---|---|---|---|")
    md.append("| 🧠 维护健康度 | 长期趋势(50%)+稳定性(50%)，4维度各25分 | 0-100 | 100 = 毫无倦怠风险，0 = 极端倦怠 |")
    md.append("| 🌱 新人友好度 | 长期趋势(50%)+稳定性(50%)，4指标各25分 | 0-100 | 100 = 极其友好，0 = 完全封闭 |")
    md.append("| 💬 社区氛围 | 毒性(1/3) + 响应(1/3) + 关闭率(1/3) | 0-100 | 100 = 完美氛围 |")
    md.append("| 🌊 人员流动 | 长期均值(50%) + 趋势斜率(25%) + 稳定性(25%) | 0-100 | 100 = 持续强劲净流入 |")
    md.append("")

    # ---- Rankings ----
    md.append("## 🏆 综合排名（原始分）")
    md.append("| 排名 | 项目 | 总分 | 等级 | 🧠 维护(R) | 🌱 新人(R) | 💬 氛围(R) | 🌊 流动(R) |")
    md.append("|---|---|---|---|---|---|---|---|")
    for i, item in enumerate(items, 1):
        r = item['raw']
        lvl = get_level(item['total']).split(" ")[0]
        repo_slug = item['repo'].replace("/", "_").replace(".", "_")
        md.append(f"| {i} | [{item['repo']}](#{repo_slug}) | **{item['total']:.1f}** | {lvl} | {r['b']:.1f} | {r['n']:.1f} | {r['a']:.1f} | {r['p']:.1f} |")

    md.append("")

    # ---- Detailed per-repo sections ----
    md.append("## 📊 详细数据分析")

    for i, item in enumerate(items, 1):
        repo = item['repo']
        repo_slug = repo.replace("/", "_").replace(".", "_")

        md.append(f"<div id='{repo_slug}'></div>")
        md.append(f"### {i}. {repo}")
        md.append(f"**Score (Raw)**: {item['total']:.1f} ({get_level(item['total'])}) [⬆️ Top](#综合排名原始分)")

        # Yearly Flow
        md.append("\n**🌊 年度人员流动 (Yearly Flow)**")
        if item['flow']:
            md.append("| 年份 | 净增长 (Net) | 状态 |")
            md.append("|---|---|---|")
            for y in sorted(item['flow'].keys()):
                val = item['flow'][y]
                st = "🟢 流入" if val > 0 else "🔴 流失"
                if val == 0: st = "⚪️ 平衡"
                if val > 15: st += " (磁铁)"
                elif val < -15: st += " (输血)"
                fmt = f"+{val:.1f}" if val > 0 else f"{val:.1f}"
                md.append(f"| {y} | **{fmt}%** | {st} |")
        else:
            md.append("*暂无年度数据*")

        # Monthly Detail
        md.append("\n**📅 月度全维度指标详情**")
        md.append("<div style='width: 100%; overflow-x: auto;'>")
        md.append("")
        md.append("| Month | 🧠Events | 🧠Users | 🧠Core | 🧠Clust | 🌱New | 🌱Dist | 🌱NewCore | 🌱Time | 🌱UnrAll | 🌱UnrAny | 💬Tox | 💬Resp | 💬Close |")
        md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")

        sorted_months = sorted(item["months"])
        for m in sorted_months:
            db = item["data"]["b"].get(m, {})
            dn = item["data"]["n"].get(m, {})
            da = item["data"]["a"].get(m, {})

            evt = db.get("events", "-")
            usr = db.get("users", "-")
            cor = db.get("core", "-")
            cst = db.get("clust", "-")

            new = dn.get("count", "-")
            dst = dn.get("dist", "-")
            ncr = dn.get("new_core", "-")
            tim = dn.get("time_core", "-")
            ual = dn.get("unr_all", "-")
            uany = dn.get("unr_any", "-")

            tox = da.get("tox", "-")
            rsp = da.get("resp", "-")
            cls = da.get("close", "-")

            md.append(f"| {m} | {evt} | {usr} | {cor} | {cst} | {new} | {dst} | {ncr} | {tim} | {ual} | {uany} | {tox} | {rsp} | {cls} |")

        md.append("")
        md.append("</div>")
        md.append("")
        md.append("---")

    # ---- Save ----
    FINAL_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("💾 Saving Raw Report...")
    with open(FINAL_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"✅ Success: {FINAL_REPORT_PATH}")
    print(f"   {len(items)} repos, {sum(len(x['months']) for x in items)} monthly records")

    # ---- Print summary comparison ----
    print("\n📊 原始分分布统计：")
    for name, st in [("维护", stats_burn), ("新人", stats_new),
                      ("氛围", stats_atm), ("流动", stats_per)]:
        print(f"  {name}: [{st['min']:.1f}, {st['max']:.1f}], mean={st['mean']:.1f}, std={st['std']:.1f}")

if __name__ == "__main__":
    main()
