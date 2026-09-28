"""GitHub 广度情报增量包导入（docs/design/github-incremental-dedup.md 契约实现）。

数据流：tech-boundary-data-feed 的 daily/YYYY-MM-DD.zip（feed-pkg/v1）由管理员
在离线服务器上传到【资料库-广度追踪-GitHub广度情报】，本服务解包、校验、
按 t|d|u 去重后把每条情报写成一条 breadth_manual_records 记录。

去重三层（契约 §2/§3/§4）：
1. 幂等重放：同 checksum 的包重复提交 → 直接回放上次会话计数，不再解包；
2. 包内去重：同包多条同键 → 保留日期最新一条（package_deduplicated）；
3. 撞库跳过：键已存在于上游分片（只读基线）或库内既有记录 → 跳过并计数。

明确不做（契约 §5）：不回写/重建上游基线索引；不改任何已有记录的 level；
不修改广度总表分片结构。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
import zipfile
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.breadth_import_session import BreadthImportSession
from app.models.breadth_manual_record import BreadthManualRecord
from app.models.uploaded_file import UploadedFile

logger = logging.getLogger(__name__)

SCHEMA_EXPECTED = "tech-boundary-feed-package/v1"
# 包内记录数上限：防御异常包（当前日包量级为百级）
MAX_PACKAGE_RECORDS = 50_000
# 上游键集合缓存的数据版本数（版本不变不重读 168MB 分片）
_UPSTREAM_CACHE_VERSIONS = 2


class GitHubPackageError(ValueError):
    """包结构/校验不合规——上传应被拒绝（400），不入库不落会话。"""


def validate_github_filename(filename: str | None) -> str:
    """增量包文件名校验：无路径成分、.zip 后缀。返回规范后缀 '.zip'。"""
    name = filename or ""
    if not name or "/" in name or "\\" in name or "\x00" in name:
        raise GitHubPackageError("文件名不能包含路径")
    if not name.lower().endswith(".zip"):
        raise GitHubPackageError("GitHub 增量包只接受 .zip 文件（daily/YYYY-MM-DD.zip）")
    return ".zip"


def _dedup_key(title: str, date: str, url: str) -> tuple[str, str, str]:
    """契约去重键：t 去首尾空白；u 为空时用 sha256:<16> 占位（包生成侧已写入）。"""
    return (str(title).strip(), str(date), str(url))


def _key_digest(key: tuple[str, str, str]) -> bytes:
    raw = "|".join(key)
    return hashlib.md5(raw.encode("utf-8")).digest()


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
    """上游分片（lite-part-*.js）全量 t|d|u 键摘要集合，按 data_version 进程内缓存。

    键做 md5 摘要后存 set：68k 键 ≈ 数 MB 内存，远小于存原键元组。
    lite 分片是 JS 赋值文件（window.__LITE_PARTS__.push([...]);），按括号切片解析。
    """
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
            key = _dedup_key(rec.get("t", ""), str(rec.get("d", "")), url)
            digests.add(_key_digest(key))
    return frozenset(digests)


def _db_key_digests(db: Session) -> set[bytes]:
    """库内既有广度记录（其他广度情报 + 历史增量包导入）的键摘要。"""
    digests: set[bytes] = set()
    rows = db.execute(
        select(BreadthManualRecord.title, BreadthManualRecord.document_date, BreadthManualRecord.url)
    ).all()
    for title, date, url in rows:
        u = str(url or "")
        key = _dedup_key(title, str(date or ""), u)
        digests.add(_key_digest(key))
    return digests


def _content_hash(record: dict) -> str:
    raw = json.dumps(
        {k: record.get(k) for k in ("t", "b", "i")},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_package(zip_path: Path) -> tuple[dict, list[dict]]:
    """解包 + 结构/完整性校验。返回 (manifest, records)。"""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names or "records.json" not in names:
                raise GitHubPackageError("增量包缺少 manifest.json 或 records.json")
            # 只读这两个成员，其余成员（如有）忽略不落地
            try:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise GitHubPackageError("manifest.json 不是合法 JSON") from exc
            try:
                records_json = zf.read("records.json").decode("utf-8")
            except (ValueError, UnicodeDecodeError) as exc:
                raise GitHubPackageError("records.json 不是合法 UTF-8 JSON") from exc
    except zipfile.BadZipFile as exc:
        raise GitHubPackageError("不是合法的 zip 包") from exc

    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA_EXPECTED:
        raise GitHubPackageError(
            f"manifest.schema 不符：期望 {SCHEMA_EXPECTED}，"
            f"实际 {manifest.get('schema') if isinstance(manifest, dict) else '?'}"
        )
    expect_sha = str(manifest.get("records_sha256", "") or "")
    if not expect_sha:
        raise GitHubPackageError("manifest 缺少 records_sha256 完整性校验值")
    if hashlib.sha256(records_json.encode("utf-8")).hexdigest() != expect_sha:
        raise GitHubPackageError("records_sha256 校验失败：包内容与清单不一致（传输损坏？）")

    try:
        records = json.loads(records_json)
    except ValueError as exc:
        raise GitHubPackageError("records.json 不是合法 JSON") from exc
    if not isinstance(records, list):
        raise GitHubPackageError("records.json 必须是记录数组")
    if len(records) > MAX_PACKAGE_RECORDS:
        raise GitHubPackageError(f"包内记录数异常（{len(records)} > {MAX_PACKAGE_RECORDS}）")
    declared = manifest.get("record_count")
    if not isinstance(declared, int) or declared != len(records):
        raise GitHubPackageError(
            f"manifest.record_count（{declared}）与 records.json 实际条数（{len(records)}）不一致"
        )
    package_date = str(manifest.get("date", "") or "").strip()
    if not package_date:
        raise GitHubPackageError("manifest 缺少 date（增量包日期）")
    if not __import__("re").fullmatch(r"\d{4}-\d{2}-\d{2}", package_date):
        raise GitHubPackageError(f"manifest.date 格式非法：{package_date}（期望 YYYY-MM-DD）")
    return manifest, records


def _to_row(record: dict, upload_id: uuid.UUID, user_id: str) -> BreadthManualRecord:
    """包记录 → 持久行。字段与 lite 分片短键逐字对齐（含 sc/scd 评分）。"""
    url = str(record.get("u", "") or "").strip()
    if not url:
        # 双保险：包生成侧已写 sha256:<16> 占位；这里对漏网记录同样补占位
        url = "sha256:" + _content_hash(record)[:16]
    itype = str(record.get("i", "") or "n")
    kp = record.get("kp") if isinstance(record.get("kp"), list) else []
    scd = record.get("scd") if isinstance(record.get("scd"), dict) else None
    return BreadthManualRecord(
        upload_id=upload_id,
        user_id=user_id,
        title=str(record.get("t", "")).strip() or "（无标题）",
        body=str(record.get("b", "") or "")[:20000] or None,
        category=str(record.get("c", "") or "").strip() or None,
        document_date=str(record.get("d", "") or "").strip() or None,
        level=max(0, min(3, int(record.get("lv") or 0))),
        intelligence_type="l" if itype == "l" else "n",
        source_name=str(record.get("a", "") or "").strip()[:255] or None,
        url=url[:1024],
        key_parameters=kp,
        ai_summary=str(record.get("as", "") or "").strip() or None,
        score=str(record.get("sc")) if record.get("sc") is not None else None,
        score_detail=scd,
        content_hash=_content_hash(record),
    )


def _session_payload(session: BreadthImportSession) -> dict:
    return {
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


def import_github_package(db: Session, record: UploadedFile, zip_path: Path) -> dict:
    """导入一个增量包。调用方保证已在事务中，本函数负责 commit。

    返回契约 §4 计数字典（含 replayed 标记幂等重放）。
    """
    # ── 幂等重放：同 checksum 已有会话 → 回放计数，不再解包（契约 §3）──
    existing = db.scalar(
        select(BreadthImportSession).where(
            BreadthImportSession.checksum_sha256 == record.checksum_sha256
        )
    )
    if existing is not None:
        if existing.upload_id != record.id:
            # 同包以新上传重复提交：把会话挂到新上传行，计数不变
            existing.upload_id = record.id
            existing.replayed = True
            db.commit()
        return _session_payload(existing)

    manifest, records = _read_package(zip_path)
    package_date = str(manifest.get("date", "") or "").strip()

    root = _breath_data_root()
    data_version = str(manifest.get("data_version", "") or "") or None
    upstream = _upstream_key_digests(_upstream_data_version(root), str(root))
    db_keys = _db_key_digests(db)

    # ── 包内去重：同键保留日期最新一条（契约 §2）──
    picked: dict[tuple[str, str, str], dict] = {}
    malformed = 0
    for rec in records:
        if not isinstance(rec, dict):
            malformed += 1
            continue
        key = _dedup_key(rec.get("t", ""), str(rec.get("d", "")), str(rec.get("u", "") or ""))
        if key not in picked or str(rec.get("d", "")) > str(picked[key].get("d", "")):
            picked[key] = rec

    imported = 0
    skipped_duplicate = len(records) - len(picked) - malformed  # 包内被合并掉的条数
    skipped_upstream = 0
    failed = malformed
    failed_titles: list[str] = []

    for key, rec in picked.items():
        digest = _key_digest(key)
        if digest in upstream:
            skipped_upstream += 1
            continue
        if digest in db_keys:
            skipped_upstream += 1
            continue
        try:
            db.add(_to_row(rec, record.id, record.submitted_by))
            db_keys.add(digest)
            imported += 1
        except (TypeError, ValueError) as exc:
            failed += 1
            failed_titles.append(str(rec.get("t", ""))[:80])
            logger.warning("增量包记录入表失败: %s", exc)

    session = BreadthImportSession(
        upload_id=record.id,
        checksum_sha256=record.checksum_sha256,
        package_date=package_date,
        schema_version=SCHEMA_EXPECTED,
        data_version=data_version,
        record_count=len(records),
        imported=imported,
        skipped_duplicate=skipped_duplicate,
        skipped_upstream_conflict=skipped_upstream,
        failed=failed,
        package_deduplicated=skipped_duplicate > 0,
        replayed=False,
        failed_titles=failed_titles[:50],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info(
        "GitHub 增量包 %s 导入完成: imported=%d dup=%d conflict=%d failed=%d",
        package_date, imported, skipped_duplicate, skipped_upstream, failed,
    )
    return _session_payload(session)


def note_for_counts(payload: dict) -> str:
    """上传资料 note 列的计数摘要（资料库列表展示）。"""
    parts = [f"导入 {payload.get('imported', 0)} 条"]
    if payload.get("skipped_duplicate"):
        parts.append(f"包内去重 {payload['skipped_duplicate']}")
    if payload.get("skipped_upstream_conflict"):
        parts.append(f"撞库跳过 {payload['skipped_upstream_conflict']}")
    if payload.get("failed"):
        parts.append(f"失败 {payload['failed']}")
    if payload.get("replayed"):
        parts.append("幂等重放")
    return " · ".join(parts)
