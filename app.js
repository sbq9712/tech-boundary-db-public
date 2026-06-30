const routes = {
  home: { label: "门户", title: "技术边界门户" },
  intel: { label: "情报总表", title: "情报总表" },
  dashboard: { label: "技术仪表盘", title: "技术仪表盘总表" },
  map: { label: "行业图景", title: "行业图景" },
  knowledge: { label: "知识图谱", title: "知识图谱" },
  sources: { label: "信源", title: "信源" }
};
const navItems = [["home","HOME"],["intel","INT"],["dashboard","DASH"],["map","MAP"],["knowledge","KG"],["sources","SRC"]];
const sourceCards = [];
const SOURCE_LIST = [["机器之心", "垂直媒体", "产业资讯", "https://www.jiqizhixin.com/"], ["能源学人", "学术论文", "学术科研", ""], ["战略前沿技术", "垂直媒体", "产业资讯", ""], ["核闻天下", "垂直媒体", "产业资讯", ""], ["先进能源科技战略情报研究中心", "咨询行研", "行业研究", ""], ["DeepTech深科技", "垂直媒体", "产业资讯", "https://www.mittrchina.com/"], ["环球零碳", "垂直媒体", "产业资讯", ""], ["南方能源观察", "垂直媒体", "产业资讯", ""], ["光子盒", "垂直媒体", "产业资讯", ""], ["矿业界", "垂直媒体", "产业资讯", ""], ["ESPLaza长时储能网", "垂直媒体", "产业资讯", ""], ["ESPLaza储热网", "垂直媒体", "产业资讯", ""], ["钙钛矿工厂", "垂直媒体", "产业资讯", ""], ["深远海风电", "垂直媒体", "产业资讯", ""], ["仁烁光能", "公司官媒", "产业资讯", ""], ["国际储能技术与产业联盟", "协会机构", "行业研究", "https://www.cnesa.org/"], ["绿金", "垂直媒体", "产业资讯", ""], ["中咨研究", "咨询行研", "行业研究", ""], ["新智元", "垂直媒体", "产业资讯", ""], ["氢能技术前沿", "垂直媒体", "产业资讯", ""], ["地学前沿观察", "垂直媒体", "产业资讯", ""], ["焦耳时代", "垂直媒体", "产业资讯", ""], ["IEEE电气电子工程学会", "学术论文", "学术科研", "https://www.ieee.org/"], ["储能科学与技术", "学术论文", "学术科研", "http://www.esst.org.cn/"], ["REAI Lab", "垂直媒体", "产业资讯", ""], ["机工文献", "学术论文", "学术科研", "https://www.cmechina.net/"], ["物理储能", "学术论文", "学术科研", ""], ["DT洞见可持续", "垂直媒体", "产业资讯", ""], ["环球科学", "学术论文", "学术科研", "https://www.huanqiukexue.com/"], ["腾讯研究院", "咨询行研", "行业研究", "https://tisi.org/"], ["能源技术情报", "垂直媒体", "产业资讯", ""], ["集邦固态电池", "垂直媒体", "产业资讯", ""], ["世界先进制造技术论坛", "垂直媒体", "产业资讯", ""], ["CCUS国家地方联合工程研究中心", "咨询行研", "行业研究", ""], ["新能源技术与装备", "垂直媒体", "产业资讯", ""], ["双碳情报", "垂直媒体", "产业资讯", ""], ["晚点LatePost", "垂直媒体", "产业资讯", "https://www.latepost.com/"], ["催化视界", "垂直媒体", "产业资讯", ""], ["中粉固态电池", "垂直媒体", "产业资讯", ""], ["能源环境经济文献精读", "学术论文", "学术科研", ""], ["可控核聚变", "垂直媒体", "产业资讯", ""], ["工业节能环保技术", "垂直媒体", "产业资讯", ""], ["国际能源小数据", "垂直媒体", "产业资讯", ""], ["现代情报", "垂直媒体", "产业资讯", ""], ["SOFC-SOEC-氢能技术", "垂直媒体", "产业资讯", ""], ["源网荷储创研新视界", "垂直媒体", "产业资讯", ""], ["新华国研经济学研究院", "咨询行研", "行业研究", ""], ["国际能源研究中心", "咨询行研", "行业研究", ""], ["视知产业研究院", "咨询行研", "行业研究", ""], ["热泵在线", "垂直媒体", "产业资讯", ""], ["麻省理工科技评论APP", "垂直媒体", "产业资讯", "https://www.mittrchina.com/"], ["Gartner公司", "公司官媒", "产业资讯", "https://www.gartner.com/"], ["新能源情报局", "垂直媒体", "产业资讯", ""], ["化工碳达峰碳中和", "垂直媒体", "产业资讯", ""], ["数据与情报科学英文刊", "学术论文", "学术科研", ""], ["昆山协鑫光电", "公司官媒", "产业资讯", ""], ["地热能在线", "垂直媒体", "产业资讯", ""], ["中国可再生能源学会地热能专委会", "协会机构", "行业研究", "http://www.cnrec.org.cn/"], ["中国科学技术发展战略研究院", "咨询行研", "行业研究", ""], ["氢能云互联", "垂直媒体", "产业资讯", ""], ["未来城市数智评论", "垂直媒体", "产业资讯", ""], ["星源PlanetaryEnergy", "垂直媒体", "产业资讯", ""], ["能源环境经济与政策研究", "垂直媒体", "产业资讯", ""], ["未来智库", "咨询行研", "行业研究", "https://www.vzkoo.com/"], ["国家新材料产业资源共享", "协会机构", "行业研究", "http://www.sinomaterials.org/"], ["氢创空间", "垂直媒体", "产业资讯", ""], ["社科院工业经济研究所", "协会机构", "行业研究", "http://ie.cass.cn/"], ["世界科技研究与发展", "垂直媒体", "产业资讯", ""], ["VPP前沿观察", "垂直媒体", "产业资讯", ""], ["低碳节能环保技术", "垂直媒体", "产业资讯", ""], ["中国国际可再生能源署合作办公室", "垂直媒体", "产业资讯", ""], ["数据小魔方", "垂直媒体", "产业资讯", ""], ["CSSD气候变化工作委员会", "协会机构", "行业研究", ""], ["Chemical Reviews (ACS ASAP)", "学术论文", "学术科研", "https://pubs.acs.org/journal/chreay"], ["Nature Nanotechnology", "学术论文", "学术科研", "https://www.nature.com/nnano/"], ["Nature Energy", "学术论文", "学术科研", "https://www.nature.com/nenergy/"], ["Nature Communications", "学术论文", "学术科研", "https://www.nature.com/ncomms/"], ["Nature Sustainability", "学术论文", "学术科研", "https://www.nature.com/natsustain/"], ["Advanced Materials", "学术论文", "学术科研", "https://onlinelibrary.wiley.com/journal/15214095"], ["Nature Materials", "学术论文", "学术科研", "https://www.nature.com/nmat/"], ["Nature Chemical Engineering", "学术论文", "学术科研", "https://www.nature.com/natchemeng/"], ["Materials Today", "学术论文", "学术科研", "https://www.materialstoday.com/"], ["Chemical Society Reviews (RSC)", "学术论文", "学术科研", "https://www.rsc.org/journals-books-databases/find-an-journal/chemical-society-reviews/"], ["ACS Energy Letters (ASAP)", "学术论文", "学术科研", "https://pubs.acs.org/journal/aelccp"], ["Chem (Cell Press)", "学术论文", "学术科研", "https://www.cell.com/chem/home"], ["Nature", "学术论文", "学术科研", "https://www.nature.com/"], ["Nature Reviews Materials", "学术论文", "学术科研", "https://www.nature.com/natrevmats/"], ["National Science Review Advance Access", "学术论文", "学术科研", "https://academic.oup.com/nsr"], ["Nature Chemistry", "学术论文", "学术科研", "https://www.nature.com/nchem/"], ["Energy & Environmental Science (RSC)", "学术论文", "学术科研", "https://www.rsc.org/journals-books-databases/find-an-journal/energy-environmental-science/"], ["Advanced Energy Materials", "学术论文", "学术科研", "https://onlinelibrary.wiley.com/journal/16146840"], ["Advanced Science", "学术论文", "学术科研", "https://onlinelibrary.wiley.com/journal/21983844"], ["PNAS", "学术论文", "学术科研", "https://www.pnas.org/"], ["Joule (Cell Press)", "学术论文", "学术科研", "https://www.cell.com/joule/home"], ["Science Advances", "学术论文", "学术科研", "https://www.science.org/journal/sciadv"], ["Science", "学术论文", "学术科研", "https://www.science.org/"], ["JACS ASAP", "学术论文", "学术科研", "https://pubs.acs.org/journal/jacsat"], ["Nature Electronics", "学术论文", "学术科研", "https://www.nature.com/natelectron/"], ["Nature Reviews Clean Technology", "学术论文", "学术科研", "https://www.nature.com/natrevcleantech/"], ["One Earth (Cell Press)", "学术论文", "学术科研", "https://www.cell.com/one-earth/home"], ["Matter (Cell Press)", "学术论文", "学术科研", "https://www.cell.com/matter/home"], ["Applied Energy", "学术论文", "学术科研", "https://www.sciencedirect.com/journal/applied-energy"], ["Energy Policy", "学术论文", "学术科研", "https://www.sciencedirect.com/journal/energy-policy"], ["起点钠电", "垂直媒体", "产业资讯", ""], ["钙钛矿学习交流平台", "垂直媒体", "产业资讯", ""], ["electrive", "垂直媒体", "产业资讯", "https://www.electrive.com/"], ["Batteries International", "垂直媒体", "产业资讯", "https://www.batteriesinternational.com/"], ["Volta Foundation", "协会机构", "行业研究", "https://voltafoundation.org/"], ["batteries news", "垂直媒体", "产业资讯", "https://www.batteriesnews.com/"], ["Battery Tech Online", "垂直媒体", "产业资讯", "https://www.batterytechonline.com/"], ["Supply Chain Digital", "垂直媒体", "产业资讯", "https://supplychaindigital.com/"], ["Battery Council International", "协会机构", "行业研究", "https://batterycouncil.org/"], ["Electrek", "垂直媒体", "产业资讯", "https://electrek.co/"], ["pv magazine", "垂直媒体", "产业资讯", "https://www.pv-magazine.com/"], ["interesting engineering", "垂直媒体", "产业资讯", "https://interestingengineering.com/"], ["scitechdaily", "垂直媒体", "产业资讯", "https://scitechdaily.com/"], ["perovskite-info", "垂直媒体", "产业资讯", "https://www.perovskite-info.com/"], ["索比光伏", "垂直媒体", "产业资讯", "https://www.solarbe.com/"], ["风电世界", "垂直媒体", "产业资讯", "https://windchinabbs.com/"], ["4C Offshore", "垂直媒体", "产业资讯", "https://www.4coffshore.com/"], ["全球风电网", "垂直媒体", "产业资讯", "http://www.windpower.org.cn/"], ["新能源网", "垂直媒体", "产业资讯", "http://www.china-nengyuan.com/"], ["the information", "垂直媒体", "产业资讯", "https://www.theinformation.com/"], ["MIT Technology Review", "垂直媒体", "产业资讯", "https://www.technologyreview.com/"], ["Informationsdienst Wissenschaft-idw", "垂直媒体", "产业资讯", "https://idw-online.de/"], ["ESS News", "垂直媒体", "产业资讯", "https://essnews.com/"], ["Batteries International News", "垂直媒体", "产业资讯", "https://www.batteriesinternational.com/"], ["pv magazine C&I PV", "垂直媒体", "产业资讯", "https://www.pv-magazine.com/"], ["Ammonia Energy Association", "协会机构", "行业研究", "https://www.ammoniaenergy.org/"], ["H2 View", "垂直媒体", "产业资讯", "https://www.h2-view.com/"], ["Hydrogen Tech World", "垂直媒体", "产业资讯", "https://hydrogentechworld.com/"], ["BloombergNEF Press", "咨询行研", "行业研究", "https://about.bnef.com/"], ["MIT Technology Review Climate", "垂直媒体", "产业资讯", "https://www.technologyreview.com/topic/climate-change/"], ["网易知光谷", "综合媒体", "产业资讯", "https://tech.163.com/"], ["中国核电信息网-国内", "垂直媒体", "产业资讯", "http://www.chinanuclear.cn/"], ["中国核电信息网-国际", "垂直媒体", "产业资讯", "http://www.chinanuclear.cn/"], ["中国电力新闻网-新能源", "综合媒体", "产业资讯", "http://www.cpnn.com.cn/"], ["中国电力新闻网-科技", "综合媒体", "产业资讯", "http://www.cpnn.com.cn/"], ["科学网新闻", "综合媒体", "产业资讯", "https://news.sciencenet.cn/"], ["新华网科技", "综合媒体", "产业资讯", "http://www.xinhuanet.com/tech/"], ["国际太阳能光伏网", "垂直媒体", "产业资讯", "https://www.solaris-china.com/"], ["Renewables Now", "垂直媒体", "产业资讯", "https://renewablesnow.com/"], ["索比光伏-综合新闻", "垂直媒体", "产业资讯", "https://www.solarbe.com/"], ["中国新能源网-新闻", "垂直媒体", "产业资讯", "http://www.china-nengyuan.com/"], ["IT之家", "综合媒体", "产业资讯", "https://www.ithome.com/"]];
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
async function apiFetch(url, opts={}){
  const res = await fetch(url, {...opts, headers:{...authHeaders(),...(opts.headers||{})}});
  if(res.status===401){
    // Token expired or invalid — clear and redirect to login
    localStorage.removeItem("auth_token");
    localStorage.removeItem("access_token");
    location.href="login.html";
    return res;
  }
  return res;
}
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
function intelView(){return `<section class="panel content-panel"><div class="eyebrow">情报总表</div><h1 class="section-title">按关键词、领域、信息来源检索情报。</h1><form class="filter-bar" id="intelFilter"><input id="intelQ" name="q" placeholder="关键词搜索"/><select id="intelDomain"><option value="">全部细分领域</option></select><select id="intelSource"><option value="">全部信息来源</option></select><button class="secondary-btn" type="submit">检索</button></form><div id="intelTotalNote" style="font-size:12px;color:#667085;margin-bottom:8px"></div><div class="table-card"><table><thead><tr><th>标题</th><th>领域</th><th>信息来源</th><th>可信度</th><th>审核</th><th>关键指标</th></tr></thead><tbody id="intelRows"><tr><td colspan="6">正在加载情报…</td></tr></tbody></table></div></section>`;}
function dashboardView(){return `<section class="panel content-panel"><div class="eyebrow">技术仪表盘总表</div><h1 class="section-title">检索技术对象，查看适用场景、核心指标和相关情报入口。</h1><form class="dashboard-search" id="dashboardFilter"><input id="dashboardQ" placeholder="搜索技术、行业或指标，例如 SOFC、寿命、LCOS"/><button class="secondary-btn" type="submit">检索</button></form><div class="dashboard-grid" id="dashboardRows"><div class="status-note">正在加载仪表盘…</div></div></section>`;}
function sourcesView(){
  const state=parseHash();
  const tab=state.params.get('srctab')||'产业资讯';
  const tabs=['产业资讯','学术科研','行业研究'];
  // Group SOURCE_LIST by info_type, then by source_type within
  const filtered=SOURCE_LIST.filter(s=>s[2]===tab);
  const groups={};
  filtered.forEach(s=>{const t=s[1];if(!groups[t])groups[t]=[];groups[t].push(s);});
  const typeOrder=['垂直媒体','综合媒体','学术论文','协会机构','咨询行研','公司官媒'];
  const typeColors={'垂直媒体':'#dbeafe','综合媒体':'#e0f2fe','学术论文':'#fef3c7','协会机构':'#dcfce7','咨询行研':'#fce7f3','公司官媒':'#ede9fe'};
  const typeBorder={'垂直媒体':'#93c5fd','综合媒体':'#7dd3fc','学术论文':'#fcd34d','协会机构':'#86efac','咨询行研':'#f9a8d4','公司官媒':'#c4b5fd'};
  let groupsHtml='';
  typeOrder.filter(t=>groups[t]).forEach(t=>{
    const items=groups[t];
    const bg=typeColors[t]||'#f1f5f9';
    const border=typeBorder[t]||'#cbd5e1';
    groupsHtml+=`<div style="margin-bottom:20px">
      <h3 style="font-size:13px;color:#475467;margin:0 0 10px;font-weight:650;display:flex;align-items:center;gap:8px">
        <span style="background:${bg};border:1px solid ${border};border-radius:999px;padding:3px 10px;font-size:12px">${t}</span>
        <span style="color:#94a3b8;font-size:12px">${items.length} 个</span>
      </h3>
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        ${items.map(s=>s[3]?`<a href="${escapeHtml(s[3])}" target="_blank" rel="noopener" style="background:white;border:1px solid #e5eaf2;border-radius:10px;padding:7px 12px;font-size:13px;color:#0e7490;box-shadow:0 1px 3px rgba(0,0,0,.04);text-decoration:none;display:inline-flex;align-items:center;gap:4px">${escapeHtml(s[0])} <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M1 9L9 1M9 1H3M9 1V7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></a>`:`<span style="background:white;border:1px solid #e5eaf2;border-radius:10px;padding:7px 12px;font-size:13px;color:#64748b;box-shadow:0 1px 3px rgba(0,0,0,.04)">${escapeHtml(s[0])}</span>`).join('')}
      </div>
    </div>`;
  });
  const tabsHtml=tabs.map(t=>`<button class="bookmark-tab ${tab===t?'active':''}" data-src-tab="${t}">${t} <span style="opacity:.6;font-size:11px">${SOURCE_LIST.filter(s=>s[2]===t).length}</span></button>`).join('');
  return `<section class="panel content-panel"><div class="eyebrow">信源</div><h1 class="section-title">按信息类型浏览 ${SOURCE_LIST.length} 个信息源，持续追踪产业动态、学术前沿和行业研究。</h1><div class="bookmark-tabs" style="margin-bottom:20px">${tabsHtml}</div><div id="sourceGroupsContent">${groupsHtml}</div></section>`;
}
function mapView(){const state=parseHash();const group=state.params.get('group')||'zero-carbon';const tabs=[["zero-carbon","零碳产业"],["ai-intelligent","AI与智能科技"],["general-tech","通用技术"]];const titleMap={"zero-carbon":"零碳产业","ai-intelligent":"AI与智能科技","general-tech":"通用技术"};return `<section class="panel content-panel map-content-panel"><div class="map-head"><div><div class="eyebrow">行业图景</div><h1 class="section-title">XMind 三页签行业树，叶子节点挂接情报 / 专刊 / 仪表盘。</h1></div><div class="map-tools"><input id="mapSearch" value="${escapeHtml(mapSearchDraft)}" placeholder="搜索节点"/><button class="secondary-btn" id="mapExpandAll" type="button">展开全部</button><button class="secondary-btn" id="mapCollapse" type="button">折叠到二级</button></div></div><div class="map-legend"><span><i class="legend-dot intel">情</i>相关情报</span><span><i class="legend-dot issue">刊</i>专刊</span><span><i class="legend-dot dashboard">盘</i>行业仪表盘</span><span><i class="legend-dot missing">!</i>缺失标红</span></div><div class="bookmark-tabs">${tabs.map(([key,label])=>`<button class="bookmark-tab ${group===key?'active':''}" data-map-group="${key}">${label}</button>`).join('')}</div><div class="map-shell"><header class="map-summary"><strong>${titleMap[group]||'零碳产业'}</strong><span id="industryMapMeta">正在加载图景…</span></header><div class="industry-tree" id="industryTree"><div class="status-note">正在加载图景…</div></div><div class="map-x-scroll" id="mapXScroll"><div class="map-x-thumb" id="mapXThumb"></div></div></div></section>`;}
function knowledgeView(){return `<section class="panel content-panel"><div class="eyebrow">知识图谱</div><h1 class="section-title">知识图谱用于承载行业节点、情报、专刊、仪表盘和长期记忆之间的关系。当前先保留入口与结构接口。</h1><div class="knowledge-placeholder"><div class="status-note">知识图谱结构接口已预留，后续接入图谱数据后在这里呈现可交互关系网络。</div></div></section>`;}
function bindEvents(){document.querySelectorAll("[data-route]").forEach(btn=>btn.addEventListener("click",()=>setRoute(btn.dataset.route)));document.querySelectorAll("[data-map-group]").forEach(btn=>btn.addEventListener("click",()=>{const p=new URLSearchParams(parseHash().params.toString());p.set('group',btn.dataset.mapGroup);setRoute('map',p);}));const logout=document.getElementById("logoutBtn");const changePwd=document.getElementById("changePwdBtn");if(changePwd)changePwd.addEventListener("click",()=>{if(window.Auth&&Auth.showChangePassword)Auth.showChangePassword();});if(logout)logout.addEventListener("click",()=>{if(window.Auth&&Auth.logout)Auth.logout();else location.href="login.html";});const ask=document.getElementById("askBtn");const input=document.getElementById("queryInput");if(input){input.value=homeDraft;if(!input.dataset.bound){input.addEventListener('input',()=>{homeDraft=input.value;localStorage.setItem('home_query_draft',homeDraft);});input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submitQuery();}});input.dataset.bound='1';}}if(ask)ask.addEventListener("click",submitQuery);const intelFilter=document.getElementById("intelFilter");if(intelFilter)intelFilter.addEventListener("submit",e=>{e.preventDefault();const p=new URLSearchParams();const qv=document.getElementById('intelQ')?.value;const dv=document.getElementById('intelDomain')?.value;const sv=document.getElementById('intelSource')?.value;if(qv)p.set('q',qv);if(dv)p.set('domain',dv);if(sv)p.set('source_type',sv);setRoute('intel',p);});const dashboardFilter=document.getElementById("dashboardFilter");if(dashboardFilter)dashboardFilter.addEventListener("submit",e=>{e.preventDefault();loadDashboards();});document.querySelectorAll("[data-src-tab]").forEach(btn=>btn.addEventListener("click",()=>{const p=new URLSearchParams(parseHash().params.toString());p.set('srctab',btn.dataset.srcTab);setRoute('sources',p);}));}
async function loadAssistantStatus(){const answer=document.getElementById("answer");if(!answer)return;try{const res=await apiFetch('/api/assistant/status');const data=await res.json();const files=(data.health||{}).markdown_files;if(data.status==='ok'){answer.insertAdjacentHTML('beforeend',`<div class="assistant-msg"><strong>只读知识库</strong><p>已连接知识库，共 ${Number.isFinite(files)?files:'若干'} 个 Markdown 文档可供检索。</p></div>`);}}catch(err){answer.insertAdjacentHTML('beforeend',`<div class="assistant-msg"><strong>只读知识库</strong><p>知识库状态检查失败，仍可提交问题。</p></div>`);}}
function applyIntelParams(params){const qEl=document.getElementById('intelQ');if(qEl&&params.has('q'))qEl.value=params.get('q');const domEl=document.getElementById('intelDomain');if(domEl&&params.has('leaf'))domEl.value=params.get('leaf');const srcEl=document.getElementById('intelSource');if(srcEl&&params.has('source_type'))srcEl.value=params.get('source_type');}
async function loadIntelMeta(){
  const domainSel=document.getElementById('intelDomain');
  const sourceSel=document.getElementById('intelSource');
  if(!domainSel||domainSel.options.length>1)return; // already populated this render cycle
  try{
    const res=await fetch('/api/delivery-intel/meta',{headers:authHeaders()});
    if(!res.ok)return;
    const meta=await res.json();
    // leaf_titles — most frequent first
    if(meta.leaf_titles){
      meta.leaf_titles.forEach(d=>{
        const o=document.createElement('option');
        o.value=d.key;
        o.textContent=`${d.label} (${d.count})`;
        domainSel.appendChild(o);
      });
    }
    if(sourceSel&&meta.source_types){
      sourceSel.innerHTML='<option value="">全部信息来源</option>';
      meta.source_types.forEach(s=>{
        const o=document.createElement('option');
        o.value=s.key;o.textContent=s.label;sourceSel.appendChild(o);
      });
    }
  }catch(e){}
}
async function loadIntel(params=new URLSearchParams()){
  // Step 1: render skeleton first so DOM exists
  // Step 2: populate dropdowns from meta (checks DOM state, re-runs if fresh)
  await loadIntelMeta();
  // Step 3: restore selected values AFTER meta populated options
  applyIntelParams(params);
  const tbody=document.getElementById("intelRows");
  const note=document.getElementById("intelTotalNote");
  if(!tbody)return;
  tbody.innerHTML='<tr><td colspan="6">正在加载情报…</td></tr>';
  try{
    // leaf comes from URL param OR from the domain select (which now holds leaf_title values)
    const leafFromUrl=params.get('leaf')||'';
    const leafFromSelect=document.getElementById('intelDomain')?.value||'';
    const leaf=leafFromUrl||leafFromSelect;
    const q=encodeURIComponent(document.getElementById('intelQ')?.value||params.get('q')||'');
    const sourceType=encodeURIComponent(document.getElementById('intelSource')?.value||params.get('source_type')||'');
    const parts=['limit=200'];
    if(leaf)parts.push(`leaf=${encodeURIComponent(leaf)}`);
    if(q)parts.push(`q=${q}`);
    if(sourceType)parts.push(`source_type=${sourceType}`);
    const url=`/api/delivery-intel?${parts.join('&')}`;
    const res=await apiFetch(url);
    const data=await res.json();
    const rows=data.items||[];
    const filterDesc=leaf?`叶子节点：${leaf}`:(q||domain||sourceType)?'已筛选':'全部';
    if(note)note.textContent=`共 ${data.total||rows.length} 条 · ${filterDesc} · 显示前 ${rows.length} 条`;
    tbody.innerHTML=rows.length?rows.map(item=>`<tr class="intel-row" data-id="${escapeHtml(item.id)}" style="cursor:pointer"><td>${escapeHtml(item.title||'未命名情报')}</td><td title="${escapeHtml(item.taxonomy_path||'')}"><span style="font-size:11px;color:#94a3b8">${escapeHtml(item.domain_label||'')} › </span>${escapeHtml(item.leaf_title||'未分类')}</td><td>${escapeHtml(item.source_type_label||item.source_type||'')}</td><td>${escapeHtml(item.confidence||'')}</td><td>${item.need_human_review?'待审':'OK'}</td><td>${escapeHtml(item.key_metric?`${item.key_metric}: ${item.value_raw}${item.unit}`:'—')}</td></tr>`).join(''):'<tr><td colspan="6">没有符合条件的情报</td></tr>';
    tbody.querySelectorAll('.intel-row').forEach(tr=>tr.addEventListener('click',()=>showIntelDetail(tr.dataset.id)));
  }catch(err){tbody.innerHTML='<tr><td colspan="6">情报加载失败，请稍后重试</td></tr>';}
}
async function loadDashboards(){const root=document.getElementById('dashboardRows');if(!root)return;root.innerHTML='<div class="status-note">正在加载仪表盘…</div>';const q=encodeURIComponent(document.getElementById('dashboardQ')?.value||parseHash().params.get('q')||'');try{const res=await apiFetch(`/api/dashboards${q?'?q='+q:''}`);const data=await res.json();root.innerHTML=data.items.length?data.items.map(item=>dashboardCard(item)).join(''):'<div class="status-note">没有符合条件的仪表盘</div>';}catch(err){root.innerHTML='<div class="status-note">仪表盘加载失败，请稍后重试</div>';}}
function mapAssetText(value){return String(value||'').toLowerCase().replace(/\s+/g,'');}
function mapNodeTerms(node){const roots=new Set(['零碳产业','AI与智能科技','通用技术']);return Array.from(new Set([node.title,...(node.path||[])].map(v=>String(v||'').trim()).filter(v=>v.length>=2&&!roots.has(v))));}
function infoMapText(item){return mapAssetText([item.title,item.leaf_title,item.taxonomy_path,item.source_name,item.key_metric].join(' '));}
function dashboardMapText(item){return mapAssetText([item.id,item.name,item.scope,item.query,item.domain,(item.metrics||[]).join(' ')].join(' '));}
function mapMatchesNode(node, rows, textGetter){const terms=mapNodeTerms(node).map(mapAssetText).filter(Boolean);return rows.filter(row=>{const text=textGetter(row);return terms.some(term=>text.includes(term));});}
async function loadMapAssets(){const [intelRes,dashboards]=await Promise.allSettled([apiFetch('/api/delivery-intel?limit=5000').then(r=>r.ok?r.json():{items:[]}),apiFetch('/api/dashboards').then(r=>r.ok?r.json():{items:[]})]);const intelItems=intelRes.status==='fulfilled'?(intelRes.value.items||[]):[]; return {infos:intelItems,dashboards:dashboards.status==='fulfilled'&&Array.isArray(dashboards.value.items)?dashboards.value.items:[]};}
function decorateIndustryAssets(node,assets){const children=node.children||[];if(!children.length){const intel=mapMatchesNode(node,assets.infos,infoMapText);const dashboards=mapMatchesNode(node,assets.dashboards,dashboardMapText);const dashboardQuery=dashboards[0]?.query||dashboards[0]?.id||node.title;node.assets={intel:{active:intel.length>0,count:intel.length,href:`#intel?leaf=${encodeURIComponent(node.title)}&from_map=1`},special_issue:{active:false,count:0,href:''},dashboard:{active:dashboards.length>0,count:dashboards.length,href:`#dashboard?q=${encodeURIComponent(dashboardQuery)}`}};}children.forEach(child=>decorateIndustryAssets(child,assets));return node;}
function countLeaves(node){const children=node.children||[];return children.length?children.reduce((sum,child)=>sum+countLeaves(child),0):1;}
function leafDots(node){const assets=node.assets||{};const fallbackCoverage=node.coverage||{};const fallbackLinks=node.links||{};const items=[['intel','情','相关情报'],['special_issue','刊','相关专刊'],['dashboard','盘','相关行业仪表盘']];return `<div class="leaf-tags">${items.map(([key,label,title])=>{const asset=assets[key]||{active:!!fallbackCoverage[key],href:fallbackLinks[key]||'#',count:0};const active=!!asset.active;const href=asset.href||'#';const status=active?`${title}：${asset.count||1}项`:`${title}：暂无`;return active?`<a class="leaf-tag active" data-link-type="${key}" href="${href}" title="${status}"><span>${label}</span></a>`:`<span class="leaf-tag missing" data-link-type="${key}" title="${status}" style="background:#dc2626;border-color:#b91c1c;color:#fff;"><span>${label}</span></span>`;}).join('')}</div>`;}
function mapNodeOwnMatch(node){const q=mapAssetText(mapSearchDraft);if(!q)return false;return mapAssetText([node.title,...(node.path||[])].join(' ')).includes(q);}
function mapNodeVisible(node){const q=mapAssetText(mapSearchDraft);if(!q)return true;if(mapNodeOwnMatch(node))return true;return (node.children||[]).some(mapNodeVisible);}
function industryNode(node){if(!mapNodeVisible(node))return '';const children=node.children||[];const leaf=children.length===0;const open=mapSearchDraft||node.depth<mapOpenDepth;const childHtml=children.map(industryNode).join('');return `<li class="mind-node depth-${node.depth} ${leaf?'leaf':''} ${mapNodeOwnMatch(node)?'match':''}"><details ${open?'open':''}><summary class="mind-card"><span>${escapeHtml(node.title)}</span>${leaf?'<em>具体行业</em>':`<em>${children.length} 个下级节点</em>`}</summary>${leaf?leafDots(node):childHtml?`<ul>${childHtml}</ul>`:''}</details></li>`;}
async function loadIndustryMap(){const root=document.getElementById('industryTree');const meta=document.getElementById('industryMapMeta');if(!root)return;const group=parseHash().params.get('group')||'zero-carbon';const titleMap={"zero-carbon":"零碳产业","ai-intelligent":"AI与智能科技","general-tech":"通用技术"};if(meta)meta.textContent=`${titleMap[group]||'零碳产业'}：正在加载 XMind 数据…`;try{const [mapRes,assets]=await Promise.all([apiFetch(`/api/industry-map?group=${encodeURIComponent(group==='zero-carbon'?'零碳产业':group==='ai-intelligent'?'AI与智能科技':'通用技术')}`),loadMapAssets()]);const data=await mapRes.json();const sheet=data.sheet||data.root||data;const rootNode=decorateIndustryAssets(sheet.root||sheet,assets);const sheetTitle=sheet.title||titleMap[group]||'行业图景';if(meta)meta.textContent=`${sheetTitle}：共 ${sheet.node_count||countNodes(rootNode)} 个节点，${countLeaves(rootNode)} 个叶子，最大层级 ${sheet.max_depth||maxDepth(rootNode)}`;root.innerHTML=`<div class="mindmap-canvas"><ul class="mindmap-root">${industryNode(rootNode)}</ul></div>`;requestAnimationFrame(initMapHorizontalScroll);}catch(err){root.innerHTML='<div class="status-note">图景加载失败，请检查 XMind 解析数据。</div>';if(meta)meta.textContent='图景加载失败';}}
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
    const res=await apiFetch(`/api/delivery-intel/${encodeURIComponent(id)}`);
    if(!res.ok){body.innerHTML='<div style="color:#dc2626">加载失败</div>';return;}
    const d=await res.json();
    body.innerHTML=`
<h2 style="font-size:20px;font-weight:750;margin:0 0 12px;line-height:1.3">${escapeHtml(d.title)}</h2>
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px">
  ${d.taxonomy_path?`<span style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:999px;padding:5px 10px;font-size:12px;color:#334155" title="完整分类路径">${escapeHtml(d.taxonomy_path)}</span>`:''}
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
