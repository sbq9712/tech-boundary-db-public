#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""engine_triage —— triage_engine ↔ tech-boundary-db 广度管线适配层（唯一对接面）。

职责（2026-09-28 起取代 auto_pipeline 内的 GLM 分类/评分，成为分类+评分唯一来源）：
  1. 行记录构造：lite 记录 → 引擎行 schema（src/date/title/body/url/meta/doi/content_quality）
  2. 子进程调用引擎（规则层 + 可选 LLM 语义复核层；引擎会改写全局模块状态，必须隔离）
  3. 结果映射（只读引擎输出，不改引擎）：
     - 领域  c   ：引擎域判定 → 主库 125 叶完整路径；域外 → "不相关"
     - 载体  i   ：引擎展示大类（论文→l / 新闻→n；v1.10 C-T16 载体前提，不信源文件名）
     - 类型  tg  ：直接保存 triage_engine 展示链分类（新闻7类 + 文献4分型）；不再压回旧 5+2 标签
     - 评分  sc  ：引擎 S8 value/10（0-100 → 0-10 前端既有刻度），T02 区间档取区间中点
     - 维度  scd ：引擎评分卡维度归一 0-10 后，按语义填入前端 b/i/r/d/t 五槽
     - 精选  aip ：新闻 S8 档位 ∈ {高,中} → aip=1；文献一律不精选；低 → 不精选
  4. 终态处置：不相关（含 AI00 未细分兜底）→ 清空评分/精选/摘要/参数等 AI 派生字段，
     不评分、不精选、后续步骤（摘要/关键参数）不再处理该记录

引擎版本记录见 pipeline/triage_engine/ENGINE_PROVENANCE.md（v1.11, a00706e）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.join(REPO, "triage_engine")

ENGINE_VERSION = "v1.11"
ENGINE_COMMIT = "a00706e"
METHOD_SUFFIX = "direct-banding-v111"

# ── 源 → 引擎 src（引擎按载体身份判定论文/新闻，来源仅作入口通道） ──
_SRC_MAP = {"news": "news-spider", "wechat": "wechat", "literature": "literature"}

# ── triage_engine 展示分类 = tg 唯一真源 ───────────────────────────────
# 新闻：v1.09 DISPLAY_CHAIN_MAP 的 7 个展示小类；文献：T01 四分型。
# 旧适配层曾把它们强行压成“新闻5 + 文献2”，导致广度页与 triage_engine
# 口径不一致，也让 T05/T23/T24 带括号说明的小类误落默认标签。
NEWS_TAGS = (
    "知识资产",
    "工程与产业化",
    "企业经营、合作与资本",
    "资源、市场与产业链",
    "政策、法规与标准",
    "人才与组织动态",
    "观点与交流",
)
LIT_TAGS = ("综述", "研究型", "分析类", "新闻/评论/观点")
_NEWS_DEFAULT_TAG = "观点与交流"
_LIT_DEFAULT_TAG = "研究型"


def _tag_key(value: str) -> str:
    """展示标签比较键：去掉空白/分隔标点，兼容引擎中的不同书写。"""
    return re.sub(r"[、，,\s·/]", "", str(value or ""))


def _strip_display_note(value: str) -> str:
    """去掉 DISPLAY_CHAIN_MAP 中仅供解释的括号后缀，不改变分类本体。"""
    return re.sub(r"[（(][^）)]*[）)]", "", str(value or "")).strip()


_NEWS_CANONICAL = {_tag_key(x): x for x in NEWS_TAGS}
_LIT_CANONICAL = {_tag_key(x): x for x in LIT_TAGS}
# triage_engine 文献四分型历史上同时出现“新闻·评论·观点”书写。
_LIT_CANONICAL[_tag_key("新闻·评论·观点")] = "新闻/评论/观点"

# ── 引擎树路径 → 主库路径 规范化 ──
# 引擎菜单用 " > " / "|" 分隔且 19 条叶把主库的"能源测"写作"能源侧"；
# 规范化（分隔符统一 + 该别名）后与主库 125 叶严格一致（106 直合 + 19 别名）。
def normalize_engine_path(path: str) -> str:
    p = str(path or "").replace("|", "/").replace(" > ", "/").replace(">", "/")
    p = p.replace("能源侧", "能源测")
    p = re.sub(r"\s*/\s*", "/", p)
    return p.strip("/")

