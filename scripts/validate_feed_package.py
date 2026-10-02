#!/usr/bin/env python3
"""feed-pkg/v2 增量包独立校验器（第五节）。

对任意 tech-boundary-data-feed 增量包 ZIP 做发布前/导入前的独立体检，
与生成器（scripts/build_feed_package.py）和导入器（backend
app/services/github_import.py）零依赖 —— 纯标准库，可在离线公司
服务器上单独运行：

    python3 validate_feed_package.py <package.zip> [--strict]

校验项（第五节要求逐项落地）：
  - ZIP 安全：成员数/重复成员/路径穿越/单成员与总解压大小上限
  - schema/契约：manifest schema 与必填键、records 白名单字段类型
  - 完整性：records_sha256、manifest 与 records 实际数量对账
  - 一致性：每条记录 id == sha256(json[t,d,u])[:16]（逐字复刻生成器），
    changes.json 的 op/id/v/key 与 records 一致，added/updated/deleted
    计数对账，data_version/generated_at/date 格式
  - 版本单调：同一 key 在 changes 内不重复（重复即断点）
  - --strict：记录缺 u 占位（"sha256:" 前缀）视为警告而非错误

退出码：0 全部通过；1 存在错误；2 用法错误。
输出：逐项 PASS/FAIL/WARN 的普通话报告。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

SCHEMA_V2 = "tech-boundary-feed-package/v2"
SCHEMA_V1 = "tech-boundary-feed-package/v1"
MAX_MEMBERS = 64
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 1536 * 1024 * 1024
PUBLIC_FIELDS = (
    "id", "t", "d", "u", "c", "a", "i", "tg", "tp", "sc", "scd",
    "aip", "as", "kp", "lv", "wr", "cl", "cp", "cln", "dp", "b", "hb",
)
REQUIRED_MANIFEST_KEYS = (
    "schema", "generator", "mode", "date", "record_count",
    "records_sha256", "data_version", "generated_at",
)
REQUIRED_RECORD_KEYS = ("id", "t", "d")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
# 五.2（2026-10-01）独立校验：嵌套字段形态与公开来源准入（与导入端
# github_import._validate_record_shapes / 生成端 public_refusal_reason 同规则）
SCD_SLOTS = ("b", "i", "r", "d", "t")
_LIST_LIMITS = {"kp": (200, 512), "cp": (64, 512)}
_PRIVATE_URL_RE = re.compile(
    r"(?i)localhost|127\.0\.0\.1|0\.0\.0\.0|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
    r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|\.local\b|file://|/home/|/root/"
    r"|C:\\\\Users|[?&](token|key|secret|password|sig)=")


def _shape_errors(rec: dict) -> list[str]:
    """记录级深层形态校验（白名单之外的值域约束）。返回错误串列表。"""
    errs: list[str] = []
    for field, (max_len, max_item) in _LIST_LIMITS.items():
        v = rec.get(field)
        if v is None:
            continue
        if not isinstance(v, list):
            # 历史形态容忍：kp 曾以整串字符串出现（导入端按标量入库）
            if isinstance(v, str) and len(v) <= max_item:
                continue
            # cp 实际生产形态是标量 int：clustering.py 写 0（簇根）/1（子）
            # 聚类父标志——2026-10-01/02 的真实发布包即此形态（T12 演练发现）。
            # 与导入端 github_import._validate_record_shapes 同规则容忍。
            if field == "cp" and isinstance(v, int) and not isinstance(v, bool):
                continue
            errs.append(f"{field} 必须为列表（实际 {type(v).__name__}）")
            continue
        if len(v) > max_len:
            errs.append(f"{field} 条目数 {len(v)} 超上限 {max_len}")
        for item in v:
            if not isinstance(item, (str, int, float)) or isinstance(item, bool) \
                    or len(str(item)) > max_item:
                errs.append(f"{field} 含非法/超长条目")
                break
    v = rec.get("scd")
    if v is not None:
        if isinstance(v, dict):
            if not v or len(v) > len(SCD_SLOTS) or set(v) - set(SCD_SLOTS):
                errs.append(f"scd 键必须为 {SCD_SLOTS} 子集且非空")
            else:
                for k2, v2 in v.items():
                    if not isinstance(v2, (int, float)) or isinstance(v2, bool):
                        errs.append(f"scd[{k2}] 必须为数值（不许嵌套）")
                        break
        elif isinstance(v, str) and len(v) <= 512:
            pass  # 历史标量容忍
        else:
            errs.append("scd 必须为五槽对象（b/i/r/d/t）或历史标量")
    u = str(rec.get("u", ""))
    if u and u != "no-url" and not u.startswith("sha256:"):
        if _PRIVATE_URL_RE.search(u):
            errs.append("u 指向非公开来源（内网/本机/本地路径/内嵌凭据）")
        elif not (u.startswith("http://") or u.startswith("https://")):
            errs.append(f"u 非 http(s) 定位符：{u[:60]!r}")
    return errs


def content_hash(rec: dict) -> str:
    """逐字复刻生成器 content_hash：公开语义字段全集（除 id 外排序序列化）。"""
    ks = sorted(k for k in rec if k != "id")
    raw = json.dumps({k: rec.get(k) for k in ks}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def stable_id(t: str, d: str, u: str) -> str:
    """逐字复刻生成器 stable_id：json.dumps([t, d, u]) 的 SHA-256 前 16 位。"""
    raw = json.dumps([t, d, u], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.passed: list[str] = []

    def ok(self, msg: str) -> None:
        self.passed.append(msg)

    def fail(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def render(self) -> str:
        lines = [f"通过 {len(self.passed)} 项"]
        lines += [f"  ✓ {m}" for m in self.passed]
        if self.warnings:
            lines.append(f"警告 {len(self.warnings)} 项")
            lines += [f"  ⚠ {m}" for m in self.warnings]
        if self.errors:
            lines.append(f"错误 {len(self.errors)} 项")
            lines += [f"  ✗ {m}" for m in self.errors]
        verdict = "校验通过" if not self.errors else "校验失败"
        return f"{verdict}：\n" + "\n".join(lines)


def validate(zip_path: Path, strict: bool = False) -> Report:
    rep = Report()
    # ── ZIP 安全 ──────────────────────────────────────────────────────
    if not zip_path.exists():
        rep.fail(f"文件不存在：{zip_path}")
        return rep
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        rep.fail(f"不是合法的 zip 文件：{exc}")
        return rep
    with zf:
        names = zf.namelist()
        if len(names) > MAX_MEMBERS:
            rep.fail(f"成员数 {len(names)} 超上限 {MAX_MEMBERS}")
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            rep.fail(f"重复成员：{sorted(dupes)}")
        else:
            rep.ok(f"成员无重复（{len(names)} 个）")
        total_uncompressed = 0
        for info in zf.infolist():
            raw_name = info.filename
            if raw_name.startswith("/") or ".." in Path(raw_name).parts or ":" in raw_name:
                rep.fail(f"恶意路径成员：{raw_name!r}")
            if info.file_size > MAX_MEMBER_BYTES:
                rep.fail(f"成员 {raw_name} 解压后 {info.file_size} 字节超单成员上限")
            total_uncompressed += info.file_size
        if total_uncompressed > MAX_TOTAL_UNCOMPRESSED:
            rep.fail(f"总解压大小 {total_uncompressed} 超上限 {MAX_TOTAL_UNCOMPRESSED}")
        else:
            rep.ok(f"zip 安全检查通过（总解压 {total_uncompressed / 1e6:.1f} MB）")
        if "manifest.json" not in names:
            rep.fail("缺少 manifest.json")
            return rep
        if "records.json" not in names:
            rep.fail("缺少 records.json")
            return rep
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except (ValueError, UnicodeDecodeError) as exc:
            rep.fail(f"manifest.json 不是合法 JSON：{exc}")
            return rep
        records_raw = zf.read("records.json")
        changes = None
        changes_raw = None
        if "changes.json" in names:
            changes_raw = zf.read("changes.json")
            try:
                changes = json.loads(changes_raw)
            except (ValueError, UnicodeDecodeError) as exc:
                rep.fail(f"changes.json 不是合法 JSON：{exc}")
                return rep

    # ── manifest 契约 ────────────────────────────────────────────────
    schema = manifest.get("schema")
    if schema not in (SCHEMA_V1, SCHEMA_V2):
        rep.fail(f"schema 不支持：{schema!r}（期望 {SCHEMA_V1}/{SCHEMA_V2}）")
        return rep
    missing_keys = [k for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
    if missing_keys:
        rep.fail(f"manifest 缺键：{missing_keys}")
    else:
        rep.ok("manifest 必填键齐全")
    if manifest.get("mode") not in ("changes", "full", None):
        rep.fail(f"mode 非法：{manifest.get('mode')!r}")
    date = str(manifest.get("date", ""))
    if not _DATE_RE.match(date):
        rep.fail(f"date 格式非法：{date!r}")
    else:
        rep.ok(f"date 格式合法：{date}")

    try:
        records = json.loads(records_raw)
    except (ValueError, UnicodeDecodeError) as exc:
        rep.fail(f"records.json 不是合法 JSON：{exc}")
        return rep
    if not isinstance(records, list):
        rep.fail("records.json 顶层必须是数组")
        return rep

    # ── 完整性 ────────────────────────────────────────────────────────
    actual_sha = hashlib.sha256(records_raw).hexdigest()
    if manifest.get("records_sha256") != actual_sha:
        rep.fail("records_sha256 与 records.json 实际哈希不一致")
    else:
        rep.ok("records_sha256 一致")
    # 五.2：changes.json 字节绑定——篡改变更条目（v 1→99）即刻可判。
    if changes_raw is not None:
        actual_changes_sha = hashlib.sha256(changes_raw).hexdigest()
        if manifest.get("changes_sha256") is None:
            rep.warn("manifest 缺 changes_sha256（旧版生成器产物，建议用新生成器重出）")
        elif manifest.get("changes_sha256") != actual_changes_sha:
            rep.fail("changes_sha256 与 changes.json 实际哈希不一致（changes.json 被篡改）")
        else:
            rep.ok("changes_sha256 一致")
    # 五.2：发布序列自洽性（sequence/predecessor/manifest_digest/chain）。
    # 字段存在即校验（空串/缺失对同侧字段视为不完整包——伪造者不能以
    # 空串绕过哈希核对）；canon 排除 generated_at（打包时刻不参与身份）。
    if "manifest_digest" in manifest or "chain" in manifest:
        canon = {k: v for k, v in manifest.items()
                 if k not in ("manifest_digest", "chain", "generated_at")}
        expect_digest = hashlib.sha256(
            json.dumps(canon, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        if manifest.get("manifest_digest") != expect_digest:
            rep.fail("manifest_digest 与 manifest 规范哈希不一致（manifest 被篡改）")
        else:
            expect_chain = hashlib.sha256(
                (str(manifest.get("predecessor", "")) + expect_digest).encode("utf-8")).hexdigest()
            if manifest.get("chain") != expect_chain:
                rep.fail("chain 与 sha256(predecessor+manifest_digest) 不一致（链被伪造/插包）")
            else:
                rep.ok(f"发布序列自洽（sequence={manifest.get('sequence')}）")
        if manifest.get("sequence") is not None and \
                (not isinstance(manifest.get("sequence"), int) or manifest["sequence"] < 1):
            rep.fail(f"sequence 非法：{manifest.get('sequence')!r}")
    if manifest.get("record_count") != len(records):
        rep.fail(f"record_count {manifest.get('record_count')} != 实际 {len(records)}")
    else:
        rep.ok(f"record_count 对账一致（{len(records)} 条）")

    # ── 记录级校验：字段/类型/id/白名单 ──────────────────────────────
    bad_private: list[str] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            rep.fail(f"records[{i}] 不是对象")
            continue
        for key in REQUIRED_RECORD_KEYS:
            if key not in rec:
                rep.fail(f"records[{i}] 缺必填键 {key}")
        if set(rec.keys()) - set(PUBLIC_FIELDS):
            bad_private.append(f"records[{i}]")
        rec_id = str(rec.get("id", ""))
        if rec_id and rec_id != stable_id(str(rec.get("t", "")), str(rec.get("d", "")),
                                          str(rec.get("u", ""))):
            rep.fail(f"records[{i}] id 与 sha256(t|d|u)[:16] 不一致（键漂移或伪造）")
        for msg in _shape_errors(rec):
            rep.fail(f"records[{i}] {msg}")
        u = str(rec.get("u", ""))
        if strict and u.startswith("sha256:"):
            rep.warn(f"records[{i}] 无 URL（u 为内容占位，键随内容变化）")
    if bad_private:
        rep.fail(f"包内出现白名单外字段：{bad_private[:5]}（私有字段泄漏风险）")
    else:
        rep.ok("记录字段全部在白名单内")

    if schema == SCHEMA_V1:
        rep.warn("v1 全量包：changes 校验跳过（v1 无增量语义）")
        return rep

    # ── v2 changes 一致性 ────────────────────────────────────────────
    if changes is None:
        rep.fail("v2 包缺少 changes.json")
        return rep
    if not isinstance(changes, list):
        rep.fail("changes.json 顶层必须是数组")
        return rep
    record_by_id = {str(r.get("id")): r for r in records if isinstance(r, dict)}
    seen_keys: set[str] = set()
    op_count = {"ADD": 0, "UPDATE": 0, "DELETE": 0}
    # 键规范串（t|d|u 拼接）→ 记录 id；含 "|" 的标题不可反拆，只能正向推导
    expect_key_by_id: dict[str, str] = {}
    for rec in records:
        if isinstance(rec, dict) and rec.get("id"):
            expect_key_by_id[str(rec["id"])] = "|".join(
                (str(rec.get("t", "")), str(rec.get("d", "")), str(rec.get("u", ""))))
    for j, ch in enumerate(changes):
        if not isinstance(ch, dict):
            rep.fail(f"changes[{j}] 不是对象")
            continue
        op = ch.get("op")
        if op not in op_count:
            rep.fail(f"changes[{j}] op 非法：{op!r}")
            continue
        op_count[op] += 1
        cid = str(ch.get("id", ""))
        key_str = str(ch.get("key", ""))
        v = ch.get("v")
        if not isinstance(v, int) or v < 1:
            rep.fail(f"changes[{j}] v 必须为 ≥1 整数，实际 {v!r}")
        if key_str in seen_keys:
            rep.fail(f"changes[{j}] key 重复出现（增量断点）：{key_str[:60]}")
        seen_keys.add(key_str)
        if cid and op in ("ADD", "UPDATE"):
            expect_key = expect_key_by_id.get(cid)
            if expect_key is not None and key_str != expect_key:
                rep.fail(f"changes[{j}] key 与记录 t|d|u 不一致")
        if op == "DELETE":
            if cid in record_by_id:
                rep.fail(f"changes[{j}] DELETE 的记录仍出现在 records.json")
        else:
            rec = record_by_id.get(cid)
            if rec is None:
                rep.fail(f"changes[{j}] {op} 的 id 在 records.json 中不存在")
            else:
                if content_hash(rec) != ch.get("hash") and ch.get("hash") is not None:
                    rep.fail(f"changes[{j}] hash 与记录内容不一致")
    for op, n in op_count.items():
        mk = f"{op.lower()}" if op != "ADD" else "added"
        mk = {"ADD": "added", "UPDATE": "updated", "DELETE": "deleted"}[op]
        if manifest.get(mk) is not None and manifest.get(mk) != n:
            rep.fail(f"manifest.{mk} {manifest.get(mk)} != changes 实际 {n}")
        else:
            rep.ok(f"{op} 计数对账一致（{n}）")
    if manifest.get("change_count") not in (None, len(changes)):
        rep.fail(f"manifest.change_count {manifest.get('change_count')} != {len(changes)}")
    if manifest.get("mode") == "changes" and not changes:
        rep.warn("changes 模式但 0 条变更（空包，可能水印未推进）")
    dv = str(manifest.get("data_version", ""))
    if dv and not re.match(r"^[0-9a-f]{8,64}$", dv):
        rep.warn(f"data_version 形态异常：{dv[:20]}…")
    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="feed-pkg 增量包独立校验器")
    parser.add_argument("package", type=Path, help="待校验的 .zip 包路径")
    parser.add_argument("--strict", action="store_true",
                        help="无 URL 占位记录视为警告并逐条列出")
    args = parser.parse_args(argv)
    rep = validate(args.package, strict=args.strict)
    print(rep.render())
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
