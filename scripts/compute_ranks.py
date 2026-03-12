#!/usr/bin/env python3
"""Compute per-dimension rankings for case study projects."""

data = [
    ('elastic/elasticsearch', 90.4, 66.9, 93.1, 84.4),
    ('pytorch/pytorch', 98.7, 73.3, 86.1, 69.6),
    ('openclaw/openclaw', 91.6, 64.3, 77.7, 85.9),
    ('grafana/grafana', 80.2, 60.4, 84.7, 90.9),
    ('ant-design/ant-design', 72.2, 70.5, 96.3, 75.2),
    ('nodejs/node', 83.3, 68.0, 86.8, 75.9),
    ('kubernetes/kubernetes', 75.2, 73.3, 94.7, 64.0),
    ('golang/go', 83.0, 62.6, 91.9, 67.0),
    ('clickhouse/clickhouse', 88.9, 54.6, 79.7, 80.5),
    ('huggingface/transformers', 77.0, 66.6, 82.6, 76.6),
    ('microsoft/vscode', 86.5, 60.2, 82.2, 73.1),
    ('kuzudb/kuzu', 75.4, 59.8, 99.5, 64.4),
    ('python/cpython', 100.0, 69.7, 77.5, 51.5),
    ('vllm-project/vllm', 98.5, 53.6, 77.6, 64.4),
    ('pytest-dev/pytest', 79.3, 41.8, 85.1, 86.7),
    ('rust-lang/rust', 75.8, 72.8, 76.9, 65.1),
    ('anthropics/anthropic-sdk-python', 57.1, 85.2, 81.7, 64.4),
    ('significant-gravitas/autogpt', 70.5, 68.9, 85.1, 63.9),
    ('helm/helm', 63.8, 64.0, 83.1, 77.4),
    ('microsoft/typescript', 70.3, 63.8, 86.4, 65.6),
    ('meta-llama/llama-stack', 74.5, 60.6, 86.0, 64.4),
    ('sveltejs/svelte', 74.2, 60.9, 80.1, 69.4),
    ('hashicorp/vault', 72.0, 58.9, 88.3, 65.1),
    ('pypa/pip', 64.2, 73.0, 80.5, 66.3),
    ('directus/directus', 81.1, 15.8, 84.8, 100.0),
    ('openai/openai-python', 84.4, 62.9, 68.5, 64.4),
    ('neovim/neovim', 87.7, 62.9, 84.8, 43.1),
    ('hashicorp/terraform', 54.1, 57.3, 89.4, 77.3),
    ('supabase/supabase', 96.8, 8.7, 81.5, 89.0),
    ('containerd/containerd', 72.6, 52.3, 86.4, 61.8),
    ('tanstack/query', 75.2, 52.4, 78.7, 64.4),
    ('shadcn-ui/ui', 70.4, 67.2, 68.2, 64.4),
    ('langgenius/dify', 87.2, 26.5, 92.2, 64.4),
    ('oven-sh/bun', 86.2, 41.0, 74.7, 64.4),
    ('webpack/webpack', 70.4, 56.9, 83.8, 54.3),
    ('tensorflow/tensorflow', 75.1, 71.4, 74.0, 43.0),
    ('argoproj/argo-cd', 84.9, 59.7, 64.3, 53.3),
    ('appwrite/appwrite', 86.9, 14.9, 82.6, 77.2),
    ('vitejs/vite', 69.4, 50.1, 78.6, 61.5),
    ('duckdb/duckdb', 93.4, 41.1, 100.0, 24.4),
    ('julialang/julia', 78.5, 31.5, 86.1, 62.0),
    ('apache/spark', 66.4, 19.0, 94.0, 77.3),
    ('strapi/strapi', 66.4, 55.8, 73.9, 60.4),
    ('apache/kafka', 85.5, 59.1, 84.5, 27.0),
    ('facebook/react', 62.6, 50.5, 79.8, 60.0),
    ('prometheus/prometheus', 72.6, 49.4, 75.2, 55.7),
    ('mui/material-ui', 50.3, 66.1, 83.3, 49.1),
    ('go-gorm/gorm', 62.4, 28.6, 84.8, 71.1),
    ('pmndrs/zustand', 76.5, 46.0, 86.8, 36.0),
    ('internlm/internlm', 43.3, 55.9, 75.6, 69.9),
    ('google/gemma.cpp', 37.8, 63.3, 78.9, 64.4),
    ('langchain-ai/langchain', 22.8, 74.3, 85.1, 57.2),
    ('mistralai/client-python', 35.6, 100.0, 54.9, 47.9),
    ('qwikdev/qwik', 38.2, 59.7, 76.1, 64.4),
    ('modelscope/modelscope', 52.7, 86.7, 81.2, 17.7),
    ('biomejs/biome', 84.6, 4.7, 83.0, 64.4),
    ('qwenlm/qwen-agent', 57.0, 76.4, 33.3, 64.4),
    ('openai/whisper', 46.3, 92.6, 52.8, 37.6),
    ('containers/podman', 66.5, 6.8, 79.1, 75.5),
    ('thudm/chatglm3', 20.4, 86.7, 68.3, 51.8),
    ('facebook/jest', 70.8, 54.6, 88.4, 0.0),
    ('comfyanonymous/comfyui', 97.7, 0.0, 49.3, 64.4),
    ('ggerganov/llama.cpp', 88.4, 14.2, 76.7, 26.3),
    ('vercel/next.js', 74.3, 59.4, 9.3, 60.7),
    ('deepseek-ai/deepseek-v3', 19.6, 80.0, 36.3, 54.7),
    ('run-llama/llama_index', 33.7, 9.8, 86.7, 56.0),
    ('remix-run/remix', 33.7, 29.9, 89.9, 29.2),
    ('apache/flink', 51.9, 16.1, 84.4, 30.2),
    ('hpcaitech/colossalai', 39.7, 40.5, 85.3, 14.6),
    ('01-ai/yi', 25.1, 23.2, 68.2, 61.0),
    ('ollama/ollama', 30.7, 38.9, 78.7, 26.3),
    ('microsoft/autogen', 0.0, 19.4, 81.5, 59.9),
    ('automatic1111/stable-diffusion-webui', 32.1, 11.8, 37.8, 39.1),
    ('baichuan-inc/baichuan2', 28.6, 60.3, 0.0, 23.1),
]