# ── 扩展域（E01–E26）树路径 → 主库 125 叶（引擎树内带括号变体的 18 条固定别名） ──
_E_TREE_ALIAS = {
    "零碳产业/能量转化/能源测/二次能源利用/电加热（热泵/电锅炉/直接电加热）": "零碳产业/能量转化/能源测/二次能源利用/电加热/热泵",
    "零碳产业/能量转化/能源测/二次能源利用（制冷散热技术/电驱动（电机））": "零碳产业/能量转化/能源测/二次能源利用/制冷散热技术",
    "零碳产业/能量转化/能源测/二次能源利用/热驱动（热机）（内燃机/外燃机）": "零碳产业/能量转化/能源测/二次能源利用/工业余热回收",
    "零碳产业/能量转化/能量存储/电化学储能（一次电池/超级电容器）": "零碳产业/能量转化/能量存储/电化学储能/一次电池",
    "零碳产业/能量转化/能量存储/储热（水/油储热、熔盐储热、固态储热）": "零碳产业/能量转化/能量存储/储热/压缩气体",
    "零碳产业/能量转化/能量存储/机械能（重力储能、飞轮储能）": "零碳产业/能量转化/能量存储/机械能/重力储能",
    "零碳产业/能量转化/能量分配与运输（电网相关技术/虚拟电厂与电力交易）": "零碳产业/能量转化/能量分配与运输/电网相关技术",
    "零碳产业/能量转化/能量分配与运输/能源载体管网（天然气管网/氢气管网/输油管道）": "零碳产业/能量转化/能量分配与运输/能源载体管网/天然气管网",
    "零碳产业/物质循环/资源回收利用与排放治理（物质回收/梯次利用）": "零碳产业/物质循环/资源回收利用与排放治理/物质回收",
    "零碳产业/物质循环/资源回收利用与排放治理（固废处理/污水处理）": "零碳产业/物质循环/资源回收利用与排放治理/固废处理",
    "零碳产业/物质循环/资源获取（勘探技术/开采技术/种植养殖技术）": "零碳产业/物质循环/资源获取/勘探技术",
    "零碳产业/物质循环/资源加工/有机物/平台化工品（合成气平台/乙烯丙烯丁二烯/苯甲苯二甲苯）": "零碳产业/物质循环/资源加工/有机物/平台化工品/合成气平台",
    "零碳产业/物质循环/资源加工/有机物/大宗化工产品（塑料/橡胶/纤维）": "零碳产业/物质循环/资源加工/有机物/大宗化工产品/塑料",
    "零碳产业/物质循环/资源加工/无机物/金属（铝业/铜业/稀土产业）": "零碳产业/物质循环/资源加工/无机物/金属/铝业",
    "零碳产业/物质循环/资源加工/无机物/非金属（玻璃/陶瓷）": "零碳产业/物质循环/资源加工/无机物/非金属/玻璃",
    "零碳产业/物质循环/资源加工/无机物/无机化工（酸/碱/尿素）": "零碳产业/物质循环/资源加工/无机物/无机化工/酸",
    "零碳产业/物质循环/资源回收利用与排放治理/其他负排放（DAC/BECCS/矿化利用）": "零碳产业/物质循环/资源回收利用与排放治理/碳捕集/其它碳捕集技术",
    "零碳产业/能量转化/能量存储/电化学储能/其它电池技术（液流电池/锌基电池等）": "零碳产业/能量转化/能量存储/其它储能技术",
    "零碳产业/能量转化/能量分配与运输（碳市场与温室气体监测）": "零碳产业/能量转化/能量分配与运输/其它能量分配技术",
    "零碳产业/能量转化/能源测/一次能源转化（地热能利用）": "零碳产业/能量转化/能源测/一次能源转化/其他发电技术",
    "零碳产业/物质循环/资源回收利用与排放治理/碳捕集（液态碱性吸收/固态胺吸附/膜分离/矿化技术/pH swing）": "零碳产业/物质循环/资源回收利用与排放治理/碳捕集/液态碱性吸收",
    "零碳产业/能量转化/能量存储/化学能/氢基能源（氢能/可再生燃料：绿氨/绿甲醇/绿色油品）": "零碳产业/能量转化/能量存储/化学能/氢基能源/氢能",
    "零碳产业/能量转化/能源测/一次能源转化/核电（裂变/聚变/核电池）": "零碳产业/能量转化/能源测/一次能源转化/核电/裂变",
    "零碳产业/能量转化/能量存储（应用层视角）": "零碳产业/能量转化/能量存储/其它储能技术",
}

