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
GENERATOR_VERSION = "feed-pkg/v1"

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


def content_hash(rec: dict) -> str:
    raw = json.dumps(
        {k: rec.get(k) for k in ("t", "b", "i")}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize(rec: dict, date: str) -> dict:
    """输出记录：契约三键（t/d/u）+ 全部处理字段。u 为空时按契约占位。"""
    out = dict(rec)
    out["d"] = date
    if not str(out.get("u", "")).strip():
        out["u"] = "sha256:" + content_hash(rec)[:16]
    # 只保留 JSON 安全的已处理字段（dict/list 嵌套同样保留，如 scd 五维分）
    return {k: v for k, v in out.items()
            if isinstance(v, (str, int, float, bool, list, dict, type(None)))}


def dedup_key(rec: dict) -> tuple[str, str, str]:
    return (str(rec.get("t", "")).strip(), str(rec.get("d", "")), str(rec.get("u", "")))


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


def main() -> int:
    global _DATA_VERSION
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--dates", help="逗号分隔的日期列表，如 2026-09-25,2026-09-26")
    g.add_argument("--yesterday", action="store_true", help="打包昨天（每日收口）")
    g.add_argument("--today", action="store_true", help="打包今天（管线后随动）")
    parser.add_argument("--no-push", action="store_true", help="只生成本地 workdir，不推送")
    args = parser.parse_args()

    if not LITE_PATH.exists():
        log(f"ERROR: 主存储不存在: {LITE_PATH}")
        return 1

    records, dv = load_records()
    _DATA_VERSION = dv
    log(f"主存储: {len(records)} 条 / data_version={dv or '?'}")

    now = datetime.now(CST)
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
