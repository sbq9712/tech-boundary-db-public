const routes = {
  home: { label: "门户", title: "技术边界门户" },
  intel: { label: "情报总表", title: "情报总表" },
  dashboard: { label: "技术仪表盘", title: "技术仪表盘总表" },
  map: { label: "行业图景", title: "行业图景" },
  knowledge: { label: "知识图谱", title: "知识图谱" },
  sources: { label: "信源", title: "信源" }
};
const navItems = [["home","HOME"],["intel","INT"],["dashboard","DASH"],["map","MAP"],["knowledge","KG"],["sources","SRC"]];
const sourceCards = [["Nature","https://www.nature.com/","高影响力科学论文与新闻，适合追踪基础研究突破、跨学科技术信号和早期科学依据。"],["Science","https://www.science.org/","综合性顶级期刊，适合发现前沿科学进展、政策相关研究和具有产业外溢潜力的新技术。"],["MIT Technology Review","https://www.technologyreview.com/","权威科技媒体，适合观察新技术商业化、投资热度和早期产业应用叙事。"],["DOE Office of Science","https://www.energy.gov/science/office-science","美国能源部科学办公室，适合核实能源技术项目、基础设施和政府资助方向。"]];
let assistantPanels = emptyPanels();
let homeDraft = localStorage.getItem('home_query_draft') || '';
let mapSearchDraft = '';
let mapOpenDepth = 2;
document.addEventListener('input', event => {
  if(event.target && event.target.id === 'mapSearch'){
    mapSearchDraft = event.target.value.trim();
    loadIndustryMap();
  }
});
document.addEventListener('click', event => {
  if(event.target && event.target.id === 'mapExpandAll'){
    mapOpenDepth = 99;
    loadIndustryMap();
  }
  if(event.target && event.target.id === 'mapCollapse'){
    mapOpenDepth = 2;
    loadIndustryMap();
  }
});
function syncMapHorizontalBar(){
  const scroller=document.getElementById('industryTree');
  const track=document.getElementById('mapXScroll');
  const thumb=document.getElementById('mapXThumb');
  if(!scroller||!track||!thumb)return;
  const maxScroll=Math.max(0,scroller.scrollWidth-scroller.clientWidth);
  const trackWidth=track.clientWidth;
  if(!maxScroll||!trackWidth){
    track.classList.add('disabled');
    thumb.style.width='100%';
    thumb.style.transform='translateX(0)';
    return;
  }
  track.classList.remove('disabled');
  const thumbWidth=Math.max(56,Math.round(trackWidth*scroller.clientWidth/scroller.scrollWidth));
  const maxThumb=Math.max(1,trackWidth-thumbWidth);
  const left=Math.round(maxThumb*scroller.scrollLeft/maxScroll);
  thumb.style.width=`${thumbWidth}px`;
  thumb.style.transform=`translateX(${left}px)`;
}
function initMapHorizontalScroll(){
  const scroller=document.getElementById('industryTree');
  const track=document.getElementById('mapXScroll');
  const thumb=document.getElementById('mapXThumb');
  if(!scroller||!track||!thumb)return;
  scroller.onscroll=syncMapHorizontalBar;
  track.onpointerdown=event=>{
    if(track.classList.contains('disabled'))return;
    const rect=track.getBoundingClientRect();
    const thumbRect=thumb.getBoundingClientRect();
    const maxScroll=Math.max(0,scroller.scrollWidth-scroller.clientWidth);
    const dragOffset=event.target===thumb?event.clientX-thumbRect.left:thumbRect.width/2;
    const moveTo=clientX=>{
      const trackWidth=track.clientWidth;
      const thumbWidth=thumb.offsetWidth||56;
      const maxThumb=Math.max(1,trackWidth-thumbWidth);
      const nextLeft=Math.min(maxThumb,Math.max(0,clientX-rect.left-dragOffset));
      scroller.scrollLeft=nextLeft/maxThumb*maxScroll;
      syncMapHorizontalBar();
    };
    moveTo(event.clientX);
    track.setPointerCapture(event.pointerId);
    track.onpointermove=moveEvent=>moveTo(moveEvent.clientX);
    track.onpointerup=track.onpointercancel=()=>{
      track.onpointermove=null;
      track.onpointerup=null;
      track.onpointercancel=null;
    };
  };
  let dragging=false;
  let startX=0;
  let startScroll=0;
  scroller.onpointerdown=event=>{
    if(event.target.closest('a,button,summary,input'))return;
    dragging=true;
    startX=event.clientX;
    startScroll=scroller.scrollLeft;
    scroller.classList.add('dragging');
    scroller.setPointerCapture(event.pointerId);
  };
  scroller.onpointermove=event=>{
    if(!dragging)return;
    scroller.scrollLeft=startScroll-(event.clientX-startX);
  };
  scroller.onpointerup=scroller.onpointercancel=()=>{
    dragging=false;
    scroller.classList.remove('dragging');
  };
  syncMapHorizontalBar();
}
window.addEventListener('resize',syncMapHorizontalBar);
let homeMessages = loadHomeMessages();
let activeSessionId = null;
function emptyPanels(){return {hot_intel:[],parameter_boundaries:[],alert_intel:[],dashboard_links:[]};}
function token(){return localStorage.getItem("auth_token")||localStorage.getItem("access_token")||"";}
function authHeaders(){return {"Authorization":`Bearer ${token()}`};}
function loadHomeMessages(){try{return JSON.parse(localStorage.getItem('home_messages')||'[]');}catch(_err){return []}}
function saveHomeMessages(){localStorage.setItem('home_messages',JSON.stringify(homeMessages.slice(-40)));}
function addHomeMessage(role,text,extra){homeMessages.push({role,text,extra:extra||null,ts:Date.now()});saveHomeMessages();}
function renderHomeMessages(){
  // Fresh session: only show the system welcome message, don't load old history
  const base='<div class="assistant-msg"><strong>系统</strong><p>请输入一个技术、行业或项目问题。回答会围绕情报、证据、参数和判断边界组织。</p></div>';
  // If we have an active session loaded, show only that session's messages (stored in activeSessionMessages)
  if(activeSessionMessages && activeSessionMessages.length){
    return base + activeSessionMessages.map(msg=>msg.role==='user'
      ?`<div class="user-msg"><strong>你</strong><p>${escapeHtml(msg.text)}</p></div>`
      :`<div class="assistant-msg"><strong>系统</strong><p>${escapeHtml(msg.text)}</p>${renderInlineResources(msg.extra)}</div>`
    ).join('');
  }
  return base;
}
let activeSessionMessages = [];
function parseHash(){const raw=(location.hash||"#home").slice(1);const [routePart,queryPart=""]=raw.split("?");return {route:routes[routePart]?routePart:"home",params:new URLSearchParams(queryPart)};}
function setRoute(route,params){const q=params?`?${params.toString()}`:"";location.hash=route+q;}
function render(){if(window.Auth&&typeof Auth.requireAuth==="function")Auth.requireAuth();const state=parseHash();document.title=`${routes[state.route].title} · 技术边界数据库`;document.getElementById("app").innerHTML=shell(state);bindEvents();if(state.route==="home")loadAssistantStatus();if(state.route==="intel")loadIntel(state.params);if(state.route==="dashboard")loadDashboards();if(state.route==="map")loadIndustryMap();}
function shell(state){const data=routes[state.route];return `<aside class="sidebar" aria-label="主导航"><div class="brand"><div class="brand-mark" aria-hidden="true"></div><div class="brand-copy"><div class="brand-title">技术边界数据库</div><div class="brand-sub">判断资产库</div></div></div><nav class="nav-section">${navItems.map(([key,code])=>`<button class="nav-item ${state.route===key?'active':''}" data-route="${key}" title="${routes[key].label}"><span class="nav-icon">${code}</span><span class="nav-text">${routes[key].label}</span></button>`).join("")}</nav><div class="account"><div class="account-row"><div class="avatar">E</div><div class="account-copy"><div class="account-name">admin1</div><div class="account-role">已登录</div></div></div><div class="account-actions"><button class="ghost-btn" id="changePwdBtn">修改密码</button><button class="ghost-btn" id="logoutBtn">退出</button></div></div></aside><section class="workspace"><header class="topbar"><div><div class="crumb">技术边界数据库 / ${data.label}</div><div class="top-title">${data.title}</div></div><div class="context-select">当前主题：由对话自动识别</div></header><main class="main ${state.route==='home'?'home-main':''}" id="main" tabindex="-1">${view(state.route)}</main></section>`;}
function view(route){return {home:homeView,intel:intelView,dashboard:dashboardView,map:mapView,knowledge:knowledgeView,sources:sourcesView}[route]();}
function homeView(){return `<section class="panel conversation-panel"><div class="eyebrow">核心门户</div><h1 class="page-title">围绕技术边界提问、追踪证据、形成判断。</h1><div class="conversation-history" id="answer">${renderHomeMessages()}</div><div class="query-box"><input id="queryInput" class="query-input" autocomplete="off" name="tech-boundary-query" placeholder="例如：SOFC 作为数据中心电源的关键边界是什么？"/><button id="askBtn" class="primary-btn">发送</button></div></section><aside class="home-insights" id="homeInsights">${renderInsightPanels()}</aside>`;}
function renderInsightPanels(){return insightCard('热点情报推送',assistantPanels.hot_intel,'暂无与本轮问题直接相关的热点情报');}
function insightCard(title,items,emptyText){return `<section class="panel insight-card"><h2>${title}</h2>${items&&items.length?items.map(item=>`<article><b>${escapeHtml(item.title||item.name||'未命名')}</b><span>${escapeHtml(item.summary||item.value||item.description||'')}</span></article>`).join(''):`<div class="empty-slot">${emptyText}</div>`}</section>`;}
function intelView(){return `<section class="panel content-panel"><div class="eyebrow">情报总表</div><h1 class="section-title">按关键词、领域、来源、类型、重要度和预警状态检索情报。</h1><form class="filter-bar" id="intelFilter"><input id="intelQ" name="q" placeholder="关键词搜索"/><select id="intelDomain"><option value="">全部领域</option><option>SOFC</option><option>AIDC</option><option>CCUS</option></select><select id="intelSource"><option value="">全部来源</option><option>期刊</option><option>产业新闻</option><option>政策</option></select><select id="intelStatus"><option value="">全部状态</option><option value="alert">仅预警</option><option value="normal">非预警</option></select><button class="secondary-btn" type="submit">检索</button></form><div class="table-card"><table><thead><tr><th>标题</th><th>领域</th><th>类型</th><th>重要度</th><th>状态</th><th>关键指标</th></tr></thead><tbody id="intelRows"><tr><td colspan="6">正在加载情报…</td></tr></tbody></table></div></section>`;}
function dashboardView(){return `<section class="panel content-panel"><div class="eyebrow">技术仪表盘总表</div><h1 class="section-title">检索技术对象，查看适用场景、核心指标和相关情报入口。</h1><form class="dashboard-search" id="dashboardFilter"><input id="dashboardQ" placeholder="搜索技术、行业或指标，例如 SOFC、寿命、LCOS"/><button class="secondary-btn" type="submit">检索</button></form><div class="dashboard-grid" id="dashboardRows"><div class="status-note">正在加载仪表盘…</div></div></section>`;}
function sourcesView(){return `<section class="panel content-panel"><div class="eyebrow">信源</div><h1 class="section-title">信源用于支撑情报、证据和参数事实的持续更新。</h1><div class="source-grid">${sourceCards.map(([name,url,desc])=>`<a class="source-card" href="${url}" target="_blank" rel="noopener noreferrer"><span>${name}</span><p>${desc}</p><em>打开信源</em></a>`).join("")}</div></section>`;}
function mapView(){const state=parseHash();const group=state.params.get('group')||'zero-carbon';const tabs=[["zero-carbon","零碳产业"],["ai-intelligent","AI与智能科技"],["general-tech","通用技术"]];const titleMap={"zero-carbon":"零碳产业","ai-intelligent":"AI与智能科技","general-tech":"通用技术"};return `<section class="panel content-panel map-content-panel"><div class="map-head"><div><div class="eyebrow">行业图景</div><h1 class="section-title">XMind 三页签行业树，叶子节点挂接情报 / 专刊 / 仪表盘。</h1></div><div class="map-tools"><input id="mapSearch" value="${escapeHtml(mapSearchDraft)}" placeholder="搜索节点"/><button class="secondary-btn" id="mapExpandAll" type="button">展开全部</button><button class="secondary-btn" id="mapCollapse" type="button">折叠到二级</button></div></div><div class="map-legend"><span><i class="legend-dot intel">情</i>相关情报</span><span><i class="legend-dot issue">刊</i>专刊</span><span><i class="legend-dot dashboard">盘</i>行业仪表盘</span><span><i class="legend-dot missing">!</i>缺失标红</span></div><div class="bookmark-tabs">${tabs.map(([key,label])=>`<button class="bookmark-tab ${group===key?'active':''}" data-map-group="${key}">${label}</button>`).join('')}</div><div class="map-shell"><header class="map-summary"><strong>${titleMap[group]||'零碳产业'}</strong><span id="industryMapMeta">正在加载图景…</span></header><div class="industry-tree" id="industryTree"><div class="status-note">正在加载图景…</div></div><div class="map-x-scroll" id="mapXScroll"><div class="map-x-thumb" id="mapXThumb"></div></div></div></section>`;}
function knowledgeView(){return `<section class="panel content-panel"><div class="eyebrow">知识图谱</div><h1 class="section-title">知识图谱用于承载行业节点、情报、专刊、仪表盘和长期记忆之间的关系。当前先保留入口与结构接口。</h1><div class="knowledge-placeholder"><div class="status-note">知识图谱结构接口已预留，后续接入图谱数据后在这里呈现可交互关系网络。</div></div></section>`;}
function bindEvents(){document.querySelectorAll("[data-route]").forEach(btn=>btn.addEventListener("click",()=>setRoute(btn.dataset.route)));document.querySelectorAll("[data-map-group]").forEach(btn=>btn.addEventListener("click",()=>{const p=new URLSearchParams(parseHash().params.toString());p.set('group',btn.dataset.mapGroup);setRoute('map',p);}));const logout=document.getElementById("logoutBtn");const changePwd=document.getElementById("changePwdBtn");if(changePwd)changePwd.addEventListener("click",()=>{if(window.Auth&&Auth.showChangePassword)Auth.showChangePassword();});if(logout)logout.addEventListener("click",()=>{if(window.Auth&&Auth.logout)Auth.logout();else location.href="login.html";});const ask=document.getElementById("askBtn");const input=document.getElementById("queryInput");if(input){input.value=homeDraft;if(!input.dataset.bound){input.addEventListener('input',()=>{homeDraft=input.value;localStorage.setItem('home_query_draft',homeDraft);});input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submitQuery();}});input.dataset.bound='1';}}if(ask)ask.addEventListener("click",submitQuery);const intelFilter=document.getElementById("intelFilter");if(intelFilter)intelFilter.addEventListener("submit",e=>{e.preventDefault();const p=new URLSearchParams();['intelQ','intelDomain','intelSource','intelStatus'].forEach(id=>{const el=document.getElementById(id);if(el&&el.value)p.set(id.replace('intel','').toLowerCase(),el.value);});setRoute('intel',p);});const dashboardFilter=document.getElementById("dashboardFilter");if(dashboardFilter)dashboardFilter.addEventListener("submit",e=>{e.preventDefault();loadDashboards();});}
async function loadAssistantStatus(){const answer=document.getElementById("answer");if(!answer)return;try{const res=await fetch('/api/assistant/status',{headers:authHeaders()});const data=await res.json();const files=(data.health||{}).markdown_files;if(data.status==='ok'){answer.insertAdjacentHTML('beforeend',`<div class="assistant-msg"><strong>只读知识库</strong><p>已连接知识库，共 ${Number.isFinite(files)?files:'若干'} 个 Markdown 文档可供检索。</p></div>`);}}catch(err){answer.insertAdjacentHTML('beforeend',`<div class="assistant-msg"><strong>只读知识库</strong><p>知识库状态检查失败，仍可提交问题。</p></div>`);}}
function applyIntelParams(params){const map={q:'intelQ',domain:'intelDomain',source:'intelSource',status:'intelStatus'};for(const [key,id] of Object.entries(map)){const el=document.getElementById(id);if(el&&params.has(key))el.value=params.get(key);} }
async function loadIntel(params=new URLSearchParams()){applyIntelParams(params);const tbody=document.getElementById("intelRows");if(!tbody)return;tbody.innerHTML='<tr><td colspan="6">正在加载情报…</td></tr>';try{const q=encodeURIComponent(document.getElementById('intelQ')?.value||params.get('q')||'');const url=q?`/api/delivery-intel?q=${q}&limit=200`:'/api/delivery-intel?limit=200';const res=await fetch(url,{headers:authHeaders()});const data=await res.json();const source=document.getElementById('intelSource')?.value||'';let rows=(data.items||[]).filter(item=>{if(source&&!(item.source_type||'').includes(source))return false;return true;}).slice(0,100);tbody.innerHTML=rows.length?rows.map(item=>`<tr class="intel-row" data-id="${escapeHtml(item.id)}" style="cursor:pointer"><td>${escapeHtml(item.title||'未命名情报')}</td><td>${escapeHtml(item.leaf_title||'未分类')}</td><td>${escapeHtml(item.source_type||'')}</td><td>${escapeHtml(item.confidence||'')}</td><td>${item.need_human_review?'待审':'OK'}</td><td>${escapeHtml(item.key_metric?`${item.key_metric}: ${item.value_raw}${item.unit}`:'—')}</td></tr>`).join(''):'<tr><td colspan="6">没有符合条件的情报</td></tr>';tbody.querySelectorAll('.intel-row').forEach(tr=>tr.addEventListener('click',()=>showIntelDetail(tr.dataset.id)));}catch(err){tbody.innerHTML='<tr><td colspan="6">情报加载失败，请稍后重试</td></tr>';}}
async function loadDashboards(){const root=document.getElementById('dashboardRows');if(!root)return;root.innerHTML='<div class="status-note">正在加载仪表盘…</div>';const q=encodeURIComponent(document.getElementById('dashboardQ')?.value||parseHash().params.get('q')||'');try{const res=await fetch(`/api/dashboards${q?'?q='+q:''}`,{headers:authHeaders()});const data=await res.json();root.innerHTML=data.items.length?data.items.map(item=>dashboardCard(item)).join(''):'<div class="status-note">没有符合条件的仪表盘</div>';}catch(err){root.innerHTML='<div class="status-note">仪表盘加载失败，请稍后重试</div>';}}
function mapAssetText(value){return String(value||'').toLowerCase().replace(/\s+/g,'');}
function mapNodeTerms(node){const roots=new Set(['零碳产业','AI与智能科技','通用技术']);return Array.from(new Set([node.title,...(node.path||[])].map(v=>String(v||'').trim()).filter(v=>v.length>=2&&!roots.has(v))));}
function infoMapText(item){return mapAssetText([item.title,item.content,item.comment,(item.tags||[]).join(' '),(item.info_types||[]).join(' '),(item.source_types||[]).join(' '),(item.domain_ids||[]).join(' ')].join(' '));}
function dashboardMapText(item){return mapAssetText([item.id,item.name,item.scope,item.query,item.domain,(item.metrics||[]).join(' ')].join(' '));}
function mapMatchesNode(node, rows, textGetter){const terms=mapNodeTerms(node).map(mapAssetText).filter(Boolean);return rows.filter(row=>{const text=textGetter(row);return terms.some(term=>text.includes(term));});}
async function loadMapAssets(){const [infos,dashboards]=await Promise.allSettled([fetch('/api/info-items?status=published',{headers:authHeaders()}).then(r=>r.ok?r.json():[]),fetch('/api/dashboards',{headers:authHeaders()}).then(r=>r.ok?r.json():{items:[]})]);return {infos:infos.status==='fulfilled'&&Array.isArray(infos.value)?infos.value:[],dashboards:dashboards.status==='fulfilled'&&Array.isArray(dashboards.value.items)?dashboards.value.items:[]};}
function decorateIndustryAssets(node,assets){const children=node.children||[];if(!children.length){const intel=mapMatchesNode(node,assets.infos,infoMapText);const dashboards=mapMatchesNode(node,assets.dashboards,dashboardMapText);const dashboardQuery=dashboards[0]?.query||dashboards[0]?.id||node.title;node.assets={intel:{active:intel.length>0,count:intel.length,href:`#intel?q=${encodeURIComponent(node.title)}&from_map=1`},special_issue:{active:false,count:0,href:''},dashboard:{active:dashboards.length>0,count:dashboards.length,href:`#dashboard?q=${encodeURIComponent(dashboardQuery)}`}};}children.forEach(child=>decorateIndustryAssets(child,assets));return node;}
function countLeaves(node){const children=node.children||[];return children.length?children.reduce((sum,child)=>sum+countLeaves(child),0):1;}
function leafDots(node){const assets=node.assets||{};const fallbackCoverage=node.coverage||{};const fallbackLinks=node.links||{};const items=[['intel','情','相关情报'],['special_issue','刊','相关专刊'],['dashboard','盘','相关行业仪表盘']];return `<div class="leaf-tags">${items.map(([key,label,title])=>{const asset=assets[key]||{active:!!fallbackCoverage[key],href:fallbackLinks[key]||'#',count:0};const active=!!asset.active;const href=asset.href||'#';const status=active?`${title}：${asset.count||1}项`:`${title}：暂无`;return active?`<a class="leaf-tag active" data-link-type="${key}" href="${href}" title="${status}"><span>${label}</span></a>`:`<span class="leaf-tag missing" data-link-type="${key}" title="${status}" style="background:#dc2626;border-color:#b91c1c;color:#fff;"><span>${label}</span></span>`;}).join('')}</div>`;}
function mapNodeOwnMatch(node){const q=mapAssetText(mapSearchDraft);if(!q)return false;return mapAssetText([node.title,...(node.path||[])].join(' ')).includes(q);}
function mapNodeVisible(node){const q=mapAssetText(mapSearchDraft);if(!q)return true;if(mapNodeOwnMatch(node))return true;return (node.children||[]).some(mapNodeVisible);}
function industryNode(node){if(!mapNodeVisible(node))return '';const children=node.children||[];const leaf=children.length===0;const open=mapSearchDraft||node.depth<mapOpenDepth;const childHtml=children.map(industryNode).join('');return `<li class="mind-node depth-${node.depth} ${leaf?'leaf':''} ${mapNodeOwnMatch(node)?'match':''}"><details ${open?'open':''}><summary class="mind-card"><span>${escapeHtml(node.title)}</span>${leaf?'<em>具体行业</em>':`<em>${children.length} 个下级节点</em>`}</summary>${leaf?leafDots(node):childHtml?`<ul>${childHtml}</ul>`:''}</details></li>`;}
async function loadIndustryMap(){const root=document.getElementById('industryTree');const meta=document.getElementById('industryMapMeta');if(!root)return;const group=parseHash().params.get('group')||'zero-carbon';const titleMap={"zero-carbon":"零碳产业","ai-intelligent":"AI与智能科技","general-tech":"通用技术"};if(meta)meta.textContent=`${titleMap[group]||'零碳产业'}：正在加载 XMind 数据…`;try{const [mapRes,assets]=await Promise.all([fetch(`/api/industry-map?group=${encodeURIComponent(group==='zero-carbon'?'零碳产业':group==='ai-intelligent'?'AI与智能科技':'通用技术')}`,{headers:authHeaders()}),loadMapAssets()]);const data=await mapRes.json();const sheet=data.sheet||data.root||data;const rootNode=decorateIndustryAssets(sheet.root||sheet,assets);const sheetTitle=sheet.title||titleMap[group]||'行业图景';if(meta)meta.textContent=`${sheetTitle}：共 ${sheet.node_count||countNodes(rootNode)} 个节点，${countLeaves(rootNode)} 个叶子，最大层级 ${sheet.max_depth||maxDepth(rootNode)}`;root.innerHTML=`<div class="mindmap-canvas"><ul class="mindmap-root">${industryNode(rootNode)}</ul></div>`;requestAnimationFrame(initMapHorizontalScroll);}catch(err){root.innerHTML='<div class="status-note">图景加载失败，请检查 XMind 解析数据。</div>';if(meta)meta.textContent='图景加载失败';}}
function dashboardCard(item){const p=new URLSearchParams();if(item.query)p.set('q',item.query);else if(item.id)p.set('q',item.id);if(item.domain)p.set('domain',item.domain);return `<article class="dashboard-card"><h3>${escapeHtml(item.name)}</h3><p>${escapeHtml(item.scope)}</p><dl><dt>核心指标</dt><dd>${escapeHtml((item.metrics||[]).join('、'))}</dd><dt>状态</dt><dd>${escapeHtml(item.status)}</dd></dl><a href="#intel?${p.toString()}">查看相关情报</a></article>`;}
function countNodes(node){return 1+((node.children||[]).reduce((sum,child)=>sum+countNodes(child),0));}
function maxDepth(node){const children=node.children||[];return children.length?Math.max(...children.map(maxDepth)):Number(node.depth||0);}
function indicatorText(item){const indicators=item.draft_data&&Array.isArray(item.draft_data.indicators)?item.draft_data.indicators:[];return indicators.length?escapeHtml(indicators.slice(0,3).map(x=>`${x.name||'指标'} ${x.value||''}${x.unit||''}`).join('；')):'—';}
function updatePanels(extra){assistantPanels=(extra&&extra.panel_recommendations)||emptyPanels();const root=document.getElementById('homeInsights');if(root)root.innerHTML=renderInsightPanels();}
function renderInlineResources(extra){const panels=(extra&&extra.panel_recommendations)||emptyPanels();const citations=(extra&&Array.isArray(extra.citations))?extra.citations:[];const sections=[];if(citations.length){sections.push(`<div class="inline-resource-group"><h4>相关文档</h4>${citations.slice(0,6).map(path=>`<a href="#sources" title="${escapeHtml(path)}">${escapeHtml(path)}</a>`).join('')}</div>`);}const boundaries=panels.parameter_boundaries||[];if(boundaries.length){sections.push(`<div class="inline-resource-group"><h4>参数边界</h4>${boundaries.slice(0,4).map(item=>`<span>${escapeHtml(item.title||item.name||item.value||'参数边界')}</span>`).join('')}</div>`);}const alerts=panels.alert_intel||[];if(alerts.length){sections.push(`<div class="inline-resource-group"><h4>预警情报</h4>${alerts.slice(0,4).map(item=>`<span>${escapeHtml(item.title||item.name||'预警情报')}</span>`).join('')}</div>`);}const dashboards=panels.dashboard_links||[];if(dashboards.length){sections.push(`<div class="inline-resource-group"><h4>相关仪表盘</h4>${dashboards.slice(0,4).map(item=>`<a href="#dashboard${item.id?`?q=${encodeURIComponent(item.id)}`:''}">${escapeHtml(item.name||item.title||'相关仪表盘')}</a>`).join('')}</div>`);}return sections.length?`<div class="inline-resources">${sections.join('')}</div>`:'';}
async function submitQuery(){
  const input=document.getElementById("queryInput");
  const answer=document.getElementById("answer");
  const query=input.value.trim();
  if(!query){input.focus();return;}

  // Unique ID for this response, so multiple rounds don't overwrite each other
  const respId="resp_"+Date.now()+"_"+Math.random().toString(36).slice(2,7);

  // Track in active session memory
  activeSessionMessages.push({role:'user',text:query});
  activeSessionMessages.push({role:'assistant',text:'',extra:null});

  // UI: append user message + new streaming container (don't touch existing messages)
  answer.insertAdjacentHTML("beforeend",
    `<div class="user-msg"><strong>你</strong><p>${escapeHtml(query)}</p></div>`+
    `<div class="assistant-msg streaming" id="${respId}">`+
    `<div class="thinking-stages" id="stages_${respId}"></div>`+
    `<div class="response-text" id="text_${respId}"></div>`+
    `<div class="citations-area" id="cit_${respId}"></div>`+
    `</div>`
  );
  input.value="";homeDraft="";localStorage.removeItem('home_query_draft');
  answer.scrollTop=answer.scrollHeight;

  const stagesEl=document.getElementById("stages_"+respId);
  const respEl=document.getElementById("text_"+respId);
  const citEl=document.getElementById("cit_"+respId);
  let fullText="";

  try{
    const sseUrl=`/api/assistant/stream?query=${encodeURIComponent(query)}`;
    const res=await fetch(sseUrl,{headers:authHeaders()});
    if(!res.ok){
      const errData=await res.json().catch(()=>({detail:`HTTP ${res.status}`}));
      respEl.innerHTML=`<span class="error">⚠ ${escapeHtml(errData.detail||'请求失败')}</span>`;
      return;
    }
    const reader=res.body.getReader();
    const decoder=new TextDecoder();
    let buffer="";
    let currentEvent="";

    while(true){
      const {done,value}=await reader.read();
      if(done)break;
      buffer+=decoder.decode(value,{stream:true});
      const lines=buffer.split("\n");
      buffer=lines.pop();

      for(const line of lines){
        if(line.startsWith("event: ")){
          currentEvent=line.slice(7).trim();
        }else if(line.startsWith("data: ")){
          const dataStr=line.slice(6);
          let data;
          try{data=JSON.parse(dataStr);}catch(_){continue;}

          if(currentEvent==="status"){
            stagesEl.insertAdjacentHTML("beforeend",
              `<div class="stage-chip">${data.message}</div>`);
            const chips=stagesEl.querySelectorAll(".stage-chip");
            chips.forEach((c,i)=>{if(i<chips.length-1)c.classList.add("done");});
            answer.scrollTop=answer.scrollHeight;

          }else if(currentEvent==="token"){
            respEl.innerHTML=renderMarkdown(fullText+data.content);
            fullText+=data.content;
            answer.scrollTop=answer.scrollHeight;

          }else if(currentEvent==="done"){
            const stats=data.retrieval_summary||{};
            citEl.innerHTML=renderCitations(data.citations||[],stats);

          }else if(currentEvent==="error"){
            respEl.innerHTML=`<span class="error">⚠ ${escapeHtml(data.error||'LLM调用失败')}</span>`;
          }
        }
      }
    }

    // Save to active session memory + persisted history
    const lastMsg=activeSessionMessages[activeSessionMessages.length-1];
    lastMsg.text=fullText;
    addHomeMessage('assistant',fullText);
    const sm=document.getElementById(respId);
    if(sm)sm.classList.remove("streaming");

  }catch(err){
    respEl.innerHTML=`<span class="error">⚠ 连接失败，请稍后重试。</span>`;
  }
}