# ── 评分卡维度语义 → 前端五槽（b突破性 i产业力 r稀缺性 d数据量 t时效性） ──
_DIM_B = ("瓶颈", "新颖", "机理", "前沿", "突破", "创新")
_DIM_I = ("验证", "中试", "示范", "产业化", "工程", "生产", "项目", "量产", "规模")
_DIM_R = ("首证", "首个", "首创", "独家", "稀缺", "唯一", "罕见")
_DIM_D = ("指标", "数据", "参数", "证据", "监测", "统计")
_DIM_T = ("时效", "时点", "新鲜", "近期", "节奏")


def load_whitelist():
    """主库 125 叶白名单（category-taxonomy.json）。"""
    path = os.path.join(REPO, "data", "category-taxonomy.json")
    with open(path, encoding="utf-8") as f:
        return set(json.load(f)["categories"])


def build_engine_domain_maps():
    """引擎域 id → 主库 125 叶路径。

    三个来源（均为引擎自身数据，适配层只做路径归一，不改判定）：
      semantic_leaf_NNN/GT → LIT_LEAVES 叶路径（125 叶菜单本体）
      规则 D 域（12 键）   → cls_data.LANDSCAPE_PATH
      扩展 E 域（26 条）   → expand_domains_data.EXPAND_DOMAINS.tree + 固定别名
    AI00（semantic_branch_ai，AI 待细分）不入表：不落任何叶 → 按用户规则归"不相关"。
    """
    for p in (os.path.join(ENGINE_DIR, "pipeline"), os.path.join(ENGINE_DIR, "rules")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import build_github_triage as base  # noqa: E402
    import cls_data  # noqa: E402
    import expand_domains_data as ex  # noqa: E402

    mapping: dict[str, str] = {}
    for leaf in base.LIT_LEAVES:
        p = normalize_engine_path(leaf.get("path", ""))
        if p:
            mapping[f"semantic_leaf_{leaf['no']}"] = p
    for key, entry in cls_data.LANDSCAPE_PATH.items():
        p = normalize_engine_path(entry[0])
        if p:
            mapping[key] = p
    for d in ex.EXPAND_DOMAINS:
        p = normalize_engine_path(d.get("tree", ""))
        if p:
            mapping[d["id"]] = p
    return mapping


def resolve_category(item: dict, dom_map: dict, whitelist: set[str]) -> str:
    """引擎 item → 主库类别。返回 '不相关' 表示域外/未落叶（终止后续管线）。"""
    if item.get("domainDisp") == "域外":
        return "不相关"
    did = str(item.get("domainId") or "")
    if did in dom_map:
        path = dom_map[did]
        if path in whitelist:
            return path
        path = _E_TREE_ALIAS.get(path, path)
        if path in whitelist:
            return path
        # 主库树内有共同父枝：取最长共享前缀叶不可取——按用户规则落"不相关"
        return "不相关"
    # LLM 决策可能给完整路径而 item.domainId 兜底失败：从决策路径恢复
    path = normalize_engine_path(item.get("domain") or "")
    if path in whitelist:
        return path
    path = _E_TREE_ALIAS.get(path, path)
    if path in whitelist:
        return path
    return "不相关"


def resolve_carrier(item: dict, rec: dict) -> str:
    """i 字段：引擎展示大类优先（论文→l / 新闻→n）；展示链未决（待定/—）保留原值。"""
    disp = item.get("displayCategory") or ""
    if disp == "论文":
        return "l"
    if disp == "新闻":
        return "n"
    return rec.get("i", "n")


def resolve_tag(item: dict, carrier: str) -> str:
    """把引擎展示小类原义写入 tg；只做展示说明/标点规范化，不再降维。"""
    raw = _strip_display_note(str(item.get("displaySubcategory") or ""))
    table = _LIT_CANONICAL if carrier == "l" else _NEWS_CANONICAL
    hit = table.get(_tag_key(raw))
    if hit:
        return hit
    # 未知新值不臆造映射：只有在引擎明确给出当前载体展示大类时才原样保留，
    # 这样未来 triage_engine 增类能直接出现在动态前端菜单；空值才用稳定默认。
    expected_category = "论文" if carrier == "l" else "新闻"
    if raw and str(item.get("displayCategory") or "") == expected_category:
        return raw
    return _LIT_DEFAULT_TAG if carrier == "l" else _NEWS_DEFAULT_TAG

def parse_value(value, value_display) -> float | None:
    """引擎 S8 分值（0-100）→ float；T02 区间档（value=None, valueDisplay='55–69'）取中点。"""
    if isinstance(value, (int, float)):
        return float(value)
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)\s*$", str(value_display or ""))
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2.0
    return None


