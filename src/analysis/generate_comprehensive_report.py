
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
BURNOUT_SUMMARY = OUTPUT_DIR / "burnout-analysis2/summary.json"
NEWCOMER_SUMMARY = OUTPUT_DIR / "newcomer-analysis/summary.json"
ATMOSPHERE_SUMMARY = OUTPUT_DIR / "community-atmosphere-analysis/full_analysis.json" # Used for score as well

# Detailed files for monthly data
BURNOUT_FULL = OUTPUT_DIR / "burnout-analysis2/full_analysis.json"
NEWCOMER_FULL = OUTPUT_DIR / "newcomer-analysis/full_analysis.json"
ATMOSPHERE_FULL = OUTPUT_DIR / "community-atmosphere-analysis/full_analysis.json" # Same file

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
    if score >= 60: return "🟡 中等" # Adjusted slightly
    if score >= 50: return "🟡及格"
    return "🔴 较差"

# --- 1. Burnout Parsing ---

def load_burnout_scores() -> Dict[str, float]:
    data = load_json(BURNOUT_SUMMARY)
    if isinstance(data, list):
        return {item["repo_name"]: float(item.get("burnout_score", 0)) for item in data}
    return {}

def load_burnout_monthly(repo: str, full_data: Dict) -> Dict[str, Dict]:
    # Returns { "YYYY-MM": { "core": int, "load": float } }
    monthly = {}
    if repo not in full_data: return monthly
    
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

def load_newcomer_scores() -> Dict[str, float]:
    data = load_json(NEWCOMER_SUMMARY)
    if isinstance(data, list):
        return {item["repo_name"]: float(item.get("health_score", 0)) for item in data}
    return {}

def load_newcomer_monthly(repo: str, full_data: Dict) -> Dict[str, Dict]:
    # Returns { "YYYY-MM": { "count": int, "dist": float } }
    monthly = defaultdict(lambda: {"count": 0, "dist_sum": 0.0})
    
    if repo not in full_data: return monthly
    
    # Newcomer data is in 'records' list
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

def load_atmosphere_scores() -> Dict[str, float]:
    # We calculate score from full analysis to ensure consistency
    full_data = load_json(ATMOSPHERE_FULL)
    scores = {}
    
    for repo, content in full_data.items():
        metrics = content.get("metrics", [])
        if not metrics:
            scores[repo] = 0.0
            continue
            
        tox_values = [m.get("toxicity_ratio", m.get("toxic_rate_0_5", 0)) for m in metrics]
        resp_values = [m.get("avg_response_time", m.get("time_to_first_response_mean", 0)) for m in metrics]
        close_values = [m.get("closing_rate", m.get("change_request_closure_ratio", 0)) for m in metrics]
        
        avg_tox = sum(tox_values) / len(tox_values) if tox_values else 0
        avg_resp = sum(resp_values) / len(resp_values) if resp_values else 0
        avg_close = sum(close_values) / len(close_values) if close_values else 0
        
        # 4:3:3 formula
        s1 = max(0.0, 1.0 - avg_tox / 0.05) * 100 * 0.4
        s2 = (100.0 / (1.0 + avg_resp / 48.0)) * 0.3
        s3 = min(100.0, avg_close * 100.0) * 0.3
        
        scores[repo] = s1 + s2 + s3
    return scores

def load_atmosphere_monthly(repo: str, full_data: Dict) -> Dict[str, Dict]:
    # Returns { "YYYY-MM": { "tox": float, "resp": float, "close": float } }
    monthly = {}
    if repo not in full_data: return monthly
    
    metrics = full_data[repo].get("metrics", [])
    for m in metrics:
        month = m.get("month")
        tox = m.get("toxicity_ratio", m.get("toxic_rate_0_5", 0))
        resp = m.get("avg_response_time", m.get("time_to_first_response_mean", 0))
        close = m.get("closing_rate", m.get("change_request_closure_ratio", 0))
        
        monthly[month] = {
            "tox": round(tox, 3),
            "resp": round(resp, 1),
            "close": round(close * 100, 1) # percent
        }
    return monthly

# --- 4. Personnel Parsing ---

