#!/bin/bash
# 技术边界数据库 — PostgreSQL 备份恢复脚本
#
# 用法：
#   ./scripts/db_restore.sh backup/techdb_20260722_030000.sql.gz
#
# 警告：恢复会覆盖当前数据库中的所有数据。
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "用法: $0 <备份文件路径>"
    echo "示例: $0 backup/techdb_20260722_030000.sql.gz"
    exit 1
fi

DUMP_FILE="$1"
if [ ! -f "$DUMP_FILE" ]; then
    echo "ERROR: 文件不存在: ${DUMP_FILE}"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

PG_DB="${POSTGRES_DB:-tech_intel}"
PG_USER="${POSTGRES_USER:-techdb}"
PG_CONTAINER="${TECHDB_DB_CONTAINER:-v260723-db-1}"

echo "=========================================="
echo "  技术边界数据库 — 备份恢复"
echo "=========================================="
echo "  备份文件: ${DUMP_FILE}"
echo "  目标数据库: ${PG_DB}@${PG_CONTAINER}"
echo ""
echo "  WARNING: 此操作将覆盖数据库中的所有现有数据。"
read -p "  确认恢复？输入 yes 继续: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "已取消。"
    exit 0
fi
echo "=========================================="

echo "[$(date)] 开始恢复..."
gunzip -c "$DUMP_FILE" | docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" 2>&1

echo "[$(date)] OK: 恢复完成。"
echo "建议执行 alembic upgrade head 确认迁移状态一致。"