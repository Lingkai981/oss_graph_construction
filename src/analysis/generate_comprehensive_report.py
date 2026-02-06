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

# Summary files for scores
BURNOUT_SUMMARY = OUTPUT_DIR / "burnout-analysis/summary.json"
NEWCOMER_SUMMARY = OUTPUT_DIR / "newcomer-analysis/summary.json"
ATMOSPHERE_SUMMARY = OUTPUT_DIR / "community-atmosphere-analysis/full_analysis.json"

# Detailed files
BURNOUT_FULL = OUTPUT_DIR / "burnout-analysis/full_analysis.json"
NEWCOMER_FULL = OUTPUT_DIR / "newcomer-analysis/full_analysis.json"
ATMOSPHERE_FULL = OUTPUT_DIR / "community-atmosphere-analysis/full_analysis.json"
PERSONNEL_FILE = OUTPUT_DIR / "personnel-flow-all/repo_yearly_status.txt"
FINAL_REPORT_PATH = OUTPUT_DIR / "comprehensive_report.md"

# ==========================================
# Parsing Logic
# ==========================================

def load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_level(score: float) -> str:
    if score >= 85: return "🟢 卓越"
    if score >= 70: return "🟢 良好"
    if score >= 60: return "🟡 中等" # Adjustment for reality
    if score >= 50: return "🟡 及格"
    return "🔴 较差"

def normalize(values: Dict[str, float]) -> Dict[str, float]:
    if not values: return {}
    vals = list(values.values())
    min_v, max_v = min(vals), max(vals)
    if max_v == min_v: return {k: 100.0 for k in values}
    return {k: (v - min_v) / (max_v - min_v) * 100.0 for k, v in values.items()}

# --- Burnout ---
def load_burnout_scores_raw() -> Dict[str, float]:
    data = load_json(BURNOUT_SUMMARY)
    if isinstance(data, list):
        return {item["repo_name"]: float(item.get("burnout_score", 0)) for item in data}
    return {}

def load_burnout_monthly_full(repo: str, full_data: Dict) -> Dict[str, Dict]:
    # Need: total_events, node_count, core_actor_count, clustering_coefficient
    monthly = {}
    if repo not in full_data: return monthly
    
    metrics = full_data[repo].get("metrics", [])
    for m in metrics:
        month = m.get("month")
        if not month: continue
        monthly[month] = {
            "events": m.get("total_events", 0),
            "users": m.get("node_count", 0), # or unique_actors
            "core": m.get("core_actor_count", 0),
            "clust": round(m.get("clustering_coefficient", 0), 3)
        }
    return monthly

# --- Newcomer ---
def load_newcomer_scores_raw() -> Dict[str, float]:
    data = load_json(NEWCOMER_SUMMARY)
    if isinstance(data, list):
        return {item["repo_name"]: float(item.get("health_score", 0)) for item in data}
    return {}

