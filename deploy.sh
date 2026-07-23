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

# 检查 API Key（唯一必填项）
if [ -z "$TECHDB_AGENT_API_KEY" ] || [ "$TECHDB_AGENT_API_KEY" = "your_api_key_here" ]; then
    echo "❌ 错误：TECHDB_AGENT_API_KEY 未设置"
    echo "   请编辑 .env 文件填写你的 API Key"
    exit 1
fi

echo "✓ API Key 已配置"
echo "✓ 模型: $TECHDB_AGENT_MODEL"
echo "✓ 端点: $TECHDB_AGENT_BASE_URL"
echo ""

# 检查外部数据目录
BUNDLED_DIR="$SCRIPT_DIR/external-data"
echo "📋 检查数据目录..."

# 知识库
KB_PATH="${TECHDB_KB_PATH:-$BUNDLED_DIR/knowledge-base}"
if [ -d "$KB_PATH" ]; then
    echo "  ✓ 知识库: $KB_PATH"
else
    echo "  ⚠️  知识库目录不存在: $KB_PATH"
    echo "     （AI 问答仍可运行，但无法检索知识库文档）"
fi

# 交付视图
DV_PATH="${TECHDB_DELIVERY_VIEWS_PATH:-$BUNDLED_DIR/delivery-views}"
if [ -d "$DV_PATH" ]; then
    echo "  ✓ 交付视图: $DV_PATH"
else
    echo "  ⚠️  交付视图目录不存在: $DV_PATH"
fi

# Chatbot 包
CB_PATH="${TECHDB_CHATBOT_PACKAGE_PATH:-$BUNDLED_DIR/chatbot-package}"
if [ -d "$CB_PATH" ]; then
    echo "  ✓ Chatbot 集成包: $CB_PATH"
else
    echo "  ⚠️  Chatbot 集成包不存在: $CB_PATH"
    echo "     （readonly-agent 的检索增强功能将不可用）"
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

# 构建镜像
echo "🔨 构建 Docker 镜像（首次约 1-2 分钟）..."
docker compose build
echo ""

# 启动服务
echo "🚀 启动服务..."
docker compose up -d
echo ""

# 等待数据库就绪
echo "⏳ 等待服务就绪..."
for i in $(seq 1 30); do
    if docker compose exec -T db pg_isready -U tech -d tech_intel &>/dev/null; then
        echo "  ✓ 数据库已就绪"
        break
    fi
    sleep 2
done

# 检查服务状态
echo ""
echo "📊 服务状态："
docker compose ps
echo ""

# 获取端口
WEB_PORT="${TECHDB_WEB_PORT:-8080}"

echo "========================================"
echo "✅ 部署完成"
echo "========================================"
echo ""
echo "访问地址："
echo "  前端：  http://localhost:${WEB_PORT}"
echo "  API：  http://localhost:8000"
echo "  Agent：http://localhost:8765/health"
echo ""
echo "常用命令："
echo "  查看日志：docker compose logs -f"
echo "  停止服务：docker compose down"
echo "  重启服务：docker compose restart"
echo "  完全清除：docker compose down -v"
echo ""
