#!/usr/bin/env python3
"""Diagnose why 49 repos failed in bus_factor analysis."""
import json, os
from pathlib import Path

INDEX = Path("output/monthly-graphs/index.json")

with open(INDEX) as f:
    idx = json.load(f)

# 24 new repos (fullday data)
NEW_REPOS = {r.lower() for r in [
    "01-ai/Yi", "anthropics/anthropic-sdk-python", "baichuan-inc/Baichuan2",
    "comfyanonymous/ComfyUI", "deepseek-ai/DeepSeek-Coder", "deepseek-ai/DeepSeek-V3",
    "ggerganov/llama.cpp", "google/gemma.cpp", "hpcaitech/ColossalAI",
    "InternLM/InternLM", "langgenius/dify", "meta-llama/llama",
    "microsoft/autogen", "mistralai/mistral-inference", "modelscope/modelscope",
    "ollama/ollama", "openai/openai-python", "openai/whisper", "openclaw/openclaw",
    "QwenLM/Qwen", "run-llama/llama_index", "Significant-Gravitas/AutoGPT",
    "THUDM/ChatGLM-6B", "vllm-project/vllm",
]}

# Check a few paths from each group
for repo, months in idx.items():
    is_new = repo.lower() in NEW_REPOS
    group = "NEW" if is_new else "OLD"
    first_month = list(months.keys())[0]
    first_types = months[first_month]
    sample_path = list(first_types.values())[0]
    exists = Path(sample_path).exists()
    
    # Also check with graphs_dir prefix
    joined = os.path.join("output/monthly-graphs", sample_path)
    joined_exists = Path(joined).exists()
    
    total_months = len(months)
    # Count existing files
    exist_count = 0
    for m, types in months.items():
        for gt, p in types.items():
            if Path(p).exists():
                exist_count += 1
            break  # just check first type per month
        
    print(f"[{group}] {repo}: {total_months} months, {exist_count} exist | sample={sample_path[:80]} exists={exists} joined_exists={joined_exists}")
