#!/usr/bin/env bash
# 独立广度管线运行器：抓取(3个爬虫仓库) → 翻译 → GLM分类 → 评分 → 摘要 → 关键参数
# → 聚类 → 会议提取 → 校验 → 发布到 breadth/data（web 容器卷挂载即时生效）→ 报告。
# 完全不依赖 tech-db 仓库。幂等：上游无新文件时秒级退出。
set -euo pipefail

BOUNDARY="$(cd "$(dirname "$0")/.." && pwd)"
PIPELINE="$BOUNDARY/pipeline"
export BOUNDARY_REPO="$BOUNDARY"

# ZAI 密钥（不回显）：env 优先，其次 ~/.zai_env
if [ -z "${ZAI_API_KEY:-}" ] && [ -f "$HOME/.zai_env" ]; then
  set -a; . "$HOME/.zai_env"; set +a
fi

# 聚类嵌入模型（bge-m3，管线私有副本）
export HF_HOME="$PIPELINE/models/huggingface"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

# 本地模式语义
export SKIP_INDEX_BUILD=1          # Step10 搜索索引不在本管线范围
export PIPELINE_MAX_DAYS="${PIPELINE_MAX_DAYS:-7}"
export TOKENIZERS_PARALLELISM=false

LOG_DIR="$BOUNDARY/runtime"
mkdir -p "$LOG_DIR"
exec "$PIPELINE/.venv/bin/python" -u "$PIPELINE/auto_pipeline.py" >> "$LOG_DIR/breadth-pipeline.log" 2>&1
