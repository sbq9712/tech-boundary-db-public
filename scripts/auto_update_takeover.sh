#!/usr/bin/env bash
# 4h auto-update takeover（spec D9）：tech-db 抓取/清洗 → 发布 → 推送 → boundary 同步。
# 由 systemd user timer 每 4 小时调用；全部步骤幂等，失败即非零退出并由 journal 记录。
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
# 更新 hydrate 钉扎（PINS 由 hydrate 脚本自身校验，失败即中断）
python3 - << PY
import re, subprocess
from pathlib import Path
p = Path("scripts/hydrate_breadth_runtime.py")
s = p.read_text(encoding="utf-8")
s = re.sub(r'UPSTREAM_COMMIT = "[^"]+"', f'UPSTREAM_COMMIT = "$PUSHED_SHA"', s)
p.write_text(s, encoding="utf-8")
PY
python3 scripts/sync_breadth_from_techdb.sh

echo "[takeover] $(date -Is) === done ==="
