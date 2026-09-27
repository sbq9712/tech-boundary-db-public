#!/usr/bin/env bash
# 广度追踪自动刷新：只读跟随上游 tech-db（GitHub main）的数据发布。
# - 不修改上游仓库 / 上游管线 / 上游 Actions 定时任务；
# - 不在本机重跑上游 pipeline，不执行 git reset --hard，不 push；
# - 上游 main 的 data_version 有变化时：改写 hydrate 钉扎 → 下载+校验+派生+安装；
#   breadth/data/processed 不入 Git（gitignore），web 容器以只读卷挂载该目录，
#   安装完成即对浏览器生效（nginx 对 .js/.json 均为 no-store）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HYDRATE="$ROOT/scripts/hydrate_breadth_runtime.py"
REPO="sbq9712/tech-db"
REMOTE="https://github.com/${REPO}.git"
TAG="[breadth-refresh $(date '+%F %T')]"

log() { echo "$TAG $*"; }

sha="$(git ls-remote "$REMOTE" refs/heads/main | awk '{print $1}')"
if [ -z "$sha" ]; then
  log "ERROR: 无法读取上游 main SHA（网络/远端异常）" >&2
  exit 1
fi

pinned="$(sed -n 's/^UPSTREAM_COMMIT = "\([0-9a-f]\{40\}\)".*/\1/p' "$HYDRATE")"
stamp_commit="$(python3 -c "import json;print(json.load(open('$ROOT/breadth/data/processed/.techdb-runtime-source.json')).get('commit',''))" 2>/dev/null || true)"

if [ "$sha" = "$pinned" ] && [ "$sha" = "$stamp_commit" ]; then
  log "上游未变化（${sha:0:12}），跳过。"
  exit 0
fi
log "检测到上游更新：pinned=${pinned:0:12} stamp=${stamp_commit:0:12} -> main=${sha:0:12}"

meta="$(mktemp)"
trap 'rm -f "$meta"' EXIT
curl -fsSL --retry 3 --retry-delay 2 --max-time 120 \
  "https://raw.githubusercontent.com/${REPO}/${sha}/data/processed/manifest-data.js" \
  -o "$meta"

read -r data_version records shards < <(python3 - "$meta" <<'PY'
import json, sys
raw = open(sys.argv[1], encoding="utf-8").read()
meta = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])["meta"]
print(meta["data_version"], int(meta["records_total"]), int(meta["total_shards"]))
PY
)
log "上游 meta：data_version=$data_version records=$records shards=$shards"

# 改写 hydrate 钉扎。EXPECTED_UPSTREAM_FILES 置 None：
# 安装后的逐文件 size+sha256 清单校验（stamp inventory）已完整覆盖完整性。
python3 - "$HYDRATE" "$sha" "$data_version" "$records" "$shards" <<'PY'
import re, sys
path, sha, dv, rec, sh = sys.argv[1:6]
s = open(path, encoding="utf-8").read()
s = re.sub(r'UPSTREAM_COMMIT = "[0-9a-f]+"', f'UPSTREAM_COMMIT = "{sha}"', s)
s = re.sub(r'EXPECTED_DATA_VERSION = "[^"]+"', f'EXPECTED_DATA_VERSION = "{dv}"', s)
s = re.sub(r'EXPECTED_RECORDS = [\d_]+', f'EXPECTED_RECORDS = {rec}', s)
s = re.sub(r'EXPECTED_SHARDS = \d+', f'EXPECTED_SHARDS = {sh}', s)
s = re.sub(r'EXPECTED_UPSTREAM_FILES = (None|[\d_]+)', 'EXPECTED_UPSTREAM_FILES = None', s)
open(path, "w", encoding="utf-8").write(s)
print(f"[breadth-refresh] 钉扎已更新 -> {sha[:12]} {dv} records={rec} shards={sh}")
PY

# 下载（~282MB，--depth=1 --filter=blob:none 仅取 data/processed）+ 校验 + 派生快照 + 安装
python3 "$HYDRATE" --force
log "广度运行时已刷新到 ${sha:0:12}（data_version=$data_version，records=$records）。web 容器即时生效。"
