#!/usr/bin/env bash
# tech-db → tech-boundary-db 广度数据同步（4h auto-update 接管的一部分）。
# 前置：tech-db 侧 pipeline 已完成并 push 到 GitHub main。
# 动作：hydrate breadth runtime（含派生文件）→ 校验 → 可选重建 canonical-qa 资产清单。
# 幂等：hydrate 内部有合法快照复用 + 失败即非零退出，调用方（systemd timer）记录日志。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[sync] $(date -Is) hydrating breadth runtime from pinned upstream commit ..."
python3 scripts/hydrate_breadth_runtime.py

echo "[sync] $(date -Is) breadth runtime up to date."
