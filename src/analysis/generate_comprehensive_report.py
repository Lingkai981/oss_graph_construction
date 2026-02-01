
import json
import re
import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict

# ==========================================
# Paths
# ==========================================
ROOT_DIR = Path("/Users/milk/Documents/ali2025/oss_graph_construction")
OUTPUT_DIR = ROOT_DIR / "output"

# Summary files for scores
BURNOUT_SUMMARY = OUTPUT_DIR / "burnout-analysis2/summary.json"
NEWCOMER_SUMMARY = OUTPUT_DIR / "newcomer-analysis/summary.json"
ATMOSPHERE_SUMMARY = OUTPUT_DIR / "community-atmosphere-analysis/full_analysis.json"

# Detailed files for monthly data
BURNOUT_FULL = OUTPUT_DIR / "burnout-analysis2/full_analysis.json"
NEWCOMER_FULL = OUTPUT_DIR / "newcomer-analysis/full_analysis.json"
ATMOSPHERE_FULL = OUTPUT_DIR / "community-atmosphere-analysis/full_analysis.json"

PERSONNEL_FILE = OUTPUT_DIR / "personnel-flow-all/repo_yearly_status.txt"
FINAL_REPORT_PATH = OUTPUT_DIR / "comprehensive_report.md"

# ==========================================
# Data Loading & Parsing
# ==========================================

def load_json(path: Path) -> Any:
    if not path.exists():
        print(f"⚠️ Warning: {path} not found.")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_level(score: float) -> str:
    if score >= 85: return "🟢 卓越"
    if score >= 70: return "🟢 良好"
    if score >= 50: return "🟡 中等"
    return "🔴 较差"

def normalize(values: Dict[str, float]) -> Dict[str, float]:
    """Min-Max normalization to 0-100 range"""
    if not values: return {}
    
    vals = list(values.values())
    min_v = min(vals)
    max_v = max(vals)
    
    if max_v == min_v:
        return {k: 100.0 for k in values} # All equal -> all 100
        
    norm = {}
    for k, v in values.items():
        n_val = (v - min_v) / (max_v - min_v) * 100.0
        norm[k] = n_val
    return norm

# --- 1. Burnout Parsing ---

def load_burnout_scores_raw() -> Dict[str, float]:
    data = load_json(BURNOUT_SUMMARY)
    if isinstance(data, list):
        return {item["repo_name"]: float(item.get("burnout_score", 0)) for item in data}
    return {}

def load_burnout_monthly(repo: str, full_data: Dict) -> Dict[str, Dict]:
    monthly = {}
    # full_data keys might be 'owner/repo'
    if repo not in full_data: 
        # try searching? No, should be exact.
        return monthly
    
    metrics = full_data[repo].get("metrics", [])
    for m in metrics:
        month = m.get("month")
        core_count = m.get("core_actor_count", 0)
        events = m.get("total_events", 0)
        load = events / core_count if core_count > 0 else 0
        
        monthly[month] = {
            "core": core_count,
            "load": round(load, 1)
        }
    return monthly

# --- 2. Newcomer Parsing ---

def load_newcomer_scores_raw() -> Dict[str, float]:
    data = load_json(NEWCOMER_SUMMARY)
    if isinstance(data, list):
        return {item["repo_name"]: float(item.get("health_score", 0)) for item in data}
    return {}

def load_newcomer_monthly(repo: str, full_data: Dict) -> Dict[str, Dict]:
    monthly = defaultdict(lambda: {"count": 0, "dist_sum": 0.0})
    
    if repo not in full_data: return monthly
    
    repo_data = full_data[repo]
    dist_data = repo_data.get("newcomer_distance", {})
    records = dist_data.get("records", [])
    
    for r in records:
        month = r.get("join_month")
        dist = r.get("avg_shortest_path_to_core")
        
        if month:
            monthly[month]["count"] += 1
            if dist is not None:
                monthly[month]["dist_sum"] += dist
                
    result = {}
    for m, v in monthly.items():
        avg_dist = v["dist_sum"] / v["count"] if v["count"] > 0 else 0
        result[m] = {
            "count": v["count"],
            "dist": round(avg_dist, 2)
        }
    return result

# --- 3. Atmosphere Parsing ---

def load_atmosphere_scores_raw() -> Dict[str, float]:
    full_data = load_json(ATMOSPHERE_FULL)
    scores = {}
    
    for repo, content in full_data.items():
        metrics = content.get("metrics", [])
        if not metrics:
            scores[repo] = 0.0
            continue
            
        tox_values = [m.get("toxicity_ratio", m.get("toxic_rate_0_5", 0.0)) for m in metrics]
        resp_values = [m.get("avg_response_time", m.get("time_to_first_response_mean", 0.0)) for m in metrics]
        close_values = [m.get("closing_rate", m.get("change_request_closure_ratio", 0.0)) for m in metrics]
        
        # Handle Nones
        tox_values = [v if v is not None else 0.0 for v in tox_values]
        resp_values = [v if v is not None else 0.0 for v in resp_values]
        close_values = [v if v is not None else 0.0 for v in close_values]
        
        avg_tox = sum(tox_values) / len(tox_values) if tox_values else 0
        avg_resp = sum(resp_values) / len(resp_values) if resp_values else 0
        avg_close = sum(close_values) / len(close_values) if close_values else 0
        
        s1 = max(0.0, 1.0 - avg_tox / 0.05) * 100 * 0.4
        s2 = (100.0 / (1.0 + avg_resp / 48.0)) * 0.3
        s3 = min(100.0, avg_close * 100.0) * 0.3 # close is usually 0.0-1.0
        
        scores[repo] = s1 + s2 + s3
    return scores

