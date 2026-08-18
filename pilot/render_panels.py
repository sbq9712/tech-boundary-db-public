#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""竖井认知面板 HTML 渲染器（SOFC / 核聚变）"""
import json, html
from pathlib import Path

def esc(s):
    return html.escape(str(s), quote=False)

SIDE_LABEL = {'technical': '技术侧', 'system': '系统侧'}
NATURE_LABEL = {'physical': '物理限制', 'engineering': '工程', 'economic': '经济', 'epistemic': '认知论',
                'regulatory': '准入审批', 'supply_chain': '供应链', 'ecosystem': '生态配套', 'social_acceptance': '社会接受'}
DS_LABEL = {'verified': ('verified', '✓ 已验证'), 'disclosed': ('pending', '⚠ 已披露'),
            'missing': ('miss', '? 缺数据'), 'disputed': ('miss', '✗ 有争议')}

CSS = """
:root { --bg:#0f1419; --panel:#161d27; --card:#1c2530; --border:#2a3644; --text:#d8e1ea; --muted:#8b9bab;
        --accent:#4f9cf9; --tech:#7dd3fc; --sys:#f0abfc; --ok:#34d399; --warn:#fbbf24; --bad:#f87171; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif; padding:24px; line-height:1.65; }
.wrap { max-width:1180px; margin:0 auto; }
h1 { font-size:22px; margin-bottom:4px; }
.sub { color:var(--muted); font-size:13px; margin-bottom:20px; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.card { background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:18px; }
.card.full { grid-column:1 / -1; }
.card h2 { font-size:15px; color:var(--accent); margin-bottom:12px; padding-bottom:8px; border-bottom:1px solid var(--border); }
.verdict { font-size:15px; line-height:1.8; }
.meta-row { display:flex; gap:16px; margin-top:10px; font-size:13px; color:var(--muted); flex-wrap:wrap; }
.meta-row b { color:var(--text); }
.pill { display:inline-block; padding:2px 10px; border-radius:99px; font-size:12px; margin:2px 4px 2px 0; }
.pill.tech { background:rgba(125,211,252,.15); color:var(--tech); border:1px solid rgba(125,211,252,.3); }
.pill.sys { background:rgba(240,171,252,.12); color:var(--sys); border:1px solid rgba(240,171,252,.3); }
.pill.binding { background:rgba(251,191,36,.15); color:var(--warn); border:1px solid rgba(251,191,36,.4); font-weight:600; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; color:var(--muted); font-weight:500; padding:6px 8px; border-bottom:1px solid var(--border); }
td { padding:8px; border-bottom:1px solid rgba(42,54,68,.5); vertical-align:top; }
tr:last-child td { border-bottom:none; }
.small { font-size:12px; color:var(--muted); }
.small b { color: var(--text); }
.verified { color:var(--ok); }
.pending { color:var(--warn); }
.miss { color:var(--bad); }
.kw { background:rgba(79,156,249,.12); border:1px solid rgba(79,156,249,.25); border-radius:4px; padding:0 4px; font-size:11px; }
ul { list-style:none; }
li { padding:4px 0 4px 14px; position:relative; font-size:13px; }
li:before { content:"\\25B8"; position:absolute; left:0; color:var(--accent); }
.footer { color:var(--muted); font-size:12px; margin-top:20px; text-align:center; }
@media (max-width:900px){ .grid{grid-template-columns:1fr} }
"""

def trunc(s, n):
    s = str(s)
    return s[:n] + ('…' if len(s) > n else '')

