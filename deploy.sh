#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "技术边界数据库 - 一键部署"
echo "========================================"
echo ""

# 检查 .env 是否存在
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "⚠️  未找到 .env，正在从模板创建..."
        cp .env.example .env
        echo "❌ 请编辑 .env 文件，填写 TECHDB_AGENT_API_KEY 后重新运行此脚本"
        echo "   命令：nano .env  或  vim .env"
        exit 1
    else
        echo "❌ 错误：未找到 .env 和 .env.example"
        exit 1
    fi
fi

# 加载环境变量
set -a
source .env
set +a

# 拒绝空值和模板占位值，避免把示例配置误当成生产配置。
require_config() {
    local name="$1"
    shift
    local value="${!name:-}"
    if [ -z "$value" ]; then
        echo "❌ 错误：${name} 未设置"
        exit 1
    fi
    for placeholder in "$@"; do
        if [ "$value" = "$placeholder" ]; then
            echo "❌ 错误：${name} 仍是模板占位值"
            exit 1
        fi
    done
}

require_config SECRET_KEY replace_with_a_random_64_hex_string
require_config POSTGRES_PASSWORD replace_with_a_strong_database_password
require_config TECHDB_INITIAL_ADMIN_PASSWORD replace_with_a_strong_admin_password
require_config TECHDB_AGENT_API_KEY your_api_key_here replace_with_company_gateway_api_key

echo "✓ API Key 已配置"
echo "✓ 模型: $TECHDB_AGENT_MODEL"
echo "✓ 端点: $TECHDB_AGENT_BASE_URL"
echo "✓ Canonical QA 检索服务: ${TECHDB_QA_SERVICE_URL:-http://canonical-qa:8765}"
echo ""

