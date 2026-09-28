#!/usr/bin/env python3
"""tech-boundary-db 独立广度管线（移植自 tech-db auto_pipeline.py，2026-09-27）。

与上游的差异（本仓库内自包含，完全不依赖 tech-db 仓库）：
- git_push() → publish_to_boundary()：产物直接安装到本仓库 breadth/data/
  （web 容器只读卷挂载，即时生效），并重建广度页派生快照、同步报告、
  bump breadth/version.txt（触发前端「新版本」提示条）。
- 无 GitHub push、无 state 上传；state 只存本地 .pipeline_state.json。
- 搜索索引重建（Step 10）由调用方以 SKIP_INDEX_BUILD=1 跳过。

原管线语义全部保留：
  1. state 是「已成功发布」的文件记录，不是「已看到的文件」
  2. 任何中间步骤失败 → state 不更新 → 下次 cron 自动重试
  3. 发布失败 = 整个 pipeline 失败，state 保留
  4. 下载失败的文件不进入 state
  5. 无日期文件（如 articles.csv）每次都重新处理（因为内容会变）
  6. 分片数量由数据量动态决定，前端也动态检测
  7. 单实例锁防止并发
"""
import json, os, sys, subprocess, time, hashlib, glob, re, fcntl
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
from build_snapshot import build_snapshot
from llm_client import call_glm_batch, call_glm

REPO = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO, "data", "processed")
LITE_PATH = os.path.join(DATA_DIR, "all-records-lite.json")
# state 放在持久化目录，不放 /tmp（tmpfs 重启即丢）
STATE_FILE = os.path.join(REPO, ".pipeline_state.json")
LOCK_FILE = os.path.join(REPO, ".pipeline.lock")
TOKEN = os.environ.get("GH_TOKEN", "")
# Self-heal: cron jobs don't inherit the user shell env.
if not TOKEN:
    for _env in (os.path.join(os.path.expanduser("~"), ".gh_env"), os.path.join(REPO, ".gh_env")):
        try:
            with open(_env) as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line.startswith("export GH_TOKEN=") or _line.startswith("GH_TOKEN="):
                        TOKEN = _line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if TOKEN:
                break
        except (FileNotFoundError, PermissionError):
            continue
GH_PUSH_URL = None  # 独立模式：不再向 GitHub 推送（保留变量名以免触碰 gh_api 注释）

# 无日期前缀的文件，内容会滚动更新，每次都必须重新处理
ROLLING_FILES = {"articles.csv"}
CHUNK_SIZE = 2000

# 合法标签集合（GLM 返回的其他标签一律纠正为默认值）
VALID_NEWS_TAGS = {"技术突破", "产业进展", "政策监管", "资本运作", "行业观察"}
VALID_LIT_TAGS = {"研究论文", "观点评论"}

# 分类树唯一权威来源：77 个固定叶子。没有用户明确命令不得增删。
TAXONOMY_PATH = os.path.join(REPO, "data", "category-taxonomy.json")
with open(TAXONOMY_PATH, encoding="utf-8") as _f:
    VALID_CATEGORY_LEAVES = set(json.load(_f)["categories"])
VALID_CLASSIFICATIONS = VALID_CATEGORY_LEAVES | {"不相关", "未分类"}

# Source repos
SOURCES = {
    "news": {"repo": "wodewoping-png/news-spider", "path": "data", "prefix": "articles-"},
    "literature": {"repo": "wodewoping-png/literature-rss-spider", "path": "output", "prefix": "news_with_abstract_"},
    "wechat": {"repo": "wodewoping-png/wechat-daily-news-csv", "path": "csv", "prefix": ""},
}

def log(msg):
    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

# ── 单实例锁 ──
def acquire_lock():
    """防止两个 cron 同时运行。"""
    lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_WRONLY)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except (BlockingIOError, OSError):
        log("[SKIP] Another pipeline instance is running. Exiting.")
        os.close(lock_fd)
        sys.exit(1)

# ── GitHub API（正确认证）──
def gh_api(url):
    """GitHub API call with proper authentication."""
    try:
        cmd = ["curl", "-4", "-sL", f"https://api.github.com/repos/{url}"]
        if TOKEN:
            cmd += ["-H", f"Authorization: Bearer {TOKEN}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
        return None

def get_source_files():
    """Get latest file lists from all 3 source repos"""
    new_files = {}
    for name, info in SOURCES.items():
        url = f"{info['repo']}/contents/{info['path']}"
        data = gh_api(url)
        if not isinstance(data, list):
            log(f"  [WARN] {name}: API failed")
            continue
        csvs = sorted([d["name"] for d in data if d["name"].endswith(".csv")])
        new_files[name] = csvs
    return new_files

# ── State 管理 ──
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"known_files": {}, "file_hashes": {}}


def ensure_state_file():
    """2026-08-17 fix: on a fresh CI checkout .pipeline_state.json does not
    exist (it is only written after a first successful push). git_push()
    stages it via a literal pathspec — `git add` fatals with 'pathspec did
    not match any files', killing the push AFTER all LLM work is done.
    Seed the default state so the pathspec always matches."""
    if not os.path.exists(STATE_FILE):
        save_state(load_state())

def save_state(state):
    """Atomic write: write to temp then rename."""
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, ensure_ascii=False)
    os.rename(tmp, STATE_FILE)