def map_dims(dimensions: list) -> dict:
    """引擎评分卡维度（[名, 得分, 满分, 注] 归一 0-10）按语义填入前端 b/i/r/d/t 五槽。

    先按维度名关键词对号入座；未命中槽按顺序回填，保证引擎各维信息不丢、
    tooltip 五行始终有值。所有取值 = 引擎该维 得分/满分×10，封顶 [0,10]。
    """
    out = {"b": 0.0, "i": 0.0, "r": 0.0, "d": 0.0, "t": 0.0}
    scored: list[tuple[str, float]] = []
    for dim in dimensions or []:
        try:
            name, got, full = dim[0], float(dim[1]), float(dim[2])
        except (TypeError, ValueError, IndexError):
            continue
        if full <= 0:
            continue
        scored.append((str(name), max(0.0, min(10.0, got / full * 10.0))))
    used: set[str] = set()
    for name, val in scored:
        for slot, keywords in (("b", _DIM_B), ("i", _DIM_I), ("r", _DIM_R),
                               ("d", _DIM_D), ("t", _DIM_T)):
            if slot not in used and any(k in name for k in keywords):
                out[slot] = round(val, 1)
                used.add(slot)
                break
    unused_vals = (v for n, v in scored if not any(k in n for ks in (_DIM_B, _DIM_I, _DIM_R, _DIM_D, _DIM_T) for k in ks))
    for slot in ("b", "i", "r", "d", "t"):
        if slot in used:
            continue
        try:
            out[slot] = round(next(unused_vals), 1)
        except StopIteration:
            break
    return out


# AI_DERIVED_FIELDS：不相关时清空（与 data_contract.enforce_terminal_categories 一致）
AI_DERIVED_FIELDS = ("aip", "sc", "scd", "as", "kp", "tp", "cl", "cp", "cln")


def record_to_row(rec: dict) -> dict:
    """lite 记录 → 引擎行 schema。"""
    sr = str(rec.get("sr") or rec.get("source") or "")
    src_key = sr.split("/", 1)[0] if sr else "news"
    src = _SRC_MAP.get(src_key, "news-spider")
    url = str(rec.get("u", "") or "")
    m = re.search(r"(10\.\d{4,9}/[^\s?#]+)", url)
    doi = m.group(1).lower().rstrip(".") if m else ""
    body = str(rec.get("b", "") or "")
    if src == "literature":
        cq = "abstract" if len(body.strip()) >= 30 else ("digest" if body.strip() else "empty")
    else:
        cq = "full" if len(body) >= 300 else ("preview" if body.strip() else "empty")
    return {
        "src": src,
        # 引擎要求必填 ISO 日期；缺日期的个别记录用占位日期保记录不丢（仅入引擎，不回写 d）
        "date": str(rec.get("d", "") or "") if re.match(r"^\d{4}-\d{2}-\d{2}$", str(rec.get("d") or "")) else "1970-01-01",
        "title": str(rec.get("t", "") or ""),
        "body": body,
        "url": url,
        "meta": str(rec.get("a", "") or ""),
        "doi": doi,
        "content_quality": cq,
    }