function renderMarkdown(text){
  // Minimal markdown: headers, bold, italic, code, line breaks, lists
  let html=escapeHtml(text);
  html=html.replace(/^### (.+)$/gm,'<h4>$1</h4>');
  html=html.replace(/^## (.+)$/gm,'<h3>$1</h3>');
  html=html.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  html=html.replace(/`(.+?)`/g,'<code>$1</code>');
  html=html.replace(/^\* (.+)$/gm,'<li>$1</li>');
  html=html.replace(/(<li>.*<\/li>)/s,'<ul>$1</ul>');
  html=html.replace(/\n/g,'<br>');
  return html;
}

function renderCitations(citations,stats){
  let html='<div class="citations-block">';
  html+=`<div class="retrieval-stats">检索：${stats.knowledge_base||0} 篇知识库 · ${stats.sources||0} 条文献 · ${stats.parameters||0} 条参数</div>`;
  if(citations.length){
    html+='<div class="citation-list"><strong>引用来源：</strong>';
    citations.forEach(c=>{
      if(c.type==='parameter'){
        html+=`<span class="cite-tag param">${escapeHtml(c.parameter_name)}: ${escapeHtml(c.value_range)} <em>${c.verification_status}</em></span>`;
      }else if(c.type==='knowledge_base'){
        html+=`<span class="cite-tag kb">📄 ${escapeHtml(c.title)}</span>`;
      }else if(c.type==='source'){
        html+=`<span class="cite-tag src">${escapeHtml((c.title||'').slice(0,40))}...</span>`;
      }
    });
    html+='</div>';
  }
  html+='</div>';
  return html;
}
function escapeHtml(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));}
async function showIntelDetail(id){
  if(!id)return;
  // Inject modal overlay if not present
  if(!document.getElementById('intelModal')){
    document.body.insertAdjacentHTML('beforeend',`
<div id="intelModal" style="display:none;position:fixed;inset:0;z-index:1000;background:rgba(15,23,42,.55);backdrop-filter:blur(4px);padding:24px;overflow:auto" onclick="if(event.target===this)closeIntelDetail()">
  <div style="max-width:860px;margin:0 auto;background:#fff;border-radius:18px;box-shadow:0 24px 64px rgba(15,23,42,.18);overflow:hidden">
    <div style="padding:18px 20px;border-bottom:1px solid #e5eaf2;display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:12px;color:#667085;text-transform:uppercase;letter-spacing:.1em">情报详情</span>
      <button onclick="closeIntelDetail()" style="border:0;background:#f1f5f9;color:#475467;border-radius:8px;padding:6px 12px;cursor:pointer;font-size:13px">关闭</button>
    </div>
    <div id="intelModalBody" style="padding:20px"></div>
  </div>
</div>`);
  }
  const modal=document.getElementById('intelModal');
  const body=document.getElementById('intelModalBody');
  body.innerHTML='<div style="color:#667085;padding:20px 0">正在加载…</div>';
  modal.style.display='block';
  document.body.style.overflow='hidden';
  try{
    const res=await fetch(`/api/delivery-intel/${encodeURIComponent(id)}`,{headers:authHeaders()});
    if(!res.ok){body.innerHTML='<div style="color:#dc2626">加载失败</div>';return;}
    const d=await res.json();
    body.innerHTML=`
<h2 style="font-size:20px;font-weight:750;margin:0 0 12px;line-height:1.3">${escapeHtml(d.title)}</h2>
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px">
  ${d.taxonomy_path?`<span style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:999px;padding:5px 10px;font-size:12px;color:#334155">${escapeHtml(d.taxonomy_path)}</span>`:''}
  ${d.source_type?`<span style="background:#e0f2fe;border:1px solid #7dd3fc;border-radius:999px;padding:5px 10px;font-size:12px;color:#0369a1">${escapeHtml(d.source_type)}</span>`:''}
  ${d.confidence?`<span style="background:${d.confidence==='high'?'#dcfce7':d.confidence==='medium'?'#fef9c3':'#fee2e2'};border-radius:999px;padding:5px 10px;font-size:12px;color:#334155">可信度: ${escapeHtml(d.confidence)}</span>`:''}
  ${d.need_human_review?`<span style="background:#fef3c7;border:1px solid #fcd34d;border-radius:999px;padding:5px 10px;font-size:12px;color:#92400e">待人工审核</span>`:''}
</div>
${d.url?`<a href="${escapeHtml(d.url)}" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:6px;color:#0e7490;font-size:13px;margin-bottom:16px;text-decoration:none">🔗 ${escapeHtml(d.source_name||'查看原文')} ${d.publish_date?'· '+escapeHtml(d.publish_date):''}</a>`:''}
${(d.key_metric||d.value_raw)?`
<div style="background:#f8fafc;border:1px solid #e5eaf2;border-radius:14px;padding:14px;margin-bottom:16px">
  <div style="font-size:12px;color:#667085;margin-bottom:8px;text-transform:uppercase;letter-spacing:.08em">关键指标</div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px">
    ${d.key_metric?`<div><div style="font-size:11px;color:#94a3b8">指标</div><div style="font-weight:650">${escapeHtml(d.key_metric)}</div></div>`:''}
    ${d.metric_type?`<div><div style="font-size:11px;color:#94a3b8">类型</div><div>${escapeHtml(d.metric_type)}</div></div>`:''}
    ${d.value_raw?`<div><div style="font-size:11px;color:#94a3b8">数值</div><div style="font-weight:650;color:#0e7490">${escapeHtml(d.value_raw)}${d.unit?' '+escapeHtml(d.unit):''}</div></div>`:''}
    ${d.object_name?`<div><div style="font-size:11px;color:#94a3b8">对象</div><div>${escapeHtml(d.object_name)}</div></div>`:''}
  </div>
</div>`:''}
${d.evidence_text?`
<div style="margin-bottom:16px">
  <div style="font-size:12px;color:#667085;margin-bottom:8px;text-transform:uppercase;letter-spacing:.08em">证据文本</div>
  <div style="background:#f8fafc;border-left:3px solid #0e7490;padding:12px 14px;border-radius:0 10px 10px 0;font-size:13px;line-height:1.65;white-space:pre-wrap">${escapeHtml(d.evidence_text)}</div>
</div>`:''}
${d.semantic_evidence?`
<div style="margin-bottom:16px">
  <div style="font-size:12px;color:#667085;margin-bottom:8px;text-transform:uppercase;letter-spacing:.08em">语义证据</div>
  <div style="background:#f8fafc;border:1px solid #e5eaf2;border-radius:10px;padding:12px 14px;font-size:13px;line-height:1.65;white-space:pre-wrap;color:#475467">${escapeHtml(d.semantic_evidence)}</div>
</div>`:''}
<div style="font-size:11px;color:#94a3b8;margin-top:8px">ID: ${escapeHtml(d.id)}</div>`;
  }catch(e){body.innerHTML='<div style="color:#dc2626">加载失败，请稍后重试</div>';}
}
function closeIntelDetail(){const m=document.getElementById('intelModal');if(m)m.style.display='none';document.body.style.overflow='';}
window.addEventListener("hashchange",render);window.addEventListener("DOMContentLoaded",render);
