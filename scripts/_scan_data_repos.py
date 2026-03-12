"""
全面扫描 data/ 目录所有有效文件中的 repo，与 fulldaily 对比。
"""
import json
import re
from pathlib import Path

DATA_DIR = Path("/Users/milk/Documents/ali2025/oss_graph_construction/data")
SKIP_12 = re.compile(r"^\d{4}-\d{2}-\d{2}-12-filtered\.json$")

FULLDAILY_REPOS = {
    "ClickHouse/ClickHouse", "JuliaLang/julia", "ant-design/ant-design",
    "apache/flink", "apache/kafka", "apache/spark", "appwrite/appwrite",
    "argoproj/argo-cd", "containerd/containerd", "containers/podman",
    "directus/directus", "elastic/elasticsearch", "facebook/jest",
    "facebook/react", "go-gorm/gorm", "golang/go", "grafana/grafana",
    "hashicorp/terraform", "hashicorp/vault", "helm/helm",
    "huggingface/transformers", "kubernetes/kubernetes", "microsoft/TypeScript",
    "microsoft/vscode", "neovim/neovim", "nodejs/node", "pmndrs/zustand",
    "prometheus/prometheus", "pypa/pip", "pytest-dev/pytest", "python/cpython",
    "pytorch/pytorch", "rust-lang/rust", "strapi/strapi", "supabase/supabase",
    "sveltejs/svelte", "tensorflow/tensorflow", "vercel/next.js",
    "vitejs/vite", "webpack/webpack",
}

data_repos = set()
file_count = 0
for d in sorted(DATA_DIR.glob("filtered*/")):
    for f in sorted(d.glob("*-filtered.json")):
        if SKIP_12.match(f.name):
            continue
        if f.name.startswith("2026-03"):
            continue
        file_count += 1
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    data_repos.add(obj["repo"]["name"])
                except Exception:
                    pass

overlap = data_repos & FULLDAILY_REPOS
only_data = data_repos - FULLDAILY_REPOS

print(f"data有效文件: {file_count}")
print(f"data全部repos: {len(data_repos)}")
print(f"与fulldaily重叠: {len(overlap)} => {sorted(overlap)}")
print(f"data独有repos ({len(only_data)}):")
for r in sorted(only_data):
    print(f"  {r}")
