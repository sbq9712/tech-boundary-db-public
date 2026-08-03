#!/bin/bash
# 技术边界数据库一致性备份：PostgreSQL + 上传对象
# 用法：cd /path/to/project && ./scripts/db_backup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/backup"
KEEP_COUNT="${TECHDB_BACKUP_KEEP:-30}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DUMP_FILE="${BACKUP_DIR}/techdb_${TIMESTAMP}.sql.gz"
UPLOAD_ARCHIVE="${BACKUP_DIR}/uploads_${TIMESTAMP}.tar.gz"
MANIFEST_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.sha256"
DUMP_PART="${DUMP_FILE}.part"
UPLOAD_PART="${UPLOAD_ARCHIVE}.part"

mkdir -p "$BACKUP_DIR"

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

if [ ! -d "$UPLOAD_PATH" ] || [ ! -r "$UPLOAD_PATH" ]; then
    echo "[$(date)] ERROR: 上传目录不存在或不可读: ${UPLOAD_PATH}"
    exit 1
fi

cleanup_parts() {
    rm -f -- "$DUMP_PART" "$UPLOAD_PART"
}
trap cleanup_parts EXIT

echo "[$(date)] 开始备份数据库 ${PG_DB} ..."
if ! docker compose --project-directory "$PROJECT_DIR" exec -T db \
    pg_dump -U "$PG_USER" -d "$PG_DB" --no-owner --no-acl 2>/dev/null | gzip > "$DUMP_PART"; then
    echo "[$(date)] ERROR: 数据库备份失败"
    exit 1
fi
mv -- "$DUMP_PART" "$DUMP_FILE"

# 文件对象一经落盘不再修改。数据库快照先于文件归档，可保证所有 DB 引用都能进入归档。
echo "[$(date)] 开始备份上传对象 ${UPLOAD_PATH} ..."
if ! tar --exclude='./.incoming' -C "$UPLOAD_PATH" -czf "$UPLOAD_PART" .; then
    rm -f -- "$DUMP_FILE"
    echo "[$(date)] ERROR: 上传对象备份失败，已移除不完整的数据库单份备份"
    exit 1
fi
mv -- "$UPLOAD_PART" "$UPLOAD_ARCHIVE"

(
    cd "$BACKUP_DIR"
    sha256sum "$(basename "$DUMP_FILE")" "$(basename "$UPLOAD_ARCHIVE")" > "$(basename "$MANIFEST_FILE")"
)

echo "[$(date)] OK: 一致性备份完成"
echo "  数据库: ${DUMP_FILE}"
echo "  文件对象: ${UPLOAD_ARCHIVE}"
echo "  校验清单: ${MANIFEST_FILE}"

# 按数据库备份时间戳清理整组旧备份。
mapfile -t OLD_DUMPS < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'techdb_*.sql.gz' -printf '%T@ %p\n' | sort -nr | tail -n +$((KEEP_COUNT + 1)) | cut -d' ' -f2-)
for old_dump in "${OLD_DUMPS[@]}"; do
    base="$(basename "$old_dump")"
    old_timestamp="${base#techdb_}"
    old_timestamp="${old_timestamp%.sql.gz}"
    rm -f -- \
        "$old_dump" \
        "${BACKUP_DIR}/uploads_${old_timestamp}.tar.gz" \
        "${BACKUP_DIR}/backup_${old_timestamp}.sha256"
    echo "[$(date)] 已清理旧备份组: ${old_timestamp}"
done
