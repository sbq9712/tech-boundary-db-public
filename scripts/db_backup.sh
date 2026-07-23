#!/bin/bash
# 技术边界数据库 — PostgreSQL 定时备份脚本
#
# 用法（crontab 每天凌晨 3 点跑一次）:
#   0 3 * * * /path/to/v260723/scripts/db_backup.sh >> /var/log/techdb-backup.log 2>&1
#
# 或手动执行：
#   cd /path/to/v260723 && ./scripts/db_backup.sh
#
# 备份文件：backup/techdb_YYYYMMDD_HHMMSS.sql.gz
# 保留最近 30 份，超出的自动删除。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/backup"
KEEP_COUNT="${TECHDB_BACKUP_KEEP:-30}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DUMP_FILE="${BACKUP_DIR}/techdb_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

# 从 docker-compose 环境读取数据库凭据
if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

PG_DB="${POSTGRES_DB:-tech_intel}"
PG_USER="${POSTGRES_USER:-techdb}"
PG_CONTAINER="${TECHDB_DB_CONTAINER:-v260723-db-1}"

echo "[$(date)] 开始备份 ${PG_DB} ..."

# 通过 docker exec 执行 pg_dump，压缩输出到文件
if ! docker exec "$PG_CONTAINER" pg_dump -U "$PG_USER" -d "$PG_DB" --no-owner --no-acl 2>/dev/null | gzip > "$DUMP_FILE"; then
    echo "[$(date)] ERROR: 备份失败：无法连接容器 ${PG_CONTAINER}"
    echo "    确认 Docker 正在运行且容器名正确。"
    echo "    如果容器名不同，设置 TECHDB_DB_CONTAINER 环境变量。"
    exit 1
fi

FILE_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "[$(date)] OK: 备份完成: ${DUMP_FILE} (${FILE_SIZE})"

# 清理旧备份，只保留最近 KEEP_COUNT 份
cd "$BACKUP_DIR"
BACKUP_COUNT=$(ls -1 techdb_*.sql.gz 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt "$KEEP_COUNT" ]; then
    REMOVE_COUNT=$((BACKUP_COUNT - KEEP_COUNT))
    ls -1t techdb_*.sql.gz | tail -n "$REMOVE_COUNT" | while read -r old_file; do
        rm -f "$old_file"
        echo "[$(date)] 已清理旧备份: ${old_file}"
    done
    echo "[$(date)] 清理完成，删除了 ${REMOVE_COUNT} 份旧备份，保留 ${KEEP_COUNT} 份。"
fi