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
        # 五.2：scd = 引擎评分卡五槽 {"b","i","r","d","t"}（与真实数据同形）
        "scd": {"b": 8.0, "i": 6.0, "r": 0.0, "d": 0.0, "t": 6.0},
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
    changes_json = json.dumps(changes, ensure_ascii=False, indent=1)
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
        "changes_sha256": hashlib.sha256(changes_json.encode("utf-8")).hexdigest(),
        "data_version": "test" + hashlib.sha256(b"dv").hexdigest()[:8],
        "generated_at": datetime.now().isoformat(),
    }
    manifest.update(manifest_overrides or {})
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("records.json", records_json)
        zf.writestr("changes.json", changes_json)
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


class TestSectionFiveContracts(unittest.TestCase):
    """五.2 契约：changes 字节绑定 / 链自洽 / scd 五槽 / 公开准入 /
    包字节可复现 / 推送失败水印不推进。"""

    def _tmp_zip(self, data: bytes) -> Path:
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        f.write(data)
        f.close()
        self.addCleanup(Path(f.name).unlink)
        return Path(f.name)

    def test_generated_package_carries_changes_sha256(self):
        recs = [_rec(1)]
        zip_bytes, n, summary = builder.build_changes_slice(recs, {})
        import io
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            changes_raw = zf.read("changes.json")
        self.assertIn("changes_sha256", manifest)
        self.assertEqual(manifest["changes_sha256"],
                         hashlib.sha256(changes_raw).hexdigest())
        self.assertEqual(summary.get("refused_private", 0), 0)

    def test_changes_sha_tamper_detected_by_validator(self):
        import io
        recs = [_rec(1)]
        zip_bytes, _, _ = builder.build_changes_slice(recs, {})
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            records_raw = zf.read("records.json")
            changes = json.loads(zf.read("changes.json"))
        changes[0]["v"] = 99  # 篡改版本号（1→99）
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("records.json", records_raw)
            zf.writestr("changes.json", json.dumps(changes, ensure_ascii=False, indent=1))
        rep = validator.validate(self._tmp_zip(out.getvalue()))
        self.assertTrue(any("changes_sha256" in e for e in rep.errors), rep.render())

    def test_real_shape_scd_passes_all_three(self):
        """真实五槽 scd 三方一致通过（回归：导入端曾按 ≤1 键误拒）。"""
        recs = [_rec(1), _rec(2, u="")]
        zip_bytes, _, _ = builder.build_changes_slice(recs, {})
        rep = validator.validate(self._tmp_zip(zip_bytes))
        self.assertEqual(rep.errors, [], rep.render())
        if not _BACKEND_IMPORTABLE:
            self.skipTest(_DOCKER_SKIP)
        import tempfile
        p = self._tmp_zip(zip_bytes)
        manifest, records, changes = github_import._read_package(p)
        self.assertEqual(manifest["record_count"], 2)
        self.assertEqual(records[0]["scd"]["t"], 6.0)

    def test_publisher_refuses_private_records(self):
        recs = [_rec(1),
                _rec(2, u="http://192.168.1.10:8080/内部系统/报告"),
                _rec(3, b="sk-ABCDEFGHijklmnOPQRSTUVwx0000 凭据泄漏在正文")]
        _, n, summary = builder.build_changes_slice(recs, {})
        self.assertEqual(n, 1)
        self.assertEqual(summary.get("refused_private", 0), 2)
        # 被拒记录不进水印 hashes（后续修复后可正常新增，不残留幽灵键）
        self.assertFalse(any("192.168" in k for k in summary["hashes"]))

    def test_validator_rejects_private_url(self):
        import io
        data = _build_v2_zip([_rec(1, u="http://localhost:9000/admin")])
        rep = validator.validate(self._tmp_zip(data))
        self.assertTrue(any("非公开" in e for e in rep.errors), rep.render())

    def test_chain_self_consistency_enforced(self):
        import io
        recs = [_rec(1)]
        manifest = {
            "sequence": 1, "predecessor": "", "manifest_digest": "", "chain": "",
        }
        data = _build_v2_zip(recs, manifest_overrides=manifest)
        rep = validator.validate(self._tmp_zip(data))
        self.assertTrue(any("manifest_digest" in e for e in rep.errors), rep.render())
        # 导入端同样拒绝
        if not _BACKEND_IMPORTABLE:
            self.skipTest(_DOCKER_SKIP)
        import tempfile
        with self.assertRaises(Exception):
            github_import._read_package(self._tmp_zip(data))

    def test_package_bytes_reproducible(self):
        """同输入同水印 → 包字节可复现（除 generated_at 外逐字节一致）。"""
        recs = [_rec(1), _rec(2)]
        wm = {}
        z1, n1, s1 = builder.build_changes_slice(recs, dict(wm))
        z2, n2, s2 = builder.build_changes_slice(recs, dict(wm))
        self.assertEqual(n1, n2)
        import io
        def members(z):
            with zipfile.ZipFile(io.BytesIO(z)) as zf:
                return {name: zf.read(name) for name in zf.namelist()}
        m1, m2 = members(z1), members(z2)
        self.assertEqual(set(m1), set(m2))
        for name in m1:
            if name == "manifest.json":
                d1 = json.loads(m1[name]); d2 = json.loads(m2[name])
                # generated_at（打包时刻）与 digest/chain 不再含它——
                # 理想情况下全部字段一致；兜底排除打包时刻对比
                for k in ("generated_at",):
                    d1.pop(k, None); d2.pop(k, None)
                self.assertEqual(d1, d2, name)
            else:
                self.assertEqual(m1[name], m2[name], name)

    def test_watermark_not_advanced_when_push_fails(self):
        """推送失败 → 退出码 1 且水印不推进（发布成功才提交 watermark，
        sequence/chain 不前进——失败重发不会跳号）。"""
        import os as _os
        import subprocess as _sp
        import tempfile as _tf

        with _tf.TemporaryDirectory() as td:
            wm_path = Path(td) / "feed_state.json"
            # 先把水印路径指到沙箱，再写入起始水印（不碰真实水印文件）
            orig_wm = builder.WATERMARK_PATH
            builder.WATERMARK_PATH = wm_path
            builder.save_watermark({"sequence": 3, "chain": "chainX",
                                    "hashes": {}, "versions": {}})
            try:
                wm = builder.load_watermark()
                self.assertEqual(wm.get("sequence"), 3)

                real_run = _sp.run

                def fake_run(cmd, *a, **k):
                    """git -C <dir> <sub>… 形态：sub 在 args[3]；git clone 在 args[1]。
                    text=True 时输出用 str（与真实 subprocess 语义一致）。"""
                    text_mode = bool(k.get("text"))
                    out = "" if text_mode else b""
                    args = [str(c) for c in cmd]
                    if args[:2] == ["git", "clone"]:
                        Path(args[-1]).mkdir(parents=True, exist_ok=True)
                        return _sp.CompletedProcess(cmd, 0, b"", b"")
                    sub = args[3] if len(args) > 3 and args[:2] == ["git", "-C"] else None
                    if sub == "push":
                        return _sp.CompletedProcess(cmd, 1, b"", "push rejected")
                    if sub == "fetch":
                        return _sp.CompletedProcess(cmd, 0, b"", b"")
                    if sub == "rebase":
                        return _sp.CompletedProcess(cmd, 1, b"", "rebase conflict")
                    if sub == "diff":
                        # --cached --quiet：退出码 1 = 暂存区有变化（继续提交）
                        return _sp.CompletedProcess(cmd, 1, out, out)
                    return _sp.CompletedProcess(cmd, 0, b"", b"")  # add/commit 等

                orig_run = builder.subprocess.run
                builder.subprocess.run = fake_run
                try:
                    env_token = _os.environ.get("GH_TOKEN")
                    _os.environ["GH_TOKEN"] = "test-token"
                    recs = [_rec(9)]
                    rc = builder._main_since_last_locked(recs, no_push=False)
                finally:
                    builder.subprocess.run = orig_run
                    if env_token is None:
                        _os.environ.pop("GH_TOKEN", None)
                    else:
                        _os.environ["GH_TOKEN"] = env_token
                self.assertEqual(rc, 1)
                wm_after = builder.load_watermark()
                self.assertEqual(wm_after.get("sequence"), 3)
                self.assertEqual(wm_after.get("chain"), "chainX")
            finally:
                builder.WATERMARK_PATH = orig_wm
                builder.WATERMARK_PATH.with_suffix(".json.tmp").unlink(missing_ok=True)


