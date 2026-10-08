#!/usr/bin/env python3
"""六.3 接收端序列校验（机器可验证）：逐包校验 sequence 连续、predecessor/
chain 哈希链、manifest_digest 自洽、records_sha256 完整性——缺口/乱序/
同日重复/篡改即刻可判，并报告缺口日期（供补齐 gap pack）。

用法：
  python3 scripts/verify_feed_sequence.py <dir-or-zip> [<dir-or-zip> ...]
  --allow-date-gaps 仅检查变化链；不证明每日发布。
退出码：0=序列完整一致；2=校验失败（stdout 列出缺口与坏包）。
"""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path


def load_manifest(zp: Path) -> dict:
    with zipfile.ZipFile(zp) as zf:
        m = json.loads(zf.read("manifest.json").decode("utf-8"))
        rec = zf.read("records.json").decode("utf-8")
        if m.get("changes_sha256") and hashlib.sha256(zf.read("changes.json")).hexdigest() != m["changes_sha256"]:
            raise ValueError(f"{zp.name}: changes_sha256 不匹配")
    # 完整性
    if m.get("records_sha256") != hashlib.sha256(rec.encode("utf-8")).hexdigest():
        raise ValueError(f"{zp.name}: records_sha256 不匹配（包被篡改或损坏）")
    canon = {k: v for k, v in m.items() if k not in ("manifest_digest", "chain", "generated_at")}
    digest = hashlib.sha256(json.dumps(
        canon, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    if digest != m.get("manifest_digest"):
        raise ValueError(f"{zp.name}: manifest_digest 不自洽")
    expect_chain = hashlib.sha256(
        (str(m.get("predecessor", "")) + digest).encode("utf-8")).hexdigest()
    if expect_chain != m.get("chain"):
        raise ValueError(f"{zp.name}: chain 与 predecessor+digest 不自洽")
    return m


def main(argv: list) -> int:
    allow_date_gaps = "--allow-date-gaps" in argv
    argv = [a for a in argv if a != "--allow-date-gaps"]
    zips: list[Path] = []
    for a in argv:
        p = Path(a)
        if p.is_dir():
            zips.extend(sorted(p.glob("*.zip")))
        elif p.is_file():
            zips.append(p)
    if not zips:
        print("未找到包", file=sys.stderr)
        return 2
    def sequence_order(path):
        try:
            return int(load_manifest(path).get("sequence", 0))
        except (ValueError, TypeError, zipfile.BadZipFile, KeyError, UnicodeError):
            return -1  # The validation loop reports malformed packages.
    # .2.zip sorts BEFORE .zip lexically; use the signed manifest sequence.
    zips.sort(key=sequence_order)
    prev_seq, prev_chain, prev_date = 0, "", ""
    problems: list[str] = []
    seen_dates: set[str] = set()
    for zp in zips:
        try:
            m = load_manifest(zp)
        except (ValueError, TypeError, zipfile.BadZipFile, KeyError, UnicodeError) as exc:
            problems.append(str(exc))
            continue
        try:
            seq = int(m.get("sequence", 0))
            date = str(m.get("date", ""))
            from datetime import date as _date
            _date.fromisoformat(date)
        except (ValueError, TypeError):
            problems.append(f"{zp.name}: sequence/date 格式错误")
            continue
        if seq != prev_seq + 1:
            problems.append(f"{zp.name}: sequence 不连续（期望 {prev_seq + 1}，实际 {seq}）"
                            + ("——同日重复或乱序" if seq <= prev_seq else "——存在缺口包"))
        if prev_chain and m.get("predecessor") != prev_chain:
            problems.append(f"{zp.name}: predecessor 与前一包 chain 不一致（插包/删包/改包）")
        if date < prev_date:
            problems.append(f"{zp.name}: 日期倒序（{date} < {prev_date}）")
        # 同日多包合法（gap pack / 当日重发）——连续性由 sequence 保证；
        # 只有 sequence 倒退/重复（上面已判）才是问题。
        seen_dates.add(date)
        prev_seq, prev_chain, prev_date = seq, str(m.get("chain", "")), date
        n_add = sum(1 for c in (m.get("changes") or []) if c.get("op") == "ADD") \
            if isinstance(m.get("changes"), list) else None
        print(f"ok {zp.name} seq={seq} date={date} "
              f"records={m.get('record_count')}")
    # 缺口日期报告（首包日期到末包日期之间缺失的自然日）
    if zips and problems == []:
        try:
            dates = sorted({str(load_manifest(z).get("date")) for z in zips})
            from datetime import date as _d, timedelta as _td
            start = _d.fromisoformat(dates[0])
            end = _d.fromisoformat(dates[-1])
            missing = []
            cur = start
            while cur <= end:
                iso = cur.isoformat()
                if iso not in dates:
                    missing.append(iso)
                cur += _td(days=1)
            if missing:
                message = f"缺口日期（无包自然日）：{missing}"
                print(message)
                if not allow_date_gaps:
                    problems.append(message)
        except Exception:
            pass
    if problems:
        print("\n".join(f"✗ {p}" for p in problems))
        return 2
    print("序列校验通过：sequence 连续、哈希链一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
