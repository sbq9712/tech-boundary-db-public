#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""竖井认知面板 HTML 渲染器 v3 — 叙事结构：整体总结 + 逻辑推导 → 卡点 → 拐点 → 路线 → 指标 → 信号 → 边界"""
import json, html
from pathlib import Path

def esc(s):
    return html.escape(str(s), quote=False)

def trunc(s, n):
    s = str(s)
    return s[:n] + ('…' if len(s) > n else '')

SIDE_LABEL = {'technical': '技术侧', 'system': '系统侧'}
NATURE_LABEL = {'physical': '物理限制', 'engineering': '工程', 'economic': '经济', 'epistemic': '认知论',
                'regulatory': '准入审批', 'supply_chain': '供应链', 'ecosystem': '生态配套', 'social_acceptance': '社会接受'}
NATURE_HINT = {'physical': '自然规律不允许，突破=绕路', 'engineering': '理论可解造出来难，突破=学习曲线',
               'economic': '造得出来但太贵，突破=成本过线', 'epistemic': '无可靠预测模型，突破=黑箱事件',
               'regulatory': '监管不放行，突破=制度事件', 'supply_chain': '上游不给，突破=产能/替代源',
               'ecosystem': '别人得先建配套，突破=首个大额承诺', 'social_acceptance': '公众不答应，突破=态度转折'}
DS_LABEL = {'verified': ('verified', '✓ 已验证'), 'disclosed': ('pending', '⚠ 已披露'),
            'missing': ('miss', '? 缺数据'), 'disputed': ('miss', '✗ 有争议')}

CSS = """
:root { --bg:#0f1419; --panel:#161d27; --card:#1c2530; --border:#2a3644; --text:#d8e1ea; --muted:#8b9bab;
        --accent:#4f9cf9; --tech:#7dd3fc; --sys:#f0abfc; --ok:#34d399; --warn:#fbbf24; --bad:#f87171; }
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif; padding:24px; line-height:1.7; }
.wrap { max-width:1080px; margin:0 auto; }
h1 { font-size:23px; margin-bottom:2px; }
.sub { color:var(--muted); font-size:13px; margin-bottom:6px; }
.toc { font-size:12px; color:var(--muted); margin-bottom:18px; }
.toc a { color:var(--accent); text-decoration:none; margin-right:14px; }
.card { background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:20px; margin-bottom:16px; }
.card h2 { font-size:16px; color:var(--accent); margin-bottom:4px; }
.card .h2sub { font-size:12.5px; color:var(--muted); margin-bottom:14px; }
.verdict { font-size:15.5px; line-height:1.85; }
.meta-row { display:flex; gap:18px; margin-top:14px; font-size:13px; color:var(--muted); flex-wrap:wrap; align-items:center; }
.meta-row b { color:var(--text); }
.pill { display:inline-block; padding:2px 10px; border-radius:99px; font-size:12px; margin:2px 4px 2px 0; white-space:nowrap; }
.pill.tech { background:rgba(125,211,252,.15); color:var(--tech); border:1px solid rgba(125,211,252,.3); }
.pill.sys { background:rgba(240,171,252,.12); color:var(--sys); border:1px solid rgba(240,171,252,.3); }
.pill.binding { background:rgba(251,191,36,.15); color:var(--warn); border:1px solid rgba(251,191,36,.4); font-weight:600; }
.step { position:relative; padding:12px 0 12px 34px; font-size:14px; line-height:1.8; border-left:2px solid var(--border); }
.step:last-child { border-left-color:transparent; }
.step:before { content:attr(data-n); position:absolute; left:-15px; top:10px; width:28px; height:28px; border-radius:50%;
  background:var(--card); border:1px solid var(--accent); color:var(--accent); font-size:13px; font-weight:600;
  display:flex; align-items:center; justify-content:center; }
.step b { color:var(--tech); }
table { width:100%; border-collapse:collapse; font-size:13px; margin-top:4px; }
th { text-align:left; color:var(--muted); font-weight:500; padding:6px 8px; border-bottom:1px solid var(--border); }
td { padding:8px; border-bottom:1px solid rgba(42,54,68,.5); vertical-align:top; }
tr:last-child td { border-bottom:none; }
.small { font-size:12px; color:var(--muted); }
.verified { color:var(--ok); } .pending { color:var(--warn); } .miss { color:var(--bad); }
.kw { background:rgba(79,156,249,.12); border:1px solid rgba(79,156,249,.25); border-radius:4px; padding:0 5px; font-size:11px; }
.ref { color:var(--tech); font-size:12px; }
ul { list-style:none; } li { padding:4px 0 4px 14px; position:relative; font-size:13px; }
li:before { content:"\\25B8"; position:absolute; left:0; color:var(--accent); }
.footer { color:var(--muted); font-size:12px; margin-top:12px; text-align:center; }
.flow { display:flex; flex-wrap:wrap; gap:6px; align-items:center; font-size:12.5px; color:var(--muted); margin-top:10px; }
.flow .node { background:var(--card); border:1px solid var(--border); border-radius:6px; padding:3px 10px; }
.flow .node.hot { border-color:rgba(251,191,36,.5); color:var(--warn); }
.flow .arr { color:var(--accent); }
"""

