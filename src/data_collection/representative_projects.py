"""
100个代表性开源项目列表

选择标准：
1. 不同规模（超大型、大型、中型）
2. 不同治理模式（公司主导、社区驱动、个人维护）
3. 不同领域（前端、后端、DevOps、AI/ML、数据库等）
4. 有研究价值（历史悠久、有过重大事件如维护者交接）
"""

# 超大型项目（>50k stars, 高活跃度）
MEGA_PROJECTS = [
    # 前端框架
    "facebook/react",
    "vuejs/vue",
    "angular/angular",
    "sveltejs/svelte",
    
    # JavaScript 生态
    "vercel/next.js",
    "nodejs/node",
    "denoland/deno",
    "oven-sh/bun",
    "microsoft/TypeScript",
    
    # 后端框架
    "django/django",
    "pallets/flask",
    "fastapi/fastapi",
    "rails/rails",
    "spring-projects/spring-boot",
    "laravel/laravel",
    "gin-gonic/gin",
    
    # 云原生 & DevOps
    "kubernetes/kubernetes",
    "docker/docker-ce",
    "moby/moby",
    "helm/helm",
    "prometheus/prometheus",
    "grafana/grafana",
    "argoproj/argo-cd",
    "hashicorp/terraform",
    "ansible/ansible",
    
    # 数据库
    "postgres/postgres",
    "redis/redis",
    "mongodb/mongo",
    "elastic/elasticsearch",
    "apache/kafka",
    "ClickHouse/ClickHouse",
    
    # AI/ML
    "pytorch/pytorch",
    "tensorflow/tensorflow",
    "huggingface/transformers",
    "langchain-ai/langchain",
    "openai/openai-python",
    "AUTOMATIC1111/stable-diffusion-webui",
    
    # 编程语言
    "rust-lang/rust",
    "golang/go",
    "python/cpython",
    "JuliaLang/julia",
    "ziglang/zig",
]

# 大型项目（10k-50k stars）
LARGE_PROJECTS = [
    # 工具链
    "webpack/webpack",
    "vitejs/vite",
    "esbuild/esbuild",
    "rome/tools",
    "biomejs/biome",
    
    # 测试框架
    "facebook/jest",
    "mochajs/mocha",
    "pytest-dev/pytest",
    
    # UI 组件库
    "ant-design/ant-design",
    "mui/material-ui",
    "tailwindlabs/tailwindcss",
    "shadcn-ui/ui",
    
    # 状态管理
    "reduxjs/redux",
    "pmndrs/zustand",
    "TanStack/query",
    
    # HTTP/网络
    "axios/axios",
    "psf/requests",
    "encode/httpx",
    
    # 数据处理
    "pandas-dev/pandas",
    "numpy/numpy",
    "apache/spark",
    "apache/flink",
    
    # 安全
    "OWASP/CheatSheetSeries",
    "hashicorp/vault",
    
    # CLI 工具
    "ohmyzsh/ohmyzsh",
    "junegunn/fzf",
    "BurntSushi/ripgrep",
    "sharkdp/bat",
    
    # 编辑器/IDE
    "neovim/neovim",
    "microsoft/vscode",
    "atom/atom",  # 已归档，研究项目生命周期
    
    # 容器/虚拟化
    "containerd/containerd",
    "containers/podman",
]

# 中型项目（1k-10k stars，研究价值高）
MEDIUM_PROJECTS = [
    # 有过维护者交接/倦怠的项目
    "chalk/chalk",
    "sindresorhus/got",
    "request/request",  # 已归档
    "moment/moment",    # 维护模式
    
    # 社区治理有特色
    "nvm-sh/nvm",
    "pypa/pip",
    "npm/cli",
    "yarnpkg/yarn",
    "pnpm/pnpm",
    
    # 安全相关（可研究漏洞响应）
    "log4j/log4j",  # Log4Shell
    "advisories/GHSA-jfh8-c2jp-5v3q",  # 如果存在
    
    # 新兴项目（观察成长）
    "astro-build/astro",
    "remix-run/remix",
    "solidjs/solid",
    "qwikdev/qwik",
    
    # 特定领域
    "strapi/strapi",
    "directus/directus",
    "supabase/supabase",
    "appwrite/appwrite",
    
    # Rust 生态
    "tokio-rs/tokio",
    "serde-rs/serde",
    "clap-rs/clap",
    
    # Go 生态
    "go-gorm/gorm",
    "uber-go/zap",
    "spf13/cobra",
]

# 合并所有项目
ALL_REPRESENTATIVE_PROJECTS = (
    MEGA_PROJECTS + 
    LARGE_PROJECTS + 
    MEDIUM_PROJECTS
)

# 确保正好100个（如果不够或多了，调整）
def get_project_list(count: int = 100) -> list:
    """获取指定数量的代表性项目"""
    projects = ALL_REPRESENTATIVE_PROJECTS[:count]
    # 转为小写以便匹配
    return [p.lower() for p in projects]

def get_project_set(count: int = 100) -> set:
    """获取项目集合（用于快速查找）"""
    return set(get_project_list(count))

# 项目名到组织的映射（用于扩展匹配）
def get_org_list() -> set:
    """获取所有涉及的组织名"""
    orgs = set()
    for project in ALL_REPRESENTATIVE_PROJECTS:
        org = project.split("/")[0].lower()
        orgs.add(org)
    return orgs


if __name__ == "__main__":
    projects = get_project_list(100)
    print(f"共 {len(projects)} 个代表性项目:")
    for i, p in enumerate(projects, 1):
        print(f"  {i:3d}. {p}")
