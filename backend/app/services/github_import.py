"""GitHub 广度情报增量包导入（docs/design/github-incremental-dedup.md 契约实现）。

v2（feed-pkg/v2，changes 模式）：
  daily/YYYY-MM-DD.zip（manifest.json + records.json + changes.json）由管理员
  上传到【资料库-广度追踪-GitHub广度情报】，本服务解包、校验（含 zip 安全与
  records_sha256 完整性），按 changes.json 应用增量：
    - ADD/UPDATE 携带记录完整最新版（records.json）与 per-key 单调版本 v；
      v 低于库内既有版本的更新被拒绝（旧不覆新），同版本同内容幂等跳过；
    - DELETE 只删除 feed 侧来源的记录（人工/其他广度情报来源受保护，不误删）；
    - 每条新增/更新记录与索引删除均入队 breadth_index_tasks（持久队列，
      由后台 worker 写 canonical-qa 增量索引，失败重试、重启续跑）。

安全边界（五节）：绝不执行包内代码；解包前检查成员数/重复成员/恶意路径/
单成员与总解压大小上限；记录字段经正向白名单过滤后才入库（record_json 只存
白名单字段）；records_sha256 保证包字节完整性。

v1（feed-pkg/v1，full-slice）兼容：只增不改的旧契约；首包字段同样白名单
过滤；同键撞人工记录/上游分片跳过。v2 首包（水印为空 → 全量 ADD）会把
v1 历史导入行升级为 feed 托管并按 v=1 应用字段，不产生重复行。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
import zipfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.models.breadth_import_session import BreadthImportSession
from app.models.breadth_manual_record import BreadthManualRecord
from app.models.feed_tombstone import FeedTombstone
from app.models.uploaded_file import UploadedFile

logger = logging.getLogger(__name__)

SCHEMA_V1 = "tech-boundary-feed-package/v1"
SCHEMA_V2 = "tech-boundary-feed-package/v2"
SCHEMA_EXPECTED = SCHEMA_V2

# 与 scripts/build_feed_package.py PUBLIC_FIELDS 逐字对齐（漂移由 contract tests 把关）
PUBLIC_FIELDS = (
    "id", "t", "d", "u", "c", "a", "i", "tg", "tp", "sc", "scd", "aip",
    "as", "kp", "lv", "wr", "cl", "cp", "cln", "dp", "b", "hb",
)

MAX_PACKAGE_RECORDS = 200_000
MAX_MEMBERS = 64
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 1536 * 1024 * 1024
_BODY_CAP = 20_000          # 入库截断（record.body 实际上限）
_BODY_HARD_REJECT = 200_000  # 入口拒绝线（T12：真实包存在 27k/91k 正文——
                              # 自家生成器原样导出，20k 拒包会让每日增量全拒；
                              # 入库侧仍按 _BODY_CAP 截断，两线分离）

_UPSTREAM_CACHE_VERSIONS = 2
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_ID_RE = re.compile(r"[0-9a-f]{16}")


class GitHubPackageError(ValueError):
    """包结构/校验不合规——上传应被拒绝（400），不入库不落会话。"""


def validate_github_filename(filename: str | None) -> str:
    """增量包文件名校验：无路径成分、必须 .zip 结尾。"""
    if not filename:
        raise GitHubPackageError("缺少文件名")
    name = os.path.basename(filename)
    if name != filename:
        raise GitHubPackageError("文件名不能包含路径")
    if not name.lower().endswith(".zip"):
        raise GitHubPackageError("GitHub 增量包必须是 .zip 文件（daily/YYYY-MM-DD.zip）")
    return ".zip"


# ── 键/哈希工具（与 feed 侧逐字对齐） ─────────────────────────────────────


def _dedup_key(title: str, date: str, url: str) -> tuple[str, str, str]:
    return (str(title or "").strip(), str(date or ""), str(url or ""))


def _key_digest(key: tuple[str, str, str]) -> bytes:
    return hashlib.md5("|".join(key).encode("utf-8")).digest()


def _feed_key_digest_hex(key_str: str) -> str:
    return hashlib.md5(key_str.encode("utf-8")).hexdigest()


def _stable_id(t: str, d: str, u: str) -> str:
    raw = json.dumps([t, d, u], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _v2_content_hash(rec: dict) -> str:
    """与 feed 侧 content_hash(rec) 完全一致：全部公开字段（除 id）。"""
    payload = {k: rec.get(k) for k in sorted(k for k in rec if k != "id")}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _filter_public(rec: dict) -> dict:
    """正向白名单过滤：白名单外字段（cm/fb/sr/source/本地路径/密钥…）不落地。"""
    return {k: rec[k] for k in PUBLIC_FIELDS if k in rec}


# ── 上游基线（只读） ──────────────────────────────────────────────────────


def _breath_data_root() -> Path:
    """上游分片根目录（容器内 /app/breadth_data；本地/测试可用环境变量覆盖）。"""
    root = Path(os.environ.get("BREADTH_DATA_PATH", "/app/breadth_data"))
    if not root.exists():
        repo_root = Path(__file__).resolve().parents[3]
        root = repo_root / "breadth" / "data"
    return root


def _upstream_data_version(root: Path) -> str:
    manifest = root / "processed" / "manifest-data.js"
    try:
        raw = manifest.read_text(encoding="utf-8")
        meta = json.loads(raw[raw.find("{"):raw.rfind("}") + 1]).get("meta", {})
        return str(meta.get("data_version", ""))
    except (OSError, ValueError):
        return ""


@lru_cache(maxsize=_UPSTREAM_CACHE_VERSIONS)
def _upstream_key_digests(data_version: str, root_str: str) -> frozenset[bytes]:
    """上游分片（lite-part-*.js）全量 t|d|u 键摘要集合，按 data_version 进程内缓存。"""
    root = Path(root_str)
    digests: set[bytes] = set()
    processed = root / "processed"
    if not processed.is_dir():
        return frozenset()
    for shard in sorted(processed.glob("lite-part-*.js")):
        try:
            raw = shard.read_text(encoding="utf-8")
        except OSError:
            continue
        start = raw.find(".push(")
        end = raw.rfind(");")
        if start < 0 or end < 0:
            continue
        try:
            records = json.loads(raw[start + 6:end])
        except ValueError:
            continue
        for rec in records:
            url = str(rec.get("u", "") or "")
            digests.add(_key_digest(_dedup_key(rec.get("t", ""), str(rec.get("d", "")), url)))
    return frozenset(digests)


def _github_upload_ids(db: Session) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(UploadedFile.id).where(UploadedFile.breadth_source == "github")
        ).all()
    )


# ── 解包与校验（zip 安全） ────────────────────────────────────────────────


def _read_package(zip_path: Path) -> tuple[dict, list[dict], list[dict] | None]:
    """解包 + 结构/完整性校验。返回 (manifest, records, changes|None)。

    只按名单读 manifest/records/changes 三个成员：不解压到磁盘、
    不执行包内代码、不受路径穿越影响（按名读取）。
    """
    try:
        with zipfile.ZipFile(zip_path) as zf:
            infos = zf.infolist()
            names = [i.filename for i in infos]
            if len(names) > MAX_MEMBERS:
                raise GitHubPackageError(f"包内成员数异常（{len(names)} > {MAX_MEMBERS}）")
            if len(names) != len(set(names)):
                raise GitHubPackageError("包内存在重复成员名")
            total = 0
            for info in infos:
                raw_name = info.filename
                if (
                    raw_name.startswith("/")
                    or ".." in Path(raw_name).parts
                    or "\\" in raw_name
                    or ":" in raw_name
                ):
                    raise GitHubPackageError(f"包内存在非法成员路径：{raw_name!r}")
                if info.file_size > MAX_MEMBER_BYTES:
                    raise GitHubPackageError(
                        f"包内成员超大：{raw_name}（{info.file_size} 字节）"
                    )
                total += info.file_size
            if total > MAX_TOTAL_UNCOMPRESSED:
                raise GitHubPackageError(f"包总解压大小异常（{total} 字节）")
            for required in ("manifest.json", "records.json"):
                if required not in names:
                    raise GitHubPackageError(f"增量包缺少 {required}")
            try:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                records_json = zf.read("records.json").decode("utf-8")
                changes_json = (
                    zf.read("changes.json").decode("utf-8")
                    if "changes.json" in names else None
                )
            except (ValueError, UnicodeDecodeError) as exc:
                raise GitHubPackageError(f"manifest/records JSON 解析失败：{exc}") from exc
    except zipfile.BadZipFile as exc:
        raise GitHubPackageError("不是合法的 zip 文件") from exc

    if not isinstance(manifest, dict):
        raise GitHubPackageError("manifest.json 必须是对象")
    schema = str(manifest.get("schema", ""))
    if schema not in (SCHEMA_V1, SCHEMA_V2):
        raise GitHubPackageError(
            f"manifest.schema 应为 {SCHEMA_V1}/{SCHEMA_V2}，实际 {schema!r}"
        )
    records_sha = str(manifest.get("records_sha256", "") or "")
    if not records_sha:
        raise GitHubPackageError("manifest 缺少 records_sha256")
    if hashlib.sha256(records_json.encode("utf-8")).hexdigest() != records_sha:
        raise GitHubPackageError("records_sha256 校验失败（包内容被篡改或不完整）")
    try:
        records = json.loads(records_json)
    except ValueError as exc:
        raise GitHubPackageError(f"records.json JSON 解析失败：{exc}") from exc
    if not isinstance(records, list):
        raise GitHubPackageError("records.json 必须是数组")
    if len(records) > MAX_PACKAGE_RECORDS:
        raise GitHubPackageError(f"包内记录数异常（{len(records)} > {MAX_PACKAGE_RECORDS}）")
    declared_records = manifest.get("record_count")
    if declared_records is not None and int(declared_records) != len(records):
        raise GitHubPackageError(
            f"manifest.record_count（{declared_records}）与 records.json 实际条数（{len(records)}）不一致"
        )
    package_date = str(manifest.get("date", "") or "").strip()
    if not _DATE_RE.fullmatch(package_date):
        raise GitHubPackageError(f"manifest.date 格式非法：{package_date}（期望 YYYY-MM-DD）")

    changes: list[dict] | None = None
    if schema == SCHEMA_V2:
        if str(manifest.get("mode", "")) != "changes":
            raise GitHubPackageError("v2 包 manifest.mode 必须为 changes")
        if changes_json is None:
            raise GitHubPackageError("v2 包缺少 changes.json")
        # 五.2（2026-10-01）：changes.json 字节绑定 + 发布序列自洽性。
        # changes_sha256 缺失=旧生成器产物（诚实放行并留待重出）；
        # 存在则必须一致——篡改变更条目（如 v 1→99）即刻可判。
        changes_sha = manifest.get("changes_sha256")
        if changes_sha is not None \
                and changes_sha != hashlib.sha256(changes_json.encode("utf-8")).hexdigest():
            raise GitHubPackageError(
                "changes_sha256 校验失败（changes.json 被篡改或与 manifest 不配套）")
        if "manifest_digest" in manifest or "chain" in manifest:
            # 字段存在即校验（空串不能绕过）；canon 排除 generated_at
            canon = {k: v for k, v in manifest.items()
                     if k not in ("manifest_digest", "chain", "generated_at")}
            expect_digest = hashlib.sha256(
                json.dumps(canon, sort_keys=True,
                           ensure_ascii=False).encode("utf-8")).hexdigest()
            if manifest.get("manifest_digest") != expect_digest:
                raise GitHubPackageError(
                    "manifest_digest 校验失败（manifest 被篡改）")
            expect_chain = hashlib.sha256(
                (str(manifest.get("predecessor", ""))
                 + expect_digest).encode("utf-8")).hexdigest()
            if manifest.get("chain") != expect_chain:
                raise GitHubPackageError(
                    "chain 校验失败（sha256(predecessor+manifest_digest) 不一致——"
                    "链被伪造/插包/改包）")
            seq = manifest.get("sequence")
            if seq is not None and (isinstance(seq, bool) or not isinstance(seq, int)
                                    or seq < 1):
                raise GitHubPackageError(f"manifest.sequence 非法：{seq!r}")
        try:
            changes = json.loads(changes_json)
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubPackageError(f"changes.json 解析失败：{exc}") from exc
        _validate_changes(manifest, records, changes)
    else:
        for i, rec in enumerate(records):
            if not isinstance(rec, dict):
                raise GitHubPackageError(f"records.json 第 {i} 项不是对象")
    return manifest, records, changes


# 六.2（2026-10-01）嵌套字段/类型约束（白名单之外的深层校验）与公开来源准入。
_FIELD_LIMITS = {
    "t": ("str", 2000), "d": ("date", 10), "u": ("url", 1024), "c": ("str", 64),
    "a": ("str", 512), "i": ("scalar", 4), "tg": ("str", 512), "tp": ("str", 512),
    # sc/i 的历史契约容忍标量（int/float/短字符串，如 sc=7.0、i=1）——消费端
    # str() 归一；六.2 校验按标量+限量约束而非硬性字符串。
    # 五.2 修复：lv 真实数据为 int 1/2/3（683 条）——原 ("str",32) 会整包误拒
    "sc": ("scalar", 16), "as": ("str", 8000), "lv": ("scalar", 32), "wr": ("str", 512),
    # cl/cln/dp 同为标量容忍（历史包中可为数值，如 dp=3 聚类深度）
    "cl": ("scalar", 512), "cln": ("scalar", 512), "dp": ("scalar", 512),
    "b": ("str", _BODY_HARD_REJECT), "hb": ("int", 2), "aip": ("int", 1),
}
_INT_RANGES = {"hb": (1, 2), "aip": (0, 1)}
_LIST_LIMITS = {"kp": (200, 512), "cp": (64, 512)}
# 五.2 修复（2026-10-01）：scd 原挂在 _LIST_LIMITS["scd"]=(1,64)——校验把
# 「键数 ≤ max_len=1」当上限，真实五维评分 {"b","i","r","d","t"} 全部被拒
# （41,812/69,131 条真实记录形态），整包导入失败。scd 是固定五槽对象，
# 单独校验：键 ⊆ 五槽、值数值、非空；历史标量形态（str ≤512）容忍。
_SCD_SLOTS = ("b", "i", "r", "d", "t")
# 公开来源准入（六.2）：私有/内网定位符不得进入公开包记录。
_PRIVATE_URL_RE = re.compile(
    r"^(?!https?://)"                       # 仅接受 http(s)
    r"|localhost|127\.0\.0\.1|0\.0\.0\.0|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\."
    r"|\.local\b|file://|/home/|/root/|C:\\\\Users",
    re.IGNORECASE)


def _check_public_url(u: str) -> None:
    """公开来源资格：u 必须为空（no-url 占位）或公网 http(s) 定位符。"""
    u = (u or "").strip()
    if not u or u == "no-url" or u.startswith("sha256:"):
        return  # 无 URL 记录以 t/d 为身份，不涉及内网泄露
    if u.startswith("http://") or u.startswith("https://"):
        rest = u.split("://", 1)[1].split("/", 1)[0]
        host = rest.split("@")[-1].split(":")[0]
        if ("localhost" == host or host.startswith("127.") or host.startswith("10.")
                or host.startswith("192.168.") or host.endswith(".local")
                or host == "0.0.0.0"
                or re.fullmatch(r"172\.(1[6-9]|2\d|3[01])\..+", host)):
            raise GitHubPackageError(f"记录引用非公开来源（内网/本机地址）：{u[:80]!r}")
        return
    raise GitHubPackageError(f"记录 u 必须为 http(s) URL（实际 {u[:60]!r}）")


def _validate_record_shapes(records: list) -> None:
    """六.2 嵌套字段/类型约束：顶层白名单之外，逐字段类型/长度/取值域校验，
    嵌套结构（scd 五维 / kp / cp）限形限量——恶意/损坏包在入口拒绝，
    不落库不落 record_json。"""
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue  # 结构校验由 _validate_changes 负责
        for field, (kind, limit) in _FIELD_LIMITS.items():
            if field not in rec or rec[field] is None:
                continue
            v = rec[field]
            if kind == "str":
                if not isinstance(v, str) or len(v) > limit:
                    raise GitHubPackageError(
                        f"records.json 第 {i} 项 {field} 必须为 ≤{limit} 字符的字符串")
            elif kind == "scalar":
                # 历史契约容忍 int/float/短字符串（消费端 str() 归一）
                if isinstance(v, bool) or not isinstance(v, (str, int, float)) \
                        or len(str(v)) > limit:
                    raise GitHubPackageError(
                        f"records.json 第 {i} 项 {field} 必须为 ≤{limit} 字符的标量")
            elif kind == "date":
                if not isinstance(v, str) or not _DATE_RE.fullmatch(v):
                    raise GitHubPackageError(
                        f"records.json 第 {i} 项 {field} 必须为 YYYY-MM-DD 日期")
            elif kind == "url":
                if not isinstance(v, str) or len(v) > limit:
                    raise GitHubPackageError(
                        f"records.json 第 {i} 项 {field} 必须为 ≤{limit} 字符的 URL")
                _check_public_url(v)
            elif kind == "int":
                if not isinstance(v, int) or isinstance(v, bool):
                    raise GitHubPackageError(f"records.json 第 {i} 项 {field} 必须为整数")
                lo, hi = _INT_RANGES[field]
                if not (lo <= v <= hi):
                    raise GitHubPackageError(
                        f"records.json 第 {i} 项 {field} 取值越界：{v!r}")
        for field, (max_len, max_item) in _LIST_LIMITS.items():
            if field not in rec or rec[field] is None:
                continue
            v = rec[field]
            if not isinstance(v, list):
                # 历史形态容忍：kp 曾以整串字符串出现（按标量入库，
                # 记录行构造时非列表折叠为 []，record_json 保留原值）
                if isinstance(v, str) and len(v) <= max_item:
                    continue
                # cp 实际生产形态是标量 int：clustering.py 写 0（簇根）/1（子）
                # 聚类父标志——2026-10-01/02 的真实发布包即此形态（T12 演练
                # 发现）。按字段语义容忍，入库折叠为 [cp]，record_json 保留原值。
                if field == "cp" and isinstance(v, int) and not isinstance(v, bool):
                    continue
                raise GitHubPackageError(
                    f"records.json 第 {i} 项 {field} 必须为 ≤{max_len} 元数组")
            if len(v) > max_len:
                raise GitHubPackageError(
                    f"records.json 第 {i} 项 {field} 必须为 ≤{max_len} 元数组")
            for item in v:
                # cp 历史包元素可为数值（如聚类编号 [1,2]）——标量容忍
                if isinstance(item, bool) or not isinstance(item, (str, int, float)) \
                        or len(str(item)) > max_item:
                    raise GitHubPackageError(
                        f"records.json 第 {i} 项 {field} 元素必须为 ≤{max_item} 字符标量")
        scd = rec.get("scd")
        if scd is not None:
            # 五.2：scd = 引擎评分卡五槽 {"b","i","r","d","t"}（0-10 数值）。
            # 键受限于五槽（未知槽=损坏/伪造包），值数值、禁止任意嵌套；
            # 历史标量形态（短字符串）容忍。
            if isinstance(scd, dict):
                if not scd or len(scd) > len(_SCD_SLOTS) or set(scd) - set(_SCD_SLOTS):
                    raise GitHubPackageError(
                        f"records.json 第 {i} 项 scd 键必须为 {_SCD_SLOTS} 子集且非空")
                for k2, v2 in scd.items():
                    if not isinstance(v2, (int, float)) or isinstance(v2, bool):
                        raise GitHubPackageError(
                            f"records.json 第 {i} 项 scd[{k2!r}] 必须为数值")
            elif isinstance(scd, str) and len(scd) <= 512:
                pass  # 历史标量容忍
            else:
                raise GitHubPackageError(
                    f"records.json 第 {i} 项 scd 必须为五槽对象（b/i/r/d/t）或历史标量")
        if "i" in rec and rec["i"] not in (None, "", "l", "n", 0, 1):
            raise GitHubPackageError(f"records.json 第 {i} 项 i 取值非法：{rec['i']!r}")


def _validate_changes(manifest: dict, records: list, changes: object) -> None:
    """嵌套结构校验：id 与 t|d|u 一致、op/v/key 合法、无重复键、计数对账。"""
    if not isinstance(changes, list):
        raise GitHubPackageError("changes.json 必须是数组")
    rec_ids: set[str] = set()
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise GitHubPackageError(f"records.json 第 {i} 项不是对象")
        rid = str(rec.get("id", ""))
        if not _ID_RE.fullmatch(rid):
            raise GitHubPackageError(f"records.json 第 {i} 项缺少合法 id")
        expect = _stable_id(
            str(rec.get("t", "")), str(rec.get("d", "")), str(rec.get("u", "") or "")
        )
        if rid != expect:
            raise GitHubPackageError(f"records.json 第 {i} 项 id 与 t|d|u 不一致（记录被篡改）")
        rec_ids.add(rid)
    _validate_record_shapes(records)  # 六.2：嵌套字段/类型 + 公开来源准入
    ops = {"ADD": 0, "UPDATE": 0, "DELETE": 0}
    seen_keys: set[str] = set()
    for i, ch in enumerate(changes):
        if not isinstance(ch, dict):
            raise GitHubPackageError(f"changes.json 第 {i} 项不是对象")
        op = str(ch.get("op", ""))
        if op not in ops:
            raise GitHubPackageError(f"changes.json 第 {i} 项 op 非法：{op!r}")
        v = ch.get("v")
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            raise GitHubPackageError(f"changes.json 第 {i} 项版本 v 非法：{v!r}")
        key = str(ch.get("key", ""))
        if not key or "|" not in key:
            raise GitHubPackageError(f"changes.json 第 {i} 项 key 非法")
        if key in seen_keys:
            raise GitHubPackageError(f"changes.json 存在重复键：{key[:80]}")
        seen_keys.add(key)
        ch_id = str(ch.get("id", ""))
        if not _ID_RE.fullmatch(ch_id):
            raise GitHubPackageError(f"changes.json 第 {i} 项 id 非法")
        if op in ("ADD", "UPDATE") and ch_id not in rec_ids:
            raise GitHubPackageError(f"changes.json {op} 的 id 在 records.json 中缺失：{ch_id}")
        if op == "DELETE":
            # 五.2：DELETE 无记录可对照——id 必须等于键规范串（右侧切两段，
            # 标题可含 "|"）推导的稳定 ID，伪造删除即刻可判
            parts = key.rsplit("|", 2)
            if len(parts) != 3 or ch_id != _stable_id(parts[0], parts[1], parts[2]):
                raise GitHubPackageError(
                    f"changes.json 第 {i} 项 DELETE id 与 key(t|d|u) 推导不一致（伪造删除）")
        ops[op] += 1
    for field, count in (
        ("added", ops["ADD"]), ("updated", ops["UPDATE"]), ("deleted", ops["DELETE"]),
    ):
        declared = manifest.get(field)
        if declared is not None and int(declared) != count:
            raise GitHubPackageError(
                f"manifest.{field}（{declared}）与 changes.json 实际（{count}）不一致"
            )
    for field, actual in (("change_count", len(changes)), ("record_count", len(records))):
        declared = manifest.get(field)
        if declared is not None and int(declared) != actual:
            raise GitHubPackageError(
                f"manifest.{field}（{declared}）与包内实际（{actual}）不一致"
            )


# ── 行构造与字段应用 ──────────────────────────────────────────────────────


def _row_fields(rec: dict, upload_id: uuid.UUID, user_id: str, version: int) -> dict:
    """包记录（白名单过滤后）→ 持久行字段。保存 record_json 保证包往返不丢字段。"""
    url = str(rec.get("u", "") or "").strip()
    if not url:
        url = "sha256:" + _v2_content_hash(rec)[:16]
    sc = rec.get("sc")
    scd = rec.get("scd") if isinstance(rec.get("scd"), dict) else None
    kp = rec.get("kp") if isinstance(rec.get("kp"), list) else []
    itype = "literature" if str(rec.get("i", "")) in {"l", "literature"} else "news"
    key = "|".join(_dedup_key(str(rec.get("t", "")), str(rec.get("d", "")), url))
    return dict(
        upload_id=upload_id,
        user_id=user_id,
        title=str(rec.get("t", ""))[:500],
        body=str(rec.get("b", "") or "")[:_BODY_CAP] or None,
        category=str(rec.get("c", "") or "")[:500] or None,
        document_date=str(rec.get("d", ""))[:32] or None,
        level=max(0, min(3, int(rec.get("lv") or 0))),
        intelligence_type=itype,
        source_name=str(rec.get("a", "") or "").strip()[:255] or None,
        url=url[:1024],
        key_parameters=kp,
        ai_summary=str(rec.get("as", "") or "") or None,
        score=str(sc) if sc is not None else None,
        score_detail=scd,
        tag=str(rec.get("tg", "") or "") or None,
        topic=str(rec.get("tp", "") or "") or None,
        ai_picked=bool(rec.get("aip") or False),
        source_version=int(version),
        stable_id=str(rec.get("id", "")) or None,
        feed_key_digest=_feed_key_digest_hex(key),
        content_hash=_v2_content_hash(rec),
        record_json=rec,
    )


def _apply_record_to_row(row: BreadthManualRecord, rec: dict, version: int) -> None:
    fields = _row_fields(rec, row.upload_id, row.user_id, version)
    for attr, value in fields.items():
        if attr in ("upload_id", "user_id"):
            continue
        setattr(row, attr, value)


# ── 应用引擎 ─────────────────────────────────────────────────────────────


def _acquire_feed_apply_lock(db: Session) -> None:
    """feed 包应用阶段的事务级串行锁（二.1 并发导入保护）。

    PostgreSQL：pg_advisory_xact_lock——同键并发导入在版本判断与写入上
    全程互斥，事务结束自动释放；SQLite：单写锁天然串行，无需处理。
    墓碑表主键（feed_key_digest）提供最后一层数据库约束兜底。"""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext('feed-import-apply'))"))


def _load_feed_rows(db: Session) -> tuple[dict[str, BreadthManualRecord], dict[str, BreadthManualRecord], set[uuid.UUID]]:
    """既有行索引：feed_key_digest → row；回退（无 digest 的历史行，重建键）→ row。

    回退索引包含全部行（含人工/其他来源）：UPDATE/DELETE 先按键定位，
    再由 _feed_owned 判定归属——人工记录被显式保护计数（skipped_protected），
    而不是表现为"键不存在"（deleted_missing）。
    """
    by_digest: dict[str, BreadthManualRecord] = {}
    fallback: dict[str, BreadthManualRecord] = {}
    github_ids = _github_upload_ids(db)
    rows_q = select(BreadthManualRecord)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        rows_q = rows_q.with_for_update()  # 二.1：版本判定窗口行锁
    for row in db.scalars(rows_q).all():
        if row.feed_key_digest:
            by_digest.setdefault(row.feed_key_digest, row)
        else:
            key = "|".join(_dedup_key(row.title, row.document_date or "", row.url or ""))
            fallback.setdefault(_feed_key_digest_hex(key), row)
    return by_digest, fallback, github_ids


def _feed_owned(row: BreadthManualRecord, github_ids: set[uuid.UUID]) -> bool:
    """feed 托管的行才允许 UPDATE/DELETE 改写；人工/其他广度情报来源受保护。"""
    return row.feed_key_digest is not None or row.upload_id in github_ids


def _apply_changes(
    db: Session,
    record: UploadedFile,
    changes: list[dict],
    records: list[dict],
    upstream: frozenset[bytes],
) -> dict:
    from app.services.breadth_index_queue import enqueue_record_delete, enqueue_record_upserts

    by_digest, fallback, github_ids = _load_feed_rows(db)
    records_by_id = {str(r.get("id", "")): r for r in records if isinstance(r, dict)}

    # 墓碑预载（仅本包涉及的键）：DELETE v 后到达的乱序/补投递包重放
    # ADD/UPDATE v' <= v 时，行已不在库、行级 source_version 无法比较，
    # 记录会被静默复活——墓碑持久化删除版本，导入侧据此拒绝/判冲突。
    tombstones: dict[str, FeedTombstone] = {}
    change_digests = {_feed_key_digest_hex(str(ch["key"])) for ch in changes}
    if change_digests:
        for tb in db.scalars(
            select(FeedTombstone).where(FeedTombstone.feed_key_digest.in_(change_digests))
        ):
            tombstones[tb.feed_key_digest] = tb

    added = updated = deleted = 0
    skipped_stale = skipped_unchanged = skipped_protected = deleted_missing = 0
    skipped_upstream = failed = 0
    skipped_tombstoned = conflicts = 0
    failed_keys: list[str] = []
    conflict_keys: list[str] = []
    touched: list[BreadthManualRecord] = []

    for ch in changes:
        op = str(ch["op"])
        v = int(ch["v"])
        key = str(ch["key"])
        hexd = _feed_key_digest_hex(key)
        row = by_digest.get(hexd) or fallback.get(hexd)
        tomb = tombstones.get(hexd)

        if op == "DELETE":
            if row is None:
                deleted_missing += 1  # 幂等：键本就不在库
                # 二.1：先删后到（DELETE 早于首包/行早已不在）也必须持久化
                # 删除版本——否则更晚重放的旧 ADD v' < v 无版本可比，静默复活
                if tomb is None:
                    tomb = FeedTombstone(feed_key_digest=hexd, deleted_version=0)
                    db.add(tomb)
                    tombstones[hexd] = tomb
                if v > tomb.deleted_version:
                    # 重复/晚到的删除仍推进墓碑版本（包内可能夹带更高版本）
                    tomb.deleted_version = v
                    tomb.deleted_content_hash = None
                    tomb.upload_id = record.id
            elif not _feed_owned(row, github_ids):
                skipped_protected += 1
            elif tomb is not None and tomb.deleted_version > v:
                skipped_stale += 1  # 墓碑版本更高：更旧的删除重放
            elif row.source_version > v:
                skipped_stale += 1  # 旧版本包的删除不能覆盖新版本
            else:
                # 二：删除行之前把统一身份持久化进任务 payload——
                # 任务异步执行时行已删，仅凭 UUID 无法对齐基础索引旧版本。
                enqueue_record_delete(db, row.id, record.id, row=row)
                # 墓碑与删除同一事务：崩溃不会出现「行已删、墓碑未记」
                if tomb is None:
                    tomb = FeedTombstone(feed_key_digest=hexd)
                    db.add(tomb)
                    tombstones[hexd] = tomb
                tomb.deleted_version = v
                tomb.deleted_content_hash = row.content_hash
                tomb.upload_id = record.id
                db.delete(row)
                by_digest.pop(hexd, None)
                fallback.pop(hexd, None)
                deleted += 1
            continue

        try:
            rec = _filter_public(records_by_id[str(ch["id"])])
            content_hash = _v2_content_hash(rec)
            if row is None:
                if tomb is not None and v < tomb.deleted_version:
                    skipped_tombstoned += 1  # 陈旧重放：拒绝复活
                    continue
                if tomb is not None and v == tomb.deleted_version:
                    if tomb.deleted_content_hash and content_hash != tomb.deleted_content_hash:
                        conflicts += 1  # 同版本不同内容：协议冲突，不落地
                        conflict_keys.append(key[:80])
                    else:
                        skipped_tombstoned += 1  # 同版本同内容：幂等重放
                    continue
                # v > tomb.deleted_version（或无墓碑）：合法（重新）上架
                # 五.2（2026-10-01）：标题可含 "|"（真实库 920 条）——键
                # t|d|u 必须从右侧按 | 切两段（日期/URL 不含裸 "|"），
                # 左 split 会把含竖线标题切错、身份对不上水印/上游。
                parts = key.rsplit("|", 2)
                parts += [""] * (3 - len(parts))
                if _key_digest((parts[0], parts[1], parts[2])) in upstream:
                    skipped_upstream += 1
                else:
                    new = BreadthManualRecord(**_row_fields(rec, record.id, record.submitted_by, v))
                    db.add(new)
                    db.flush()
                    by_digest[hexd] = new
                    added += 1
                    touched.append(new)
                    if tomb is not None:
                        # 重新上架成功 → 墓碑使命完成
                        db.delete(tomb)
                        tombstones.pop(hexd, None)
                continue
            if tomb is not None and tomb.deleted_version > v:
                skipped_tombstoned += 1  # 行在但墓碑版本更新：人工恢复被更高版本保护
                continue
            if not _feed_owned(row, github_ids):
                skipped_protected += 1
            elif v < row.source_version:
                skipped_stale += 1  # 旧不覆新
            elif v == row.source_version and row.content_hash == content_hash:
                skipped_unchanged += 1  # 幂等重放
                if row.upload_id != record.id:
                    row.upload_id = record.id
            elif v == row.source_version:
                # 二.1：同版本不同内容 = 协议冲突——绝不能当作更新静默改写
                conflicts += 1
                conflict_keys.append(key[:80])
            else:
                _apply_record_to_row(row, rec, v)
                row.upload_id = record.id
                updated += 1
                touched.append(row)
                if tomb is not None:
                    db.delete(tomb)  # 记录已推进到 v，旧墓碑失效
                    tombstones.pop(hexd, None)
        except (TypeError, ValueError) as exc:
            failed += 1
            failed_keys.append(key[:80])
            logger.warning("增量包记录应用失败 %s: %s", key[:80], exc)

    db.flush()
    if touched:
        enqueue_record_upserts(db, touched)
    return {
        "added": added, "updated": updated, "deleted": deleted,
        "skipped_stale": skipped_stale, "skipped_unchanged": skipped_unchanged,
        "skipped_protected": skipped_protected, "deleted_missing": deleted_missing,
        "skipped_upstream": skipped_upstream, "failed": failed,
        # 墓碑判定（二.4，2026-09-30）：陈旧重放拒绝 + 同版本不同内容冲突
        "skipped_tombstoned": skipped_tombstoned,
        "conflicts": conflicts, "conflict_keys": conflict_keys,
        "skipped_in_package": 0, "package_deduplicated": False,
        "failed_keys": failed_keys,
    }


def _apply_v1(
    db: Session,
    record: UploadedFile,
    records: list[dict],
    upstream: frozenset[bytes],
) -> dict:
    """v1 full-slice 契约：只增不改；撞人工记录/上游分片跳过。"""
    from app.services.breadth_index_queue import enqueue_record_upserts

    by_digest, fallback, github_ids = _load_feed_rows(db)

    imported = skipped_upstream = failed = 0
    skipped_in_package = 0
    failed_titles: list[str] = []
    touched: list[BreadthManualRecord] = []
    seen_keys: set[str] = set()

    for raw in records:
        try:
            rec = _filter_public(raw)
            url = str(rec.get("u", "") or "").strip()
            if not url:
                url = "sha256:" + _v2_content_hash(rec)[:16]
                rec["u"] = url
            key = "|".join(_dedup_key(str(rec.get("t", "")), str(rec.get("d", "")), url))
            hexd = _feed_key_digest_hex(key)
            if key in seen_keys:
                skipped_in_package += 1  # 包内去重：同键保留首条
                continue
            seen_keys.add(key)
            row = by_digest.get(hexd) or fallback.get(hexd)
            if row is not None:
                skipped_upstream += 1
                continue
            # 五.2：同上——键从右侧切（标题可含 "|"）
            parts = key.rsplit("|", 2)
            parts += [""] * (3 - len(parts))
            if _key_digest((parts[0], parts[1], parts[2])) in upstream:
                skipped_upstream += 1
                continue
            new = BreadthManualRecord(**_row_fields(rec, record.id, record.submitted_by, 1))
            db.add(new)
            db.flush()
            by_digest[hexd] = new
            touched.append(new)
            imported += 1
        except (TypeError, ValueError) as exc:
            failed += 1
            failed_titles.append(str(raw.get("t", "") if isinstance(raw, dict) else "")[:80])
            logger.warning("v1 增量包记录入表失败: %s", exc)

    if touched:
        enqueue_record_upserts(db, touched)
    return {
        "added": imported, "updated": 0, "deleted": 0,
        "skipped_stale": 0, "skipped_unchanged": 0,
        "skipped_protected": 0, "deleted_missing": 0,
        "skipped_upstream": skipped_upstream, "failed": failed,
        "skipped_in_package": skipped_in_package,
        "package_deduplicated": skipped_in_package > 0,
        "failed_keys": failed_titles,
    }


# ── 会话与入口 ───────────────────────────────────────────────────────────


def _session_payload(session: BreadthImportSession) -> dict:
    payload = {
        "session_id": str(session.id),
        "package_date": session.package_date,
        "schema_version": session.schema_version,
        "data_version": session.data_version,
        "record_count": session.record_count,
        "imported": session.imported,
        "skipped_duplicate": session.skipped_duplicate,
        "skipped_upstream_conflict": session.skipped_upstream_conflict,
        "failed": session.failed,
        "package_deduplicated": bool(session.package_deduplicated),
        "replayed": bool(session.replayed),
        "failed_titles": list(session.failed_titles or []),
    }
    details = session.details if isinstance(session.details, dict) else {}
    if details:
        payload["details"] = dict(details)
    return payload


def _gap_days(db: Session, package_date: str) -> int | None:
    """漏包检测：与上一次导入的包日期差。≥2 天提示用 --since-last 生成补包。"""
    prev = db.scalar(
        select(BreadthImportSession.package_date)
        .where(BreadthImportSession.package_date < package_date)
        .order_by(BreadthImportSession.package_date.desc())
        .limit(1)
    )
    if not prev:
        return None
    try:
        delta = datetime.strptime(package_date, "%Y-%m-%d") - datetime.strptime(prev, "%Y-%m-%d")
        return max(0, delta.days)
    except ValueError:
        return None


def import_github_package(db: Session, record: UploadedFile, zip_path: Path) -> dict:
    """导入一个增量包。调用方保证已在事务中，本函数负责 commit。

    返回计数字典（含 replayed 标记幂等重放；v2 另有 details 细分计数）。
    """
    # ── 幂等重放：同 checksum 已有会话 → 回放计数，不再解包 ──
    existing = db.scalar(
        select(BreadthImportSession).where(
            BreadthImportSession.checksum_sha256 == record.checksum_sha256
        )
    )
    if existing is not None:
        if existing.upload_id != record.id:
            # 同包以新上传重复提交：会话与历史记录行一并挂到新上传行，
            # 否则删除旧上传行会级联误删已导入记录（重复上传后删除误删）。
            old_upload = existing.upload_id
            existing.upload_id = record.id
            existing.replayed = True
            if old_upload is not None:
                rows = db.execute(
                    update(BreadthManualRecord)
                    .where(BreadthManualRecord.upload_id == old_upload)
                    .values(upload_id=record.id)
                )
                logger.info("replay: re-pointed %s breadth rows to new upload", rows.rowcount)
            db.commit()
        return _session_payload(existing)

    # 二.1：并发导入同键时，版本判断与写入必须串行——PostgreSQL 取事务级
    # advisory lock 序列化 feed 应用阶段（SQLite 单写锁天然串行）。行锁
    # （with_for_update）作第二层：锁既有行的版本判定窗口。
    _acquire_feed_apply_lock(db)

    manifest, records, changes = _read_package(zip_path)
    package_date = str(manifest.get("date", "") or "").strip()
    schema = str(manifest.get("schema", ""))

    root = _breath_data_root()
    data_version = str(manifest.get("data_version", "") or "") or None
    upstream = _upstream_key_digests(_upstream_data_version(root), str(root))

    if changes is not None:
        result = _apply_changes(db, record, changes, records, upstream)
    else:
        result = _apply_v1(db, record, records, upstream)

    details: dict = {k: v for k, v in result.items() if k not in ("failed_keys",)}
    gap = _gap_days(db, package_date)
    # 五.2：链状态可证明连续（同 sequence 体系、无缺口标记）时，安静日
    # （发布端无变化不发包）不构成漏包——不再用日期差误报 gap_days。
    # 仅 v1 包（无 sequence）或链上有真实缺口时保留日期差提示。
    chain_continuous = False

    # 五.2 发布序列链判定（v2 包且 manifest 带 sequence/chain 时）：
    #   continuity 基准 = 已导入会话中 sequence 最大行；
    #   - sequence == last+1 且 predecessor == last.chain_head → 干净推进；
    #   - sequence == last+1 但前驱对不上 → 链分叉/伪造，导入前拒绝；
    #   - sequence > last+1 → 缺口（漏包）：per-key v 保护下照常应用，
    #     details.chain_gap 如实标记（不阻塞，后续补包可推进链）；
    #   - sequence ≤ last → 迟到/重出旧包：应用幂等（v 保护），
    #     details.stale_sequence 标记，链以更大 sequence 为准不回退。
    seq = manifest.get("sequence")
    pred = str(manifest.get("predecessor", "") or "")
    seq_known = isinstance(seq, int) and not isinstance(seq, bool) and seq >= 1
    if seq_known:
        last = db.scalar(
            select(BreadthImportSession)
            .where(BreadthImportSession.package_sequence.is_not(None))
            .order_by(BreadthImportSession.package_sequence.desc())
            .limit(1)
        )
        if last is not None:
            last_seq = int(last.package_sequence or 0)
            if seq == last_seq + 1 and pred != str(last.chain_head or ""):
                # 事务级 advisory 锁随回滚自动释放，直接抛错即可
                raise GitHubPackageError(
                    f"发布序列链断裂：包 sequence={seq} 的 predecessor 与已导入链头"
                    f"（sequence={last_seq}）不一致——链被伪造/插包/改包，拒绝导入")
            if seq > last_seq + 1:
                details["chain_gap"] = {"expected": last_seq + 1, "got": seq}
            elif seq <= last_seq:
                details["stale_sequence"] = seq
            else:
                chain_continuous = True
        else:
            chain_continuous = True  # 链状态引导（首个带 sequence 的包）

    if chain_continuous and gap is not None and gap >= 2:
        # 链干净推进：安静日不算漏包，不误报
        pass
    elif gap is not None and gap >= 2:
        details["gap_days"] = gap

    session = BreadthImportSession(
        upload_id=record.id,
        checksum_sha256=record.checksum_sha256,
        package_date=package_date,
        schema_version=schema,
        data_version=data_version,
        record_count=len(records),
        imported=result["added"] + result["updated"],
        skipped_duplicate=result["skipped_in_package"],
        skipped_upstream_conflict=result["skipped_upstream"] + result["skipped_protected"],
        failed=result["failed"],
        package_deduplicated=result["package_deduplicated"],
        replayed=False,
        failed_titles=result["failed_keys"][:50],
        details=details,
        package_sequence=seq if seq_known else None,
        manifest_digest=str(manifest.get("manifest_digest") or "") or None,
        chain_head=str(manifest.get("chain") or "") or None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info(
        "GitHub 增量包 %s(%s) 导入完成: +%d ~%d -%d stale=%d unchanged=%d "
        "conflict=%d failed=%d gap=%s",
        package_date, schema, result["added"], result["updated"], result["deleted"],
        result["skipped_stale"], result["skipped_unchanged"],
        result["skipped_upstream"] + result["skipped_protected"], result["failed"],
        details.get("gap_days"),
    )
    return _session_payload(session)


def note_for_counts(payload: dict) -> str:
    """上传资料 note 列的计数摘要（资料库列表展示）。"""
    parts = [f"导入 {payload.get('imported', 0)} 条"]
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    if details.get("updated"):
        parts.append(f"更新 {details['updated']}")
    if details.get("deleted"):
        parts.append(f"删除 {details['deleted']}")
    if details.get("skipped_stale"):
        parts.append(f"旧版跳过 {details['skipped_stale']}")
    if payload.get("skipped_upstream_conflict"):
        parts.append(f"撞库跳过 {payload['skipped_upstream_conflict']}")
    if payload.get("failed"):
        parts.append(f"失败 {payload['failed']}")
    if details.get("gap_days"):
        parts.append(f"距上次包 {details['gap_days']} 天，如需补齐请用 --since-last 生成补包")
    if payload.get("replayed"):
        parts.append("幂等重放")
    return " · ".join(parts)