def reasoning_html(steps):
    out = ''
    for i, s in enumerate(steps, 1):
        out += f'<div class="step" data-n="{i}">{esc(s)}</div>'
    return out

def render(domain_file, title, subtitle, out_path):
    j = json.load(open(f'pilot/judgments/{domain_file}', encoding='utf-8'))
    s = json.load(open(f'pilot/signals/{domain_file}', encoding='utf-8'))
    sig_by_id = {x['id']: x for x in s['signals']}
    bott_by_id = {b['id']: b for b in j['bottlenecks']}
    ij = j['industry_judgment']
    binding_name = bott_by_id.get(ij['binding_constraint'], {}).get('name', ij['binding_constraint'])
    vlog = j.get('verification_log', [])
    vlog_html = esc('；'.join(f"{v['date']} 核实 {v['items']}" for v in vlog)) if vlog else '存量提取（未联网核实）'

    # 3 卡点全景：约束性在前，技术/系统分组
    ordered = sorted(j['bottlenecks'], key=lambda b: (not b.get('binding'), b['side'] != 'technical'))
    botts = ''
    for b in ordered:
        side_cls = 'tech' if b['side'] == 'technical' else 'sys'
        binding = '<span class="pill binding">⚑ 约束性卡点</span>' if b.get('binding') else ''
        cond = f"<div class='small' style='margin-top:4px'>条件性：{esc(b['conditional_on'])}</div>" if b.get('conditional_on') else ''
        botts += (f"<tr><td style='width:23%'><b>{esc(b['name'])}</b><br>{binding}"
                  f"<div style='margin-top:4px'><span class='pill {side_cls}'>{SIDE_LABEL[b['side']]}·{NATURE_LABEL[b['nature']]}</span></div>"
                  f"<div class='small' style='margin-top:4px'>{esc(NATURE_HINT.get(b['nature'],''))}</div>{cond}</td>"
                  f"<td class='small'>{esc(trunc(b['statement'], 260))}</td>"
                  f"<td style='width:24%' class='small'>{esc(trunc(b['breakthrough_form'], 130))}</td></tr>")

    # 4 拐点：显式挂卡点
    infl = ''
    for ic in ij['inflection_criteria']:
        sig = sig_by_id.get(ic.get('signal_ref'), {})
        if ic.get('bottleneck_ref'):
            src = f"<span class='ref'>⇠ {esc(bott_by_id.get(ic['bottleneck_ref'],{}).get('name',''))}</span>"
        elif ic.get('route_ref'):
            src = f"<span class='ref'>⇠ 路线级：{esc(ic['route_ref'])}</span>"
        else:
            src = ''
        infl += (f"<tr><td style='width:38%'>{esc(ic['condition'])}<div style='margin-top:2px'>{src}</div></td>"
                 f"<td>{esc(ic['meaning'])}</td>"
                 f"<td class='small' style='width:24%'>{esc(trunc(sig.get('baseline',''), 55))}</td></tr>")

    # 5 路线：卡点连锁
    routes = ''
    for r in j['routes']:
        locks = '、'.join(bott_by_id[b]['name'].split('（')[0] for b in r.get('bottleneck_refs', [])) or '—'
        routes += (f"<tr><td style='width:22%'><b>{esc(r['name'])}</b><br><span class='small'>{esc(r.get('maturity',''))}</span></td>"
                   f"<td class='small'>{esc(trunc(r['judgment'], 150))}</td>"
                   f"<td class='small' style='width:22%'>{esc(locks)}</td></tr>")

    # 6 指标
    inds = ''
    for i in j['indicators']:
        cls, lab = DS_LABEL.get(i['data_status'], ('pending', ''))
        inds += (f"<tr><td><b>{esc(i['name'])}</b></td><td class='small'>{esc(trunc(i['current'], 85))}</td>"
                 f"<td class='small'>{esc(trunc(i['commercial_requirement'], 55))}</td>"
                 f"<td class='small'>{esc(trunc(i.get('gap_nature',''), 60))}</td><td class='{cls}'>{lab}</td></tr>")

    # 7 信号
    sigs = ''
    for sig in s['signals']:
        linked = sig.get('linked_bottleneck') or sig.get('linked_route') or sig.get('linked') or ''
        linked_disp = bott_by_id.get(linked, {}).get('name', linked)
        sigs += (f"<tr><td style='width:17%'><b>{esc(sig['name'])}</b><br><span class='kw'>{esc(sig['type'])}</span></td>"
                 f"<td class='small'>{esc(trunc(sig.get('baseline',''), 100))}</td>"
                 f"<td class='small'>{esc(trunc(sig.get('threshold',''), 75))}</td>"
                 f"<td class='small'>{esc(trunc(linked_disp, 40))}</td></tr>")

    to_verify = ''.join(f'<li>{esc(v)}</li>' for v in j.get('to_verify', [])[:10])
    doc_list = ''.join(f'<li>{esc(d)}</li>' for d in j.get('source_docs', []))
    reasoning = ij.get('reasoning', [])

    # 逻辑链流程条（卡片2顶部）
    flow_nodes = ['行业结构'] + [f"<span class='node'>约束性卡点<br><b>{esc(binding_name[:14])}</b></span>"]
    flow = (f"<div class='flow'><span class='node'>行业结构与事实</span><span class='arr'>→</span>"
            f"<span class='node hot'>约束性卡点：{esc(binding_name.split('（')[0])}</span><span class='arr'>→</span>"
            f"<span class='node'>拐点标准（{len(ij['inflection_criteria'])} 条）</span><span class='arr'>→</span>"
            f"<span class='node'>信号监测（{len(s['signals'])} 条）</span></div>")

    out = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>{esc(title)} · 认知面板</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>{esc(title)} — 行业认知面板</h1>