# 准备上传文件持久目录。相对路径统一相对于项目根目录解析。
UPLOAD_PATH="${TECHDB_UPLOAD_HOST_PATH:-./uploads}"
case "$UPLOAD_PATH" in
    /*) ;;
    *) UPLOAD_PATH="$SCRIPT_DIR/${UPLOAD_PATH#./}" ;;
esac
mkdir -p "$UPLOAD_PATH"
if [ ! -d "$UPLOAD_PATH" ] || [ ! -w "$UPLOAD_PATH" ]; then
    echo "❌ 错误：上传目录不可写: $UPLOAD_PATH"
    exit 1
fi
echo "✓ 上传目录: $UPLOAD_PATH"
echo ""

# 检查外部数据目录
BUNDLED_DIR="$SCRIPT_DIR/external-data"
echo "📋 检查数据目录..."

# 旧知识库（仅供兼容 readonly-agent/深度研究工具使用）
KB_PATH="${TECHDB_KB_PATH:-$BUNDLED_DIR/knowledge-base}"
if [ -d "$KB_PATH" ]; then
    echo "  ✓ 旧知识库目录: $KB_PATH"
else
    echo "  ⚠️  旧知识库目录不存在: $KB_PATH"
    echo "     （不影响 canonical QA；仅影响兼容工具）"
fi

# 交付视图
DV_PATH="${TECHDB_DELIVERY_VIEWS_PATH:-$BUNDLED_DIR/delivery-views}"
if [ -d "$DV_PATH" ]; then
    echo "  ✓ 交付视图: $DV_PATH"
else
    echo "  ⚠️  交付视图目录不存在: $DV_PATH"
fi

# 旧 Chatbot 包（不参与 0801 门户问答）
CB_PATH="${TECHDB_CHATBOT_PACKAGE_PATH:-$BUNDLED_DIR/chatbot-package}"
if [ -d "$CB_PATH" ]; then
    echo "  ✓ 旧 Chatbot 集成包目录: $CB_PATH"
else
    echo "  ⚠️  旧 Chatbot 集成包不存在: $CB_PATH"
    echo "     （不影响 canonical QA；仅影响兼容 readonly-agent）"
fi

echo ""

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 错误：Docker 未安装"
    echo "   请先安装 Docker Engine 和 Docker Compose V2"
    exit 1
fi
echo "✓ Docker $(docker --version)"

if ! docker compose version &> /dev/null; then
    echo "❌ 错误：Docker Compose V2 未安装"
    exit 1
fi
echo "✓ Docker Compose V2"
echo ""

# 创建 PostgreSQL 数据卷
PG_VOLUME="${TECHDB_PG_VOLUME:-v260723_pg_data}"
echo "📦 准备数据卷..."
if docker volume inspect "$PG_VOLUME" >/dev/null 2>&1; then
    echo "  ✓ 数据卷 $PG_VOLUME 已存在（复用已有数据）"
else
    echo "  ⚙️  创建数据卷 $PG_VOLUME..."
    docker volume create "$PG_VOLUME"
    echo "  ✓ 数据卷创建成功"
fi
echo ""

# 每个服务独立版本。1001 是完成 QA 迁移/Feed/上传收口后的集成基线。
# 这里绝不能再硬编码 0801，否则一键部署会静默绕过仓库里的新版代码。
QA_TAG="${TECHDB_QA_IMAGE_TAG:-1008}"
API_TAG="${TECHDB_API_IMAGE_TAG:-1019}"
AGENT_TAG="${TECHDB_AGENT_IMAGE_TAG:-1019}"
WEB_TAG="${TECHDB_WEB_IMAGE_TAG:-1017}"

QA_IMAGE="techdb-canonical-qa:${QA_TAG}"
if ! docker image inspect "$QA_IMAGE" >/dev/null 2>&1; then
    echo "❌ 错误：缺少 $QA_IMAGE 镜像"
    echo "   canonical-qa 镜像包含 bge-m3、向量/BM25 基线索引和记录资产；"
    echo "   公司离线服务器不要现场全量重跑 embedding。请先构建/导入与"
    echo "   TECHDB_QA_IMAGE_TAG 一致的已验收镜像后再部署。"
    exit 1
fi

APP_IMAGES=("techdb-api:${API_TAG}" "techdb-readonly-agent:${AGENT_TAG}" "techdb-web:${WEB_TAG}")
APP_SERVICES=("api" "readonly-agent" "web")
BUILD_SERVICES=()
for i in "${!APP_IMAGES[@]}"; do
    if ! docker image inspect "${APP_IMAGES[$i]}" >/dev/null 2>&1; then
        BUILD_SERVICES+=("${APP_SERVICES[$i]}")
    fi
done

if [ "${TECHDB_FORCE_BUILD:-false}" = "true" ]; then
    BUILD_SERVICES=("api" "readonly-agent" "web")
fi

if [ "${#BUILD_SERVICES[@]}" -gt 0 ]; then
    if [[ " ${BUILD_SERVICES[*]} " == *" web "* ]] && [ ! -f "$SCRIPT_DIR/breadth/data/processed/manifest-data.js" ]; then
        echo "❌ 错误：构建 web 镜像需要已批准的 breadth/data/processed 资产"
        echo "   请先导入 techdb-web:${WEB_TAG}，或由资料提供方补齐广度追踪数据。"
        exit 1
    fi
    echo "🔨 构建缺失镜像: ${BUILD_SERVICES[*]}"
    docker compose build "${BUILD_SERVICES[@]}"
else
    echo "✓ 已找到所需应用镜像（qa=${QA_TAG}, api=${API_TAG}, agent=${AGENT_TAG}, web=${WEB_TAG}），跳过源码重建"
fi

if ! docker image inspect postgres:16 >/dev/null 2>&1; then
    echo "❌ 错误：缺少 postgres:16 镜像"
    echo "   请从 GitHub Release（server-20261004）下载镜像分片并装载："
    echo "     cat postgres-16.tar.gz.part-* | gunzip | docker load"
    exit 1
fi
echo ""

# 启动服务
echo "🚀 启动服务..."
docker compose up -d --no-build
echo ""

# 等待数据库就绪
echo "⏳ 等待服务就绪..."
DB_READY=false
for i in $(seq 1 30); do
    if docker compose exec -T db pg_isready -U "${POSTGRES_USER:-techdb}" -d "${POSTGRES_DB:-tech_intel}" &>/dev/null; then
        echo "  ✓ 数据库已就绪"
        DB_READY=true
        break
    fi
    sleep 2
done
if [ "$DB_READY" != "true" ]; then
    echo "❌ 数据库在 60 秒内未就绪"
    docker compose ps
    exit 1
fi

QA_READY=false
for i in $(seq 1 90); do
    if docker compose exec -T canonical-qa python -c \
        "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4)); assert d['vector_index_ready'] and d['bm25_ready'] and d['index_mapping_ready'] and d['incremental_index_ready'] and not d.get('incremental_corrupt', False)" \
        >/dev/null 2>&1; then
        echo "  ✓ Canonical QA 模型、索引、记录映射和增量索引已就绪"
        QA_READY=true
        break
    fi
    sleep 2
done
if [ "$QA_READY" != "true" ]; then
    echo "❌ Canonical QA 在 180 秒内未就绪"
    docker compose logs --tail=100 canonical-qa
    exit 1
fi

# 检查服务状态
echo ""
echo "📊 服务状态："
docker compose ps
echo ""

# 获取端口
WEB_PORT="${TECHDB_WEB_PORT:-8080}"
AGENT_PORT="${TECHDB_AGENT_PORT:-8766}"
QA_PORT="${TECHDB_QA_PORT:-8765}"

echo "========================================"
echo "✅ 部署完成"
echo "========================================"
echo ""
echo "访问地址："
echo "  前端：  http://localhost:${WEB_PORT}"
echo "  API：  http://localhost:8000"
echo "  QA 诊断：http://localhost:${QA_PORT}/api/health"
echo "  兼容 Agent：http://localhost:${AGENT_PORT}/health"
echo ""
echo "常用命令："
echo "  查看日志：docker compose logs -f"
echo "  停止服务：docker compose down"
echo "  重启服务：docker compose restart"
echo "  注意：不要在生产环境执行 docker compose down -v（会删除数据库卷）"
echo ""
