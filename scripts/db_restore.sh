#!/bin/bash
# 技术边界数据库一致性恢复：PostgreSQL + 匹配的上传对象
# 用法：./scripts/db_restore.sh backup/techdb_YYYYMMDD_HHMMSS.sql.gz [uploads_*.tar.gz]
set -euo pipefail

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "用法: $0 <数据库备份.sql.gz> [上传对象备份.tar.gz]"
    exit 1
fi

DUMP_FILE="$(cd "$(dirname "$1")" 2>/dev/null && pwd)/$(basename "$1")"
if [ ! -f "$DUMP_FILE" ]; then
    echo "ERROR: 数据库备份不存在: ${DUMP_FILE}"
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
UPLOAD_PATH="${TECHDB_UPLOAD_HOST_PATH:-./uploads}"
case "$UPLOAD_PATH" in
    /*) ;;
    *) UPLOAD_PATH="${PROJECT_DIR}/${UPLOAD_PATH#./}" ;;
esac

dump_base="$(basename "$DUMP_FILE")"
timestamp="${dump_base#techdb_}"
timestamp="${timestamp%.sql.gz}"
if [ $# -eq 2 ]; then
    UPLOAD_ARCHIVE="$(cd "$(dirname "$2")" 2>/dev/null && pwd)/$(basename "$2")"
else
    UPLOAD_ARCHIVE="$(dirname "$DUMP_FILE")/uploads_${timestamp}.tar.gz"
fi

RESTORE_UPLOADS=true
if [ ! -f "$UPLOAD_ARCHIVE" ]; then
    RESTORE_UPLOADS=false
fi

case "$UPLOAD_PATH" in
    ""|"/"|"$PROJECT_DIR")
        echo "ERROR: 拒绝使用不安全的上传恢复目录: ${UPLOAD_PATH}"
        exit 1
        ;;
esac

STAGE_DIR=""
SERVICES_STOPPED=false
cleanup() {
    if [ -n "$STAGE_DIR" ] && [ -d "$STAGE_DIR" ]; then
        rm -rf -- "$STAGE_DIR"
    fi
    if [ "$SERVICES_STOPPED" = "true" ]; then
        docker compose --project-directory "$PROJECT_DIR" up -d api readonly-agent >/dev/null || true
    fi
}
trap cleanup EXIT

if [ "$RESTORE_UPLOADS" = "true" ]; then
    # 先检查成员名，再解压到同一文件系统的暂存目录；不直接覆盖生产目录。
    if tar -tzf "$UPLOAD_ARCHIVE" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then
        echo "ERROR: 上传对象备份包含越界路径，拒绝恢复"
        exit 1
    fi
    if tar -tvzf "$UPLOAD_ARCHIVE" | awk 'substr($1,1,1) ~ /[lh]/ { found=1 } END { exit(found ? 0 : 1) }'; then
        echo "ERROR: 上传对象备份包含符号链接或硬链接，拒绝恢复"
        exit 1
    fi
    upload_parent="$(dirname "$UPLOAD_PATH")"
    mkdir -p "$upload_parent"
    STAGE_DIR="$(mktemp -d "${upload_parent}/.techdb-restore.XXXXXX")"
    tar -xzf "$UPLOAD_ARCHIVE" -C "$STAGE_DIR" --no-same-owner --no-same-permissions
fi

echo "=========================================="
echo "  技术边界数据库 - 一致性恢复"
echo "=========================================="
echo "  数据库备份: ${DUMP_FILE}"
echo "  目标数据库: ${PG_DB}"
if [ "$RESTORE_UPLOADS" = "true" ]; then
    echo "  文件对象备份: ${UPLOAD_ARCHIVE}"
    echo "  文件对象目录: ${UPLOAD_PATH}"
else
    echo "  WARNING: 未找到匹配的上传对象备份，将只恢复数据库。"
    echo "  恢复后可能出现数据库记录存在但实体文件缺失。"
fi
echo ""
if [ "$RESTORE_UPLOADS" = "true" ]; then
    echo "  WARNING: 此操作会覆盖现有数据库，并替换上传对象目录。"
else
    echo "  WARNING: 此操作会覆盖现有数据库。"
fi
read -r -p "  确认恢复？输入 yes 继续: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "已取消。"
    exit 0
fi

docker compose --project-directory "$PROJECT_DIR" stop api readonly-agent
SERVICES_STOPPED=true

echo "[$(date)] 单事务重建 schema 并恢复数据库 ..."
{
    printf '%s\n' 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
    gunzip -c "$DUMP_FILE"
} | docker compose --project-directory "$PROJECT_DIR" exec -T db \
    psql --single-transaction -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB"

if [ "$RESTORE_UPLOADS" = "true" ]; then
    previous_uploads="${UPLOAD_PATH}.pre-restore.$(date +%Y%m%d_%H%M%S)"
    if [ -e "$UPLOAD_PATH" ]; then
        mv -- "$UPLOAD_PATH" "$previous_uploads"
        echo "[$(date)] 原上传目录保留于: ${previous_uploads}"
    fi
    mv -- "$STAGE_DIR" "$UPLOAD_PATH"
    STAGE_DIR=""
fi

docker compose --project-directory "$PROJECT_DIR" up -d api readonly-agent
SERVICES_STOPPED=false
echo "[$(date)] OK: 恢复完成。API 启动时将校验文件并执行最新迁移。"