def render(domain_file, title, subtitle, out_path):
    j = json.load(open(f'pilot/judgments/{domain_file}', encoding='utf-8'))
    s = json.load(open(f'pilot/signals/{domain_file}', encoding='utf-8'))
    sig_by_id = {x['id']: x for x in s['signals']}
    ij = j['industry_judgment']

    # 行业判断
    binding_name = next((b['name'] for b in j['bottlenecks'] if b['id'] == ij['binding_constraint']), ij['binding_constraint'])
    vlog = j.get('verification_log', [])
    vlog_html = esc(' · '.join(f"{v['date']} 联网核实: {v['items']}" for v in vlog)) if vlog else '<span class="small">（存量提取，未联网核实）</span>'

    # 拐点
    infl = ''
    for ic in ij['inflection_criteria']:
        sig = sig_by_id.get(ic.get('signal_ref'), {})
        infl += f"<tr><td style='width:40%'>{esc(ic['condition'])}</td><td>{esc(ic['meaning'])}</td><td class='small'>{esc(trunc(sig.get('baseline',''), 60))}</td></tr>"

    # 路线
    routes = ''
    for r in j['routes']:
        routes += (f"<tr><td><b>{esc(r['name'])}</b> <span class='small'>· {esc(r.get('maturity',''))}</span>"
                   f"<div class='small' style='margin-top:4px'>{esc(trunc(r['judgment'], 170))}</div></td></tr>")

    # 卡点
    botts = ''
    for b in j['bottlenecks']:
        side_cls = 'tech' if b['side'] == 'technical' else 'sys'
        binding = '<span class="pill binding">⚑ 约束性</span>' if b.get('binding') else ''
        cond = f"<div class='small'>条件性：{esc(b['conditional_on'])}</div>" if b.get('conditional_on') else ''
        botts += (f"<tr><td style='width:24%'><b>{esc(b['name'])}</b><br>{binding}"
                  f"<div style='margin-top:4px'><span class='pill {side_cls}'>{SIDE_LABEL[b['side']]}·{NATURE_LABEL[b['nature']]}</span></div>{cond}</td>"
                  f"<td class='small'>{esc(trunc(b['statement'], 300))}</td>"
                  f"<td style='width:26%' class='small'>{esc(b['breakthrough_form'])}</td></tr>")

    # 指标
    inds = ''
    for i in j['indicators']:
        cls, lab = DS_LABEL.get(i['data_status'], ('pending', ''))
        inds += (f"<tr><td><b>{esc(i['name'])}</b></td><td class='small'>{esc(trunc(i['current'], 90))}</td>"
                 f"<td class='small'>{esc(trunc(i['commercial_requirement'], 60))}</td><td class='{cls}'>{lab}</td></tr>")

    # 信号
    sigs = ''
    for sig in s['signals']:
        linked = sig.get('linked_bottleneck') or sig.get('linked_route') or sig.get('linked') or ''
        note = f"<tr><td colspan='4' class='small' style='color:var(--muted)'>└ {esc(sig['note'])}</td></tr>" if sig.get('note') else ''
        sigs += (f"<tr><td style='width:17%'><b>{esc(sig['name'])}</b><br><span class='kw'>{esc(sig['type'])}</span></td>"
                 f"<td class='small'>{esc(trunc(sig.get('baseline',''), 110))}</td>"
                 f"<td class='small'>{esc(trunc(sig.get('threshold',''), 85))}</td>"
                 f"<td class='small'>{esc(linked)}</td></tr>{note}")

    to_verify = ''.join(f'<li>{esc(v)}</li>' for v in j.get('to_verify', [])[:12])

    doc_list = ''.join(f'<li>{esc(d)}</li>' for d in j.get('source_docs', []))

    out = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>{esc(title)} · 认知面板</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>{esc(title)} — 行业认知面板</h1>
<div class="sub">{esc(subtitle)} · 证据截至 {esc(j['as_of'])}</div>
<div class="grid">

<div class="card full"><h2>行业判断</h2>
<div class="verdict">{esc(ij['conclusion'])}</div>
<div class="meta-row">
<span>置信度 <b class="{'verified' if ij['confidence']=='high' else 'pending'}">{esc(ij['confidence'])}</b></span>
<span>约束性卡点 <b>{esc(binding_name)}</b></span>
<span class="small">核实：{vlog_html}</span>
</div></div>

<div class="card"><h2>拐点标准（{len(ij['inflection_criteria'])} 条）</h2>
<table><tr><th>条件</th><th>含义</th><th>当前基线</th></tr>{infl}</table></div>

<div class="card"><h2>技术路线（{len(j['routes'])} 条）</h2>
<table><tr><th>路线 · 成熟度 · 判断</th></tr>{routes}</table></div>

<div class="card full"><h2>卡点（技术侧 {sum(1 for b in j['bottlenecks'] if b['side']=='technical')} + 系统侧 {sum(1 for b in j['bottlenecks'] if b['side']=='system')}）</h2>
<table><tr><th>卡点</th><th>现状</th><th>突破形态</th></tr>{botts}</table></div>

<div class="card"><h2>指标边界（{len(j['indicators'])} 项）</h2>
<table><tr><th>指标</th><th>当前</th><th>需求</th><th>状态</th></tr>{inds}</table></div>

<div class="card"><h2>信号规格（{len(s['signals'])} 条）</h2>
<table><tr><th>信号</th><th>基线</th><th>阈值</th><th>挂载</th></tr>{sigs}</table></div>

<div class="card"><h2>待核实清单（{len(j.get('to_verify', []))} 条）</h2>
<ul>{to_verify}</ul></div>

<div class="card"><h2>权威文档（ADR-0009：判断的 single source of truth）</h2>
<ul>{doc_list}</ul>
<div class="small" style="margin-top:8px">本面板为判断树的可视化投影；判断变更须经人审后写入文档，再重新提取。</div></div>

</div>
<div class="footer">竖井认知面板 v2 · 2026-08-18 · 判断树数据: pilot/judgments/{esc(domain_file)}</div>
</div></body></html>"""
    Path(out_path).write_text(out, encoding='utf-8')
    print(f'OK {out_path} ({Path(out_path).stat().st_size} bytes)')

if __name__ == '__main__':
    render('sofc.json', 'SOFC 固体氧化物燃料电池', '源: SOFC行业深度报告 v2.3 + 专利地图 + 2026-08-18 联网核实', 'pilot/panel.html')
    render('fusion.json', '核聚变', '源: 核聚变商业化进展 v1.0 + 广度观测 + 2026-08-18 联网核实', 'pilot/fusion-panel.html')