def run_engine(rows: list[dict], workdir: str, use_llm: bool = False,
               llm_batch: int = 8, llm_sleep: float = 2.0) -> dict:
    """子进程跑引擎（规则层 + 可选 LLM 复核），返回 semantic_results.json。

    引擎运行层会 monkeypatch 全局模块状态（AI_INTERFACE §4.3 亦要求服务化隔离），
    因此一律子进程调用，本进程绝不 import 引擎执行体。
    返回 {"result": <semantic json>, "llm": <decisions|None>, "failed": int}
    """
    os.makedirs(workdir, exist_ok=True)
    # out 目录每次调用必须全新：引擎 LLM 层按"行下标 i"断点续跑（audit 里 i 会跨批重复），
    # 共享 out 会让后续批次误跳过 LLM 复核、并把上一批决策错配到本批记录——历史事故点，勿回退。
    # rows 一并放入该目录：调用间互不可见，支持多线程并发跑引擎（各自独立子进程）。
    out_dir = tempfile.mkdtemp(prefix="engine_out_", dir=workdir)
    rows_path = os.path.join(out_dir, "rows.json")
    with open(rows_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)

    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if use_llm:
        env = _ensure_llm_env_file()

    engine_parent = os.path.dirname(ENGINE_DIR)  # pipeline/ — the package root for -m resolution
    llm_info = None
    if use_llm:
        # --scoped：与引擎自家管线默认一致（仅域外/T25/AI00+问题记录送复核，
        # 规则层结果照常产出；全量送审是引擎 cli 的小批量审计口径，68k 全量不可承受）
        cmd = [sys.executable, "-m", "triage_engine.cli", "llm",
               "--rows", rows_path, "--out", out_dir, "--scoped",
               "--batch", str(llm_batch), "--sleep", str(llm_sleep)]
        r = subprocess.run(cmd, cwd=engine_parent, env=env, capture_output=True, text=True,
                           encoding="utf-8", timeout=3600 * 4)
        dec_path = os.path.join(out_dir, "llm_semantic_decisions.json")
        if os.path.isfile(dec_path):
            with open(dec_path, encoding="utf-8") as f:
                llm_info = json.load(f)
        else:
            sys.stderr.write(f"[engine_triage] LLM 层未产出 decisions：{r.stdout[-300:]} {r.stderr[-300:]}\n")

    cmd = [sys.executable, "-m", "triage_engine.cli", "run", "--rows", rows_path, "--out", out_dir]
    if llm_info:
        cmd += ["--llm-decisions", os.path.join(out_dir, "llm_semantic_decisions.json")]
    r = subprocess.run(cmd, cwd=engine_parent, env=env, capture_output=True, text=True,
                       encoding="utf-8", timeout=3600)
    res_path = os.path.join(out_dir, "semantic_results.json")
    if r.returncode != 0 or not os.path.isfile(res_path):
        raise RuntimeError(f"engine run failed rc={r.returncode}: {r.stdout[-400:]} {r.stderr[-400:]}")
    with open(res_path, encoding="utf-8") as f:
        result = json.load(f)
    shutil.rmtree(out_dir, ignore_errors=True)  # 结果已读入内存，临时产物即弃
    return {"result": result, "llm": llm_info}


