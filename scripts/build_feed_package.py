#!/usr/bin/env python3
"""tech-boundary-data-feed 每日增量包生成器。

从本仓库独立管线主存储（pipeline/data/processed/all-records-lite.json，已跑完整
管线的处理数据）按记录日期切片，产出契约形状的增量包（zip），并推送到
GitHub sbq9712/tech-boundary-data-feed 的 main 分支。

包结构（对齐 docs/design/github-incremental-dedup.md 的 t|d|u 去重契约）：
  daily/YYYY-MM-DD.zip
    ├─ manifest.json   # {schema, date, record_count, records_sha256, data_version, generator}
    └─ records.json    # [ {t, d, u, i, b, c, tg, as, sc, scd, kp, cl, cp, a, ...}, ...]
  LATEST.json         # {latest_date, packages: [{date, record_count, sha256}], updated_at}

去重语义（与契约一致）：
  - 包内 t|d|u 完全一致 → 只留一条；
  - u 为空 → 用内容 SHA-256 前 16 位占位（sha256:<prefix>）参与键与输出；
  - 输出记录按 (d, t) 排序，稳定且可复现。

用法：
  python3 scripts/build_feed_package.py --dates 2026-09-25,2026-09-26,2026-09-27   # 补历史
  python3 scripts/build_feed_package.py --yesterday                                # 每日收口
  python3 scripts/build_feed_package.py --today --no-push                          # 只生成不推送
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LITE_PATH = ROOT / "pipeline" / "data" / "processed" / "all-records-lite.json"
MANIFEST_DATA = ROOT / "pipeline" / "data" / "processed" / "manifest-data.js"
FEED_REPO = "sbq9712/tech-boundary-data-feed"
GENERATOR_VERSION = "feed-pkg/v2"

# ── v2 增量语义（feed-pkg/v2）────────────────────────────────────────────
# v1 按"记录发布日期 == 昨天"切片：迟到情报/旧记录修订/重评分/删除全部漏包。
# v2 改为"自上次成功打包以来的实际变化"：
#   runtime/feed_state.json 维护上次成功发布的 {key: content_hash} 全集；
#   每次运行对比当前 lite 全集 → ADD / UPDATE / DELETE；
#   changes.json 逐条记录 {op, id, key, v}（id=稳定 ID，v=单调版本），
#   records.json 仍输出受影响键的最新完整记录（导入端可只按 changes 增量）。
# 推送成功后才提交 watermark——失败不丢变化，下轮自动补齐。
# 幂等：同输入重复运行且无新变化 → 产出 no-change，不推送。
# 白名单导出：仅正向字段白名单（禁 cm/fb/sr/source 等内部字段进入公开包）。
PUBLIC_FIELDS = (
    "id", "t", "d", "u", "c", "a", "i", "tg", "tp", "sc", "scd", "aip",
    "as", "kp", "lv", "wr", "cl", "cp", "cln", "dp", "b", "hb",
)
WATERMARK_PATH = ROOT / "runtime" / "feed_state.json"

CST = timezone(timedelta(hours=8))


def log(msg: str) -> None:
    print(f"[feed-pkg {datetime.now(CST):%F %T}]", msg, flush=True)


def load_records() -> tuple[list[dict], str]:
    """读主存储 + data_version。"""
    records = json.loads(LITE_PATH.read_text(encoding="utf-8"))
    data_version = ""
    try:
        raw = MANIFEST_DATA.read_text(encoding="utf-8")
        start, end = raw.find("{"), raw.rfind("}")
        meta = json.loads(raw[start:end + 1]).get("meta", {})
        data_version = str(meta.get("data_version", ""))
    except (OSError, ValueError):
        pass
    return records, data_version


def record_date(rec: dict) -> str:
    """记录日期：d 字段（YYYY-MM-DD）；缺失归入 ''（不打包）。"""
    d = str(rec.get("d", "")).strip()
    return d if len(d) == 10 else ""


def content_hash(rec: dict, fields=None) -> str:
    """内容哈希：默认覆盖全部公开语义字段（v2）。

    v1 只哈希 t/b/i —— 重评分/重分类/摘要更新不会改变哈希，UPDATE 全部漏检。
    现在默认对"normalize 后的公开字段全集"哈希：任何会进入公开包的语义变化
    （分数、分类、档位、摘要、参数、主题…）都能被检测到并进入增量。
    fields 参数保留显式子集能力（导入端兼容旧包时可用）。"""
    ks = fields if fields is not None else sorted(k for k in rec if k != "id")
    raw = json.dumps({k: rec.get(k) for k in ks}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def stable_id(t: str, d: str, u: str) -> str:
    """稳定 ID：t|d|u 规范键的 SHA-256 前 16 位（跨批次/跨包不变）。"""
    raw = json.dumps([t, d, u], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def normalize(rec: dict, date: str) -> dict:
    """输出记录：正向字段白名单导出（v2）。

    - 白名单外交织字段（cm 评论 / fb 冗余全文 / sr/source 内部文件名等）不进公开包；
    - u 为空时按契约占位（"no-url" 常量）参与键——六.1（2026-10-01）：
      原占位 sha256:<内容哈希> 使无 URL 记录的内容更新（重评分/摘要）
      漂移身份（UPDATE 误判为 DELETE+ADD）；占位与内容解耦后身份稳定。
      同 t+d 的不同无 URL 记录本就无法区分（v1 同语义），合并为同键。
      旧水印键做一次性迁移（见 diff_against_watermark）。
    - id = t|d|u 规范键的稳定 ID。
    """
    out = dict(rec)
    out["d"] = date
    if not str(out.get("u", "")).strip():
        out["u"] = "no-url"  # 六.1：身份占位与内容解耦（内容漂移修复）
    out["id"] = stable_id(str(out.get("t", "")).strip(), date, str(out.get("u", "")))
    # 正向白名单：只导出公开语义字段（dict/list 嵌套保留，如 scd 五维分）
    return {k: out[k] for k in PUBLIC_FIELDS
            if k in out and isinstance(out[k], (str, int, float, bool, list, dict, type(None)))}


# 五.2（2026-10-01）公开来源准入（发布侧）：URL 可公开访问 ≠ 内容可公开
# 发布——内网/本机定位符、本地路径、内嵌凭据的记录一律拒绝导出；与导入端
# github_import._check_public_url、独立校验器公开准入检查同一规则集。
_PRIVATE_URL_RE = re.compile(
    r"(?i)localhost|127\.0\.0\.1|0\.0\.0\.0|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
    r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|\.local\b|file://|/home/|/root/"
    r"|C:\\\\Users|C:\\\\Users|[?&](token|key|secret|password|sig)=",)


def public_refusal_reason(norm: dict) -> str | None:
    """返回拒绝导出的原因；None = 通过公开准入。"""
    u = str(norm.get("u", ""))
    if u and u != "no-url" and not u.startswith("sha256:"):
        if _PRIVATE_URL_RE.search(u):
            return "非公开 URL（内网/本机/本地路径/内嵌凭据）"
        if not (u.startswith("http://") or u.startswith("https://")):
            return f"非 http(s) 定位符：{u[:60]!r}"
    # 白名单内字段不允许藏凭据形态的字符串（导出前最后一道闸）
    for field in ("t", "as", "b", "a", "wr"):
        val = str(norm.get(field, "") or "")
        if re.search(r"(?i)(ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}"
                     r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)", val):
            return f"{field} 含凭据形态字符串"
    return None


def dedup_key(rec: dict) -> tuple[str, str, str]:
    return (str(rec.get("t", "")).strip(), str(rec.get("d", "")), str(rec.get("u", "")))


# ── v2 watermark（自上次成功发布以来的实际变化）─────────────────────────
def load_watermark() -> dict:
    """上次成功发布时的 {key: content_hash} 全集 + 键版本号。"""
    if WATERMARK_PATH.exists():
        try:
            state = json.loads(WATERMARK_PATH.read_text(encoding="utf-8"))
            if isinstance(state, dict) and isinstance(state.get("hashes"), dict):
                return state
        except ValueError:
            pass
    return {"hashes": {}, "versions": {}, "updated_at": None,
            "sequence": 0, "chain": ""}


def save_watermark(state: dict) -> None:
    WATERMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = WATERMARK_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, WATERMARK_PATH)


def diff_against_watermark(records: list[dict], wm: dict) -> dict:
    """当前 lite 全集 vs 上次成功发布 → {added, updated, deleted, unchanged}。

    键 = t|d|u（规范化后，空 u 用内容占位）；内容变化以 content_hash 判定
    （覆盖迟到修订、重评分、摘要/分类更新），新增/删除以键的存在性判定。
    """
    hashes: dict[str, str] = {}
    by_key: dict[str, dict] = {}
    refused: list[str] = []
    for rec in records:
        date = record_date(rec)
        if not date:
            continue  # 无日期记录不进公开包（与 v1 一致）
        norm = normalize(rec, date)
        # 五.2 公开来源准入：内网/本地/凭据形态的记录不进公开包，
        # 也不进水印（已发布记录若变为不合格 → 自然产出 DELETE 变更）
        reason = public_refusal_reason(norm)
        if reason:
            refused.append(f"{norm.get('id', '')}: {reason}")
            continue
        key = "|".join(dedup_key(norm))
        hashes[key] = content_hash(norm)
        by_key.setdefault(key, norm)
    if refused:
        print(f"[feed] 公开准入拒绝 {len(refused)} 条记录（不入公开包/水印）:")
        for line in refused[:10]:
            print(f"  - {line}")
    old: dict[str, str] = dict(wm.get("hashes", {}))
    # 六.1 一次性迁移：旧无 URL 占位键（t|d|sha256:<内容>，占位含内容哈希，
    # 内容更新即漂移）→ 新 t|d|no-url 键。占位哈希基于旧内容、无法由当前
    # 记录复算——按 t|d 前缀匹配迁移（同 t+d 的无 URL 记录本就同键）。
    new_no_url_prefixes = {}
    for rec in records:
        date = record_date(rec)
        if not date:
            continue
        norm = normalize(rec, date)
        if str(norm.get("u", "")) == "no-url":
            new_no_url_prefixes[f"{norm.get('t', '')}|{date}|"] = \
                "|".join(dedup_key(norm))
    for lk in list(old.keys()):
        for prefix, nk in new_no_url_prefixes.items():
            if lk.startswith(prefix + "sha256:"):
                old[nk] = old.pop(lk)
                break
    added = [k for k in hashes if k not in old]
    updated = [k for k in hashes if k in old and old[k] != hashes[k]]
    deleted = [k for k in old if k not in hashes]
    return {"added": added, "updated": updated, "deleted": deleted,
            "hashes": hashes, "by_key": by_key, "refused": refused}


def build_changes_slice(records: list[dict], wm: dict) -> tuple[bytes, int, dict]:
    """v2 变化包：changes.json（ADD/UPDATE/DELETE + 稳定 id + 单调版本）
    + records.json（受影响键的最新完整记录，DELETE 键除外）。

    - 版本号 per-key 单调递增（旧版本包不能覆盖新版本：导入端按 v 比较）；
    - 包字节可复现（同输入同输出，除 generated_at 外）。
    返回 (zip_bytes, record_count, changes_summary)。
    """
    d = diff_against_watermark(records, wm)
    versions: dict[str, int] = dict(wm.get("versions", {}))
    changes = []
    out_records = []
    for key in sorted(set(d["added"] + d["updated"])):
        versions[key] = int(versions.get(key, 0)) + 1
        op = "ADD" if key in set(d["added"]) else "UPDATE"
        rec = d["by_key"][key]
        changes.append({"op": op, "id": rec.get("id"), "key": key, "v": versions[key]})
        out_records.append(rec)
    for key in sorted(d["deleted"]):
        versions[key] = int(versions.get(key, 0)) + 1
        # 六.1（2026-10-01）：标题可含 "|"，键必须从右侧按 | 切两段
        # （日期/URL 不含裸 "|"）——原 split("|") 在含竖线标题上抛 TypeError。
        changes.append({"op": "DELETE", "id": stable_id(*key.rsplit("|", 2)), "key": key,
                        "v": versions[key]})
    changes.sort(key=lambda c: c["key"])
    records_json = json.dumps(out_records, ensure_ascii=False, separators=(",", ":"))
    manifest = {
        "schema": "tech-boundary-feed-package/v2",
        "generator": GENERATOR_VERSION,
        "mode": "changes",
        "date": datetime.now(CST).strftime("%Y-%m-%d"),
        "record_count": len(out_records),
        "change_count": len(changes),
        "added": len(d["added"]), "updated": len(d["updated"]), "deleted": len(d["deleted"]),
        "records_sha256": hashlib.sha256(records_json.encode("utf-8")).hexdigest(),
        # 五.2（2026-10-01）：changes.json 字节绑定进 manifest（受
        # manifest_digest/chain 覆盖）——篡改变更条目（如 v 1→99）在
        # 校验器/导入端即刻哈希不一致，不再只靠计数对账。
        "changes_sha256": hashlib.sha256(
            json.dumps(changes, ensure_ascii=False, indent=1).encode("utf-8")).hexdigest(),
        "data_version": _DATA_VERSION,
        "generated_at": datetime.now(CST).isoformat(),
        "depends_on": "LATEST.json 全部先前包（漏包可按日期检测补齐）",
        # 六.3（2026-10-01）机器可验证的发布序列：
        #   sequence——单调自增（自 watermark.sequence+1），接收端按前驱
        #     +1 校验，缺口/乱序/重复包即刻可判；
        #   predecessor——上一包的 manifest_digest（空串为首包）；
        #   manifest_digest——本包 manifest 规范 JSON 的 sha256（链节点）；
        #   chain——sha256(prev_chain + manifest_digest) 哈希链头，任何
        #     插包/删包/改包都会破坏后续 chain 验证。
        "sequence": int(wm.get("sequence", 0)) + 1,
        "predecessor": str(wm.get("chain", "")),
        "manifest_digest": "",
        "chain": "",
    }
    # 六.3：链值计算（digest 基于除自引用字段外的 manifest 规范序列化）
    # 五.2：generated_at 是打包时刻、不是包内容——排除出 digest，同输入
    # 同水印重出的包链值逐字节一致（可复现包）。完整性由 records/changes
    # 哈希与接收端前驱对齐保证，打包时刻不参与身份。
    canon = {k: v for k, v in manifest.items()
             if k not in ("manifest_digest", "chain", "generated_at")}
    manifest["manifest_digest"] = hashlib.sha256(
        json.dumps(canon, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    manifest["chain"] = hashlib.sha256(
        (str(manifest["predecessor"]) + manifest["manifest_digest"]).encode("utf-8")).hexdigest()
    buf = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    buf.close()
    with zipfile.ZipFile(buf.name, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("records.json", records_json)
        # 与 changes_sha256 完全同字节（哈希与写入共用同一次序列化）
        zf.writestr("changes.json", json.dumps(changes, ensure_ascii=False, indent=1))
    data = Path(buf.name).read_bytes()
    os.unlink(buf.name)
    summary = {"added": len(d["added"]), "updated": len(d["updated"]),
               "deleted": len(d["deleted"]), "hashes": d["hashes"], "versions": versions,
               "sequence": manifest["sequence"], "chain": manifest["chain"],
               "manifest_date": manifest["date"],
               "refused_private": len(d.get("refused", []))}
    return data, len(out_records), summary


def build_slice(records: list[dict], date: str) -> tuple[bytes, int]:
    """某日期切片 → zip 字节 + 条数。幂等：同数据同日期产出字节一致。"""
    picked: dict[tuple, dict] = {}
    for rec in records:
        if record_date(rec) != date:
            continue
        norm = normalize(rec, date)
        key = dedup_key(norm)
        if key not in picked:
            picked[key] = norm
    items = sorted(picked.values(), key=lambda r: (r["d"], r["t"], r["u"]))
    records_json = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    manifest = {
        "schema": "tech-boundary-feed-package/v1",
        "generator": GENERATOR_VERSION,
        "date": date,
        "record_count": len(items),
        "records_sha256": hashlib.sha256(records_json.encode("utf-8")).hexdigest(),
        "data_version": data_version_of(records),
        "generated_at": datetime.now(CST).isoformat(),
    }
    buf = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    buf.close()
    with zipfile.ZipFile(buf.name, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("records.json", records_json)
    data = Path(buf.name).read_bytes()
    os.unlink(buf.name)
    return data, len(items)


_DATA_VERSION = ""


def data_version_of(records: list[dict]) -> str:
    return _DATA_VERSION


def main_since_last(records: list[dict], no_push: bool) -> int:
    """v2 每日收口：打包自上次成功发布以来的实际变化（ADD/UPDATE/DELETE）。

    watermark 只在确认「本地包已写好且（若推送）推送成功」后提交——
    失败/中断不丢变化，下轮重跑自动补齐（漏跑补跑语义）。

    六.4（2026-10-01）：整个 读水印→打包→推送→存水印 流程持独占文件锁
    （watermark 同目录 .lock，flock）——并发发布两个进程会读同一水印、
    各自产生 sequence N+1，推送后链分叉（后存者覆盖前者）。锁保证串行；
    第二个进程读到前者已提交的水印，自然产出 N+2 或空变化。
    """
    import fcntl
    WATERMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = WATERMARK_PATH.with_suffix(".lock")
    with open(lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        return _main_since_last_locked(records, no_push)


def _main_since_last_locked(records: list[dict], no_push: bool) -> int:
    wm = load_watermark()
    data, count, summary = build_changes_slice(records, wm)
    n_changes = summary["added"] + summary["updated"] + summary["deleted"]
    log(f"变化: +{summary['added']} ~{summary['updated']} -{summary['deleted']} "
        f"（记录 {count} 条，包 {len(data):,} bytes）")
    if n_changes == 0:
        log("自上次成功发布以来无变化，不产包（幂等）")
        return 0

    workdir = Path(tempfile.mkdtemp(prefix="feed-pkg-"))
    try:
        repo_dir = workdir / "feed"
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            for env_file in (Path.home() / ".gh_env", ROOT / ".gh_env"):
                if env_file.exists():
                    for line in env_file.read_text().splitlines():
                        if line.startswith(("export GH_TOKEN=", "GH_TOKEN=")):
                            token = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
                    if token:
                        break
        if not token and not no_push:
            log("ERROR: 推送需要 GH_TOKEN（~/.gh_env）；--no-push 可只生成本地包")
            return 1
        push_url = f"https://sbq9712:{token}@github.com/{FEED_REPO}.git" if token else ""
        if token:
            subprocess.run(["git", "clone", "--depth", "1",
                            "https://github.com/" + FEED_REPO + ".git", str(repo_dir)],
                           check=True, capture_output=True)
        else:
            repo_dir.mkdir(parents=True)
        subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "tech-boundary-feed"],
                       check=False)
        subprocess.run(["git", "-C", str(repo_dir), "config",
                        "user.email", "tech-boundary-feed@users.noreply.github.com"], check=False)

        daily = repo_dir / "daily"
        daily.mkdir(exist_ok=True)
        date_tag = datetime.now(CST).strftime("%Y-%m-%d")
        seq = 1
        target = daily / f"{date_tag}.zip"
        while target.exists():
            seq += 1
            target = daily / f"{date_tag}.{seq}.zip"
        target.write_bytes(data)
        log(f"→ {target.name} ({len(data):,} bytes)")

        # LATEST.json 索引
        latest_path = repo_dir / "LATEST.json"
        latest = {"schema": "tech-boundary-feed-index/v1", "generator": GENERATOR_VERSION,
                  "packages": [], "updated_at": datetime.now(CST).isoformat()}
        if latest_path.exists():
            try:
                old = json.loads(latest_path.read_text(encoding="utf-8"))
                latest["packages"] = [p for p in old.get("packages", [])
                                      if p.get("file") != target.name]
            except ValueError:
                pass
        latest["packages"].append({
            "date": date_tag, "file": target.name, "mode": "changes",
            "record_count": count, "change_count": n_changes,
            "added": summary["added"], "updated": summary["updated"],
            "deleted": summary["deleted"],
            "package_sha256": hashlib.sha256(data).hexdigest(),
        })
        latest["packages"].sort(key=lambda p: (p.get("date", ""), p.get("file", "")))
        latest["latest_date"] = latest["packages"][-1]["date"]
        latest_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")

        if no_push:
            keep = Path(tempfile.mkdtemp(prefix="feed-pkg-result-"))
            shutil.copytree(repo_dir, keep / "feed")
            log(f"[no-push] 结果保留在 {keep / 'feed'}（watermark 不提交，正式推送后生效）")
            return 0

        subprocess.run(["git", "-C", str(repo_dir), "add", "-A"], check=True)
        staged = subprocess.run(["git", "-C", str(repo_dir), "diff", "--cached", "--quiet"],
                                capture_output=True)
        if staged.returncode == 0:
            log("feed 仓库无变化（同数据重复生成，幂等跳过推送）")
            # 五.2：未发布任何包——sequence/chain 不推进（推进会产生
            # 幽灵链头：下一真包的前驱在接收端永远对不上）。只刷新
            # hashes/versions（内容基线与本轮计算一致）。
            save_watermark({"hashes": summary["hashes"], "versions": summary["versions"],
                            "updated_at": datetime.now(CST).isoformat(),
                            "sequence": wm.get("sequence", 0),
                            "chain": wm.get("chain", "")})
            return 0
        commit = subprocess.run(
            ["git", "-C", str(repo_dir), "commit", "-m",
             f"feed: changes +{summary['added']} ~{summary['updated']} -{summary['deleted']}"],
            capture_output=True, text=True)
        if commit.returncode != 0:
            log("ERROR: commit 失败: " + commit.stderr[:200])
            return 1
        push = subprocess.run(["git", "-C", str(repo_dir), "push", push_url, "main"],
                              capture_output=True, text=True)
        if push.returncode != 0:
            subprocess.run(["git", "-C", str(repo_dir), "fetch", "origin", "main"],
                           capture_output=True, check=True)
            rebase = subprocess.run(["git", "-C", str(repo_dir), "rebase", "origin/main"],
                                    capture_output=True, text=True)
            if rebase.returncode != 0:
                subprocess.run(["git", "-C", str(repo_dir), "rebase", "--abort"],
                               capture_output=True)
                log("ERROR: rebase 失败: " + rebase.stderr[:200])
                return 1
            push = subprocess.run(["git", "-C", str(repo_dir), "push", push_url, "main"],
                                  capture_output=True, text=True)
            if push.returncode != 0:
                log("ERROR: push 失败（rebase 后）: " + push.stderr[:200])
                return 1
        # 推送成功 → 才提交 watermark（失败重试不丢变化）
        save_watermark({"hashes": summary["hashes"], "versions": summary["versions"],
                        "updated_at": datetime.now(CST).isoformat(),
                        "sequence": summary["sequence"], "chain": summary["chain"]})
        log(f"已推送 {FEED_REPO}: {target.name} (+{summary['added']} ~{summary['updated']} "
            f"-{summary['deleted']})")
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    global _DATA_VERSION
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--since-last", action="store_true",
                   help="v2 增量：打包自上次成功发布以来的全部实际变化（推荐每日收口）")
    g.add_argument("--dates", help="逗号分隔的日期列表，如 2026-09-25,2026-09-26（v1 按记录日期切片）")
    g.add_argument("--yesterday", action="store_true", help="v1 兼容：打包昨天（按记录日期切片）")
    g.add_argument("--today", action="store_true", help="v1 兼容：打包今天（按记录日期切片）")
    parser.add_argument("--no-push", action="store_true", help="只生成本地 workdir，不推送")
    args = parser.parse_args()

    if not LITE_PATH.exists():
        log(f"ERROR: 主存储不存在: {LITE_PATH}")
        return 1

    records, dv = load_records()
    _DATA_VERSION = dv
    log(f"主存储: {len(records)} 条 / data_version={dv or '?'}")

    now = datetime.now(CST)
    if args.since_last:
        return main_since_last(records, args.no_push)
    if args.yesterday:
        dates = [(now - timedelta(days=1)).strftime("%Y-%m-%d")]
    elif args.today:
        dates = [now.strftime("%Y-%m-%d")]
    else:
        dates = [d.strip() for d in args.dates.split(",") if d.strip()]

    workdir = Path(tempfile.mkdtemp(prefix="feed-pkg-"))
    try:
        # 浅克隆 feed 仓库（保留既有 LATEST.json / README）
        repo_dir = workdir / "feed"
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            for env_file in (Path.home() / ".gh_env", ROOT / ".gh_env"):
                if env_file.exists():
                    for line in env_file.read_text().splitlines():
                        if line.startswith(("export GH_TOKEN=", "GH_TOKEN=")):
                            token = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
                if token:
                    break
        if not token:
            log("ERROR: 找不到 GH_TOKEN（~/.gh_env）")
            return 1
        push_url = f"https://sbq9712:{token}@github.com/{FEED_REPO}.git"
        subprocess.run(["git", "clone", "--depth", "1",
                        "https://github.com/" + FEED_REPO + ".git", str(repo_dir)],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "tech-boundary-feed"],
                       check=True)
        subprocess.run(["git", "-C", str(repo_dir), "config",
                        "user.email", "tech-boundary-feed@users.noreply.github.com"], check=True)

        daily = repo_dir / "daily"
        daily.mkdir(exist_ok=True)
        packages_meta = []
        for date in dates:
            data, count = build_slice(records, date)
            if count == 0:
                log(f"{date}: 0 条记录，跳过")
                continue
            target = daily / f"{date}.zip"
            target.write_bytes(data)
            log(f"{date}: {count} 条 → {target.name} ({len(data):,} bytes)")
            packages_meta.append({
                "date": date, "record_count": count,
                "package_sha256": hashlib.sha256(data).hexdigest(),
            })

        if not packages_meta:
            log("没有可打包的日期，退出")
            return 0

        # LATEST.json 索引（保留既有其他日期的条目，更新本次涉及日期）
        latest_path = repo_dir / "LATEST.json"
        latest = {"schema": "tech-boundary-feed-index/v1", "generator": GENERATOR_VERSION,
                  "packages": [], "updated_at": datetime.now(CST).isoformat()}
        if latest_path.exists():
            try:
                old = json.loads(latest_path.read_text(encoding="utf-8"))
                latest["packages"] = [p for p in old.get("packages", [])
                                      if p.get("date") not in {m["date"] for m in packages_meta}]
                latest["packages"].extend(packages_meta)
            except ValueError:
                pass
        else:
            latest["packages"] = packages_meta
        latest["packages"].sort(key=lambda p: p["date"])
        latest["latest_date"] = latest["packages"][-1]["date"]
        latest_path.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")

        if args.no_push:
            keep = Path(tempfile.mkdtemp(prefix="feed-pkg-result-"))
            shutil.copytree(repo_dir, keep / "feed")
            log(f"[no-push] 结果保留在 {keep / 'feed'}")
            return 0

        subprocess.run(["git", "-C", str(repo_dir), "add", "-A"], check=True)
        staged = subprocess.run(["git", "-C", str(repo_dir), "diff", "--cached", "--quiet"],
                                capture_output=True)
        if staged.returncode == 0:
            log("feed 仓库无变化（同数据重复生成，幂等跳过推送）")
            return 0
        dates_str = ",".join(m["date"] for m in packages_meta)
        commit = subprocess.run(
            ["git", "-C", str(repo_dir), "commit", "-m",
             f"feed: daily packages {dates_str} ({sum(m['record_count'] for m in packages_meta)} records)"],
            capture_output=True, text=True)
        if commit.returncode != 0:
            log("ERROR: commit 失败: " + commit.stderr[:200])
            return 1
        push = subprocess.run(["git", "-C", str(repo_dir), "push", push_url, "main"],
                              capture_output=True, text=True)
        if push.returncode != 0:
            # 远端有新提交 → rebase 重试一次（幂等覆盖场景）
            subprocess.run(["git", "-C", str(repo_dir), "fetch", "origin", "main"],
                           capture_output=True, check=True)
            rebase = subprocess.run(["git", "-C", str(repo_dir), "rebase", "origin/main"],
                                    capture_output=True, text=True)
            if rebase.returncode != 0:
                subprocess.run(["git", "-C", str(repo_dir), "rebase", "--abort"],
                               capture_output=True)
                log("ERROR: rebase 失败: " + rebase.stderr[:200])
                return 1
            push = subprocess.run(["git", "-C", str(repo_dir), "push", push_url, "main"],
                                  capture_output=True, text=True)
            if push.returncode != 0:
                log("ERROR: push 失败（rebase 后）: " + push.stderr[:200])
                return 1
        log(f"已推送 {FEED_REPO}: {dates_str}")
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
