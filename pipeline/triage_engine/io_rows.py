# -*- coding: utf-8 -*-
"""triage_engine.io_rows —— 三源 CSV → 行记录列表 读取器。

与 outputs/test-triage-2026062{5,6} 测试 harness 的读取逻辑同源：
  - news-spider：articles-*.csv（title/published_at/content/url/source_name），quality=full|empty
  - wechat：*.csv（clean_text > content_preview > digest 分层），quality=full|preview|digest|empty
  - literature：news_with_abstract_*.csv（abstract 为摘要载体，含 doi/link），quality=abstract|empty
日期缺失时退化为文件名日期。预处理（body_prep）调用管线 base.preprocess_body，保持单源。
"""
from __future__ import annotations

import csv
import glob
import os

from .engine import load_base


def _prep(raw_body: str, title: str):
    base = load_base()
    return base.preprocess_body(raw_body, title)


def _fday(base, path, strip_prefixes):
    name = os.path.basename(path)
    for p in strip_prefixes:
        name = name.replace(p, "").replace(".csv", "")
    return base._d_from_str(name)


def read_news_csv(path):
    base = load_base()
    fday = _fday(base, path, ["articles-"])
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        d = base._d_from_str(r.get("published_at")) or fday
        raw_body = r.get("content") or ""
        body, body_prep = _prep(raw_body, (r.get("title") or "").strip())
        rows.append({"src": "news-spider", "date": d.isoformat(),
                     "title": (r.get("title") or "").strip(), "url": r.get("url") or "",
                     "meta": r.get("source_name") or "", "body": body, "doi": "",
                     "body_prep": body_prep,
                     "content_quality": "full" if raw_body.strip() else "empty"})
    return rows


def read_wechat_csv(path):
    base = load_base()
    fday = _fday(base, path, [])
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        d = base._d_from_str(r.get("publish_time")) or fday
        raw_full = r.get("clean_text") or ""
        raw_preview = r.get("content_preview") or ""
        raw_digest = r.get("digest") or ""
        raw_body = raw_full or raw_preview or raw_digest
        quality = ("full" if raw_full.strip() else
                   "preview" if raw_preview.strip() else
                   "digest" if raw_digest.strip() else "empty")
        body, body_prep = _prep(raw_body, (r.get("title") or "").strip())
        rows.append({"src": "wechat", "date": d.isoformat(),
                     "title": (r.get("title") or "").strip(), "url": r.get("url") or "",
                     "meta": r.get("account_name") or "", "body": body, "doi": "",
                     "body_prep": body_prep, "content_quality": quality})
    return rows


def read_literature_csv(path):
    base = load_base()
    fday = _fday(base, path, ["news_with_abstract_"])
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        d = base._d_from_str(r.get("pub_date")) or fday
        raw_body = r.get("abstract") or ""
        body, body_prep = _prep(raw_body, (r.get("title") or "").strip())
        rows.append({"src": "literature", "date": d.isoformat(),
                     "title": (r.get("title") or "").strip(), "url": r.get("link") or "",
                     "meta": r.get("source") or "", "body": body,
                     "doi": r.get("doi") or "", "body_prep": body_prep,
                     "content_quality": "abstract" if raw_body.strip() else "empty"})
    return rows


def read_batch_dir(root):
    """按批次目录批量读取（扁平布局）：
    root/news-spider/articles-*.csv、root/wechat/*.csv、root/literature/news_with_abstract_*.csv。
    返回 (rows, 读到的文件列表)。"""
    rows, files = [], []
    for p in sorted(glob.glob(os.path.join(root, "news-spider", "articles-*.csv"))):
        rows += read_news_csv(p); files.append(p)
    for p in sorted(glob.glob(os.path.join(root, "wechat", "*.csv"))):
        rows += read_wechat_csv(p); files.append(p)
    for p in sorted(glob.glob(os.path.join(root, "literature", "news_with_abstract_*.csv"))):
        rows += read_literature_csv(p); files.append(p)
    return rows, files


def read_rows_json(path):
    """读取外部已准备好的行记录 JSON（list[dict]，schema 见 AI_INTERFACE.md）。"""
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)