def file_content_hash(path):
    """SHA256 of file content — used to detect rolling file changes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

# ── Checkpoint / resume support (T4) ──
CHECKPOINT_FILE = os.path.join(REPO, ".rebuild_checkpoint.json")

def load_checkpoint():
    """Load checkpoint for interrupt-resume of LLM-heavy stages."""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_checkpoint(stage, completed_ids, results=None):
    """Save checkpoint after each batch."""
    cp = load_checkpoint()
    cp[stage] = {"completed_ids": sorted(set(completed_ids))}
    if results:
        cp[stage]["results"] = results
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(cp, f, ensure_ascii=False)

def clear_checkpoint():
    """Remove checkpoint file after successful completion."""
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

def check_new_files():
    """检测新文件或内容变化的滚动文件。
    不修改 state。返回 (has_new, new_per_source, current, n_failed)。"""
    state = load_state()
    current = get_source_files()

    # CI mode: only process files from the last N days to avoid backlog.
    # 冷启动豁免：state 里没有任何已知文件（新环境/全量重建）时不裁剪——
    # 从三个源头完整重建必须处理全部历史，不能只处理最近 7 天。
    max_days = os.environ.get("PIPELINE_MAX_DAYS")
    cold_start = not any(state.get("known_files", {}).values())
    if max_days and not cold_start:
        max_days = int(max_days)
        cutoff = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=max_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")
        log(f"  CI mode: only processing files dated >= {cutoff_str}")

    n_failed = len(SOURCES) - len(current)
    has_new = False
    new_per_source = {}
    for name, files in current.items():
        known = set(state["known_files"].get(name, []))
        current_set = set(files)
        new = current_set - known
        # CI filter: only keep recent files
        if max_days:
            new = {f for f in new if _extract_date_from_filename(f, name) >= cutoff_str}
        # 滚动文件：即使文件名已知，如果内容 hash 变了也要重新处理
        for fname in list(files):
            if fname in ROLLING_FILES and fname in known:
                new.add(fname)
        if new:
            has_new = True
            new_per_source[name] = sorted(new)
            log(f"  {name}: {len(new)} new/changed files: {', '.join(sorted(new)[:5])}")
        else:
            log(f"  {name}: up to date ({len(files)} files)")

    return has_new, new_per_source, current, n_failed


def _extract_date_from_filename(fname, source_name):
    """Extract a YYYY-MM-DD date from a filename, return '' if not parseable."""
    import re
    # articles-2026-07-21.csv → 2026-07-21
    # news_with_abstract_2026-07-21.csv → 2026-07-21
    # 2026-06-15.csv → 2026-06-15
    m = re.search(r'(\d{4}-\d{2}-\d{2})', fname)
    if m:
        return m.group(1)
    # Also try YYYYMMDD format
    m = re.search(r'(\d{4})(\d{2})(\d{2})', fname)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""

def commit_state(current, processed_files):
    """只把成功处理并推送的文件标记为已处理。
    processed_files: {source_name: [(fname, content_hash), ...]}"""
    state = load_state()
    # Ensure keys exist (handle legacy state files)
    if "known_files" not in state:
        state["known_files"] = {}
    if "file_hashes" not in state:
        state["file_hashes"] = {}
    for name in current:
        existing = set(state["known_files"].get(name, []))
        for fname, _hash in processed_files.get(name, []):
            existing.add(fname)
            state["file_hashes"][f"{name}/{fname}"] = _hash
        state["known_files"][name] = sorted(existing)
    save_state(state)
    log(f"  State committed ({sum(len(v) for v in processed_files.values())} files marked)")

# ── CSV 下载与解析 ──
def download_new_csvs(new_per_source):
    """下载 CSV 文件。返回 (records, successfully_downloaded, failed_files)。
    successfully_downloaded: {source: [(fname, hash), ...]}
    failed_files: [(source, fname), ...]
    """
    import csv as csv_mod

    new_records = []
    successfully_downloaded = {}
    failed_files = []

    for name, new_files in new_per_source.items():
        info = SOURCES[name]
        successfully_downloaded[name] = []

        for fname in new_files:
            url = f"https://raw.githubusercontent.com/{info['repo']}/main/{info['path']}/{fname}"
            local_path = f"/tmp/techdb_{name}_{fname}"
            # Never accept a stale file left by an earlier failed run.
            try:
                os.remove(local_path)
            except FileNotFoundError:
                pass
            ok = False
            for _attempt in range(3):
                rc = None
                try:
                    # --fail：HTTP ≥400（404 文本/限流页等）必须视为失败，
                    # 绝不能把错误响应体落盘当数据处理（历史缺陷：404 文本被记为处理成功）。
                    r = subprocess.run(
                        ["curl", "-4", "-sSL", "--fail", "--retry", "3", "--retry-delay", "2",
                         "--connect-timeout", "15", "--max-time", "90",
                         url, "-o", local_path],
                        capture_output=True, timeout=120
                    )
                    rc = r.returncode
                except subprocess.TimeoutExpired:
                    log(f"  [WARN] timeout dl {fname} (attempt {_attempt+1}/3)")
                if rc == 0 and os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                    ok = True
                    break
                # raw.githubusercontent.com may be unreachable; fall back to API raw endpoint
                api_url = f"https://api.github.com/repos/{info['repo']}/contents/{info['path']}/{fname}"
                try:
                    r = subprocess.run(
                        ["curl", "-4", "-sSL", "--fail", "-H", "Accept: application/vnd.github.v3.raw",
                         "--connect-timeout", "15", "--max-time", "90",
                         api_url, "-o", local_path],
                        capture_output=True, timeout=120
                    )
                    if r.returncode == 0 and os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                        log(f"  {fname}: raw endpoint failed, got via API fallback")
                        ok = True
                        break
                except subprocess.TimeoutExpired:
                    log(f"  [WARN] timeout API dl {fname} (attempt {_attempt+1}/3)")
                time.sleep(2)
            if not ok:
                log(f"  [ERROR] Failed to download {fname} — will NOT mark as processed")
                failed_files.append((name, fname))
                continue

            # 验证内容是否真的变化（针对滚动文件）
            chash = file_content_hash(local_path)
            # T5: Persist CSV to data/csv_cache/ for future record-level diff
            cache_dir = os.path.join(REPO, "data", "csv_cache", name)
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, fname)
            try:
                import shutil
                shutil.copy2(local_path, cache_path)
            except Exception:
                pass  # Non-fatal: cache is best-effort
            state = load_state()
            old_hash = state.get("file_hashes", {}).get(
                f"{name}/{fname}",
                state.get("file_hashes", {}).get(fname),  # legacy state compatibility
            )
            if fname in ROLLING_FILES and old_hash == chash:
                log(f"  {fname}: content unchanged, skipping")
                successfully_downloaded[name].append((fname, chash))
                continue

            # Parse CSV
            try:
                # 内容兜底校验：即便下载"成功"，也必须长得像本源 CSV（表头含 title 列、
                # 且不是 HTML 错误页），否则视为失败不推进状态。
                with open(local_path, "r", encoding="utf-8-sig", newline="") as _probe:
                    _head = _probe.read(4096)
                if "title" not in _head.lower() or _head.lstrip()[:1] in ("<", "{"):
                    raise ValueError(
                        f"downloaded content is not a valid CSV for source '{name}' "
                        f"(looks like {_head.lstrip()[:1]!r} page)")
                with open(local_path, "r", encoding="utf-8-sig", newline="") as f:
                    reader = csv_mod.DictReader(f)
                    for row in reader:
                        title = row.get("title", row.get("Title", ""))
                        # Body extraction: per-source primary column with assertion (T2)
                        # Uses shared _extract_body for consistency with diff hashing
                        primary = PRIMARY_BODY_COL.get(name)
                        body = ""
                        if primary and not row.get(primary):
                            log(f"  [WARN] {name} {fname}: 主列{primary}缺失，回退链取值")
                        body = _extract_body(row, name)
                        # Date extraction: prefer publish date from row, fallback to filename
                        pub_date = row.get("publish_time",
                                   row.get("published_at",
                                   row.get("pub_date",
                                   row.get("published_str", ""))))
                        if pub_date:
                            m2 = re.search(r'(\d{4}-\d{2}-\d{2})', pub_date)
                            date = m2.group(1) if m2 else ""
                        else:
                            date = ""
                        if not date:
                            m = re.search(r'(\d{4}-\d{2}-\d{2})', fname)
                            date = m.group(1) if m else ""
                        url_val = row.get("url", row.get("link", row.get("URL", "")))
                        source_name = row.get("source", row.get("account_name",
                                   row.get("source_name",
                                   row.get("authors",
                                   row.get("author", row.get("Authors", ""))))))
                        if not title:
                            continue
                        new_records.append({
                            "t": title[:500],
                            "b": body if body else "",
                            "d": date,
                            "u": url_val,
                            "c": "未分类",
                            "a": source_name,
                            "i": "l" if "literature" in name else "n",
                            "source": fname,
                            "sr": f"{name}/{fname}",
                        })
                successfully_downloaded[name].append((fname, chash))
            except Exception as e:
                log(f"  [ERROR] Parse error {fname}: {e} — will NOT mark as processed")
                failed_files.append((name, fname))

    return new_records, successfully_downloaded, failed_files

# ── 去重 ──
def normalize_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    m = re.search(r'(10\.\d{4,}/[^\s?#]+)', url)
    if m:
        return f"DOI:{m.group(1).lower().rstrip('.')}"
    m = re.search(r'nature\.com/articles/(s\d+-\d+-\d+[-\w]*)', url)
    if m:
        return f"DOI:10.1038/{m.group(1).lower()}"
    parsed = urlparse(url.lower().rstrip('/'))
    return f"URL:{parsed.netloc}{parsed.path}"

def dedup_check(new_records, existing_lite):
    existing_titles = set()
    existing_body_prefix = set()
    existing_urls = set()
    for r in existing_lite:
        t = r.get("t", "").strip().lower()[:80]
        b = r.get("b", "")[:80]
        u = normalize_url(r.get("u", ""))
        if t: existing_titles.add(t)
        if b: existing_body_prefix.add(b)
        if u: existing_urls.add(u)

    unique = []
    dupes = 0
    # Add accepted records to these sets so duplicates inside the same new batch are removed too.
    for r in new_records:
        t = r.get("t", "").strip().lower()[:80]
        b = r.get("b", "")[:80]
        u = normalize_url(r.get("u", ""))
        if t in existing_titles or (b and b in existing_body_prefix) or (u and u in existing_urls):
            dupes += 1
        else:
            unique.append(r)
            if t: existing_titles.add(t)
            if b: existing_body_prefix.add(b)
            if u: existing_urls.add(u)
    return unique, dupes

# ── Record-level diff (T6) ──
# Shared body extraction logic for consistent hashing between diff and download
PRIMARY_BODY_COL = {"wechat": "clean_text", "news": "content", "literature": "abstract"}

def _extract_body(row, source_name):
    """Extract body using source-specific primary column, with fallback chain.
    Shared between download_new_csvs and _record_hash for consistency."""
    primary = PRIMARY_BODY_COL.get(source_name)
    if primary and row.get(primary):
        return row[primary]
    return (row.get("clean_text", row.get("abstract", row.get("content",
            row.get("body", row.get("Body", row.get("content_preview",
            row.get("digest", row.get("summary", ""))))))))) or ""

def _record_hash(row, source_name):
    """Hash content-semantic fields only (excludes timestamps, filenames, row numbers)."""
    import hashlib
    t = (row.get("title", row.get("Title", "")) or "").strip()
    b = (_extract_body(row, source_name)).strip()
    u = (row.get("url", row.get("link", row.get("URL", ""))) or "").strip()
    a = (row.get("source", row.get("account_name", row.get("source_name", ""))) or "").strip()
    raw = f"{t}\x00{b}\x00{u}\x00{a}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def diff_csv_records(old_csv_path, new_csv_path, source_name):
    """Compare old and new CSV at record level using URL as key.
    Returns dict with keys: unchanged, changed, deleted, new (lists of new-CSV rows).
    """
    def load_csv_rows(path):
        """Load CSV into {normalize_url: [rows]} mapping."""
        groups = {}
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv_mod.DictReader(f)
                for row in reader:
                    url_key = normalize_url(row.get("url", row.get("link", row.get("URL", ""))))
                    if not url_key:
                        continue
                    groups.setdefault(url_key, []).append(row)
        except Exception as e:
            log(f"  [WARN] diff_csv load error {path}: {e}")
        return groups

    old_groups = load_csv_rows(old_csv_path)
    new_groups = load_csv_rows(new_csv_path)

    result = {"unchanged": [], "changed": [], "deleted": [], "new": []}

    old_urls = set(old_groups.keys())
    new_urls = set(new_groups.keys())

    for url in new_urls - old_urls:
        result["new"].extend(new_groups[url])

    for url in old_urls - new_urls:
        result["deleted"].append(url)

    for url in old_urls & new_urls:
        old_set_hash = sorted(_record_hash(r, source_name) for r in old_groups[url])
        new_set_hash = sorted(_record_hash(r, source_name) for r in new_groups[url])
        if old_set_hash == new_set_hash:
            result["unchanged"].extend(new_groups[url])
        else:
            result["changed"].extend(new_groups[url])

    return result

# ── Upsert records (T7) ──
def upsert_records(lite, changed_records, deleted_urls):
    """Process changed and deleted records from rolling file updates.
    Does NOT touch manually imported records (source=='excel-import' or lv>=1).
    Returns updated lite list.
    """
    PROTECTED = lambda r: r.get("source") == "excel-import" or r.get("lv") == 3

    # Build URL → [idx] index for non-protected records only
    url_index = {}
    for idx, r in enumerate(lite):
        if PROTECTED(r):
            continue
        u = normalize_url(r.get("u", ""))
        if u:
            url_index.setdefault(u, []).append(idx)

    # Handle changed: delete old, append new
    changed_count = 0
    if changed_records:
        changed_urls = set()
        for r in changed_records:
            u = normalize_url(r.get("u", ""))
            if u:
                changed_urls.add(u)
        # Delete old records with these URLs (non-protected only)
        to_delete = set()
        for u in changed_urls:
            for idx in url_index.get(u, []):
                if not PROTECTED(lite[idx]):
                    to_delete.add(idx)
        lite = [r for i, r in enumerate(lite) if i not in to_delete]
        changed_count = len(to_delete)

    # Handle deleted: remove records with these URLs
    deleted_count = 0
    if deleted_urls:
        to_delete = set()
        for u in deleted_urls:
            for idx in url_index.get(u, []):
                if not PROTECTED(lite[idx]):
                    to_delete.add(idx)
        lite = [r for i, r in enumerate(lite) if i not in to_delete]
        deleted_count = len(to_delete)

    return lite, changed_count, deleted_count

# ── GLM 调用 ──
# call_glm_batch is imported from llm_client (no longer uses hermes CLI)

# ── 标题翻译 ──
def translate_non_chinese_titles(records):
    """将无中文字符的标题翻译为中文（GLM-5.3-flash 批量翻译）。

    原 Google Translate 方案因 429 限流失效（2026-09 起），改用 ZAI GLM API。
    每批携带 id，按 id 回填，批内乱序/缺项不影响对齐。
    """
    has_cn = lambda s: bool(re.search(r'[\u4e00-\u9fff]', s or ''))
    targets = [(i, r['t']) for i, r in enumerate(records) if not has_cn(r.get('t', ''))]
    if not targets:
        log(f"  标题翻译: 0 条需要翻译")
        return records

    log(f"  标题翻译: {len(targets)} 条需要翻译 (GLM 批量)")
    TRANSLATE_PROMPT = (
        "你是技术情报标题翻译引擎。将下列 JSON 数组中的每条外语标题翻译成简体中文。\n"
        "要求：\n"
        "1. 保留专业术语的准确性与行业通用译法\n"
        "2. 专有名词（公司名/产品名/模型名/人名）保留英文\n"
        "3. 只输出 JSON 数组，格式：[{\"id\":0,\"zh\":\"翻译\"},...]，"
        "id 与输入一致，不要输出其他任何内容\n\n输入："
    )

    from concurrent.futures import ThreadPoolExecutor, as_completed
    BATCH = 25
    MAX_WORKERS = 5
    batches = []
    for bstart in range(0, len(targets), BATCH):
        chunk = targets[bstart:bstart + BATCH]
        batches.append([{"id": k, "title": t} for k, (_, t) in enumerate(chunk)])

    def _do_batch(batch):
        full_prompt = TRANSLATE_PROMPT + json.dumps(batch, ensure_ascii=False)
        for attempt, delay in enumerate((0, 5, 15, 45)):
            if delay:
                time.sleep(delay)
            try:
                out = call_glm(full_prompt, timeout=120)
                s, e = out.find("["), out.rfind("]")
                if s >= 0 and e > s:
                    arr = json.loads(out[s:e + 1])
                    if isinstance(arr, list):
                        return arr
            except Exception:
                pass
        return None

    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_do_batch, b): (bn, b) for bn, b in enumerate(batches)}
        for f in as_completed(futures):
            bn, batch = futures[f]
            try:
                arr = f.result()
            except Exception:
                arr = None
            if not arr:
                continue
            base = bn * BATCH
            for row in arr:
                try:
                    rid = int(row.get("id"))
                    zh = (row.get("zh") or "").strip()
                except Exception:
                    continue
                if 0 <= rid < len(batch) and zh and has_cn(zh):
                    records[targets[base + rid][0]]['t'] = zh
                    done += 1

    log(f"  标题翻译: {done}/{len(targets)} 成功")
    return records


def classify_and_score(records):
    """Step 4：领域分类 + 情报类型 + 评分 + AI精选判定（2026-09-28 起 = triage_engine）。

    引擎（v1.11）取代原 GLM 分类/评分提示词，成为唯一分类与评分来源：
    - 领域 c：引擎语义叶/规则域/扩展域 → 主库 125 叶；域外 → "不相关"（终止后续管线）
    - 载体 i：引擎展示链判定论文/新闻（C-T16 载体前提，不按源文件名）
    - 类型 tg：引擎展示链 → 前端既有 7 标签词表
    - 评分 sc：引擎 S8 value/10；维度 scd 由引擎评分卡归一
    - 精选 aip：新闻按引擎最终档位（高/中 → 精选，低不精选）；文献一律不精选
    - 档位只在后台判断使用，不落任何面向用户的标签
    其余管线步骤（标题翻译/主题 tp/AI 摘要/关键参数/聚类/发布）语义不变。
    """
    if not records:
        return records
    import engine_triage
    use_llm = not os.environ.get("TRIAGE_LLM_OFF")
    try:
        stats = engine_triage.engine_triage_records(
            records, use_llm=use_llm,
            workdir=os.path.join(REPO, ".engine_triage_work"),
            llm_batch=int(os.environ.get("TRIAGE_LLM_BATCH", "8")),
            llm_sleep=float(os.environ.get("TRIAGE_LLM_SLEEP", "2.0")),
        )
    except Exception as exc:
        log(f"[ERROR] triage_engine failed: {exc}")
        raise
    log(f"  引擎分诊: {stats['matched']}/{stats['total']} matched, "
        f"{stats['irrelevant']} 不相关, {stats['scored']} scored, "
        f"{stats['featured']} AI精选, {stats['carrier_switched']} 载体改判 "
        f"(engine {stats.get('engine')})")
    return generate_topics(records)

# ── 生成主题（既有功能保留：GLM 5字主题；分类/评分已由引擎负责，此步只出主题） ──
TOPIC_PROMPT = """为以下每条技术情报生成一个不超过6个字的中文主题词（概括核心对象，如"固态电池""光伏组件""虚拟电厂"）。
只输出JSON数组：[{"id":0,"topic":"固态电池"}]