<div class="sub">{esc(subtitle)} · 证据截至 {esc(j['as_of'])}</div>
<div class="toc"><a href="#s1">① 速览</a><a href="#s2">② 判断链</a><a href="#s3">③ 卡点</a><a href="#s4">④ 拐点</a><a href="#s5">⑤ 路线</a><a href="#s6">⑥ 指标</a><a href="#s7">⑦ 信号</a><a href="#s8">⑧ 边界</a></div>

<div class="card" id="s1"><h2>① 行业速览</h2><div class="h2sub">整体总结——这是什么行业，现在到哪一步，当前判断是什么</div>
<div class="verdict">{esc(ij['conclusion'])}</div>
{flow}
<div class="meta-row">
<span>置信度 <b class="{'verified' if ij['confidence']=='high' else 'pending'}">{esc(ij['confidence'])}</b></span>
<span>约束性卡点 <b>{esc(binding_name)}</b></span>
<span class="small">核实记录：{vlog_html}</span>
</div></div>

<div class="card" id="s2"><h2>② 判断链推导</h2><div class="h2sub">从行业结构到约束性卡点到拐点——每一步的"为什么"</div>
{reasoning_html(reasoning)}
</div>

<div class="card" id="s3"><h2>③ 卡点全景</h2><div class="h2sub">约束性卡点置顶（⚑）；侧·类型决定突破形态与监测方式</div>
<table><tr><th>卡点</th><th>现状（含核实更新）</th><th>突破形态</th></tr>{botts}</table></div>

<div class="card" id="s4"><h2>④ 拐点标准</h2><div class="h2sub">每条拐点 ⇠ 源自哪个卡点——满足即触发行业判断变更</div>
<table><tr><th>拐点条件</th><th>含义</th><th>当前基线</th></tr>{infl}</table></div>

<div class="card" id="s5"><h2>⑤ 路线竞争</h2><div class="h2sub">各路线被哪些卡点锁住——路线间的差异本质是卡点组合的差异</div>
<table><tr><th>路线 · 成熟度</th><th>判断</th><th>被锁卡点</th></tr>{routes}</table></div>

<div class="card" id="s6"><h2>⑥ 指标证据</h2><div class="h2sub">卡点与拐点的量化支撑——当前值 vs 场景需求</div>
<table><tr><th>指标</th><th>当前</th><th>需求</th><th>差距性质</th><th>状态</th></tr>{inds}</table></div>

<div class="card" id="s7"><h2>⑦ 信号监测</h2><div class="h2sub">拐点的前置雷达——类型由卡点 nature 驱动（事件型/趋势型/制度事件）</div>
<table><tr><th>信号</th><th>基线</th><th>阈值</th><th>监测对象</th></tr>{sigs}</table></div>

<div class="card" id="s8"><h2>⑧ 判断的边界</h2><div class="h2sub">明确不知道什么、待核实什么——判断质量取决于排查覆盖度</div>
<div class="small" style="margin-bottom:8px">待核实清单（{len(j.get('to_verify', []))} 条）：</div>
<ul>{to_verify}</ul>
<div class="small" style="margin:10px 0 6px">权威文档（判断的 single source of truth，ADR-0009）：</div>
<ul>{doc_list}</ul>
</div>

<div class="footer">竖井认知面板 v3 · 2026-08-18 · 叙事结构：整体总结 + 逻辑推导 · 判断树: pilot/judgments/{esc(domain_file)} · 判断变更待人审</div>
</div></body></html>"""
    Path(out_path).write_text(out, encoding='utf-8')
    print(f'OK {out_path} ({Path(out_path).stat().st_size} bytes)')

if __name__ == '__main__':
    render('sofc.json', 'SOFC 固体氧化物燃料电池', '源: SOFC行业深度报告 v2.3 + 专利地图 + 联网核实', 'pilot/panel.html')
    render('fusion.json', '核聚变', '源: 核聚变商业化进展 v1.0 + 广度观测 + 联网核实', 'pilot/fusion-panel.html')