case_studies = [
    'elastic/elasticsearch',
    'pytorch/pytorch',
    'langchain-ai/langchain',
    'openclaw/openclaw',
    'automatic1111/stable-diffusion-webui',
]

dims = ['Maint', 'Newcomer', 'Atmos', 'Flow']

for cs in case_studies:
    print(f"\n=== {cs} ===")
    for dim_idx, dim_name in enumerate(dims, 1):
        scores = [(d[0], d[dim_idx]) for d in data]
        scores.sort(key=lambda x: -x[1])
        for rank, (name, score) in enumerate(scores, 1):
            if name == cs:
                print(f"  {dim_name}: {score} -> #{rank}")
                break

# Also compute tier counts
print("\n=== Tier Counts ===")
totals = []
for d in data:
    total = round((d[1] + d[2] + d[3] + d[4]) / 4, 1)
    totals.append((d[0], total))

# Use the actual total scores from the ranking
total_scores = {
    'elastic/elasticsearch': 83.7, 'pytorch/pytorch': 81.9, 'openclaw/openclaw': 79.9,
    'grafana/grafana': 79.1, 'ant-design/ant-design': 78.6, 'nodejs/node': 78.5,
    'kubernetes/kubernetes': 76.8, 'golang/go': 76.1, 'clickhouse/clickhouse': 75.9,
    'huggingface/transformers': 75.7, 'microsoft/vscode': 75.5, 'kuzudb/kuzu': 74.8,
    'python/cpython': 74.7, 'vllm-project/vllm': 73.5, 'pytest-dev/pytest': 73.2,
    'rust-lang/rust': 72.6, 'anthropics/anthropic-sdk-python': 72.1,
    'significant-gravitas/autogpt': 72.1, 'helm/helm': 72.1,
    'microsoft/typescript': 71.5, 'meta-llama/llama-stack': 71.4,
    'sveltejs/svelte': 71.2, 'hashicorp/vault': 71.1, 'pypa/pip': 71.0,
    'directus/directus': 70.4, 'openai/openai-python': 70.1,
    'neovim/neovim': 69.6, 'hashicorp/terraform': 69.5, 'supabase/supabase': 69.0,
    'containerd/containerd': 68.3, 'tanstack/query': 67.7, 'shadcn-ui/ui': 67.6,
    'langgenius/dify': 67.6, 'oven-sh/bun': 66.6, 'webpack/webpack': 66.3,
    'tensorflow/tensorflow': 65.9, 'argoproj/argo-cd': 65.5, 'appwrite/appwrite': 65.4,
    'vitejs/vite': 64.9, 'duckdb/duckdb': 64.7, 'julialang/julia': 64.5,
    'apache/spark': 64.2, 'strapi/strapi': 64.1, 'apache/kafka': 64.0,
    'facebook/react': 63.2, 'prometheus/prometheus': 63.2, 'mui/material-ui': 62.2,
    'go-gorm/gorm': 61.7, 'pmndrs/zustand': 61.3, 'internlm/internlm': 61.2,
    'google/gemma.cpp': 61.1, 'langchain-ai/langchain': 59.9,
    'mistralai/client-python': 59.6, 'qwikdev/qwik': 59.6,
    'modelscope/modelscope': 59.6, 'biomejs/biome': 59.2,
    'qwenlm/qwen-agent': 57.8, 'openai/whisper': 57.3, 'containers/podman': 57.0,
    'thudm/chatglm3': 56.8, 'facebook/jest': 53.5, 'comfyanonymous/comfyui': 52.9,
    'ggerganov/llama.cpp': 51.4, 'vercel/next.js': 50.9,
    'deepseek-ai/deepseek-v3': 47.7, 'run-llama/llama_index': 46.5,
    'remix-run/remix': 45.7, 'apache/flink': 45.6, 'hpcaitech/colossalai': 45.0,
    '01-ai/yi': 44.4, 'ollama/ollama': 43.6, 'microsoft/autogen': 40.2,
    'automatic1111/stable-diffusion-webui': 30.2, 'baichuan-inc/baichuan2': 28.0,
}

green = sum(1 for v in total_scores.values() if v >= 70)
yellow = sum(1 for v in total_scores.values() if 50 <= v < 70)
red = sum(1 for v in total_scores.values() if v < 50)
print(f"Green (>=70): {green}")
print(f"Yellow (50-70): {yellow}")
print(f"Red (<50): {red}")
print(f"Total: {green + yellow + red}")

# Newcomer negative correlations (from comprehensive report)
# mistralai new friend score
print("\n=== Special rankings ===")
for dim_idx, dim_name in enumerate(dims, 1):
    scores = [(d[0], d[dim_idx]) for d in data]
    scores.sort(key=lambda x: -x[1])
    for rank, (name, score) in enumerate(scores, 1):
        if name == 'mistralai/client-python':
            print(f"  mistralai {dim_name}: {score} -> #{rank}")
            break