"""

def generate_topics(records):
    """为相关且尚无主题(tp)的记录生成 5-6 字主题词。既有功能，语义与原管线一致。"""
    todo_ids = [i for i, r in enumerate(records)
                if r.get("c", "") not in ("", "不相关", "未分类")
                and not str(r.get("tp", "")).strip()]
    if not todo_ids:
        log("  主题生成: 0 条需要生成")
        return records
    log(f"  主题生成中... ({len(todo_ids)} 条)")
    items = [{"id": k, "title": records[gi]["t"][:120], "category": records[gi].get("c", "")}
             for k, gi in enumerate(todo_ids)]
    results = call_glm_batch(TOPIC_PROMPT, items, batch_size=20)
    got = 0
    for r in results:
        try:
            k = int(r.get("id"))
        except (TypeError, ValueError):
            continue
        if not (0 <= k < len(todo_ids)):
            continue
        topic = str(r.get("topic", "")).strip()[:8]
        if topic:
            records[todo_ids[k]]["tp"] = topic
            got += 1
    log(f"  主题完成: {got}/{len(todo_ids)}")
    return records


# ── AI 摘要 ──
def backfill_unclassified(lite_path=LITE_PATH, max_records=400):
    """Self-heal：未分类记录改由 triage_engine 重新分诊（2026-09-28 起）。

    旧 GLM 分类提示词已退役——引擎是唯一分类/评分来源，新旧两套不得同时生效。
    每轮最多 max_records 条（控制单轮预算），保留既有人工/人工审核字段（lv/wr/cm）。
    返回重新分诊的记录数（调用方负责重建快照并发布）。
    """
    with open(lite_path) as f:
        lite = json.load(f)
    targets = [i for i, r in enumerate(lite) if r.get("c") == "未分类"]
    if not targets:
        return 0
    targets = targets[:max_records]
    log(f"  [self-heal] {len(targets)} 未分类 records → engine re-triage")
    batch = [lite[i] for i in targets]
    import engine_triage
    use_llm = not os.environ.get("TRIAGE_LLM_OFF")
    stats = engine_triage.engine_triage_records(
        batch, use_llm=use_llm,
        workdir=os.path.join(REPO, ".engine_triage_work"),
        llm_batch=int(os.environ.get("TRIAGE_LLM_BATCH", "8")),
        llm_sleep=float(os.environ.get("TRIAGE_LLM_SLEEP", "2.0")),
    )
    healed = stats["matched"] - stats["irrelevant"]
    # 引擎改判成功的记录写回 lite（未分类 → 正式叶/不相关 均算收敛）
    for i, rec in zip(targets, batch):
        lite[i] = rec
    with open(lite_path, "w", encoding="utf-8") as f:
        json.dump(lite, f, ensure_ascii=False)
    log(f"  [self-heal] engine re-triage done: {stats['matched']} matched, {stats['irrelevant']} 不相关")
    return len(targets)

def gen_summaries(records):
    SUMMARY_PROMPT_FULL = """你是技术情报摘要专家。为以下每条情报生成100-200字的中文AI摘要。