def load_newcomer_monthly_full(repo: str, full_data: Dict) -> Dict[str, Dict]:
    # Need: newcomer_count, avg_dist, new_core_count, time_to_core, unreach_all, unreach_any
    # NOTE: The data is split across 3 monthly_summary arrays in full_analysis.json
    # We need to scan "newcomer_distance", "periphery_to_core", "core_reachability" sections
    
    monthly = defaultdict(lambda: {
        "count": 0, "dist": "-", 
        "new_core": 0, "time_core": "-",
        "unr_all": 0, "unr_any": 0
    })
    
    if repo not in full_data: return monthly
    
    repo_data = full_data[repo]
    
    # 1. Newcomer Distance & Count
    # Stored in: repo_data["newcomer_distance"]["monthly_summary"]? 
    # Actually based on grep:
    # "core_reachability": { "monthly_summary": [ {month, newcomers, avg_shortest_path_to_core...} ] }
    # This seems to have count and dist.
    
    cr = repo_data.get("core_reachability", {})
    ms_cr = cr.get("monthly_summary", [])
    if not ms_cr:
         # Try finding in root?
         pass

    # 2. Periphery to Core
    # "periphery_to_core": { "monthly_summary": [ {month, new_core_count, avg_months_to_core...} ] }
    ptc = repo_data.get("periphery_to_core", {})
    ms_ptc = ptc.get("monthly_summary", [])
    
    # 3. Unreachability
    # "core_reachability" -> "monthly_summary" has `unreachable_to_all/any_core_rate`? 
    # Check grep again:
    # "core_reachability": { "monthly_summary": [ {month, unreachable_to_all_core_rate...} ] } (Wait, grep showed specific rates in one of the monthly_summary blocks)
    # Actually, look at grep output for "total_actor_count ... unreachable_to_all_core_rate". That block seems like "core_reachability".
    
    # Merger logic
    # We will iterate all blocks found in repo_data values that have "monthly_summary"
    
    # Let's target specific keys to be safe
    
    # Block A: Newcomer Count & Dist & Unreachability (from core_reachability.monthly_summary usually)
    # Actually grep output showed:
    # { month="2021-01", newcomers=100, avg_shortest_path_to_core=3.07... } -> This is likely Newcomer Distance or CoreReachability?
    # Another block: { month="2021-01", total_actor_count=13, unreachable_to_all_core_rate=... } -> This is Core Reachability.
    
    # Let's try to just be robust and check expected keys in any monthly_summary list
    
    keys_to_check = ["core_reachability", "periphery_to_core", "newcomer_distance"]
    
    for k in keys_to_check:
        section = repo_data.get(k, {})
        ms = section.get("monthly_summary", [])
        if not ms: continue
        
        for record in ms:
            m = record.get("month")
            if not m: continue
            
            # Extract whatever is present
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
            elif "median_months_to_core" in record:
                 # fallback if average is missing? User asked for "晋核耗时" -> avg is good
                 pass
            
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
        if not metrics:
            scores[repo] = 0.0
            continue
            
        # Collect raw values with fallbacks
        vals_t = []
        vals_r = []
        vals_c = []
        
        for m in metrics:
            # Toxicity
            t = m.get("toxicity_ratio")
            if t is None: t = m.get("toxic_rate_0_5", 0)
            vals_t.append(t)
            
            # Response Time
            r = m.get("avg_response_time")
            if r is None: r = m.get("time_to_first_response_mean", 0)
            vals_r.append(r)
            
            # Closing Rate
            c = m.get("closing_rate")
            if c is None: c = m.get("change_request_closure_ratio", 0)
            vals_c.append(c)
        
        avg_t = sum(vals_t)/len(vals_t) if vals_t else 0
        avg_r = sum(vals_r)/len(vals_r) if vals_r else 0
        avg_c = sum(vals_c)/len(vals_c) if vals_c else 0
        
        # 1. Toxicity (40pts) - Lower is better
        # 0 -> 40pts; 0.05 -> 0pts
        s1 = max(0.0, 1.0 - avg_t/0.05) * 40.0
        
        # 2. Response Time (30pts) - Lower is better
        # 0h -> 30pts; 48h -> 15pts
        s2 = (1.0 / (1.0 + avg_r/48.0)) * 30.0
        
        # 3. Closing Rate (30pts) - Higher is better
        # 1.0 -> 30pts
        s3 = min(1.0, avg_c) * 30.0
        
        scores[repo] = s1 + s2 + s3
    return scores

