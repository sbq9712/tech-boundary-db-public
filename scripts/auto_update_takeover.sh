#!/usr/bin/env bash
# 4h auto-update takeover（spec D9）：tech-db 抓取/清洗 → 发布 → 推送 → boundary 同步。
# 由 systemd user timer 每 4 小时调用；全部步骤幂等，失败即非零退出并由 journal 记录。
#
# 【已停用 2026-09-28】本脚本会在本地重跑上游 pipeline 并 git reset --hard 上游工作区。
# 现已改为只读跟随上游 GitHub 发布的方案，请使用：
#   scripts/refresh_breadth_from_techdb.sh
# （systemd 单元 techdb-auto-update.service 已指向新脚本。）
echo "[auto_update_takeover] 已停用：请改用 scripts/refresh_breadth_from_techdb.sh" >&2
exit 1
set -euo pipefail

TECHDB="${TECHDB_DIR:-/home/rhett/tech-db-fresh}"
BOUNDARY="${BOUNDARY_DIR:-/home/rhett/tech-boundary-db}"

echo "[takeover] $(date -Is) === tech-db pipeline start ==="
cd "$TECHDB"
git fetch origin main
git reset --hard origin/main          # 远端为准；本地无独立开发
python3 auto_pipeline.py --all >> runtime/auto_pipeline.log 2>&1
git add data/
if ! git diff --cached --quiet; then
  git commit -q -m "chore(data): auto pipeline nightly publish

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
  git pull --rebase origin main
  git push origin main
  PUSHED_SHA=$(git rev-parse HEAD)
  echo "[takeover] tech-db pushed $PUSHED_SHA"
else
  PUSHED_SHA=$(git rev-parse HEAD)
  echo "[takeover] tech-db 无新数据 ($PUSHED_SHA)"
fi

echo "[takeover] $(date -Is) === boundary breadth hydrate ==="
cd "$BOUNDARY"
git fetch origin main
# 动态改写 hydrate 钉扎：UPSTREAM_COMMIT=刚推送的 SHA；
# DATA_VERSION/RECORDS/SHARDS 从本次管线产物（tech-db manifest）读取，
# 避免静态 pins 在数据演进后失效。PINS 由 hydrate 自身校验，失败即中断。
python3 - << PY
import json, re
from pathlib import Path
techdb = Path("$TECHDB")
manifest_raw = (techdb / "data" / "processed" / "manifest-data.js").read_text(encoding="utf-8")
meta = json.loads(manifest_raw[manifest_raw.find("{"):manifest_raw.rfind("}") + 1])["meta"]
data_version = meta["data_version"]
records = int(meta["records_total"])
shards = int(meta["total_shards"])
p = Path("scripts/hydrate_breadth_runtime.py")
s = p.read_text(encoding="utf-8")
s = re.sub(r'UPSTREAM_COMMIT = "[^"]+"', f'UPSTREAM_COMMIT = "$PUSHED_SHA"', s)
s = re.sub(r'EXPECTED_DATA_VERSION = "[^"]+"', f'EXPECTED_DATA_VERSION = "{data_version}"', s)
s = re.sub(r'EXPECTED_RECORDS = [\d_]+', f'EXPECTED_RECORDS = {records}', s)
s = re.sub(r'EXPECTED_SHARDS = \d+', f'EXPECTED_SHARDS = {shards}', s)
p.write_text(s, encoding="utf-8")
print(f"[takeover] pins -> $PUSHED_SHA {data_version} records={records} shards={shards}")
PY
python3 scripts/sync_breadth_from_techdb.sh

echo "[takeover] $(date -Is) === done ==="