def load_atmosphere_monthly(repo: str, full_data: Dict) -> Dict[str, Dict]:
    monthly = {}
    if repo not in full_data: return monthly
    
    metrics = full_data[repo].get("metrics", [])
    for m in metrics:
        month = m.get("month")
        tox = m.get("toxicity_ratio", m.get("toxic_rate_0_5", 0))
        resp = m.get("avg_response_time", m.get("time_to_first_response_mean", 0))
        close = m.get("closing_rate", m.get("change_request_closure_ratio", 0))
        
        monthly[month] = {
            "tox": round(tox, 3) if tox is not None else 0,
            "resp": round(resp, 1) if resp is not None else 0,
            "close": round(close * 100, 1) if close is not None else 0
        }
    return monthly

# --- 4. Personnel Parsing ---

def load_personnel_data() -> Dict[str, Dict[str, float]]:
    result = defaultdict(dict)
    
    if not PERSONNEL_FILE.exists():
        return result
        
    with open(PERSONNEL_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Relaxed Regex
    # Match "[ 2024 年度状态 ]" or similar
    year_pattern = re.compile(r"\[\s*(\d{4})\s*年度状态")
    # Matches: "  repo_name  : 净增 +XX.X% ..."
    repo_pattern = re.compile(r"^\s+([a-zA-Z0-9\-\_\./]+)\s+:\s+净[增流].*?([+\-]?\d+\.?\d*)%")
    
    current_year = None
    
    for line in lines:
        ym = year_pattern.search(line)
        if ym:
            current_year = ym.group(1)
            continue
            
        rm = repo_pattern.search(line)
        if rm and current_year:
            repo = rm.group(1).strip()
            pct_val = float(rm.group(2))
            result[repo][current_year] = pct_val
            
    return result

def calculate_personnel_score_raw(yearly_data: Dict[str, float]) -> float:
    if not yearly_data: return 50.0
    vals = yearly_data.values()
    avg_pct = sum(vals) / len(vals)
    score = 50.0 + (avg_pct / 2.0)
    return max(0.0, min(100.0, score))


# ==========================================
# Main Execution
# ==========================================

def main():
    print("⏳ Loading datasets...")
    
    # 1. Load Data
    full_burnout = load_json(BURNOUT_FULL)
    full_newcomer = load_json(NEWCOMER_FULL)
    full_atmosphere = load_json(ATMOSPHERE_FULL)
    flow_data = load_personnel_data()
    
    # 2. Extract Raw Scores
    raw_burn = load_burnout_scores_raw()
    raw_new = load_newcomer_scores_raw()
    raw_atm = load_atmosphere_scores_raw()
    raw_per = {}
    
    all_repos = set(raw_burn.keys()) | set(raw_new.keys()) | set(raw_atm.keys()) | set(flow_data.keys())
    
    for repo in all_repos:
        raw_per[repo] = calculate_personnel_score_raw(flow_data.get(repo, {}))
        
    # 3. Normalize Scores (Min-Max to 0-100)
    norm_burn = normalize(raw_burn)
    norm_new = normalize(raw_new)
    norm_atm = normalize(raw_atm)
    norm_per = normalize(raw_per)
    
    # 4. Build Report Items
    report_items = []
    
    for repo in all_repos:
        # Normalized scores used for TOTAL
        n_b = norm_burn.get(repo, 0.0)
        n_n = norm_new.get(repo, 0.0)
        n_a = norm_atm.get(repo, 0.0)
        n_p = norm_per.get(repo, 50.0) # Default mid
        
        # Raw scores used for DISPLAY (to explain reality)
        r_b = raw_burn.get(repo, 0)
        r_n = raw_new.get(repo, 0)
        r_a = raw_atm.get(repo, 0)
        r_p = raw_per.get(repo, 50)
        
        total = (n_b * 0.25) + (n_n * 0.25) + (n_a * 0.25) + (n_p * 0.25)
        
        # Detailed data
        m_burn = load_burnout_monthly(repo, full_burnout)
        m_new = load_newcomer_monthly(repo, full_newcomer)
        m_atm = load_atmosphere_monthly(repo, full_atmosphere)
        yearly_flow = flow_data.get(repo, {})
        
        all_months = sorted(set(m_burn.keys()) | set(m_new.keys()) | set(m_atm.keys()))
        
        report_items.append({
            "repo": repo,
            "total": total,
            # We store raw scores for display
            "raw": {"burn": r_b, "new": r_n, "atm": r_a, "per": r_p},
            "norm": {"burn": n_b, "new": n_n, "atm": n_a, "per": n_p},
            "months": all_months,
            "data_burn": m_burn,
            "data_new": m_new,
            "data_atm": m_atm,
            "data_flow": yearly_flow
        })
        
    report_items.sort(key=lambda x: x["total"], reverse=True)
    
    # 5. Generate Markdown
    md = []
    md.append("# 📈 OSS 项目全维度深度健康报告")
    md.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append("")
    md.append("本报告采用 **归一化评分 (Normalized Scoring)** 机制。") 
    md.append("原始指标经过 Min-Max 归一化处理后，加权计算总分 (各维度 25%)。")
    md.append("**表格中展示分为： `归一化分 (原始分)`**")
    md.append("")
    
    md.append("## 🏆 综合排名总览")
    md.append("| 排名 | 项目 | 总分 | 等级 | 🧠 维护(Norm) | 🌱 新人(Norm) | 💬 氛围(Norm) | 🌊 流动(Norm) |")
    md.append("|---|---|---|---|---|---|---|---|")
    
    for i, item in enumerate(report_items, 1):
        n = item["norm"]
        r = item["raw"]
        level = get_level(item["total"]).split(" ")[0]
        
        # Format: 85.1
        f_b = f"{n['burn']:.1f}"
        f_n = f"{n['new']:.1f}"
        f_a = f"{n['atm']:.1f}"
        f_p = f"{n['per']:.1f}"
        
        md.append(f"| {i} | `{item['repo']}` | **{item['total']:.1f}** | {level} | {f_b} | {f_n} | {f_a} | {f_p} |")
        
    md.append("")
    md.append("## 📊 项目深入分析")
    
    for i, item in enumerate(report_items, 1):
        repo = item['repo']
        n = item['norm']
        r = item['raw']
        
        md.append(f"### {i}. {repo}")
        md.append(f"**总分**: {item['total']:.1f} | **等级**: {get_level(item['total'])}")
        md.append(f"> **各维得分(原始/归一化)**:")
        md.append(f"- 🧠 维护: Raw {r['burn']:.1f} ➔ Norm **{n['burn']:.1f}**")
        md.append(f"- 🌱 新人: Raw {r['new']:.1f} ➔ Norm **{n['new']:.1f}**")
        md.append(f"- 💬 氛围: Raw {r['atm']:.1f} ➔ Norm **{n['atm']:.1f}**")
        md.append(f"- 🌊 流动: Raw {r['per']:.1f} ➔ Norm **{n['per']:.1f}**")
        
        # Yearly Flow
        md.append("\n**🌊 年度人员流动 (Yearly Personnel Flow)**\n")
        if item["data_flow"]:
            md.append("| 年份 | 净增长率 (Net Growth) | 状态 |")
            md.append("|---|---|---|")
            # Sort years descending (newest first)
            sorted_years = sorted(item["data_flow"].keys(), reverse=True)
            for y in sorted_years:
                val = item["data_flow"][y]
                status = "🟢 流入" if val > 0 else ("🔴 流失" if val < 0 else "⚪️ 持平")
                if val > 15: status += " (磁铁型)"
                elif val < -15: status += " (输血型)"
                
                # Check for +0.0 or -0.0
                fmt_val = f"+{val:.1f}" if val > 0 else f"{val:.1f}"
                if val == 0: fmt_val = "0.0"
                
                md.append(f"| {y} | **{fmt_val}%** | {status} |")
        else:
             md.append("*暂无年度数据*")
             
        # Monthly
        md.append("\n**📅 月度指标详情 (Monthly Metrics)**\n")
        md.append("| 月份 | 🧠 核心人数 | 🧠 人均负荷 | 🌱 新人数量 | 🌱 平均距离 | 💬 毒性 | 💬 响应(h) | 💬 关闭率 |")
        md.append("|---|---|---|---|---|---|---|---|")
        
        rev_months = sorted(item["months"], reverse=True)
        
        for m in rev_months:
            if not m: continue
            
            d_b = item["data_burn"].get(m, {})
            d_n = item["data_new"].get(m, {})
            d_a = item["data_atm"].get(m, {})
            
            core = d_b.get("core", "-")
            load = d_b.get("load", "-")
            
            new_cnt = d_n.get("count", "-")
            dist = d_n.get("dist", "-")
            
            tox = d_a.get("tox", "-")
            resp = d_a.get("resp", "-")
            close = d_a.get("close", "-")
            if close != "-": close = f"{close}%"
            
            md.append(f"| {m} | {core} | {load} | {new_cnt} | {dist} | {tox} | {resp} | {close} |")
            
        md.append("")
        md.append("---")

    print("💾 Writing Markdown...")
    with open(FINAL_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
        
    print(f"✅ Detailed & Normalized report generated at: {FINAL_REPORT_PATH}")

if __name__ == "__main__":
    main()