def load_atmosphere_monthly_full(repo: str, full_data: Dict) -> Dict[str, Dict]:
    # Need: toxicity, response_time, closing_rate
    monthly = {}
    if repo not in full_data: return monthly
    
    metrics = full_data[repo].get("metrics", [])
    for m in metrics:
        month = m.get("month")
        if not month: continue
        
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
    # Supports both "净增 +10%" and "净 +10%" formats
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
    if not data: return 50.0
    
    # Sort by year keys to ensure chronological order
    sorted_years = sorted(data.keys())
    vals = [data[y] for y in sorted_years]
    n = len(vals)
    if n == 0: return 50.0
    
    # ---------------------------------------------------------
    # PART 1: Magnitude / Baseline (50%)
    # "Positive average definitely better than negative"
    # ---------------------------------------------------------
    avg_val = sum(vals) / n
    # Mapping: +25% avg -> 100pts, 0% -> 50pts, -25% avg -> 0pts
    score_avg = max(0.0, min(100.0, 50.0 + avg_val * 2.0))
    
    # ---------------------------------------------------------
    # PART 2: Trend & Dynamics (50% Shared)
    # Ratio 4:4:2 -> Slope(0.2) : Gap(0.2) : Stability(0.1)
    # ---------------------------------------------------------
    
    if n > 1:
        # A. Long Term Trend (Slope) - 20%
        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = avg_val
        numerator = sum((xs[i] - x_mean) * (vals[i] - y_mean) for i in range(n))
        denominator = sum((xs[i] - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0.0
        
        # Slope +5 per year -> +25 pts -> 75
        score_slope = max(0.0, min(100.0, 50.0 + slope * 5.0))
        
        # B. Recent Status (Gap) - 20%
        # "Gap between newest and oldest"
        gap = vals[-1] - vals[0]
        # Gap +20% -> +20pts -> 70
        score_gap = max(0.0, min(100.0, 50.0 + gap * 1.0))
        
        # C. Stability (Volatility) - 10%
        # "Volatility" -> Standard Deviation
        variance = sum((x - avg_val) ** 2 for x in vals) / (n - 1)
        std_dev = variance ** 0.5
        # StdDev 0 -> 100 pts
        # StdDev 20 -> 0 pts (Highly volatile)
        score_stab = max(0.0, 100.0 - std_dev * 5.0)
        
    else:
        # Single data point fallback
        score_slope = 50.0
        score_gap = 50.0
        score_stab = 100.0 # Perfectly stable if only one point
        
    
def calc_personnel_score_raw(data: Dict[str, float]) -> float:
    if not data: return 50.0
    
    # Sort by year keys to ensure chronological order
    sorted_years = sorted(data.keys())
    vals = [data[y] for y in sorted_years]
    n = len(vals)
    if n == 0: return 50.0
    
    # ---------------------------------------------------------
    # PART 1: Magnitude / Baseline (50%)
    # ---------------------------------------------------------
    avg_val = sum(vals) / n
    score_avg = max(0.0, min(100.0, 50.0 + avg_val * 2.0))
    
    # ---------------------------------------------------------
    # PART 2: Trend & Dynamics
    # ---------------------------------------------------------
    
    if n > 1:
        # A. Long Term Trend (Slope) - 20%
        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = avg_val
        numerator = sum((xs[i] - x_mean) * (vals[i] - y_mean) for i in range(n))
        denominator = sum((xs[i] - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0.0
        
        score_slope = max(0.0, min(100.0, 50.0 + slope * 5.0))
        
        # B. Recent Status (Gap) - 20%
        gap = vals[-1] - vals[0]
        score_gap = max(0.0, min(100.0, 50.0 + gap * 1.0))
        
        # C. Stability (Volatility) - 10%
        variance = sum((x - avg_val) ** 2 for x in vals) / (n - 1)
        std_dev = variance ** 0.5
        score_stab = max(0.0, 100.0 - std_dev * 5.0)
        
    else:
        score_slope = 50.0
        score_gap = 50.0
        score_stab = 100.0 
    
    # Final Weighted Sum
    # Avg(0.5) + Slope(0.2) + Gap(0.2) + Stab(0.1)
    final_score = (score_avg * 0.50) + \
                  (score_slope * 0.20) + \
                  (score_gap * 0.20) + \
                  (score_stab * 0.10)
                  
    return final_score

# ==========================================
# Statistic Utils
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
    # t-test for pearson correlation coefficient
    if abs(r) >= 1.0: return "***"
    if n <= 2: return ""
    
    t_stat = abs(r) * ((n - 2) ** 0.5) / ((1 - r ** 2) ** 0.5)
    
    # Approx critical values for df around 40-50
    # p < 0.001 ~ 3.5
    # p < 0.01 ~ 2.68
    # p < 0.05 ~ 2.01
    if t_stat > 3.5: return "***" # p < 0.001
    if t_stat > 2.68: return "**" # p < 0.01
    if t_stat > 2.01: return "*"  # p < 0.05
    return ""

# ==========================================
# Main
# ==========================================
                  
    return final_score

# ==========================================
# Main
# ==========================================

def main():
    print("⏳ Loading full datasets...")
    f_burn = load_json(BURNOUT_FULL)
    f_new = load_json(NEWCOMER_FULL)
    f_atm = load_json(ATMOSPHERE_FULL)
    d_flow = load_personnel_data()
    
    # Scores
    r_burn = load_burnout_scores_raw()
    r_new = load_newcomer_scores_raw()
    r_atm = load_atmosphere_scores_raw()
    r_per = {r: calc_personnel_score_raw(d_flow.get(r, {})) for r in 
             (set(r_burn)|set(r_new)|set(r_atm)|set(d_flow))}
    
    # Normalize
    n_burn = normalize(r_burn)
    n_new = normalize(r_new)
    n_atm = normalize(r_atm)
    n_per = normalize(r_per)
    
    # Build
    items = []
    all_repos = sorted(list(r_per.keys()))
    
    for repo in all_repos:
        # Total Score
        nb = n_burn.get(repo, 0)
        nn = n_new.get(repo, 0)
        na = n_atm.get(repo, 0)
        np_ = n_per.get(repo, 50)
        total = (nb+nn+na+np_)/4.0
        
        # Monthly details
        mb = load_burnout_monthly_full(repo, f_burn)
        mn = load_newcomer_monthly_full(repo, f_new)
        ma = load_atmosphere_monthly_full(repo, f_atm)
        
        months = sorted(set(mb.keys()) | set(mn.keys()) | set(ma.keys()), reverse=True)
        
        items.append({
            "repo": repo,
            "total": total,
            "norm": {"b": nb, "n": nn, "a": na, "p": np_},
            "raw": {"b": r_burn.get(repo,0), "n": r_new.get(repo,0), "a": r_atm.get(repo,0), "p": r_per.get(repo,50)},
            "flow": d_flow.get(repo, {}),
            "months": months,
            "data": {"b": mb, "n": mn, "a": ma}
        })
        
    items.sort(key=lambda x: x["total"], reverse=True)
    
    # Write Markdown
    md = []
    md.append("# 📈 OSS 项目全维度深度健康报告")
    md.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append("")
    md.append("本报告采用归一化评分 (Normalized)。详细月度指标覆盖倦怠、新人、氛围三大维度。")
    md.append("")
    
    # Econometric Analysis
    md.append("## 📈 计量分析 (Econometric Analysis)")
    
    # Collect data vectors
    vec_total = [x['total'] for x in items]
    vec_maint = [x['norm']['b'] for x in items]
    vec_ncomer = [x['norm']['n'] for x in items]
    vec_atmos = [x['norm']['a'] for x in items]
    vec_flow = [x['norm']['p'] for x in items]
    n_samples = len(vec_total)
    
    md.append(f"基于 **N={n_samples}** 个样本项目的 Pearson 相关性分析。")
    md.append("")
    
    # Helper to format cell
    def fmt_corr(v1, v2):
        r = pearson_r(v1, v2)
        sig = get_significance(r, n_samples)
        return f"{r:.3f}{sig}"

    md.append("| 变量 (Variables) | 总分 (Total) | 🧠 维护 | 🌱 新人 | 💬 氛围 | 🌊 流动 |")
    md.append("|---|---|---|---|---|---|")
    
    # Total Row
    row_total = f"| **总分 (Total)** | 1.000 | {fmt_corr(vec_total, vec_maint)} | {fmt_corr(vec_total, vec_ncomer)} | {fmt_corr(vec_total, vec_atmos)} | {fmt_corr(vec_total, vec_flow)} |"
    md.append(row_total)
    
    # Dimension Rows
    md.append(f"| **🧠 维护 (Maint)** | {fmt_corr(vec_maint, vec_total)} | 1.000 | {fmt_corr(vec_maint, vec_ncomer)} | {fmt_corr(vec_maint, vec_atmos)} | {fmt_corr(vec_maint, vec_flow)} |")
    md.append(f"| **🌱 新人 (Newcomer)** | {fmt_corr(vec_ncomer, vec_total)} | {fmt_corr(vec_ncomer, vec_maint)} | 1.000 | {fmt_corr(vec_ncomer, vec_atmos)} | {fmt_corr(vec_ncomer, vec_flow)} |")
    md.append(f"| **💬 氛围 (Atmos)** | {fmt_corr(vec_atmos, vec_total)} | {fmt_corr(vec_atmos, vec_maint)} | {fmt_corr(vec_atmos, vec_ncomer)} | 1.000 | {fmt_corr(vec_atmos, vec_flow)} |")
    md.append(f"| **🌊 流动 (Flow)** | {fmt_corr(vec_flow, vec_total)} | {fmt_corr(vec_flow, vec_maint)} | {fmt_corr(vec_flow, vec_ncomer)} | {fmt_corr(vec_flow, vec_atmos)} | 1.000 |")
    
    md.append("")
    md.append("**显著性水平 (Significance Levels):** `*** p<0.001`, `** p<0.01`, `* p<0.05`")
    md.append("")
    md.append("**💡 关键发现 (Key Findings):**")
    
    # Automated Insight Generation
    corrs = [
        ("维护 (Maint)", pearson_r(vec_total, vec_maint)),
        ("新人 (Newcomer)", pearson_r(vec_total, vec_ncomer)),
        ("氛围 (Atmos)", pearson_r(vec_total, vec_atmos)),
        ("流动 (Flow)", pearson_r(vec_total, vec_flow))
    ]
    # Sort by correlation strength
    corrs.sort(key=lambda x: x[1], reverse=True)
    
    top_factor = corrs[0]
    md.append(f"1. **{top_factor[0]}** 与总得分的相关性最高 (r={top_factor[1]:.3f})，说明它是拉开项目差距的关键因素。")
    
    # Check for trade-offs (negative correlation between dimensions)
    trade_off_found = False
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
            md.append(f"2. **{n1}** 与 **{n2}** 呈现负相关 (r={r_val:.3f})，暗示这两个指标之间可能存在权衡 (Trade-off)。")
            trade_off_found = True
            break # Just one example is enough
            
    if not trade_off_found:
        md.append("2. 各子维度之间普遍呈正相关或弱相关，说明健康的项目往往在各方面表现均衡。")

    md.append("")
    
    # Methodology Section
    md.append("## 📐 评分模型说明 (Scoring Methodology)")
    md.append("总分由四大维度构成 (**各占 25%**)，且所有分数均经过 Min-Max 归一化处理。")
    md.append("**⚠️ 统一标准**: 所有维度的评分 (Normalized Score) 均为 **越高越好 (Higher is Better)**。")
    md.append("")
    md.append("### 1. 🧠 维护健康度 (Project Maintenance)")
    md.append("> **数据来源**: Burnout Analysis Model (Pre-calculated)")
    md.append("*   **核心指标**: 事件总量 (Events)、贡献者规模 (Contributors)、核心开发者数 (Core Actors)、网络聚类系数 (Clustering)。")
    md.append("*   **评估逻辑**: 综合评估项目的活跃规模与核心维护团队的抗风险能力 (Burnout Resilience)。")
    md.append("")
    md.append("### 2. 🌱 新人友好度 (Newcomer Friendliness)")
    md.append("> **数据来源**: Newcomer Analysis Model (Pre-calculated)")
    md.append("*   **核心指标**: 新人以晋升核心圈的平均距离 (Distance)、所需时间 (Time to Core)、以及核心不可达率 (Unreachability)。")
    md.append("*   **评估逻辑 (关键)**: 系统自动将指标反向处理——")
    md.append("    *   **距离 (Distance)**: 越短 -> 分数越高")
    md.append("    *   **耗时 (Time)**: 越少 -> 分数越高")
    md.append("    *   **不可达率 (Unreachability)**: 越低 -> 分数越高")
    md.append("    *   *最终呈现为 Health Score (0-100)，分越高对新人越友好。*")
    md.append("")
    md.append("### 3. 💬 社区氛围 (Atmosphere)")
    md.append("*   **40% 毒性控制 (Toxicity)**: 评论中的负面/攻击性言论比例 (基准线 5% 以下)。")
    md.append("*   **30% 响应效率 (Response)**: Issue/PR 的首次响应时间 (基准线 48h 以内)。")
    md.append("*   **30% 问题解决 (Resolution)**: Issue/PR 的关闭率/解决率。")
    md.append("")
    md.append("### 4. 🌊 人员流动 (Personnel Flow)")
    md.append("*   **50% 长期均值 (Magnitude)**: 2021-2025 历年平均净增长率。")
    md.append("*   **20% 长期趋势 (Slope)**: 增长率的线性回归斜率 (考察是在变好还是变坏)。")
    md.append("*   **20% 近期演变 (Gap)**: 最新状态相对于初始状态的改变量 (Last - First)。")
    md.append("*   **10% 稳定性 (Stability)**: 增长的一致性 (正增长年份比例) 与 波动率 (标准差惩罚)。")
    md.append("")
    
    # 1. Summary
    md.append("## 🏆 综合排名")
    md.append("| 排名 | 项目 | 总分 | 等级 | 🧠 维护(N) | 🌱 新人(N) | 💬 氛围(N) | 🌊 流动(N) |")
    md.append("|---|---|---|---|---|---|---|---|")
    for i, item in enumerate(items, 1):
        n = item['norm']
        lvl = get_level(item['total']).split(" ")[0]
        # Valid anchor id: replace / with - or _
        repo_slug = item['repo'].replace("/", "_").replace(".", "_")
        md.append(f"| {i} | [{item['repo']}](#{repo_slug}) | **{item['total']:.1f}** | {lvl} | {n['b']:.1f} | {n['n']:.1f} | {n['a']:.1f} | {n['p']:.1f} |")
        
    md.append("")
    md.append("## 📊 详细数据分析")
    
    for i, item in enumerate(items, 1):
        repo = item['repo']
        repo_slug = repo.replace("/", "_").replace(".", "_")
        
        md.append(f"<div id='{repo_slug}'></div>")
        md.append(f"### {i}. {repo}")
        md.append(f"**Score**: {item['total']:.1f} ({get_level(item['total'])}) [⬆️ Top](#综合排名)")
        
        # Yearly Flow (Correct Order: 2021 -> 2025)
        md.append("\n**🌊 年度人员流动 (Yearly Flow)**")
        if item['flow']:
            md.append("| 年份 | 净增长 (Net) | 状态 |")
            md.append("|---|---|---|")
            yrs = sorted(item['flow'].keys()) # Default is ASC string sort "2021"..."2025"
            for y in yrs:
                val = item['flow'][y]
                st = "🟢 流入" if val > 0 else "🔴 流失"
                if val == 0: st = "⚪️ 平衡"
                if val > 15: st += " (磁铁)"
                elif val < -15: st += " (输血)"
                fmt = f"+{val:.1f}" if val > 0 else f"{val:.1f}"
                md.append(f"| {y} | **{fmt}%** | {st} |")
        else:
            md.append("*暂无年度数据*")
            
        # Monthly Detail (Complex Table)
        md.append("\n**📅 月度全维度指标详情**")
        md.append("<div style='width: 100%; overflow-x: auto;'>")
        md.append("")
        
        # Headers with category icons
        # 🧠 Burnout, 🌱 Newcomer, 💬 Atmosphere
        md.append("| Month | 🧠Events | 🧠Users | 🧠Core | 🧠Clust | 🌱New | 🌱Dist | 🌱NewCore | 🌱Time | 🌱UnrAll | 🌱UnrAny | 💬Tox | 💬Resp | 💬Close |")
        md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        
        # Sort months ASCENDING (Oldest -> Newest) as requested "从21年开始往下排" (2021 top, 2025 bottom)
        # item['months'] contains "YYYY-MM". sorting it works naturally for strings.
        # Previously we did reverse=True (Newest top).
        sorted_months = sorted(item["months"])
        
        for m in sorted_months:
             db = item["data"]["b"].get(m, {})
             dn = item["data"]["n"].get(m, {})
             da = item["data"]["a"].get(m, {})
             
             # Extract safely
             evt = db.get("events", "-")
             usr = db.get("users", "-")
             cor = db.get("core", "-")
             cst = db.get("clust", "-")
             
             new = dn.get("count", "-")
             dst = dn.get("dist", "-")
             ncr = dn.get("new_core", "-") # 0 is valid, so check existence? defaultdict returns 0
             tim = dn.get("time_core", "-")
             ual = dn.get("unr_all", "-")
             uany = dn.get("unr_any", "-")
             
             tox = da.get("tox", "-")
             rsp = da.get("resp", "-")
             cls = da.get("close", "-")
             
             md.append(f"| {m} | {evt} | {usr} | {cor} | {cst} | {new} | {dst} | {ncr} | {tim} | {ual} | {uany} | {tox} | {rsp} | {cls} |")
             
        md.append("")
        md.append("</div>") # Close scrollable div
        md.append("")
        md.append("---")
        
    print("💾 Saving Report...")
    with open(FINAL_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
        
    print(f"✅ Success: {FINAL_REPORT_PATH}")

if __name__ == "__main__":
    main()
