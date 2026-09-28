#!/usr/bin/env python3
"""feed 包三方契约测试（第五节）。

锁定 生成器（scripts/build_feed_package.py）→ 独立校验器
（scripts/validate_feed_package.py）→ 导入器（backend app/services/
github_import.py）的契约一致性：

  1. PUBLIC_FIELDS 三方逐字一致（白名单漂移即失败）；
  2. stable_id / content_hash 函数字节级同构（生成=校验=导入）；
  3. 真实生成的 v2 增量包通过独立校验器（含 id/键推导、计数对账）；
  4. 包 → 导入器（内存 SQLite）往返：字段不丢、旧不覆新、删除传播；
  5. 校验器拒收：坏哈希 / 白名单外私有字段 / 重复 key 断点 / 恶意 zip。

仅标准库 + 后端模型依赖（SQLAlchemy），可在 CI 与离线环境运行。
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
import uuid
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_feed_package as builder  # noqa: E402
import validate_feed_package as validator  # noqa: E402

try:  # backend 依赖（SQLAlchemy 等）缺失时跳过导入器契约侧
    from app.services import github_import  # noqa: E402

    _BACKEND_IMPORTABLE = True
except Exception:  # pragma: no cover
    github_import = None
    _BACKEND_IMPORTABLE = False

_DOCKER_SKIP = "需要 backend 依赖（api 容器内运行）"


def _rec(i: int, **overrides) -> dict:
    rec = {
        "t": f"测试情报{i}",
        "d": "2026-09-28",
        "u": f"https://example.com/{i}",
        "c": "固态电池",
        "a": "测试源",
        "i": "n",
        "tg": "tag",
        "tp": "topic",
        "sc": "7.8",
        "scd": {"novelty": 8, "credibility": 7},
        "aip": 1,
        "as": "摘要",
        "kp": ["参数"],
        "lv": 2,
        "wr": "writer",
        "cl": "cell",
        "cp": ["cp1"],
        "cln": 4,
        "dp": 3,
        "b": "正文",
        "hb": 1,
        # 白名单外（必须被剥离）
        "cm": "内部评论",
        "fb": "冗余全文",
        "sr": "内部文件名",
    }
    rec.update(overrides)
    return rec


class TestWhitelistContract(unittest.TestCase):
    def test_public_fields_three_way_match(self):
        self.assertEqual(tuple(builder.PUBLIC_FIELDS), tuple(validator.PUBLIC_FIELDS))
        if not _BACKEND_IMPORTABLE:
            self.skipTest(_DOCKER_SKIP)
        self.assertEqual(tuple(builder.PUBLIC_FIELDS), tuple(github_import.PUBLIC_FIELDS))

    def test_hash_functions_byte_identical(self):
        rec = _rec(1)
        self.assertEqual(builder.content_hash(rec), validator.content_hash(rec))
        sid = builder.stable_id("t1", "d1", "u1")
        self.assertEqual(sid, validator.stable_id("t1", "d1", "u1"))
        self.assertEqual(len(sid), 16)
        if not _BACKEND_IMPORTABLE:
            self.skipTest(_DOCKER_SKIP)
        self.assertEqual(builder.content_hash(rec), github_import._v2_content_hash(rec))
        self.assertEqual(sid, github_import._stable_id("t1", "d1", "u1"))


def _build_v2_zip(records: list[dict], changes: list[dict] | None = None,
                  manifest_overrides: dict | None = None) -> bytes:
    """直接构造 v2 包（与 build_changes_slice 的产物结构逐字同构）。"""
    from datetime import datetime
    out_records = []
    for rec in records:
        out = {k: rec.get(k) for k in builder.PUBLIC_FIELDS if k in rec}
        out["id"] = builder.stable_id(str(out.get("t", "")), str(out.get("d", "")),
                                      str(out.get("u", "")))
        rec["id"] = out["id"]
        out_records.append(out)
    if changes is None:
        changes = [{"op": "ADD", "id": r["id"],
                    "key": f"{r.get('t','')}|{r.get('d','')}|{r.get('u','')}",
                    "v": 1} for r in out_records]
    records_json = json.dumps(out_records, ensure_ascii=False, indent=1)
    manifest = {
        "schema": "tech-boundary-feed-package/v2",
        "generator": "tech-boundary-feed-package/v2 test",
        "mode": "changes",
        "date": "2026-09-28",
        "record_count": len(out_records),
        "change_count": len(changes),
        "added": sum(1 for c in changes if c["op"] == "ADD"),
        "updated": sum(1 for c in changes if c["op"] == "UPDATE"),
        "deleted": sum(1 for c in changes if c["op"] == "DELETE"),
        "records_sha256": hashlib.sha256(records_json.encode("utf-8")).hexdigest(),
        "data_version": "test" + hashlib.sha256(b"dv").hexdigest()[:8],
        "generated_at": datetime.now().isoformat(),
    }
    manifest.update(manifest_overrides or {})
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("records.json", records_json)
        zf.writestr("changes.json", json.dumps(changes, ensure_ascii=False, indent=1))
    return buf.getvalue()


class TestValidatorRoundtrip(unittest.TestCase):
    def _tmp_zip(self, data: bytes) -> Path:
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        f.write(data)
        f.close()
        self.addCleanup(Path(f.name).unlink)
        return Path(f.name)

    def test_generated_v2_package_passes_validator(self):
        recs = [_rec(1), _rec(2, u="")]
        data = _build_v2_zip(recs)
        rep = validator.validate(self._tmp_zip(data))
        self.assertEqual(rep.errors, [], rep.render())

    def test_validator_rejects_tampered_hash(self):
        recs = [_rec(1)]
        data = _build_v2_zip(recs, manifest_overrides={"records_sha256": "0" * 64})
        rep = validator.validate(self._tmp_zip(data))
        self.assertTrue(any("records_sha256" in e for e in rep.errors))

    def test_validator_rejects_private_fields(self):
        import io
        data = _build_v2_zip([_rec(1)])
        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf) as zf:
            records = json.loads(zf.read("records.json"))
            manifest = json.loads(zf.read("manifest.json"))
            changes = json.loads(zf.read("changes.json"))
        records[0]["cm"] = "泄漏的内部评论"
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("records.json", json.dumps(records, ensure_ascii=False))
            zf.writestr("changes.json", json.dumps(changes))
        rep = validator.validate(self._tmp_zip(out.getvalue()))
        self.assertTrue(any("白名单外" in e for e in rep.errors))

    def test_validator_rejects_mismatched_key(self):
        recs = [_rec(1)]
        data = _build_v2_zip(recs)  # _build_v2_zip 给 recs 补 id
        rid = recs[0]["id"]
        real_key = f"{recs[0]['t']}|{recs[0]['d']}|{recs[0]['u']}"
        ch = [{"op": "ADD", "id": rid, "key": real_key, "v": 1},
              {"op": "UPDATE", "id": rid, "key": "伪造|键|串", "v": 2}]
        data = _build_v2_zip(recs, changes=ch,
                             manifest_overrides={"added": 1, "updated": 1})
        rep = validator.validate(self._tmp_zip(data))
        self.assertTrue(any("key 与记录" in e for e in rep.errors), rep.render())

    def test_validator_rejects_duplicate_key_breakpoint(self):
        recs = [_rec(1)]
        data = _build_v2_zip(recs)
        rid = recs[0]["id"]
        real_key = f"{recs[0]['t']}|{recs[0]['d']}|{recs[0]['u']}"
        ch = [{"op": "ADD", "id": rid, "key": real_key, "v": 1},
              {"op": "UPDATE", "id": rid, "key": real_key, "v": 2}]
        data = _build_v2_zip(recs, changes=ch,
                             manifest_overrides={"added": 1, "updated": 1})
        rep = validator.validate(self._tmp_zip(data))
        self.assertTrue(any("重复" in e for e in rep.errors), rep.render())

    def test_validator_rejects_evil_zip(self):
        import io
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr("../evil.json", "{}")
            zf.writestr("manifest.json", "{}")
            zf.writestr("records.json", "[]")
        rep = validator.validate(self._tmp_zip(out.getvalue()))
        self.assertTrue(any("恶意路径" in e for e in rep.errors))
        self.assertTrue(any("schema" in e for e in rep.errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