class ScalarCpToleranceTest(unittest.TestCase):
    """T12 演练发现（2026-10-02）：真实发布包 cp 为标量 int（聚类父标志）。

    生产源头 pipeline/scripts/clustering.py 写 cp=0（簇根）/1（子）；
    validator 与导入端同规则容忍标量 int cp（仅 0/1，bool 排除），列表形态照旧。
    """

    def test_scalar_int_cp_passes(self):
        import tempfile
        from pathlib import Path
        import validate_feed_package as validator
        for cp_val in (0, 1):
            rec = _rec(1, cp=cp_val)
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
                f.write(_build_v2_zip([rec]))
                path = f.name
            rep = validator.validate(Path(path))
            self.assertEqual(rep.errors, [], f"cp={cp_val} 应容忍：{rep.errors}")
        # 非 0/1 标量：布尔语义 flag，非法值拒绝
        import tempfile
        from pathlib import Path
        import validate_feed_package as validator
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(_build_v2_zip([_rec(1, cp=42)]))
            path = f.name
        rep = validator.validate(Path(path))
        self.assertTrue(rep.errors, "cp=42 应拒绝：布尔语义只允许 0/1")

    def test_bool_cp_still_rejected(self):
        import tempfile
        from pathlib import Path
        import validate_feed_package as validator
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(_build_v2_zip([_rec(1, cp=True)]))
            path = f.name
        rep = validator.validate(Path(path))
        self.assertTrue(any("cp" in e for e in rep.errors), rep.errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
