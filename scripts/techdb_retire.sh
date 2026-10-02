#!/usr/bin/env bash
# tech-db 退役演练脚本（T1，2026-10-02）
#
# 用途：打印退役核对清单的「逐条命令 + 预期输出」，供人工核对后手工执行。
# 安全设计：
#   - 默认（无参 / --dry-run）：只 echo 演练，绝不执行任何 systemctl/curl 写操作；
#   - --execute：仍要求环境变量 TECHDB_RETIRE_CONFIRM=I-AM-SURE 才会真正执行，
#     且本脚本的操作范围明确排除 ~/tech-db-fresh 与其 systemd 单元（不删数据、
#     不动 tech-db-fresh——那是维护者手动范围）。
# 退出码：0=演练完成；2=参数/确认错误。

set -euo pipefail

MODE="dry-run"
[[ "${1:-}" == "--execute" ]] && MODE="execute"
[[ "${1:-}" == "--dry-run" || -z "${1:-}" ]] && MODE="dry-run"
if [[ "${1:-}" != "" && "${1:-}" != "--execute" && "${1:-}" != "--dry-run" ]]; then
  echo "用法: $0 [--dry-run|--execute]" >&2; exit 2
fi

RUN() {  # RUN <描述> <命令...>
  local desc="$1"; shift
  echo "  \$ $*"
  if [[ "$MODE" == "execute" ]]; then
    "$@"
  else
    echo "    [dry-run] 未执行——人工核对后用 --execute 或直接复制运行"
  fi
}
SAY() { echo; echo "── $* ──────────────────────────────────"; }

echo "tech-db 退役${MODE}（$(date '+%F %T')）"
[[ "$MODE" == "execute" ]] && {
  if [[ "${TECHDB_RETIRE_CONFIRM:-}" != "I-AM-SURE" ]]; then
    echo "✗ --execute 需要环境变量 TECHDB_RETIRE_CONFIRM=I-AM-SURE（防误触）" >&2
    exit 2
  fi
  echo "⚠ execute 模式：仍不删除任何文件/仓库；~/tech-db-fresh 与其 systemd 单元不在操作范围。"
}

SAY "1/4 删库前置确认（只读检查，始终真实执行）"
RUN "新链定时器状态" systemctl --user list-timers breadth-pipeline.timer
RUN "新链近 24h 运行记录（找 failure）" journalctl --user -u breadth-pipeline -S "-24 hours" --no-pager
RUN "QA 基础索引健康" curl -s http://127.0.0.1:8767/api/health
echo "  预期：timer active；journal 无 failure（exit 3 部分成功为设计态）；health JSON total_records 与发布视图一致、incremental_index_ready=true"

SAY "2/4 停用旧链（顺序：先隧道/服务，后确认 404）"
RUN "停用全部旧单元" systemctl --user disable --now techdb-tunnel techdb-server techdb-data-sync.timer techdb-pipeline.timer techdb-graph.timer techdb-vector.timer techdb-auto-update.service techdb-auto-update.timer
echo "  预期输出：Removed \"/home/rhett/.config/systemd/user/...\" ×N；然后旧站隧道断开"
RUN "确认旧站 404" curl -sI https://sbq9712.github.io/tech-db/
echo "  预期首行：HTTP/2 404（Pages 需在 GitHub 网页手动关闭——CLI 关不了，这是已知边界）"

SAY "3/4 删库后验证（tech-boundary-db 全链路无 tech-db 依赖）"
RUN "api 日志查残留引用" docker compose logs api --since 4h
RUN "canonical-qa 日志查残留引用" docker compose logs canonical-qa --since 4h
RUN "仓库生产路径 grep" bash -c "grep -rn 'tech-db' --include='*.py' --include='*.sh' --include='*.yml' backend/ pipeline/ scripts/ docker-compose.yml | grep -v tech-boundary | grep -v retire || true"
echo "  预期：无 /home/rhett/tech-db* 路径、无 techdb-* 单元名报错；grep 无生产路径命中"

SAY "4/4 数据漂移核对（默认结论：以新库为准，无需补齐）"
cat <<'NOTE'
  旧库 69,471 vs 新库 69,368（差 103 = 2h/4h 步调差，非丢数据）。
  差异查询（删库前在两库各跑一次，按 content_hash 双向 EXCEPT）：
    psql -c "COPY (SELECT content_hash FROM breadth ORDER BY 1) TO STDOUT" > /tmp/<old|new>.hash
    diff /tmp/old.hash /tmp/new.hash | grep '^<' | wc -l   # 旧有新无
  判断：全部 >7 天前 → 无需补齐；含近 7 天 → 手动导入最近 feed 包并查 4h 定时器。
 详见 docs/tech-db-retirement.md 第 4 节。
NOTE

echo
echo "✔ 退役${MODE}演练完成。真正的删除（~/tech-db、GitHub 仓库、Pages）由维护者手动执行。"