def _ensure_llm_env_file() -> str | None:
    """把 LLM 复核层配置写成引擎可发现的 .env（run_llm_semantic_triage.load_env 只认文件）。

    load_env 从引擎 pipeline/ 模块目录向上找 4 层 .env —— 写在 triage_engine/ 包根即可命中。
    凭证只从既有配置文件/环境读取，文件权限 0600，且已加入 .gitignore（绝不入库）。
    返回引擎子进程可继承的环境 dict（env 中也带一份，便于未来引擎支持 os.environ）。
    """
    env_path = os.path.join(ENGINE_DIR, ".env")
    env = dict(os.environ)
    if not (os.path.isfile(env_path) and os.path.getsize(env_path) > 0):
        key = env.get("LLM_API_KEY", "")
        if not key:
            proxy_env = os.path.join(os.path.expanduser("~"), ".config", "anthropic-proxy.env")
            if os.path.isfile(proxy_env):
                for line in open(proxy_env, encoding="utf-8", errors="ignore"):
                    if line.startswith("ZAI_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        if not key:
            return env
        content = (f"LLM_BASE_URL={env.get('LLM_BASE_URL', 'https://api.z.ai/api/anthropic')}\n"
                   f"LLM_API_KEY={key}\n"
                   f"LLM_MODEL={env.get('LLM_MODEL', 'glm-5.2')}\n"
                   f"LLM_TIMEOUT_SECONDS={env.get('LLM_TIMEOUT_SECONDS', '120')}\n")
        fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
    env.setdefault("LLM_BASE_URL", "https://api.z.ai/api/anthropic")
    env.setdefault("LLM_MODEL", "glm-5.2")
    return env


def index_items(items: list[dict]) -> dict:
    """引擎 items（含事件级并入）→ 身份键索引。

    键：url 全键 + 规范化题名键。并入记录经 mergedRefs 一并登记，
    保证每条原记录都能拿回引擎结果（不因引擎去重丢记录）。
    """
    def norm_title(t: str) -> str:
        return re.sub(r"[\W_]+", "", str(t or "").lower(), flags=re.U)

    idx: dict[str, dict] = {}
    for it in items:
        for key in (f"u::{it.get('url', '')}", f"t::{norm_title(it.get('title', ''))}"):
            if key not in ("u::", "t::"):
                idx.setdefault(key, it)
        for ref in it.get("mergedRefs", []) or []:
            for key in (f"u::{ref.get('url', '')}", f"t::{norm_title(ref.get('title', ''))}"):
                if key not in ("u::", "t::"):
                    idx.setdefault(key, it)
    return idx


def apply_triage(records: list[dict], run: dict, dom_map: dict, whitelist: set[str]) -> dict:
    """把引擎结果写回记录。返回统计计数。

    每条记录先清 aip（重跑必须清除旧精选标记），再按新规则回填；
    不相关记录清空全部 AI 派生字段（终止后续管线）。
    """
    items = run["result"].get("items", [])
    idx = index_items(items)
    stats = {"total": len(records), "matched": 0, "unmatched": 0, "irrelevant": 0,
             "scored": 0, "featured": 0, "carrier_switched": 0}

    for rec in records:
        row = record_to_row(rec)
        item = idx.get(f"u::{row['url']}")
        if item is None:
            title_key = "t::" + re.sub(r"[\W_]+", "", row["title"].lower(), flags=re.U)
            item = idx.get(title_key)
        if item is None:
            # 兜底：清精选但保留原分类，待下轮重试（不能臆造结果）
            rec.pop("aip", None)
            stats["unmatched"] += 1
            continue

        stats["matched"] += 1
        carrier = resolve_carrier(item, rec)
        if carrier != rec.get("i"):
            stats["carrier_switched"] += 1
        rec["i"] = carrier

        cat = resolve_category(item, dom_map, whitelist)
        if cat == "不相关":
            stats["irrelevant"] += 1
            rec["c"] = "不相关"
            rec["tg"] = _LIT_DEFAULT_TAG if carrier == "l" else _NEWS_DEFAULT_TAG
            for field in AI_DERIVED_FIELDS:
                rec.pop(field, None)
            continue

        rec["c"] = cat
        rec["tg"] = resolve_tag(item, carrier)

        # 评分（引擎唯一来源）：sc=引擎 S8 value/10；scd=引擎卡维度归一五槽
        val = parse_value(item.get("value"), item.get("valueDisplay"))
        band = str(item.get("scoreBand") or "")
        if val is not None and band in ("高", "中", "低"):
            rec["sc"] = round(val / 10.0, 1)
            rec["scd"] = map_dims(item.get("dimensions"))
            stats["scored"] += 1
        else:
            # 入域但无分值（极端兜底）：不留半套结果
            rec.pop("sc", None)
            rec.pop("scd", None)

        # AI 精选：仅新闻按引擎最终档位（高/中 → 精选）；文献一律不精选
        is_literature = carrier == "l" or item.get("displayCategory") == "论文"
        if not is_literature and band in ("高", "中"):
            rec["aip"] = 1
            stats["featured"] += 1
        else:
            rec.pop("aip", None)
    return stats


def engine_triage_records(records: list[dict], use_llm: bool = False, workdir: str | None = None,
                          llm_batch: int = 8, llm_sleep: float = 2.0) -> dict:
    """对外主入口：一批 lite 记录过引擎（分类+类型+评分+精选判定），原地写回。"""
    if not records:
        return {"total": 0, "matched": 0, "unmatched": 0, "irrelevant": 0,
                "scored": 0, "featured": 0, "carrier_switched": 0}
    tmp_work = workdir or tempfile.mkdtemp(prefix="engine_triage_")
    rows = [record_to_row(r) for r in records]
    run = run_engine(rows, tmp_work, use_llm=use_llm, llm_batch=llm_batch, llm_sleep=llm_sleep)
    dom_map = build_engine_domain_maps()
    whitelist = load_whitelist()
    stats = apply_triage(records, run, dom_map, whitelist)
    stats["engine"] = ENGINE_VERSION
    stats["method"] = run["result"].get("method", "")
    return stats