重要规则：
1. 无论原文是什么语言，摘要必须全部用中文撰写
2. 严格基于提供的标题和正文生成摘要，绝对不要编造正文中没有的信息
3. 提炼核心技术要点、关键参数和结论
4. 不要使用"该研究/该技术可能..."等推测性语句，只总结已知事实
只输出JSON数组：[{"id":0,"summary":"..."}]
待处理情报：
"""

    SUMMARY_PROMPT_SHORT = """为以下每条情报生成简短中文摘要（30-80字）。
正文极短，请基于标题和有限正文生成简短摘要。
不要编造数据或结论。只总结已知信息。
只输出JSON数组：[{"id":0,"summary":"..."}]
待处理情报：
"""

    SUMMARY_PROMPT_TITLE_ONLY = """这些情报没有正文，只有标题。请根据标题生成简短中文摘要（20-50字）。
根据标题推断研究主题和技术方向，简要描述该情报可能涉及的内容。
不要编造具体数据。只输出JSON数组：[{"id":0,"summary":"..."}]
待处理情报：
"""

    # Policy: Full summary for body>=50 chars, short for shorter body or title-only.
    # Records with empty body but valid title still get short summaries.
    eligible_full = [i for i, r in enumerate(records)
                     if r.get("c", "") in VALID_CATEGORY_LEAVES
                     and len(r.get("b", "").strip()) >= 50]
    eligible_short = [i for i, r in enumerate(records)
                      if r.get("c", "") in VALID_CATEGORY_LEAVES
                      and 0 < len(r.get("b", "").strip()) < 50
                      and not r.get("as", "").strip()]
    # Title-only records: generate short summary from title alone
    eligible_title_only = [i for i, r in enumerate(records)
                           if r.get("c", "") in VALID_CATEGORY_LEAVES
                           and not r.get("b", "").strip()
                           and not r.get("as", "").strip()]

    log(f"  摘要生成中... ({len(eligible_full)} 条正文 + {len(eligible_short)} 条短正文)")

    # Process full-body records
    for round_no in range(3):
        pending = [i for i in eligible_full if not records[i].get("as", "").strip()]
        if not pending:
            break
        if round_no > 0:
            log(f"  重试第 {round_no} 轮: {len(pending)} 条待生成")
        items = [{"id": i, "title": records[i]["t"][:200], "body": records[i].get("b","")[:800]}
                 for i in pending]
        results = call_glm_batch(SUMMARY_PROMPT_FULL, items, batch_size=20)
        for r in results:
            try:
                idx = int(r.get("id"))  # GLM occasionally returns "123" as a string
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(records):
                summary = r.get("summary", "").strip()
                if summary:
                    records[idx]["as"] = summary

    # Process short-body records
    for round_no in range(3):
        pending = [i for i in eligible_short if not records[i].get("as", "").strip()]
        if not pending:
            break
        if round_no > 0:
            log(f"  短正文重试第 {round_no} 轮: {len(pending)} 条待生成")
        items = [{"id": i, "title": records[i]["t"][:200], "body": records[i].get("b","")[:200]}
                 for i in pending]
        results = call_glm_batch(SUMMARY_PROMPT_SHORT, items, batch_size=20)
        for r in results:
            try:
                idx = int(r.get("id"))  # GLM occasionally returns "123" as a string
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(records):
                summary = r.get("summary", "").strip()
                if summary:
                    records[idx]["as"] = summary

    # Process title-only records (no body) — generate short summary from title
    for round_no in range(3):
        pending = [i for i in eligible_title_only if not records[i].get("as", "").strip()]
        if not pending:
            break
        if round_no == 0:
            log(f"  无正文记录: {len(pending)} 条，从标题生成简短摘要")
        items = [{"id": i, "title": records[i]["t"][:200]}
                 for i in pending]
        results = call_glm_batch(SUMMARY_PROMPT_TITLE_ONLY, items, batch_size=50)
        for r in results:
            try:
                idx = int(r.get("id"))  # GLM occasionally returns "123" as a string
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(records):
                summary = r.get("summary", "").strip()
                if summary:
                    records[idx]["as"] = summary

    has_summary = sum(1 for r in records if r.get("as","").strip())
    has_body = sum(1 for r in records if r.get("b","").strip())
    log(f"  摘要完成: {has_summary}/{len(records)} (有正文记录: {has_body})")
    return records


# ── 关键参数提取 ──
def extract_key_params(records):
    """Extract key technical parameters for each relevant record.
    Processes records with valid category AND (body>=10 chars OR AI summary).
    For records without body, uses title + AI summary for extraction.
    Uses GLM to extract structured key_params from title + body/summary.
    """
    todo_ids = [i for i, r in enumerate(records)
                if r.get("c", "") in VALID_CATEGORY_LEAVES
                and r.get("c", "") not in ("不相关", "未分类", "")
                and (len(r.get("b", "").strip()) >= 10 or len(r.get("as", "").strip()) >= 10)]

    # Clear stale kp on records that are NOT eligible (changed category or no body/summary)
    todo_set = set(todo_ids)
    for i, r in enumerate(records):
        if i not in todo_set:
            r.pop("kp", None)

    if not todo_ids:
        log("  关键参数: 0 条需要提取")
        return records

    KP_PROMPT = """作为顶级情报分析专家，请基于深层语义理解提取输入文本中的关键技术情报。