def load_personnel_data() -> Dict[str, Dict[str, float]]:
    # Returns { repo: { "2021": 0.15, "2022": -0.05 } }
    result = defaultdict(dict)
    
    if not PERSONNEL_FILE.exists():
        return result
        
    with open(PERSONNEL_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    current_year = ""
    year_pattern = re.compile(r"\[ (\d{4}) 年度状态 \]")
    repo_pattern = re.compile(r"^\s+([a-zA-Z0-9\-\_\./]+)\s+:\s+净[增流]\s+([+\-]?\d+\.?\d*)%")
    
    for line in lines:
        ym = year_pattern.search(line)
        if ym:
            current_year = ym.group(1)
            continue
            
        rm = repo_pattern.search(line)
        if rm and current_year:
            repo = rm.group(1).strip()
            # Capture as float from regex. Wait, regex matches "+100.0" which float() handles
            pct_str = rm.group(2)
            # Remove '+' for float conversion if needed, but float("+1") is valid
            try:
                pct = float(pct_str)
            except:
                pct = 0.0
            result[repo][current_year] = pct
            
    return result

def calculate_personnel_score(yearly_data: Dict[str, float]) -> float:
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
    # Load High Level Scores
    s_burnout = load_burnout_scores()
    s_newcomer = load_newcomer_scores()
    s_atmosphere = load_atmosphere_scores()
    
    # Load Full Data for Detailed Views
    full_burnout = load_json(BURNOUT_FULL)
    full_newcomer = load_json(NEWCOMER_FULL)
    full_atmosphere = load_json(ATMOSPHERE_FULL)
    flow_data = load_personnel_data()
    
    # Build Master Repo List
    all_repos = set(s_burnout.keys()) | set(s_newcomer.keys()) | set(s_atmosphere.keys()) | set(flow_data.keys())
    
    # Construct Report List
    report_items = []
    
    for repo in all_repos:
        # 1. Scores
        v_burn = s_burnout.get(repo, 0.0)
        v_new = s_newcomer.get(repo, 0.0)
        v_atm = s_atmosphere.get(repo, 0.0)
        
        yearly_flow = flow_data.get(repo, {})
        v_per = calculate_personnel_score(yearly_flow)
        
        total = (v_burn * 0.25) + (v_new * 0.25) + (v_atm * 0.25) + (v_per * 0.25)
        
        # 2. Detailed Data
        m_burn = load_burnout_monthly(repo, full_burnout)
        m_new = load_newcomer_monthly(repo, full_newcomer)
        m_atm = load_atmosphere_monthly(repo, full_atmosphere)
        
        # Get all months sorted
        all_months = sorted(set(m_burn.keys()) | set(m_new.keys()) | set(m_atm.keys()))
        
        report_items.append({
            "repo": repo,
            "total": total,
            "scores": {"burn": v_burn, "new": v_new, "atm": v_atm, "per": v_per},
            "months": all_months,
            "data_burn": m_burn,
            "data_new": m_new,
            "data_atm": m_atm,
            "data_flow": yearly_flow
        })
        
    # Sort by total score
    report_items.sort(key=lambda x: x["total"], reverse=True)
    
    # === Generate Markdown ===
    md = []
    md.append("# 📈 OSS 项目全维度深度健康报告")
    md.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append("")
    md.append("本报告包含每个项目的 **综合评分** 及 **按月详细指标趋势**。")
    md.append("")
    
    # --- Summary Table ---
    md.append("## 🏆 综合排名总览")
    md.append("| 排名 | 项目 | 总分 | 等级 | 🧠 维护 | 🌱 新人 | 💬 氛围 | 🌊 流动 |")
    md.append("|---|---|---|---|---|---|---|---|")
    for i, item in enumerate(report_items, 1):
        s = item["scores"]
        level = get_level(item["total"]).split(" ")[0]
        md.append(f"| {i} | `{item['repo']}` | **{item['total']:.1f}** | {level} | {s['burn']:.1f} | {s['new']:.1f} | {s['atm']:.1f} | {s['per']:.1f} |")
    md.append("")
    
    # --- Detailed Analysis ---
    md.append("## 📊 项目详细深度分析")
    md.append("每个项目的详细数据包括：")
    md.append("- **年度人员流动**: 反映人才净流入/流出比例。")
    md.append("- **月度指标趋势**: 包含核心团队规模/负荷、新人进入情况、社区回应效率等。")
    md.append("")
    
    for i, item in enumerate(report_items, 1):
        repo = item['repo']
        s = item['scores']
        md.append(f"### {i}. {repo} (Score: {item['total']:.1f})")
        
        # 1. Yearly Flow Table
        if item["data_flow"]:
            md.append("\n**🌊 年度人员流动 (Yearly Personnel Flow)**\n")
            md.append("| 年份 | 净增长率 (Net Growth) | 状态 |")
            md.append("|---|---|---|")
            sorted_years = sorted(item["data_flow"].keys())
            for y in sorted_years:
                val = item["data_flow"][y]
                status = "🟢 流入" if val > 0 else ("🔴 流失" if val < 0 else "⚪️ 持平")
                if val > 15: status += " (磁铁型)"
                elif val < -15: status += " (输血型)"
                md.append(f"| {y} | **{val:+.1f}%** | {status} |")
            md.append("")
        else:
            md.append("\n**🌊 年度人员流动**: *暂无数据*\n")

        # 2. Monthly Metrics Table
        md.append("**📅 月度指标详情**")
        header = "| 月份 | 核心人数 (Burnout) | 人均负荷 | 新人数量 (Newcomer) | 平均距离 | 毒性 (Atmos) | 响应均值(h) | 关闭率 |"
        md.append(header)
        md.append("|---|---|---|---|---|---|---|---|")
        
        rev_months = sorted(item["months"], reverse=True)
        
        for m in rev_months:
            if not m: continue
            
            d_b = item["data_burn"].get(m, {})
            d_n = item["data_new"].get(m, {})
            d_a = item["data_atm"].get(m, {})
            
            # Formatting
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
        
    print(f"✅ Detailed report generated at: {FINAL_REPORT_PATH}")

if __name__ == "__main__":
    main()
