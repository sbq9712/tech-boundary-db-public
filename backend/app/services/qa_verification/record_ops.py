"""canonical-qa record_ops.py 移植版（2026-09-30，一.1/一.2）——语义与
services/canonical-qa/qa-backend/record_ops.py 逐字一致（无包内依赖，
仅本头三行注释差异）；链 A 专用状态仓，此处副本供 api 容器隔离测试。

一.1（2026-09-30）语义修复：原 server.clear_superseded_by_chunks 在新版本
upsert 落地后把 record_key_sha 移出遮蔽集合——基础索引无法按记录改写，
其中的旧版本因此从「禁止召回」变回「允许召回」（隔离复现）。修复后：

状态模型（全部持久化，原子写 os.replace）：
- tombstones[ksha]        DELETE 已生效：向量/BM25/图谱/引用全链路屏蔽；
- superseded_pending[ksha] record-mutate update 已删旧增量 chunk、新版本
                           尚未确认落地——基础版本屏蔽（等待落地）；
- superseded_landed[ksha]  新版本已确认落地（或导入链直接取代基础版本身
                           份）——基础旧版本「永久失效」。

两个 superseded 状态对检索完全等价（都屏蔽基础索引版本）；区分只为运维
可观测与「等待落地」卡死告警。基础旧版本只要还在基础索引里就永远不能
解除遮蔽——即使新版本随后被 DELETE，也由墓碑继续全链路屏蔽；唯一恢复
通道是显式 unblock（纠错通道）。

持久化格式向后兼容：
- 读取：新键 superseded_pending/superseded_landed；旧键 superseded_key_shas
  视为 pending（旧代码落地即清除，凡持久化的都是等待落地）；
- 写入：同时写旧键 = pending ∪ landed——回滚到旧版本代码时保持遮蔽。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RecordOpsStore:
    """墓碑 + 替换遮蔽的持久化状态仓（依赖注入，便于隔离测试）。

    base_key_shas_fn : () -> list[str]   基础索引每条记录的 record_key_sha；
    remove_chunks_fn : async (keys) -> int  按 record_key_sha 删增量 chunk；
    on_change        : () -> void        状态变化后的钩子（图谱碎片重推）。
    """

    def __init__(self, path, base_key_shas_fn: Callable[[], list] | None = None,
                 remove_chunks_fn=None, on_change: Callable[[], None] | None = None,
                 count_chunks_with_content_fn: Callable[[str, str], int] | None = None):
        self.path = Path(path)
        self.base_key_shas_fn = base_key_shas_fn or (lambda: [])
        self.remove_chunks_fn = remove_chunks_fn
        self.on_change = on_change or (lambda: None)
        self.count_chunks_with_content_fn = count_chunks_with_content_fn
        self.tombstones: dict[str, dict] = {}
        self.superseded_pending: set[str] = set()
        self.superseded_landed: set[str] = set()
        self.deleted_base_positions: set[int] = set()
        self.superseded_base_positions: set[int] = set()
        self.loaded = False

    # ── 兼容视图 ─────────────────────────────────────────────────────
    @property
    def superseded_key_shas(self) -> set[str]:
        """pending ∪ landed（旧字段名兼容视图；检索判定请用 is_base_masked）。"""
        return self.superseded_pending | self.superseded_landed

    def is_base_masked(self, key_sha: str) -> bool:
        k = str(key_sha or "")
        return bool(k) and (k in self.superseded_pending or k in self.superseded_landed)

    def is_deleted_key(self, key_sha: str) -> bool:
        return str(key_sha or "") in self.tombstones

    # ── 持久化 ───────────────────────────────────────────────────────
    def load(self) -> None:
        if self.loaded:
            return
        self.loaded = True
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text("utf-8"))
        except (ValueError, OSError) as exc:
            print(f"[record-ops] WARNING: state read failed ({exc}) — "
                  f"starting from empty state", flush=True)
            return
        self.tombstones = dict(data.get("tombstones") or {})
        pending = data.get("superseded_pending")
        landed = data.get("superseded_landed")
        if pending is None and landed is None:
            # 旧格式：落地即被（错误地）清除，凡持久化的都是等待落地
            pending = data.get("superseded_key_shas") or []
            landed = []
        self.superseded_pending = {str(s) for s in (pending or [])}
        self.superseded_landed = {str(s) for s in (landed or [])}
        self.superseded_pending -= self.superseded_landed
        self.restore_persisted()  # 载入即重算基础遮蔽位置（自洽，不依赖调用方）
        print(f"[startup] Record ops state loaded: {len(self.tombstones)} tombstones, "
              f"{len(self.superseded_pending)} superseded-pending, "
              f"{len(self.superseded_landed)} superseded-landed", flush=True)

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(
            {"tombstones": self.tombstones,
             "superseded_pending": sorted(self.superseded_pending),
             "superseded_landed": sorted(self.superseded_landed),
             # 旧键回滚兼容：旧代码读它并继续遮蔽 pending ∪ landed
             "superseded_key_shas": sorted(self.superseded_key_shas)},
            ensure_ascii=False), "utf-8")
        os.replace(tmp, self.path)

    # ── 变更操作 ─────────────────────────────────────────────────────
    def mark_superseded_landed(self, key_shas: Iterable[str]) -> int:
        """新版本 upsert 确认落地后调用（一.1 修复核心）。

        pending → landed：取代完成，基础旧版本从「等待落地」转为「永久
        失效」——遮蔽保持，绝不解除。导入链直接取代基础版本身份（同
        record_key_sha 且尚未登记）也在此登记为 landed（跨路径同身份去
        重，一.3/一.4）。返回发生变化的数量。"""
        base_shas = None
        n = 0
        for ksha in {str(k or "") for k in key_shas}:
            if not ksha:
                continue
            if ksha in self.superseded_pending:
                self.superseded_pending.discard(ksha)
                self.superseded_landed.add(ksha)
                n += 1
            elif (ksha not in self.superseded_landed):
                if base_shas is None:
                    base_shas = set(self.base_key_shas_fn())
                if ksha in base_shas:
                    self.superseded_landed.add(ksha)
                    n += 1
        if n:
            self._persist()
            self.restore_persisted()
        return n

    def repair_landed_from_incremental(self, alive_key_shas: Iterable[str]) -> int:
        """启动修复：增量索引中存活、且与基础记录同身份的 chunk，登记为
        landed（修复旧版 clear_superseded_by_chunks 遗留的暴露状态）。
        幂等；仅在新增时持久化一次。"""
        base_shas = set(self.base_key_shas_fn())
        fresh = {str(k or "") for k in alive_key_shas} & base_shas \
            - self.superseded_landed - self.superseded_pending
        if fresh:
            self.superseded_landed |= fresh
            self._persist()
            self.restore_persisted()
        return len(fresh)

    async def apply_async(self, ops: list[dict]) -> tuple[int, list[dict]]:
        """执行 record 级变更：删除既有增量 chunk + 基础版本遮蔽/墓碑。

        - delete：增量 chunk 删除 + 墓碑（pending/landed 一并清除——墓碑
          语义更强，恢复只能 unblock）；一.1：此前已 landed 的记录被删除
          后，基础旧版本同样被墓碑屏蔽，不会回归。重发幂等。
        - update：删除旧增量 chunk + pending（等待新版本落地）。一.2 幂等
          协议：op 携带 keep_content_sha（新版本内容哈希）时只删内容不匹
          配的旧 chunk；新版本已在索引则直接登记 landed 并在回执中报告
          surviving_new_chunks>0——超时重发不删除已落地的新版本。
        - unblock：纠错通道——清墓碑 + 清两级遮蔽（不删任何增量 chunk）。

        返回 (applied, details)：details 逐 op 服务端终态
        {op, record_key_sha, final_state: tombstoned|landed|pending|cleared,
         chunks_removed, surviving_new_chunks}——客户端据此推进基线。
        """
        self.load()
        details: list[dict] = []
        plan: list[tuple[str, set[str]]] = []  # (ksha, exclude_content_shas)
        for op in ops:
            ksha = str(op.get("record_key_sha") or "")
            kind = op.get("op")
            if not ksha or kind == "unblock":
                continue
            keep = str(op.get("keep_content_sha") or "")
            plan.append((ksha, {keep} if (keep and kind == "update") else set()))
        removed = 0
        if self.remove_chunks_fn is not None and plan:
            # 同键多 op 罕见；按键聚合 exclude 集
            by_key: dict[str, set[str]] = {}
            for ksha, exc in plan:
                by_key.setdefault(ksha, set()).update(exc)
            removed = await self.remove_chunks_fn(
                list(by_key.keys()), exclude_content_shas=set().union(*by_key.values())
                if by_key else None)
        for op in ops:
            ksha = str(op.get("record_key_sha") or "")
            if not ksha:
                continue
            kind = op.get("op")
            final_state = "cleared"
            chunks_removed = removed if len(ops) == 1 else None
            surviving = 0
            if kind == "delete":
                self.tombstones[ksha] = {
                    "deleted_at": _utcnow(),
                    "reason": str(op.get("reason") or "pipeline-delete")}
                self.superseded_pending.discard(ksha)
                self.superseded_landed.discard(ksha)
                final_state = "tombstoned"
            elif kind == "update":
                self.tombstones.pop(ksha, None)
                keep = str(op.get("keep_content_sha") or "")
                if keep and self.count_chunks_with_content_fn is not None:
                    surviving = self.count_chunks_with_content_fn(ksha, keep)
                    if surviving > 0:
                        # 新版本已在索引：直接「永久失效」而非等待落地
                        self.superseded_pending.discard(ksha)
                        self.superseded_landed.add(ksha)
                        final_state = "landed"
                    else:
                        self.superseded_pending.add(ksha)
                        final_state = "pending"
                else:
                    self.superseded_pending.add(ksha)
                    final_state = "pending"
            elif kind == "unblock":
                self.tombstones.pop(ksha, None)
                self.superseded_pending.discard(ksha)
                self.superseded_landed.discard(ksha)
                final_state = "cleared"
            details.append({"op": kind, "record_key_sha": ksha,
                            "final_state": final_state,
                            "chunks_removed": chunks_removed,
                            "surviving_new_chunks": surviving})
        self._persist()
        self.restore_persisted()
        self.on_change()  # chunk 被移除 → 图谱碎片重推
        print(f"[record-ops] applied {len(ops)} ops: incremental chunks removed="
              f"{removed}, superseded pending={len(self.superseded_pending)}, "
              f"landed={len(self.superseded_landed)}, "
              f"tombstones total={len(self.tombstones)}", flush=True)
        return len(ops), details

    def restore_persisted(self) -> None:
        """从持久化 sha 集合重算基础索引遮蔽位置（幂等；基础索引 meta 在
        进程生命周期内不变）。"""
        shas_by_meta = self.base_key_shas_fn()
        del_positions: set[int] = set()
        sup_positions: set[int] = set()
        for idx, ksha in enumerate(shas_by_meta):
            if ksha in self.tombstones:
                del_positions.add(idx)
            elif self.is_base_masked(ksha):
                sup_positions.add(idx)
        self.deleted_base_positions = del_positions
        self.superseded_base_positions = sup_positions