【禁止项】
严禁降级为关键词或向量匹配。所有提取必须基于对全文技术内涵的理解。

【提取规则】
1. 有明确量化参数的，格式为：参数名[核心条件]: 参数值
   例：能量密度[软包电池]: 350 Wh/kg
   转换效率[钙钛矿叠层]: 30.4%
2. 有明确属性但不可量化的，格式为：参数名[核心条件]: 定性特征
   例：催化剂[碱性海水]: 镍铁层状双氢氧化物
3. 无明确参数名但有关键技术状态/工艺特点/结论的，格式为：[核心条件]: 关键特征陈述
4. 如无任何关键技术参数可提取，返回空数组

只输出JSON数组：
[{"id":0,"key_params":["参数名[条件]: 值","..."]}]
待处理情报：
"""

    todo = [{"id": local_id,
             "title": records[gi].get("t", "")[:200],
             "body": (records[gi].get("b", "") or records[gi].get("as", ""))[:500],
             "category": records[gi].get("c", "")}
            for local_id, gi in enumerate(todo_ids)]

    log(f"  关键参数提取中... ({len(todo)} 条)")
    results = call_glm_batch(KP_PROMPT, todo, batch_size=10)

    # Build a set of ids that got results
    got_kp = set()
    extracted = 0
    for r in results:
        local_id = r.get("id")
        if not isinstance(local_id, int) or local_id < 0 or local_id >= len(todo_ids):
            continue
        global_idx = todo_ids[local_id]
        kp = r.get("key_params", [])
        if isinstance(kp, list) and kp:
            # Filter empty strings and strip whitespace, cap at 5 items
            cleaned = [str(k).strip()[:200] for k in kp[:5] if str(k).strip()]
            if cleaned:
                records[global_idx]["kp"] = cleaned
                got_kp.add(global_idx)
                extracted += 1
                continue
        # Clear stale kp if LLM says no params or all params were empty
        records[global_idx].pop("kp", None)

    # Clear stale kp for records that were processed but got no result
    for local_id in range(len(todo_ids)):
        gi = todo_ids[local_id]
        if gi not in got_kp:
            records[gi].pop("kp", None)

    log(f"  关键参数完成: {extracted}/{len(todo)} 条提取到参数")
    return records


# ── 合并 + 重建分片 ──
def merge_and_rebuild(new_records):
    """Merge new records into lite, rebuild chunks. Returns (count, start_index)."""
    with open(LITE_PATH) as f:
        lite = json.load(f)

    unique, dupes = dedup_check(new_records, lite)
    log(f"  去重: {len(new_records)} → {len(unique)} ({dupes} duplicates)")

    if not unique:
        log("  无新记录需要合并")
        return 0, len(lite)

    start_index = len(lite)
    for r in unique:
        lite.append(r)

    log(f"  合并后总记录: {len(lite)}")

    # Publish lite JSON, all contiguous shards and manifest from one snapshot.
    shard_count = build_snapshot(lite)
    log(f"  原子重建 {shard_count} 个分片")

    return len(unique), start_index


# ── 增量聚类 ──
def incremental_cluster(start_index, total_count):
    """Cluster only newly-merged records against the 20-day historical pool.

    Uses the same scheme-1 thresholds and LLM adjudication as the full run,
    but only processes records from start_index onward. Existing clusters
    are preserved; new records may join existing clusters or form new ones.
    """
    if start_index >= total_count:
        log("  无新记录需要聚类")
        return 0

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    import clustering

    data = json.load(open(LITE_PATH))
    # Compute pool once, then derive new_indices as a subset
    pool_indices = [i for i, r in enumerate(data)
                    if clustering.is_relevant(r) and r.get("dp") != 1]
    new_indices = [i for i in pool_indices if i >= start_index]

    if not new_indices:
        log("  新记录中无 eligible 条目，跳过聚类")
        return 0

    cache = clustering.load_cache()
    log(f"  增量聚类: {len(new_indices)} 新记录，embedding 缓存 {len(cache)}")

    # Ensure vectors for new records (historical ones are already cached)
    vectors = clustering.ensure_vectors(data, new_indices, cache, save_every=64)

    candidates = clustering.make_candidates(data, new_indices, pool_indices, vectors)
    log(f"  候选对: {len(candidates)}")

    if not candidates:
        log("  无候选对，跳过聚类")
        return 0

    decisions = clustering.adjudicate(data, candidates, "zai", "glm-5.3-flash")
    accepted = [k for k, v in decisions.items() if v.get("accepted")]
    log(f"  裁决通过: {len(accepted)}/{len(decisions)}")

    if not accepted:
        log("  无裁决通过的对，跳过聚类写入")
        return 0

    judged_indices = sorted({idx for pair in decisions for idx in pair})
    groups = clustering.complete_link_groups(judged_indices, decisions)
    applied = clustering.apply_groups(data, groups, decisions) if groups else []
    log(f"  聚类应用: {len(applied)} 个")

    if applied:
        shard_count = build_snapshot(data)
        log(f"  重建分片: {shard_count}")

    return len(applied)

# ── 推送 GitHub ──
def _manifest_data_version(target_processed: str) -> str:
    """从 manifest-data.js 提取 data_version（hydrate 来源戳用）。"""
    try:
        raw = open(os.path.join(target_processed, "manifest-data.js"), encoding="utf-8").read()
        start, end = raw.find("{"), raw.rfind("}")
        return str(json.loads(raw[start:end + 1]).get("meta", {}).get("data_version", ""))
    except Exception:
        return ""


def _manifest_records_total(target_processed: str) -> int:
    try:
        raw = open(os.path.join(target_processed, "manifest-data.js"), encoding="utf-8").read()
        start, end = raw.find("{"), raw.rfind("}")
        return int(json.loads(raw[start:end + 1]).get("meta", {}).get("records_total", 0))
    except Exception:
        return 0


def publish_to_boundary():
    """把生成的数据产物安装到本仓库 breadth/data，广度页即时生效。

    - lite/meta/summary 分片 + manifest-data.js + conferences.json → breadth/data/processed
      （镜像式安装：源里没有的旧分片会被清理，防止分片数缩减后残留）
    - data/reports → breadth/data/reports（日报/周报/月报视图）
    - 重建广度页派生快照（alert-records.json / category-counts.json）
    - bump breadth/version.txt（原 inode 截断写，配合 compose 单文件挂载）
    失败返回 False → 上层保持「state 不提交，下轮重试」的语义。
    """
    import glob as _glob
    import shutil as _shutil

    boundary_repo = os.environ.get("BOUNDARY_REPO",
                                   os.path.dirname(os.path.abspath(__file__)))
    breadth_data = os.path.join(boundary_repo, "breadth", "data")
    target_processed = os.path.join(breadth_data, "processed")
    src_processed = os.path.join(REPO, "data", "processed")

    # 发布的生成产物白名单（镜像范围只限分片 + manifest-data.js + conferences.json）
    mirror_globs = ["lite-part-*.js", "meta-part-*.js", "summary-part-*.js"]
    copy_files = ["manifest-data.js", "conferences.json", "graph-export.json"]

    staged = []
    try:
        for pattern in mirror_globs:
            staged.extend(sorted(_glob.glob(os.path.join(src_processed, pattern))))
        staged.extend(os.path.join(src_processed, f) for f in copy_files
                      if os.path.isfile(os.path.join(src_processed, f)))
        if not any("manifest-data.js" in f for f in staged):
            log("  [ERROR] manifest-data.js missing — refusing to publish")
            return False

        os.makedirs(target_processed, exist_ok=True)
        # 安装（先写 .publish-tmp 再 os.replace，浏览器端不会读到半个文件）
        for src in staged:
            name = os.path.basename(src)
            tmp = os.path.join(target_processed, "." + name + ".publish-tmp")
            _shutil.copy2(src, tmp)
            os.replace(tmp, os.path.join(target_processed, name))
        # 清理源里已不存在的旧分片（分片数缩减场景）
        src_names = {os.path.basename(f) for f in staged}
        for pattern in mirror_globs:
            for old in _glob.glob(os.path.join(target_processed, pattern)):
                if os.path.basename(old) not in src_names:
                    os.remove(old)
        log(f"  installed {len(staged)} artifacts -> breadth/data/processed")

        # 报告镜像（追加式：不删除 breadth 侧已有报告）
        src_reports = os.path.join(REPO, "data", "reports")
        if os.path.isdir(src_reports):
            for sub in ("daily", "weekly", "monthly"):
                sdir = os.path.join(src_reports, sub)
                tdir = os.path.join(breadth_data, "reports", sub)
                if not os.path.isdir(sdir):
                    continue
                os.makedirs(tdir, exist_ok=True)
                n = 0
                for f in sorted(_glob.glob(os.path.join(sdir, "*.json"))):
                    dst = os.path.join(tdir, os.path.basename(f))
                    if not (os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(f)):
                        tmp = dst + ".publish-tmp"
                        _shutil.copy2(f, tmp)
                        os.replace(tmp, dst)
                        n += 1
                if n:
                    log(f"  reports/{sub}: +{n}")

        # 广度页派生快照（预警 + 分类计数）
        for script in ("build_breadth_alert_snapshot.py", "build_breadth_category_counts.py"):
            result = subprocess.run(
                [sys.executable, os.path.join(boundary_repo, "scripts", script),
                 "--data-dir", breadth_data],
                capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                log(f"  [ERROR] {script} failed: {(result.stderr or result.stdout)[:200]}")
                return False
        log("  derived snapshots rebuilt (alert-records / category-counts)")

        # 知识图谱（门户星空背景）：基于本管线主存储重建（纯本地正则抽取，秒级）。
        # 服务路径 services/canonical-qa/graph-live/graph-export.json 是单文件 bind
        # mount 的稳定 inode——必须原地截断写（r+/truncate），绝不能 os.replace。
        graph_result = subprocess.run(
            [sys.executable, os.path.join(REPO, "scripts", "build_graph_export.py")],
            capture_output=True, text=True, timeout=600)
        if graph_result.returncode == 0:
            _gsrc = os.path.join(src_processed, "graph-export.json")
            _glive = os.path.join(boundary_repo, "services", "canonical-qa",
                                  "graph-live", "graph-export.json")
            if os.path.isfile(_gsrc) and os.path.exists(_glive):
                with open(_gsrc, "rb") as sf:
                    with open(_glive, "r+b") as lf:
                        lf.write(sf.read())
                        lf.truncate()
                log("  knowledge graph rebuilt & published (portal starfield)")
            else:
                log("  [WARN] graph live path missing — skip publish: " + _glive)
        else:
            log("  [WARN] graph export failed (non-fatal): "
                + (graph_result.stderr or graph_result.stdout)[:200])

        # 数据纪元标记：前端轮询它提示「有新数据，请刷新」。
        # 放在 processed/ 目录内（目录级挂载，无单文件 inode 问题，不入 Git）。
        auto_version = os.path.join(target_processed, "auto-version.txt")
        tag = "auto-" + datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M")
        tmp = auto_version + ".publish-tmp"
        with open(tmp, "w", encoding="utf-8") as vf:
            vf.write(tag + "\n")
        os.replace(tmp, auto_version)
        log(f"  auto-version.txt -> {tag}")

        # 本地管线运行时来源戳：声明 breadth/data/processed 现由本管线自有产物驱动。
        # hydration（scripts/hydrate_breadth_runtime.py）据此识别「合法的新版本」：
        # 戳存在且清单/分片自洽 → 直接复用本地数据，绝不回写 tech-db 固定旧快照；
        # 戳缺失或结构损坏 → 才回退 tech-db 钉住的快照兜底。
        stamp = {
            "schema": "tech-boundary-breadth-runtime/v2",
            "source": "local-pipeline",
            "records_total": _manifest_records_total(target_processed),
            "data_version": _manifest_data_version(target_processed),
            "total_shards": len(_glob.glob(os.path.join(target_processed, "lite-part-*.js"))),
            "generator": "pipeline/auto_pipeline.publish_to_boundary",
            "published_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        }
        stamp_path = os.path.join(target_processed, ".runtime-source.json")
        tmp = stamp_path + ".publish-tmp"
        with open(tmp, "w", encoding="utf-8") as sf:
            json.dump(stamp, sf, ensure_ascii=False, indent=2)
        os.replace(tmp, stamp_path)
        legacy = os.path.join(target_processed, ".techdb-runtime-source.json")
        if os.path.isfile(legacy):
            os.remove(legacy)  # 已切换为本地管线来源，旧钉住快照戳不再适用

        log("  published to breadth/data")
        return True
    except Exception as pub_err:
        log(f"  [ERROR] publish failed: {pub_err}")
        return False


# ── 主流程 ──
def main():
    lock_fd = acquire_lock()

    log("=" * 50)
    log("tech-db auto-sync pipeline starting")

    # Seed the state file if missing (fresh-install bootstrap; state tracks
    # published files so downloads are never re-processed).
    ensure_state_file()

    # Step 1: Check for new files (does NOT save state)
    log("Step 1: Checking source repos...")
    has_new, new_per_source, current, n_failed = check_new_files()

    if n_failed == len(SOURCES):
        log(f"[ERROR] All {n_failed} source API calls failed. Aborting (will retry next run).")
        return
    if n_failed:
        log(f"  [WARN] {n_failed}/{len(SOURCES)} source(s) API failed — proceeding with partial data.")
    if not has_new:
        # 2026-08-16 fix: no new source files ≠ nothing to do — a previous
        # run may have left 未分类 records (failed classification batches).
        # Self-heal them (bounded per run) and push before exiting.
        healed = backfill_unclassified(max_records=400)
        if healed:
            shard_count = build_snapshot(json.load(open(LITE_PATH)))
            log(f"  [self-heal] snapshot rebuilt ({shard_count} shards)")
            if not publish_to_boundary():
                log("  [WARN] self-heal publish failed — retried next run")
        log("No new files. Done.")
        return

    try:
        # Step 2: Download and parse new CSVs
        log("Step 2: Downloading new data...")
        new_records, successfully_downloaded, failed_files = download_new_csvs(new_per_source)
        log(f"  Parsed {len(new_records)} new records from CSVs")
        if failed_files:
            log(f"  [WARN] {len(failed_files)} files failed to download: {[f[1] for f in failed_files]}")

        # 即使没有新记录（全是重复或下载失败），也只 commit 成功下载的文件
        if not new_records:
            log("No new records to process. Ensuring pending artifacts are published before state commit.")
            if not publish_to_boundary():
                log("[FATAL] Publish failed — state NOT committed.")
                sys.exit(1)
            commit_state(current, successfully_downloaded)
            return

        # Step 3: Dedup against existing
        log("Step 3: Dedup check...")
        # 冷启动支持：主存储缺失（新环境/被清理）→ 从空库全量重建，
        # 不要求事先存在 all-records-lite.json。
        if os.path.exists(LITE_PATH):
            with open(LITE_PATH) as f:
                existing = json.load(f)
        else:
            log("  [cold-start] all-records-lite.json 不存在——从空库全量重建")
            existing = []
        unique, dupes = dedup_check(new_records, existing)
        log(f"  {len(new_records)} → {len(unique)} unique ({dupes} dupes)")

        if not unique:
            log("All records are duplicates. Ensuring pending artifacts are published before state commit.")
            if not publish_to_boundary():
                log("[FATAL] Publish failed — state NOT committed.")
                sys.exit(1)
            commit_state(current, successfully_downloaded)
            return

        # Step 4: Translate titles + Classify + Score
        log("Step 4: Translate titles + Classify + Score...")
        unique = translate_non_chinese_titles(unique)
        unique = classify_and_score(unique)

        # Step 5: AI Summaries
        log("Step 5: AI Summaries...")
        unique = gen_summaries(unique)

        # Step 5b: Extract key parameters
        log("Step 5b: Extract key parameters...")
        try:
            unique = extract_key_params(unique)
        except Exception as kp_err:
            log(f"  [WARN] 关键参数提取失败 (non-fatal): {kp_err}")

        # Step 6: Merge + Rebuild
        log("Step 6: Merge + Rebuild lite...")
        merged_count, start_index = merge_and_rebuild(unique)
        total_after_merge = start_index + merged_count

        # Step 6b: Incremental clustering (new records only)
        # Skip if caller sets SKIP_CLUSTER (clustering loads heavy embedding model → OOM risk)
        if merged_count > 0 and not os.environ.get("SKIP_CLUSTER"):
            log("Step 6b: Incremental clustering...")
            try:
                cluster_count = incremental_cluster(start_index, total_after_merge)
            except Exception as ce:
                log(f"  [WARN] 增量聚类失败，跳过: {ce}")
                cluster_count = 0
        elif merged_count > 0:
            log("Step 6b: SKIPPED (SKIP_CLUSTER env var set)")
            cluster_count = 0

        # Step 6c: Extract conferences + dedup —— 与聚类解耦：
        # 历史缺陷：本段误嵌在 SKIP_CLUSTER 的 elif 分支内，正常生产（跑聚类）时
        # 会议提取永不执行。现在只要本批有合并记录就执行。
        if merged_count > 0:
            log("Step 6c: Extract conferences...")
            try:
                conf_result = subprocess.run(
                    [sys.executable, os.path.join(REPO, "scripts", "extract_conferences.py")],
                    capture_output=True, text=True, cwd=REPO, timeout=300
                )
                if conf_result.returncode == 0:
                    log("  " + conf_result.stdout.strip().split('\n')[-1])
                else:
                    log(f"  [WARN] 会议提取失败: {conf_result.stderr[:200]}")
            except subprocess.TimeoutExpired:
                log("  [WARN] 会议提取超时，跳过")
            except Exception as ce:
                log(f"  [WARN] 会议提取异常: {ce}")

            log("Step 6c.2: Dedup conferences...")
            try:
                dedup_result = subprocess.run(
                    [sys.executable, os.path.join(REPO, "scripts", "dedup_conferences.py")],
                    capture_output=True, text=True, cwd=REPO, timeout=120
                )
                if dedup_result.returncode == 0:
                    log("  " + dedup_result.stdout.strip().split('\n')[-1])
                else:
                    log(f"  [WARN] 会议去重失败: {dedup_result.stderr[:200]}")
            except Exception as ce:
                log(f"  [WARN] 会议去重异常: {ce}")

        # Step 6d: self-heal 未分类 backlog (incl. any from THIS run's
        # failed classification batches — bounded to keep the run fast).
        log("Step 6d: Self-heal 未分类...")
        try:
            healed = backfill_unclassified(max_records=400)
            if healed:
                # merge_and_rebuild already published its snapshot BEFORE
                # this step — republish so shards include the healed
                # categories (Step 7 validates lite ↔ shards consistency).
                shard_count = build_snapshot(json.load(open(LITE_PATH)))
                log(f"  [self-heal] snapshot republished ({shard_count} shards)")
        except Exception as heal_err:
            log(f"  [WARN] self-heal failed (non-fatal): {heal_err}")
            healed = 0

        # Step 7: Validate all immutable data contracts, then push.
        log("Step 7: Validate data contracts...")
        validation = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "validate_data_contract.py")],
                                    capture_output=True, text=True, cwd=REPO, timeout=60)
        if validation.returncode != 0:
            raise RuntimeError(validation.stdout or validation.stderr or "data contract validation failed")
        log("  " + validation.stdout.strip())
        log("Step 8: Publish to boundary breadth...")
        if os.environ.get("SKIP_PUSH"):
            log("  SKIPPED (SKIP_PUSH env var set — caller handles publish)")
        elif not publish_to_boundary():
            # 发布失败必须非零退出：state 不提交，下轮自动重试（不烧重复 LLM 配额的
            # 前提是产物仍在 pipeline/data/processed，重试只重跑发布）。
            log("[FATAL] Publish failed — state NOT committed. Files will be retried next run.")
            sys.exit(1)  # 不 commit_state，下次 cron 自动重试

        # Step 9: Commit state ONLY after successful publish（本地文件，无需上传）
        log("Step 9: Commit state...")
        commit_state(current, successfully_downloaded)


        # Step 10: 问答索引同步（发布视图 → canonical-qa 增量索引）
        # 旧实现（本仓库 qa-backend/ 下重建 BM25/向量索引）已随 tech-db 迁出
        # 而失效；现在通过 scripts/sync_qa_index.py 把发布分片差异推送进
        # canonical-qa 的增量索引（/api/index/upsert 契约，幂等、断点续推）。
        # 失败非致命：下一轮管线自动补推（水印只在全部批次成功后落盘）。
        sync_script = os.path.join(REPO, "scripts", "sync_qa_index.py")
        sync_python = os.path.join(REPO, "pipeline", ".venv", "bin", "python")
        if not os.path.exists(sync_python):
            sync_python = sys.executable
        if os.environ.get("SKIP_QA_INDEX_SYNC"):
            log("Step 10: SKIPPED (SKIP_QA_INDEX_SYNC env var set)")
        elif not os.path.exists(sync_script):
            log("Step 10: SKIPPED (scripts/sync_qa_index.py not found)")
        else:
            log("Step 10: Syncing published records into canonical-qa index...")
            try:
                sync_result = subprocess.run(
                    [sync_python, sync_script],
                    capture_output=True, text=True, cwd=REPO, timeout=28800,
                    env={**os.environ, "TECHDB_QA_SYNC_URL": os.environ.get("TECHDB_QA_SYNC_URL", "http://127.0.0.1:8767")},
                )
                output_tail = [l for l in (sync_result.stdout or "").strip().split("\n") if l.strip()]
                for line in output_tail[-4:]:
                    log(f"  {line}")
                if sync_result.returncode != 0:
                    log(f"  [WARN] QA index sync failed (non-fatal, retried next run): "
                        f"{(sync_result.stderr or '')[-200:]}")
                else:
                    log("  QA index sync complete.")
            except subprocess.TimeoutExpired:
                log("  [WARN] QA index sync timeout (8h) — retried next run")
            except Exception as sync_exc:
                log(f"  [WARN] QA index sync error (non-fatal): {sync_exc}")

        # 10c: Knowledge graph — graph-export.json 由独立图谱管线重建并
        # 发布到 services/canonical-qa/graph-live/（bind mount 即时生效），
        # 见 Step 8/发布段；此处不再重复构建。

        # Step 11: Reports — 补跑制：每次运行用 --all 补齐所有缺失周期。
        # generate_reports.generate_all 以「完整周期已过」为界枚举日期，
        # 已存在且非空的报告自动跳过 → 幂等；上次 GLM 失败/超时留下的缺口
        # 本轮自动补上（失败非致命，缺口下轮继续补）。无新情报的日期按
        # "no records" 跳过（真实语义：该日无精选/预警级情报可成稿）。
        log("Step 11: Generating reports (catch-up all)...")
        try:
            venv_python = os.path.join(REPO, ".venv", "bin", "python")
            report_scripts = os.path.join(REPO, "pipeline", "scripts", "generate_reports.py")
            report_failed = False
            for rtype, timeout_s in (("daily", 300), ("weekly", 600), ("monthly", 600)):
                log(f"  11/{rtype}: catch-up...")
                try:
                    result = subprocess.run(
                        [venv_python, report_scripts, "--type", rtype, "--all"],
                        capture_output=True, text=True, cwd=REPO, timeout=timeout_s)
                    if result.returncode == 0:
                        tail = [l for l in result.stdout.strip().split("\n") if l.strip()]
                        log("  " + (tail[-1] if tail else "ok"))
                    else:
                        report_failed = True
                        log(f"  [WARN] {rtype} report failed: {(result.stderr or result.stdout)[:200]}")
                except subprocess.TimeoutExpired:
                    report_failed = True
                    log(f"  [WARN] {rtype} report timeout ({timeout_s}s) — catch-up retries next run")

            # 11d: Publish reports to breadth（无 GitHub；本地安装即时生效）
            log("  11d: Publishing reports...")
            if not publish_to_boundary():
                log("  [WARN] report publish failed — retried next run")

            log("Step 11 complete." + (" (with failures — catch-up next run)" if report_failed else ""))
        except Exception as re:
            log(f"  [WARN] Report generation failed (non-fatal): {re}")

        log(f"Pipeline complete: +{merged_count} records")
    except Exception as e:
        log(f"[ERROR] Pipeline failed: {e}")
        log("State NOT committed — files will be retried next run.")
        import traceback
        traceback.print_exc()
        raise
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except:
            pass

if __name__ == "__main__":
    main()
