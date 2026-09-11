const routes = {
  home: { label: "门户", title: "技术边界门户" },
  breadth: { label: "广度追踪", title: "广度追踪" },
  dashboard: { label: "深度调研", title: "深度调研" },
  map: { label: "行业图景", title: "行业图景" },
  users: { label: "用户管理", title: "用户管理" },
  library: { label: "资料库", title: "资料库" }
};
const navItems = [["home","HOME"],["breadth","BRD"],["dashboard","DDY"],["map","MAP"],["library","LIB"],["users","USR"]];
let currentUser = null;  // {username, display_name, role} filled by loadCurrentUser()
const sourceCards = [];

// ── Lightweight Markdown → HTML renderer for dashboard detail ──
function mdToHtml(md){
  if(!md) return '';
  let html = md;
  // Code blocks (```...```)
  html = html.replace(/```[\s\S]*?```/g, m => `<pre class="md-pre">${m.replace(/```\w*\n?/g,'').replace(/</g,'&lt;')}</pre>`);
  // Tables
  html = html.replace(/((?:^\|.*\n)+)/gm, (m) => {
    const lines = m.trim().split('\n');
    if (lines.length < 2) return m;
    const headers = lines[0].split('|').slice(1, -1).map(h => h.trim());
    const body = lines.slice(2).map(line => {
      const cells = line.split('|').slice(1, -1).map(c => c.trim());
      return `<tr>${cells.map(c => `<td>${inlineMd(c)}</td>`).join('')}</tr>`;
    }).join('');
    return `<table class="md-table"><thead><tr>${headers.map(h => `<th>${inlineMd(h)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>`;
  });
  // Split into blocks for block-level processing
  const blocks = html.split(/\n\n+/);
  return blocks.map(block => {
    block = block.trim();
    if (!block) return '';
    if (block.startsWith('<')) return block; // Already HTML (table/pre)
    // Headers
    const h = block.match(/^(#{1,4})\s+(.+)$/m);
    if (h && block.split('\n').length === 1) {
      const level = h[1].length;
      return `<h${level+2} class="md-h">${inlineMd(h[2])}</h${level+2}>`;
    }
    // Blockquote
    if (block.startsWith('>')) {
      return `<blockquote class="md-quote">${block.split('\n').map(l => inlineMd(l.replace(/^>\s?/,''))).join('<br>')}</blockquote>`;
    }
    // Bullet list
    if (block.match(/^[-•]\s/m)) {
      const items = block.split('\n').filter(l => l.match(/^[-•]\s/)).map(l => `<li>${inlineMd(l.replace(/^[-•]\s*/,''))}</li>`).join('');
      return `<ul class="md-ul">${items}</ul>`;
    }
    // Numbered list
    if (block.match(/^\d+\.\s/m)) {
      const items = block.split('\n').filter(l => l.match(/^\d+\.\s/)).map(l => `<li>${inlineMd(l.replace(/^\d+\.\s*/,''))}</li>`).join('');
      return `<ol class="md-ol">${items}</ol>`;
    }
    // Paragraph
    return `<p class="md-p">${inlineMd(block)}</p>`;
  }).join('\n');
}
function inlineMd(text){
  if(!text) return '';
  let t = text;
  // Bold + italic
  t = t.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Inline code
  t = t.replace(/`([^`]+)`/g, '<code class="md-code">$1</code>');
  // Links
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Escape remaining < > that aren't part of tags we created
  // (Do this minimally to avoid breaking existing HTML)
  return t;
}
const SOURCE_LIST = [["机器之心", "垂直媒体", "产业资讯", "https://www.jiqizhixin.com/"], ["能源学人", "学术论文", "学术科研", ""], ["战略前沿技术", "垂直媒体", "产业资讯", ""], ["核闻天下", "垂直媒体", "产业资讯", ""], ["先进能源科技战略情报研究中心", "咨询行研", "行业研究", ""], ["DeepTech深科技", "垂直媒体", "产业资讯", "https://www.mittrchina.com/"], ["环球零碳", "垂直媒体", "产业资讯", ""], ["南方能源观察", "垂直媒体", "产业资讯", ""], ["光子盒", "垂直媒体", "产业资讯", ""], ["矿业界", "垂直媒体", "产业资讯", ""], ["ESPLaza长时储能网", "垂直媒体", "产业资讯", ""], ["ESPLaza储热网", "垂直媒体", "产业资讯", ""], ["钙钛矿工厂", "垂直媒体", "产业资讯", ""], ["深远海风电", "垂直媒体", "产业资讯", ""], ["仁烁光能", "公司官媒", "产业资讯", ""], ["国际储能技术与产业联盟", "协会机构", "行业研究", "https://www.cnesa.org/"], ["绿金", "垂直媒体", "产业资讯", ""], ["中咨研究", "咨询行研", "行业研究", ""], ["新智元", "垂直媒体", "产业资讯", ""], ["氢能技术前沿", "垂直媒体", "产业资讯", ""], ["地学前沿观察", "垂直媒体", "产业资讯", ""], ["焦耳时代", "垂直媒体", "产业资讯", ""], ["IEEE电气电子工程学会", "学术论文", "学术科研", "https://www.ieee.org/"], ["储能科学与技术", "学术论文", "学术科研", "http://www.esst.org.cn/"], ["REAI Lab", "垂直媒体", "产业资讯", ""], ["机工文献", "学术论文", "学术科研", "https://www.cmechina.net/"], ["物理储能", "学术论文", "学术科研", ""], ["DT洞见可持续", "垂直媒体", "产业资讯", ""], ["环球科学", "学术论文", "学术科研", "https://www.huanqiukexue.com/"], ["腾讯研究院", "咨询行研", "行业研究", "https://tisi.org/"], ["能源技术情报", "垂直媒体", "产业资讯", ""], ["集邦固态电池", "垂直媒体", "产业资讯", ""], ["世界先进制造技术论坛", "垂直媒体", "产业资讯", ""], ["CCUS国家地方联合工程研究中心", "咨询行研", "行业研究", ""], ["新能源技术与装备", "垂直媒体", "产业资讯", ""], ["双碳情报", "垂直媒体", "产业资讯", ""], ["晚点LatePost", "垂直媒体", "产业资讯", "https://www.latepost.com/"], ["催化视界", "垂直媒体", "产业资讯", ""], ["中粉固态电池", "垂直媒体", "产业资讯", ""], ["能源环境经济文献精读", "学术论文", "学术科研", ""], ["可控核聚变", "垂直媒体", "产业资讯", ""], ["工业节能环保技术", "垂直媒体", "产业资讯", ""], ["国际能源小数据", "垂直媒体", "产业资讯", ""], ["现代情报", "垂直媒体", "产业资讯", ""], ["SOFC-SOEC-氢能技术", "垂直媒体", "产业资讯", ""], ["源网荷储创研新视界", "垂直媒体", "产业资讯", ""], ["新华国研经济学研究院", "咨询行研", "行业研究", ""], ["国际能源研究中心", "咨询行研", "行业研究", ""], ["视知产业研究院", "咨询行研", "行业研究", ""], ["热泵在线", "垂直媒体", "产业资讯", ""], ["麻省理工科技评论APP", "垂直媒体", "产业资讯", "https://www.mittrchina.com/"], ["Gartner公司", "公司官媒", "产业资讯", "https://www.gartner.com/"], ["新能源情报局", "垂直媒体", "产业资讯", ""], ["化工碳达峰碳中和", "垂直媒体", "产业资讯", ""], ["数据与情报科学英文刊", "学术论文", "学术科研", ""], ["昆山协鑫光电", "公司官媒", "产业资讯", ""], ["地热能在线", "垂直媒体", "产业资讯", ""], ["中国可再生能源学会地热能专委会", "协会机构", "行业研究", "http://www.cnrec.org.cn/"], ["中国科学技术发展战略研究院", "咨询行研", "行业研究", ""], ["氢能云互联", "垂直媒体", "产业资讯", ""], ["未来城市数智评论", "垂直媒体", "产业资讯", ""], ["星源PlanetaryEnergy", "垂直媒体", "产业资讯", ""], ["能源环境经济与政策研究", "垂直媒体", "产业资讯", ""], ["未来智库", "咨询行研", "行业研究", "https://www.vzkoo.com/"], ["国家新材料产业资源共享", "协会机构", "行业研究", "http://www.sinomaterials.org/"], ["氢创空间", "垂直媒体", "产业资讯", ""], ["社科院工业经济研究所", "协会机构", "行业研究", "http://ie.cass.cn/"], ["世界科技研究与发展", "垂直媒体", "产业资讯", ""], ["VPP前沿观察", "垂直媒体", "产业资讯", ""], ["低碳节能环保技术", "垂直媒体", "产业资讯", ""], ["中国国际可再生能源署合作办公室", "垂直媒体", "产业资讯", ""], ["数据小魔方", "垂直媒体", "产业资讯", ""], ["CSSD气候变化工作委员会", "协会机构", "行业研究", ""], ["Chemical Reviews (ACS ASAP)", "学术论文", "学术科研", "https://pubs.acs.org/journal/chreay"], ["Nature Nanotechnology", "学术论文", "学术科研", "https://www.nature.com/nnano/"], ["Nature Energy", "学术论文", "学术科研", "https://www.nature.com/nenergy/"], ["Nature Communications", "学术论文", "学术科研", "https://www.nature.com/ncomms/"], ["Nature Sustainability", "学术论文", "学术科研", "https://www.nature.com/natsustain/"], ["Advanced Materials", "学术论文", "学术科研", "https://onlinelibrary.wiley.com/journal/15214095"], ["Nature Materials", "学术论文", "学术科研", "https://www.nature.com/nmat/"], ["Nature Chemical Engineering", "学术论文", "学术科研", "https://www.nature.com/natchemeng/"], ["Materials Today", "学术论文", "学术科研", "https://www.materialstoday.com/"], ["Chemical Society Reviews (RSC)", "学术论文", "学术科研", "https://www.rsc.org/journals-books-databases/find-an-journal/chemical-society-reviews/"], ["ACS Energy Letters (ASAP)", "学术论文", "学术科研", "https://pubs.acs.org/journal/aelccp"], ["Chem (Cell Press)", "学术论文", "学术科研", "https://www.cell.com/chem/home"], ["Nature", "学术论文", "学术科研", "https://www.nature.com/"], ["Nature Reviews Materials", "学术论文", "学术科研", "https://www.nature.com/natrevmats/"], ["National Science Review Advance Access", "学术论文", "学术科研", "https://academic.oup.com/nsr"], ["Nature Chemistry", "学术论文", "学术科研", "https://www.nature.com/nchem/"], ["Energy & Environmental Science (RSC)", "学术论文", "学术科研", "https://www.rsc.org/journals-books-databases/find-an-journal/energy-environmental-science/"], ["Advanced Energy Materials", "学术论文", "学术科研", "https://onlinelibrary.wiley.com/journal/16146840"], ["Advanced Science", "学术论文", "学术科研", "https://onlinelibrary.wiley.com/journal/21983844"], ["PNAS", "学术论文", "学术科研", "https://www.pnas.org/"], ["Joule (Cell Press)", "学术论文", "学术科研", "https://www.cell.com/joule/home"], ["Science Advances", "学术论文", "学术科研", "https://www.science.org/journal/sciadv"], ["Science", "学术论文", "学术科研", "https://www.science.org/"], ["JACS ASAP", "学术论文", "学术科研", "https://pubs.acs.org/journal/jacsat"], ["Nature Electronics", "学术论文", "学术科研", "https://www.nature.com/natelectron/"], ["Nature Reviews Clean Technology", "学术论文", "学术科研", "https://www.nature.com/natrevcleantech/"], ["One Earth (Cell Press)", "学术论文", "学术科研", "https://www.cell.com/one-earth/home"], ["Matter (Cell Press)", "学术论文", "学术科研", "https://www.cell.com/matter/home"], ["Applied Energy", "学术论文", "学术科研", "https://www.sciencedirect.com/journal/applied-energy"], ["Energy Policy", "学术论文", "学术科研", "https://www.sciencedirect.com/journal/energy-policy"], ["起点钠电", "垂直媒体", "产业资讯", ""], ["钙钛矿学习交流平台", "垂直媒体", "产业资讯", ""], ["electrive", "垂直媒体", "产业资讯", "https://www.electrive.com/"], ["Batteries International", "垂直媒体", "产业资讯", "https://www.batteriesinternational.com/"], ["Volta Foundation", "协会机构", "行业研究", "https://voltafoundation.org/"], ["batteries news", "垂直媒体", "产业资讯", "https://www.batteriesnews.com/"], ["Battery Tech Online", "垂直媒体", "产业资讯", "https://www.batterytechonline.com/"], ["Supply Chain Digital", "垂直媒体", "产业资讯", "https://supplychaindigital.com/"], ["Battery Council International", "协会机构", "行业研究", "https://batterycouncil.org/"], ["Electrek", "垂直媒体", "产业资讯", "https://electrek.co/"], ["pv magazine", "垂直媒体", "产业资讯", "https://www.pv-magazine.com/"], ["interesting engineering", "垂直媒体", "产业资讯", "https://interestingengineering.com/"], ["scitechdaily", "垂直媒体", "产业资讯", "https://scitechdaily.com/"], ["perovskite-info", "垂直媒体", "产业资讯", "https://www.perovskite-info.com/"], ["索比光伏", "垂直媒体", "产业资讯", "https://www.solarbe.com/"], ["风电世界", "垂直媒体", "产业资讯", "https://windchinabbs.com/"], ["4C Offshore", "垂直媒体", "产业资讯", "https://www.4coffshore.com/"], ["全球风电网", "垂直媒体", "产业资讯", "http://www.windpower.org.cn/"], ["新能源网", "垂直媒体", "产业资讯", "http://www.china-nengyuan.com/"], ["the information", "垂直媒体", "产业资讯", "https://www.theinformation.com/"], ["MIT Technology Review", "垂直媒体", "产业资讯", "https://www.technologyreview.com/"], ["Informationsdienst Wissenschaft-idw", "垂直媒体", "产业资讯", "https://idw-online.de/"], ["ESS News", "垂直媒体", "产业资讯", "https://essnews.com/"], ["Batteries International News", "垂直媒体", "产业资讯", "https://www.batteriesinternational.com/"], ["pv magazine C&I PV", "垂直媒体", "产业资讯", "https://www.pv-magazine.com/"], ["Ammonia Energy Association", "协会机构", "行业研究", "https://www.ammoniaenergy.org/"], ["H2 View", "垂直媒体", "产业资讯", "https://www.h2-view.com/"], ["Hydrogen Tech World", "垂直媒体", "产业资讯", "https://hydrogentechworld.com/"], ["BloombergNEF Press", "咨询行研", "行业研究", "https://about.bnef.com/"], ["MIT Technology Review Climate", "垂直媒体", "产业资讯", "https://www.technologyreview.com/topic/climate-change/"], ["网易知光谷", "综合媒体", "产业资讯", "https://tech.163.com/"], ["中国核电信息网-国内", "垂直媒体", "产业资讯", "http://www.chinanuclear.cn/"], ["中国核电信息网-国际", "垂直媒体", "产业资讯", "http://www.chinanuclear.cn/"], ["中国电力新闻网-新能源", "综合媒体", "产业资讯", "http://www.cpnn.com.cn/"], ["中国电力新闻网-科技", "综合媒体", "产业资讯", "http://www.cpnn.com.cn/"], ["科学网新闻", "综合媒体", "产业资讯", "https://news.sciencenet.cn/"], ["新华网科技", "综合媒体", "产业资讯", "http://www.xinhuanet.com/tech/"], ["国际太阳能光伏网", "垂直媒体", "产业资讯", "https://www.solaris-china.com/"], ["Renewables Now", "垂直媒体", "产业资讯", "https://renewablesnow.com/"], ["索比光伏-综合新闻", "垂直媒体", "产业资讯", "https://www.solarbe.com/"], ["中国新能源网-新闻", "垂直媒体", "产业资讯", "http://www.china-nengyuan.com/"], ["IT之家", "综合媒体", "产业资讯", "https://www.ithome.com/"]];
let assistantPanels = emptyPanels();
let homeDraft = localStorage.getItem('home_query_draft') || '';
const fallbackAssistantModels = ['glm-5.2','glm-5.1','glm-4.5-flash'];
let assistantModels = fallbackAssistantModels.slice();
let selectedModel = localStorage.getItem('assistant_model') || assistantModels[0];
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
let activeSessionId = null;
let activeRequestController = null;
let lastFailedQuery = '';
let knowledgeGraphCleanup = null;
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
function renderHomeMessages(){
  const answer=document.getElementById('answer');
  const empty=document.getElementById('knowledgeEmptyState');
  const hasMessages=Array.isArray(activeSessionMessages)&&activeSessionMessages.length>0;
  if(empty)empty.hidden=hasMessages;
  if(answer)answer.hidden=!hasMessages;
  return hasMessages?activeSessionMessages.map((msg,index)=>renderConversationMessage(msg,index)).join(''):'';
}
function renderConversationMessage(msg,index){
  if(msg.role==='user')return `<div class="qa-message user user-msg"><div class="qa-message-avatar" aria-hidden="true">你</div><div class="qa-message-content"><div class="qa-message-bubble">${escapeHtml(msg.text||'')}</div></div></div>`;
  const content=msg.text||'';
  const citations=(msg.extra&&msg.extra.citations)||[];
  const isStreaming=Boolean(msg.streaming);
  const isLast=index===activeSessionMessages.length-1;
  const rendered=renderMarkdown(content).replace(/\[(\d+)\]/g,(match,num)=>citations.some(c=>Number(c.id)===Number(num)?true:false)?`<button type="button" class="qa-citation-ref" data-citation="${Number(num)}">[${num}]</button>`:match);
  const body=msg.error?`<div class="qa-error-state"><span>${escapeHtml(msg.error)}</span><button type="button" class="ghost-btn" data-qa-action="retry" data-msg-idx="${index}">重试</button></div>`:`${rendered}${isStreaming?'<span class="qa-typing-cursor"></span>':''}`;
  const actions=!isStreaming&&!msg.error&&content?`<div class="qa-actions"><button class="qa-action-btn" type="button" data-qa-action="copy" data-msg-idx="${index}" title="复制回答">复制</button>${isLast?`<button class="qa-action-btn" type="button" data-qa-action="regenerate" data-msg-idx="${index}" title="重新生成最后一条回答">重新生成</button>`:''}<button class="qa-action-btn" type="button" data-qa-action="export" data-msg-idx="${index}" title="导出 Markdown">导出</button></div>`:'';
  return `<div class="qa-message assistant assistant-msg ${isStreaming?'streaming':''}" data-message-index="${index}"><div class="qa-message-avatar" aria-hidden="true">AI</div><div class="qa-message-content"><div class="qa-message-bubble"><div class="response-text">${body}</div></div>${msg.status?`<div class="qa-status-line">${escapeHtml(msg.status)}</div>`:''}${!isStreaming&&!msg.error?renderInlineResources(msg.extra):''}${actions}</div></div>`;
}
function modelLabel(model){
  if(model==='glm-5.2')return 'GLM-5.2 深度';
  if(model==='glm-5.1')return 'GLM-5.1 Agent';
  if(model==='glm-4.5-flash')return 'GLM-4.5 Flash 快速';
  return model;
}
function renderModelOptions(){return assistantModels.map(model=>`<option value="${escapeHtml(model)}" ${model===selectedModel?'selected':''}>${escapeHtml(modelLabel(model))}</option>`).join('');}
async function loadAssistantModels(){
  try{
    const res=await apiFetch('/api/assistant/models');
    if(!res.ok)return;
    const data=await res.json();
    if(Array.isArray(data.models)&&data.models.length){
      assistantModels=data.models;
      if(!assistantModels.includes(selectedModel))selectedModel=data.default_model||assistantModels[0];
      const select=document.getElementById('modelSelect');
      if(select)select.innerHTML=renderModelOptions();
    }
  }catch(_err){}
}
let activeSessionMessages = [];
async function loadConversations(preferredId=null){
  const select=document.getElementById('sessionSelect');
  if(!select)return;
  try{
    const res=await apiFetch('/api/conversations');
    if(!res.ok)return;
    const sessions=(await res.json()).sessions||[];
    select.innerHTML='<option value="">新对话</option>'+sessions.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.title||'未命名对话')}</option>`).join('');
    const target=preferredId&&sessions.some(item=>item.id===preferredId)?preferredId:'';
    select.value=target;
    const deleteBtn=document.getElementById('deleteConversationBtn');
    if(deleteBtn)deleteBtn.disabled=!target;
    if(target)await loadConversationMessages(target);
  }catch(_err){}
}
async function loadConversationMessages(sessionId){
  const answer=document.getElementById('answer');
  if(!answer)return;
  const res=await apiFetch(`/api/conversations/${encodeURIComponent(sessionId)}/messages?limit=40`);
  if(!res.ok)return;
  const data=await res.json();
  activeSessionId=sessionId;
  const deleteBtn=document.getElementById('deleteConversationBtn');
  if(deleteBtn)deleteBtn.disabled=false;
  activeSessionMessages=(data.messages||[]).map(message=>({
    role:message.role,
    text:message.content,
    extra:{citations:message.citations||[],panel_recommendations:message.panel_recommendations||{},retrieval_summary:message.retrieval_summary||{}},
  }));
  answer.innerHTML=renderHomeMessages();
  answer.scrollTop=answer.scrollHeight;
}
async function deleteConversation(sessionId){
  if(!sessionId)return;
  const select=document.getElementById('sessionSelect');
  const title=select?.selectedOptions?.[0]?.textContent||'当前会话';
  if(!window.confirm(`删除${title}及其消息？`))return;
  const res=await apiFetch(`/api/conversations/${encodeURIComponent(sessionId)}`,{method:'DELETE'});
  if(!res.ok){showToast('删除会话失败');return;}
  startNewConversation();
  await loadConversations();
  showToast('会话已删除');
}
function startNewConversation(){
  if(activeRequestController)activeRequestController.abort();
  activeSessionId=null;
  activeSessionMessages=[];
  const answer=document.getElementById('answer');
  if(answer)answer.innerHTML=renderHomeMessages();
  const select=document.getElementById('sessionSelect');
  if(select)select.value='';
  document.getElementById('queryInput')?.focus();
}
document.addEventListener('change',event=>{
  if(event.target?.id==='sessionSelect'){
    const sessionId=event.target.value;
    const deleteBtn=document.getElementById('deleteConversationBtn');
    if(deleteBtn)deleteBtn.disabled=!sessionId;
    if(sessionId)loadConversationMessages(sessionId);else startNewConversation();
  }
});
document.addEventListener('click',event=>{
  if(event.target?.id==='newConversationBtn')startNewConversation();
  if(event.target?.id==='deleteConversationBtn')deleteConversation(activeSessionId);
  if(event.target?.id==='stopBtn'&&activeRequestController)activeRequestController.abort();
  if(event.target?.id==='retryBtn'&&lastFailedQuery){
    const input=document.getElementById('queryInput');
    if(input){input.value=lastFailedQuery;submitQuery();}
  }
  const action=event.target?.closest?.('[data-qa-action]');
  if(action){event.preventDefault();handleConversationAction(action.dataset.qaAction,Number(action.dataset.msgIdx));}
  const citation=event.target?.closest?.('.qa-citation-ref');
  if(citation){const target=document.querySelector(`[data-citation-card="${citation.dataset.citation}"]`);target?.scrollIntoView({behavior:'smooth',block:'nearest'});target?.classList.add('is-highlighted');setTimeout(()=>target?.classList.remove('is-highlighted'),1400);}
  const example=event.target?.closest?.('[data-example-query]');
  if(example){const input=document.getElementById('queryInput');if(input){input.value=example.dataset.exampleQuery;input.focus();submitQuery();}}
});
function parseHash(){const raw=(location.hash||"#home").slice(1);const [routePart,queryPart=""]=raw.split("?");return {route:routes[routePart]?routePart:"home",params:new URLSearchParams(queryPart)};}
function setRoute(route,params){const q=params?`?${params.toString()}`:"";location.hash=route+q;}
function render(){if(libRefreshTimer){clearTimeout(libRefreshTimer);libRefreshTimer=null;}if(window.Auth&&typeof Auth.requireAuth==="function")Auth.requireAuth();const state=parseHash();document.title=`${routes[state.route].title} · 技术边界数据库`;if(state.route==="home"){activeSessionId=null;activeSessionMessages=[];}if(state.route!=="home"&&knowledgeGraphCleanup){knowledgeGraphCleanup();knowledgeGraphCleanup=null;}document.getElementById("app").innerHTML=shell(state);bindEvents();if(state.route==="home"){loadAssistantModels();loadAssistantStatus();loadHomeBoundaries();loadAlertIntel();loadConversations();loadKnowledgeGraph();}if(state.route==="dashboard")loadDashboards();if(state.route==="map")loadIndustryMap();if(state.route==="users")loadUsers();if(state.route==="library")initLibrary();}
async function ensureCurrentUser(){if(!currentUser){await loadCurrentUser();}return currentUser;}
function loadCurrentUser(){return apiFetch("/api/auth/me").then(r=>r.ok?r.json():null).then(d=>{if(d){currentUser=d;}}).catch(()=>{});}
function isAdmin(){return currentUser&&currentUser.role==="admin";}
function shell(state){
  const data=routes[state.route];
  const visibleNav=navItems.filter(([key])=>key!=='users'||isAdmin());
  const accName=(currentUser&&(currentUser.display_name||currentUser.username))||'加载中…';
  const accRole=currentUser?(currentUser.role==='admin'?'管理员':'普通用户'):'';
  const avatarLetter=(accName||'?')[0].toUpperCase();
  const navHtml=visibleNav.map(([key,code])=>{
    const r=routes[key];
    if(r&&r.href){return `<a class="sidebar-nav-item" href="${r.href}">${r.label}</a>`;}
    return `<button class="sidebar-nav-item ${state.route===key?'active':''}" data-route="${key}">${r.label}</button>`;
  }).join("");
  return `<aside class="sidebar"><div class="sidebar-brand"><div class="sidebar-logo"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg></div><div class="sidebar-title">技术边界数据库</div></div><nav class="sidebar-nav">${navHtml}</nav><div class="sidebar-account"><div class="sidebar-avatar">${escapeHtml(avatarLetter)}</div><div class="sidebar-account-info"><div class="sidebar-account-name">${escapeHtml(accName)}</div><div class="sidebar-account-role">${escapeHtml(accRole)}</div></div><div class="sidebar-actions"><button class="ghost-btn" id="changePwdBtn">密码</button><button class="ghost-btn" id="logoutBtn">退出</button></div></div></aside><section class="workspace"><main class="main ${state.route==='home'?'home-main':state.route==='breadth'?'breadth-main':''}" id="main" tabindex="-1">${view(state.route)}</main></section>`;
}
function view(route){const m={home:homeView,breadth:breadthView,dashboard:dashboardView,map:mapView,users:usersView,library:libraryView};return (m[route]||homeView)();}
function homeView(){
  const knowledgeExpanded=localStorage.getItem('knowledge_interaction_expanded')==='1';
  return `<div class="home-body ${knowledgeExpanded?'knowledge-expanded':''}">
  <section class="home-section home-boundary-section" aria-labelledby="homeBoundaryTitle">
    <div class="home-section-heading">
      <div><h1 id="homeBoundaryTitle">技术边界</h1></div>
      <button class="home-section-link" type="button" data-route="dashboard">查看全部</button>
    </div>
    <div class="home-boundary-grid" id="homeBoundaryCards">
      <div class="home-loading-card">正在加载技术边界…</div>
    </div>
  </section>
  <section class="home-section home-alert-section" aria-labelledby="homeAlertTitle">
    <div class="home-section-heading compact">
      <div><h2 id="homeAlertTitle">技术预警</h2></div>
      <button class="home-section-link" type="button" data-route="breadth">进入广度追踪</button>
    </div>
    <div class="home-alert-table-wrap" id="alertPanelBody">
      <div class="alert-empty">正在加载技术预警…</div>
    </div>
  </section>
  <section class="home-section home-knowledge-section" aria-labelledby="homeKnowledgeTitle">
    <div class="home-section-heading compact knowledge-heading">
      <div><h2 id="homeKnowledgeTitle">与知识库互动</h2></div>
      <div class="knowledge-heading-actions"><span class="knowledge-hint">基于广度情报索引检索并给出可核验引用</span><button class="knowledge-toggle" id="knowledgeToggle" type="button" aria-expanded="${knowledgeExpanded?'true':'false'}" aria-controls="knowledgeConversation"><span>${knowledgeExpanded?'收起':'展开'}</span><i aria-hidden="true"></i></button></div>
    </div>
    <div class="panel conversation-panel" id="knowledgeConversation">
      <div class="conversation-toolbar"><label class="session-picker"><span>会话</span><select id="sessionSelect" aria-label="选择历史会话"><option value="">新对话</option></select></label><button id="deleteConversationBtn" class="icon-btn" type="button" title="删除当前会话" aria-label="删除当前会话" disabled>×</button><button id="newConversationBtn" class="ghost-btn" type="button">＋ 新对话</button><span id="conversationState">正在检查检索服务…</span></div>
      <div class="qa-empty-state" id="knowledgeEmptyState" ${activeSessionMessages.length?'hidden':''}>
        <div class="qa-graph-container" id="qaGraphContainer"><div class="qa-graph-placeholder">正在读取关系图谱…</div></div>
        <div class="qa-empty-copy"><strong>技术情报知识库</strong><span>关系图谱概览与广度情报索引来自同一套检索服务</span></div>
        <div class="qa-example-questions"><button type="button" data-example-query="固态电池最新研究进展有哪些？">固态电池最新研究进展有哪些？</button><button type="button" data-example-query="钙钛矿太阳能电池的效率纪录是多少？">钙钛矿太阳能电池的效率纪录是多少？</button><button type="button" data-example-query="锂电池回收技术有哪些新突破？">锂电池回收技术有哪些新突破？</button></div>
      </div>
      <div class="conversation-history" id="answer" ${activeSessionMessages.length?'':'hidden'}>${renderHomeMessages()}</div>
      <div class="query-box qa-input-area">
        <label class="model-picker" title="选择本次回答使用的模型"><span>模型</span><select id="modelSelect" class="model-select">${renderModelOptions()}</select></label>
        <textarea id="queryInput" class="query-input" autocomplete="off" name="tech-boundary-query" rows="1" placeholder="输入你的问题…"></textarea>
        <button id="askBtn" class="primary-btn">发送</button>
        <button id="stopBtn" class="secondary-btn" type="button" hidden>停止</button>
        <button id="retryBtn" class="ghost-btn" type="button" hidden>重试</button>
      </div>
    </div>
  </section>
</div>`;
}
function renderInsightPanels(){return '';}
function breadthView(){const alertLevel=parseHash().params.get('alert')||'';const query=alertLevel?`?alert=${encodeURIComponent(alertLevel)}`:'';return `<section style="padding:0;overflow:hidden;height:100%;display:flex;flex-direction:column"><div style="flex:1;overflow:hidden;display:block" id="breadthFrameWrap"><iframe src="/breadth/index.html${query}" style="width:100%;height:100%;border:none;display:block" title="广度追踪" allowfullscreen></iframe></div></section>`;}
function dashboardView(){return `<section class="flat-content"><h1 class="section-title">基于知识库文档凝聚的技术边界判断，含核心指标、卡点分析和突破预警</h1><form class="dashboard-search" id="dashboardFilter"><input id="dashboardQ" placeholder="搜索技术、行业或指标，例如 压缩空气、超导、钠电池"/><button class="secondary-btn" type="submit">检索</button></form><div class="dashboard-grid" id="dashboardRows"><div class="status-note">正在加载仪表盘…</div></div></section>`;}
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
  return `<section class="panel content-panel"><h1 class="section-title">按信息类型浏览 ${SOURCE_LIST.length} 个信息源，持续追踪产业动态、学术前沿和行业研究</h1><div class="bookmark-tabs" style="margin-bottom:20px">${tabsHtml}</div><div id="sourceGroupsContent">${groupsHtml}</div></section>`;
}
function mapView(){const state=parseHash();const group=state.params.get('group')||'zero-carbon';const tabs=[["zero-carbon","零碳产业"],["ai-intelligent","AI与智能科技"],["general-tech","通用技术"]];const titleMap={"zero-carbon":"零碳产业","ai-intelligent":"AI与智能科技","general-tech":"通用技术"};return `<section class="flat-content map-content-panel"><div class="map-head"><div><h1 class="section-title">追求完备而互斥</h1></div><div class="map-tools"><input id="mapSearch" value="${escapeHtml(mapSearchDraft)}" placeholder="搜索节点" aria-label="搜索行业图景节点"/><button class="secondary-btn" id="mapExpandAll" type="button">展开全部</button><button class="secondary-btn" id="mapCollapse" type="button">折叠到二级</button></div></div><div class="bookmark-tabs">${tabs.map(([key,label])=>`<button class="bookmark-tab ${group===key?'active':''}" data-map-group="${key}">${label}</button>`).join('')}</div><div class="map-shell"><header class="map-summary"><strong>${titleMap[group]||'零碳产业'}</strong><span id="industryMapMeta">正在加载图景…</span><span class="map-hint">点击叶子节点查看关联内容</span></header><div class="industry-tree" id="industryTree"><div class="status-note">正在加载图景…</div></div><div class="map-x-scroll" id="mapXScroll"><div class="map-x-thumb" id="mapXThumb"></div></div></div></section>`;}
function bindEvents(){document.querySelectorAll("[data-route]").forEach(btn=>btn.addEventListener("click",()=>setRoute(btn.dataset.route)));document.querySelectorAll("[data-map-group]").forEach(btn=>btn.addEventListener("click",()=>{const p=new URLSearchParams(parseHash().params.toString());p.set('group',btn.dataset.mapGroup);setRoute('map',p);}));const logout=document.getElementById("logoutBtn");const changePwd=document.getElementById("changePwdBtn");if(changePwd)changePwd.addEventListener("click",()=>{if(window.Auth&&Auth.showChangePassword)Auth.showChangePassword();});if(logout)logout.addEventListener("click",()=>{if(window.Auth&&Auth.logout)Auth.logout();else location.href="login.html";});const ask=document.getElementById("askBtn");const input=document.getElementById("queryInput");const modelSelect=document.getElementById("modelSelect");if(modelSelect){modelSelect.value=selectedModel;modelSelect.addEventListener('change',()=>{selectedModel=modelSelect.value;localStorage.setItem('assistant_model',selectedModel);});}if(input){input.value=homeDraft;if(!input.dataset.bound){input.addEventListener('input',()=>{homeDraft=input.value;localStorage.setItem('home_query_draft',homeDraft);input.style.height='auto';input.style.height=`${Math.min(input.scrollHeight,120)}px`;});input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submitQuery();}});input.dataset.bound='1';}}if(ask)ask.addEventListener("click",submitQuery);const knowledgeToggle=document.getElementById('knowledgeToggle');if(knowledgeToggle)knowledgeToggle.addEventListener('click',()=>{const body=document.querySelector('.home-body');const expanded=!body?.classList.contains('knowledge-expanded');body?.classList.toggle('knowledge-expanded',expanded);knowledgeToggle.setAttribute('aria-expanded',expanded?'true':'false');const label=knowledgeToggle.querySelector('span');if(label)label.textContent=expanded?'收起':'展开';localStorage.setItem('knowledge_interaction_expanded',expanded?'1':'0');localStorage.removeItem('knowledge_interaction_collapsed');});const dashboardFilter=document.getElementById("dashboardFilter");if(dashboardFilter)dashboardFilter.addEventListener("submit",e=>{e.preventDefault();loadDashboards();});const createUserBtn=document.getElementById("createUserBtn");if(createUserBtn)createUserBtn.addEventListener("click",showCreateUserModal);}
async function loadAssistantStatus(){
  const state=document.getElementById("conversationState");
  try{
    const res=await apiFetch('/api/assistant/status');
    const data=await res.json();
    const count=(data.stats||{}).indexed_records;
    if(state){state.textContent=data.ready?`检索服务已就绪 · ${Number(count||0).toLocaleString('zh-CN')} 条索引`:data.message||'检索服务未配置';state.dataset.status=data.status||'unknown';}
  }catch(err){if(state){state.textContent='检索服务状态检查失败';state.dataset.status='error';}}
}
async function loadKnowledgeGraph(){
  const container=document.getElementById('qaGraphContainer');
  if(!container)return;
  if(knowledgeGraphCleanup){knowledgeGraphCleanup();knowledgeGraphCleanup=null;}
  try{
    const res=await apiFetch('/api/assistant/graph?limit=200');
    if(!res.ok)throw new Error(`graph ${res.status}`);
    const data=await res.json();
    if(!Array.isArray(data.nodes)||!data.nodes.length){container.innerHTML='<div class="qa-graph-placeholder">关系图谱资产尚未提供</div>';return;}
    knowledgeGraphCleanup=renderKnowledgeGraphCanvas(container,data);
  }catch(_err){container.innerHTML='<div class="qa-graph-placeholder">关系图谱将在检索服务配置后显示</div>';}
}
function renderKnowledgeGraphCanvas(container,data){
  const canvas=document.createElement('canvas');
  const tooltip=document.createElement('div');tooltip.className='qa-graph-tooltip';
  container.innerHTML='';container.append(canvas,tooltip);
  const ctx=canvas.getContext('2d');
  const colors={'公司':'#6366f1','机构':'#8b5cf6','技术':'#2563eb','材料':'#059669','产品':'#d97706','人物':'#dc2626','政策':'#db2777','指标':'#0d9488','organization':'#6366f1','artifact':'#d97706','concept':'#2563eb','person':'#dc2626','method':'#9333ea','event':'#ea580c','data':'#0d9488','other':'#64748b','UNKNOWN':'#64748b'};
  let width=0,height=0,raf=0,temperature=1,hover=null,drag=null,panning=false,panStart=null;
  const transform={x:0,y:0,scale:1};
  const nodes=(data.nodes||[]).slice(0,200).map((node,index)=>{const angle=index*2.399963;const radius=18*Math.sqrt(index);return {...node,x:Math.cos(angle)*radius,y:Math.sin(angle)*radius,vx:0,vy:0,radius:Math.max(4,Math.min(14,4+Number(node.degree||0)*.45)),color:colors[node.type]||'#64748b'};});
  const nodeMap=new Map(nodes.map(node=>[node.label,node]));
  const edges=(data.edges||[]).filter(edge=>nodeMap.has(edge.source)&&nodeMap.has(edge.target)).slice(0,500);
  function resize(){const rect=container.getBoundingClientRect();width=Math.max(1,Math.round(rect.width));height=Math.max(1,Math.round(rect.height));const ratio=Math.min(window.devicePixelRatio||1,2);canvas.width=width*ratio;canvas.height=height*ratio;canvas.style.width=`${width}px`;canvas.style.height=`${height}px`;ctx.setTransform(ratio,0,0,ratio,0,0);}
  function point(event){const rect=canvas.getBoundingClientRect();return {screenX:event.clientX-rect.left,screenY:event.clientY-rect.top,x:(event.clientX-rect.left-transform.x-width/2)/transform.scale,y:(event.clientY-rect.top-transform.y-height/2)/transform.scale};}
  function hit(position){return [...nodes].reverse().find(node=>Math.hypot(position.x-node.x,position.y-node.y)<=node.radius+4)||null;}
  function simulate(){
    if(temperature>.025){for(let i=0;i<nodes.length;i++){for(let j=i+1;j<nodes.length;j++){const a=nodes[i],b=nodes[j],dx=b.x-a.x,dy=b.y-a.y,d2=Math.max(36,dx*dx+dy*dy),force=120/d2*temperature;a.vx-=dx*force;a.vy-=dy*force;b.vx+=dx*force;b.vy+=dy*force;}}edges.forEach(edge=>{const a=nodeMap.get(edge.source),b=nodeMap.get(edge.target),dx=b.x-a.x,dy=b.y-a.y,dist=Math.max(1,Math.hypot(dx,dy)),force=(dist-72)*.0025*temperature;a.vx+=dx/dist*force;a.vy+=dy/dist*force;b.vx-=dx/dist*force;b.vy-=dy/dist*force;});nodes.forEach(node=>{if(node===drag)return;node.vx+=-node.x*.0005*temperature;node.vy+=-node.y*.0005*temperature;node.vx*=.86;node.vy*=.86;node.x+=node.vx;node.y+=node.vy;});temperature*=.994;}
  }
  function draw(){ctx.clearRect(0,0,width,height);ctx.save();ctx.translate(width/2+transform.x,height/2+transform.y);ctx.scale(transform.scale,transform.scale);ctx.strokeStyle='rgba(100,116,139,.18)';ctx.lineWidth=1/transform.scale;edges.forEach(edge=>{const a=nodeMap.get(edge.source),b=nodeMap.get(edge.target);ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();});nodes.forEach(node=>{if(node===hover){ctx.beginPath();ctx.arc(node.x,node.y,node.radius+5,0,Math.PI*2);ctx.fillStyle=`${node.color}30`;ctx.fill();}ctx.beginPath();ctx.arc(node.x,node.y,node.radius,0,Math.PI*2);ctx.fillStyle=node.color;ctx.fill();if(node===hover||node.radius>9){ctx.fillStyle='#334155';ctx.font=`${10/Math.max(.8,transform.scale)}px sans-serif`;ctx.textAlign='center';ctx.fillText(String(node.label||'').slice(0,14),node.x,node.y-node.radius-5);}});ctx.restore();}
  function animate(){simulate();draw();raf=requestAnimationFrame(animate);}
  function pointerDown(event){const p=point(event);drag=hit(p);if(drag){temperature=Math.max(temperature,.25);}else{panning=true;panStart={x:event.clientX-transform.x,y:event.clientY-transform.y};}canvas.setPointerCapture?.(event.pointerId);}
  function pointerMove(event){const p=point(event);if(drag){drag.x=p.x;drag.y=p.y;drag.vx=0;drag.vy=0;}else if(panning){transform.x=event.clientX-panStart.x;transform.y=event.clientY-panStart.y;}else{hover=hit(p);canvas.style.cursor=hover?'pointer':'grab';if(hover){tooltip.textContent=`${hover.label}（${hover.type||'未知'}） · 连接度 ${hover.degree||0}`;tooltip.style.left=`${p.screenX+12}px`;tooltip.style.top=`${p.screenY+12}px`;tooltip.classList.add('visible');}else tooltip.classList.remove('visible');}}
  function pointerUp(){drag=null;panning=false;}
  function wheel(event){event.preventDefault();const before=point(event),next=Math.max(.35,Math.min(4,transform.scale*(event.deltaY>0?.9:1.1)));transform.x+=before.x*(transform.scale-next);transform.y+=before.y*(transform.scale-next);transform.scale=next;}
  resize();canvas.addEventListener('pointerdown',pointerDown);canvas.addEventListener('pointermove',pointerMove);canvas.addEventListener('pointerup',pointerUp);canvas.addEventListener('pointercancel',pointerUp);canvas.addEventListener('pointerleave',()=>{pointerUp();hover=null;tooltip.classList.remove('visible');});canvas.addEventListener('wheel',wheel,{passive:false});window.addEventListener('resize',resize);animate();
  return ()=>{cancelAnimationFrame(raf);window.removeEventListener('resize',resize);};
}
function applyIntelParams(params){const qEl=document.getElementById('intelQ');if(qEl&&params.has('q'))qEl.value=params.get('q');const domEl=document.getElementById('intelDomain');if(domEl&&params.has('leaf'))domEl.value=params.get('leaf');const srcEl=document.getElementById('intelSource');if(srcEl&&params.has('source_type'))srcEl.value=params.get('source_type');}

function formatHomeDate(value,fallback='持续更新'){if(!value)return fallback;const date=new Date(value);return Number.isNaN(date.getTime())?String(value).slice(0,10):date.toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'}).replaceAll('/','-');}
function compactHomeText(value,limit=10){const text=String(value||'').replace(/\s+/g,'').trim();return text.length>limit?`${text.slice(0,Math.max(1,limit-1))}…`:text;}
function homeBoundaryDefinition(item){const name=item.name||'该技术';const scope=String(item.scope||'').trim();if(scope&&scope!=='深度调研')return `${name}聚焦${scope.replace(/[。；;]+$/,'')}。`;const verdict=String(item.verdict||'').split(/[。；;]/).map(text=>text.trim()).find(Boolean);return verdict?`${verdict}。`:`${name}的技术定义与适用边界正在持续完善。`;}
function homeBoundaryLines(item){const indicators=(item.key_indicators||[]).slice(0,3).map(ind=>`${ind.name||''}${ind.value&&ind.value!=='—'?`：${ind.value}${ind.unit&&ind.unit!=='—'?ind.unit:''}`:''}`);if(indicators.length)return indicators;const metrics=(item.metrics||[]).slice(0,3);return metrics.length?metrics:['关键指标边界待补充'];}
async function loadHomeBoundaries(){const root=document.getElementById('homeBoundaryCards');if(!root)return;try{const res=await apiFetch('/api/dashboards');const data=await res.json();const all=data.items||[];const items=all.slice().sort((a,b)=>new Date(b.updated_at||0)-new Date(a.updated_at||0)).slice(0,3);if(!items.length){root.innerHTML='<div class="home-loading-card">尚无已发布的技术边界</div>';return;}root.innerHTML=items.map((item,index)=>{const reviewLabel=item.review_status==='validated'?'已审核':item.metric_review_status==='reviewed'?'指标已审阅':'持续更新';return `<button class="home-boundary-card ${index===0?'primary':''}" type="button" data-home-dashboard="${escapeHtml(item.id)}"><div class="boundary-card-meta"><time>${escapeHtml(formatHomeDate(item.updated_at))}</time><span>${reviewLabel}</span></div><h3>${escapeHtml(item.name||'未命名技术')}</h3><p class="boundary-card-definition"><strong>是什么</strong><span class="boundary-card-def-text">${escapeHtml(homeBoundaryDefinition(item))}</span></p><div class="boundary-card-label">关键指标边界</div><ol>${homeBoundaryLines(item).map(line=>`<li>${escapeHtml(line)}</li>`).join('')}</ol><div class="boundary-card-action">查看边界详情 <span aria-hidden="true">→</span></div></button>`}).join('');root.querySelectorAll('[data-home-dashboard]').forEach(card=>card.addEventListener('click',()=>showDashboardDetail(card.dataset.homeDashboard)));}catch(err){root.innerHTML='<div class="home-loading-card">技术边界加载失败</div>';}}

async function loadAlertIntel(){
  const body=document.getElementById('alertPanelBody');
  if(!body)return;
  try{
    const res=await fetch('/breadth/data/processed/alert-records.json',{cache:'no-store'});
    if(!res.ok)throw new Error(`alert snapshot ${res.status}`);
    const data=await res.json();
    const items=Array.isArray(data.items)?data.items:[];
    if(!items.length){
      body.innerHTML='<div class="alert-empty">当前没有活跃预警情报</div>';
      return;
    }
    body.innerHTML=`<table class="home-alert-table"><thead><tr><th>标题</th><th>情报发布</th><th>预警生成</th><th>领域</th><th>预警原因</th></tr></thead><tbody>${items.slice(0,4).map(item=>{
      const color=item.alert_color||(item.confidence==='high'?'high':item.confidence==='medium'?'orange':'normal');
      const title=item.alert_title||item.title||'未命名情报';
      const alertBody=item.alert_body||item.summary||(item.content||'').slice(0,120)||'';
      const publishedTime=item.published_at||item.publish_date||'';
      const alertCreatedTime=item.alert_created_at||item.alert_time||item.created_at||'';
      const target=item.target_url||'#breadth';
      const domain=item.domain_name||item.domain||String(item.info_item_id||'').split('_')[1]||'待归类';
      const reason=item.reviewer_comment||alertBody||'持续跟踪';
      return `<tr><td><a class="home-alert-title" href="${escapeHtml(target)}"><i class="alert-signal ${escapeHtml(color)}"></i>${escapeHtml(title)}</a></td><td><time>${escapeHtml(formatHomeDate(publishedTime,'—'))}</time></td><td><time>${escapeHtml(formatHomeDate(alertCreatedTime,'—'))}</time></td><td><span class="home-alert-domain">${escapeHtml(domain)}</span></td><td title="${escapeHtml(reason)}">${escapeHtml(compactHomeText(reason,10))}</td></tr>`;
    }).join('')}</tbody></table>`;
  }catch(err){
    body.innerHTML='<div class="alert-empty">技术预警加载失败</div>';
  }
}
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
    const filterDesc=leaf?`叶子节点：${leaf}`:(q||sourceType)?'已筛选':'全部';
    if(note)note.textContent=`共 ${data.total||rows.length} 条 · ${filterDesc} · 显示前 ${rows.length} 条`;
    tbody.innerHTML=rows.length?rows.map(item=>`<tr class="intel-row" data-id="${escapeHtml(item.id)}" style="cursor:pointer"><td>${escapeHtml(item.title||'未命名情报')}</td><td title="${escapeHtml(item.taxonomy_path||'')}"><span style="font-size:11px;color:#94a3b8">${escapeHtml(item.domain_label||'')} › </span>${escapeHtml(item.leaf_title||'未分类')}</td><td>${escapeHtml(item.source_type_label||item.source_type||'')}</td><td>${escapeHtml(item.confidence||'')}</td><td>${item.need_human_review?'待审':'OK'}</td><td>${escapeHtml(item.key_metric?`${item.key_metric}: ${item.value_raw}${item.unit}`:'—')}</td></tr>`).join(''):'<tr><td colspan="6">没有符合条件的情报</td></tr>';
    tbody.querySelectorAll('.intel-row').forEach(tr=>tr.addEventListener('click',()=>showIntelDetail(tr.dataset.id)));
  }catch(err){tbody.innerHTML='<tr><td colspan="6">情报加载失败，请稍后重试</td></tr>';}
}
let dashboardReturnRoute='dashboard';
function closeDashboardDetail(){
  const route=dashboardReturnRoute||'dashboard';
  dashboardReturnRoute='dashboard';
  location.hash=route;
  render();
}
async function loadDashboards(){
  const root=document.getElementById('dashboardRows');
  if(!root)return;
  root.innerHTML='<div class="status-note">正在加载仪表盘…</div>';
  const q=encodeURIComponent(document.getElementById('dashboardQ')?.value||parseHash().params.get('q')||'');
  try{
    const res=await apiFetch(`/api/dashboards${q?'?q='+q:''}`);
    const data=await res.json();
    const items=data.items||[];
    const reviewed=items.filter(item=>item.featured&&item.review_status==='validated');
    const drafts=items.filter(item=>!reviewed.includes(item));
    const reviewedHtml=`<div class="dashboard-section-label"><strong>已审核深度报告</strong><span>结论、证据边界与待核实项已拆分</span></div><div class="dashboard-reviewed-layout">${researchKnowledgeFlowCard()}${reviewed.length?dashboardCard(reviewed[0]):reviewedEmptyCard()}</div>${reviewed.slice(1).map(item=>dashboardCard(item)).join('')}`;
    const draftsHtml=drafts.length?`<div class="dashboard-section-label draft-label"><strong>研究草稿与历史仪表盘</strong><span>仅作线索，不代表已完成深度判断</span></div>${drafts.map(item=>dashboardCard(item)).join('')}`:(items.length?'':'<div class="status-note">没有符合条件的仪表盘</div>');
    root.innerHTML=`${reviewedHtml}${draftsHtml}`;
  }catch(err){
    root.innerHTML='<div class="status-note">仪表盘加载失败，请稍后重试</div>';
  }
}
function researchKnowledgeFlowCard(){
  const steps=[
    ['01','零散信息','自动搜集','从动态更新的信源自动化搜集情报并落档。'],
    ['02','结构化情报','分类与评价','自动化分类并提取关键指标；通过人机协同训练，将专家知识沉淀为 AGENT 自动化信息评价标准。'],
    ['03','知识库文档','提炼与索引','基于全量知识提炼行业或技术边界的判断标准，识别卡点技术或共性技术，同时成为整个知识库的索引。'],
    ['04','行业仪表盘','判断与复用','直观给出行业整体判断，快速定位关键环节，实现知识迁移和复用。'],
  ];
  return `<aside class="research-process-card" aria-labelledby="researchProcessTitle">
    <div class="research-process-kicker">HOW IT WORKS</div>
    <h3 id="researchProcessTitle">深度调研如何沉淀为知识？</h3>
    <ol class="research-process-steps">${steps.map(([number,title,action,detail],index)=>`<li>
      <div class="research-process-number${index===steps.length-1?' current':''}">${number}</div>
      <div class="research-process-copy"><div class="research-process-heading"><strong>${title}</strong><span>${action}</span></div><p>${detail}</p></div>
    </li>`).join('')}</ol>
  </aside>`;
}
function mapAssetText(value){return String(value||'').toLowerCase().replace(/\s+/g,'');}
function dashboardMapText(item){
  // Extract only the leaf-level segment from taxonomy_leaf for precise matching
  const leaf=item.taxonomy_leaf||'';
  // Last 1-2 segments of the leaf path are the specific terms
  const segments=leaf.split('/').filter(s=>s.length>=2);
  const leafEnd=segments.slice(-2).join('');
  return mapAssetText([leafEnd,item.id,item.name,item.scope,item.query,item.domain,(item.metrics||[]).join(' ')].join(' '));
}
// Explicit mapping for dashboard → industry map leaf node(s) where the
// KB doc taxonomy_leaf doesn't exactly match a leaf in the current tree.
// Key = dashboard id, Value = array of leaf node titles to match.
const DASHBOARD_LEAF_MAP={
  'rebco':['超导材料'],
  'nh3':['合成氨和绿氨'],
};
function mapMatchesNode(node, rows, textGetter){
  const ownTerm=mapAssetText(node.title);
  if(!ownTerm||ownTerm.length<2)return [];
  return rows.filter(row=>{
    const text=textGetter(row);
    // Direct match: node title in dashboard text
    if(text.includes(ownTerm))return true;
    // Explicit leaf map override
    const leafMap=DASHBOARD_LEAF_MAP[row.id];
    if(leafMap&&leafMap.some(l=>ownTerm.includes(mapAssetText(l))||mapAssetText(l).includes(ownTerm)))return true;
    return false;
  });
}
function findIntelLeaf(node,counts){const fullPath=mapAssetText((node.path||[]).join('/'));return counts.find(item=>mapAssetText(item.path)===fullPath);}
async function loadMapAssets(){const [intelMeta,dashboards]=await Promise.allSettled([apiFetch('/api/delivery-intel/category-counts').then(r=>r.ok?r.json():{category_counts:[]}),apiFetch('/api/dashboards').then(r=>r.ok?r.json():{items:[]})]);const intelCounts=intelMeta.status==='fulfilled'&&Array.isArray(intelMeta.value.category_counts)?intelMeta.value.category_counts:[];return {intelCounts,dashboards:dashboards.status==='fulfilled'&&Array.isArray(dashboards.value.items)?dashboards.value.items:[]};}
function decorateIndustryAssets(node,assets){const children=node.children||[];if(!children.length){const intelLeaf=findIntelLeaf(node,assets.intelCounts);const intelCount=Number(intelLeaf?.count)||0;const dashboards=mapMatchesNode(node,assets.dashboards,dashboardMapText);const matchedDash=dashboards[0];const dashId=matchedDash?.id;node.assets={intel:{active:intelCount>0,count:intelCount,href:'#breadth'},special_issue:{active:false,count:0,href:''},dashboard:{active:!!dashId,count:dashboards.length,dashId:dashId||null}};}children.forEach(child=>decorateIndustryAssets(child,assets));return node;}
function countLeaves(node){const children=node.children||[];return children.length?children.reduce((sum,child)=>sum+countLeaves(child),0):1;}
function leafDots(node){const assets=node.assets||{};const fallbackCoverage=node.coverage||{};const fallbackLinks=node.links||{};const items=[['intel','相关情报'],['special_issue','专刊'],['dashboard','行业仪表盘']];const available=items.map(([key,label])=>{const asset=assets[key]||{active:!!fallbackCoverage[key],href:fallbackLinks[key]||'#',count:0};return {key,label,asset,active:!!asset.active};}).filter(item=>item.active);if(!available.length)return '';return `<div class="leaf-tags">${available.map(({key,label,asset})=>{const status=`${label}：${asset.count||1}项`;const state=`${asset.count||1} 项`;
  // Dashboard tag: open full-screen detail directly instead of navigating
  if(key==='dashboard'&&asset.dashId){
    return `<a class="leaf-tag active" data-link-type="${key}" href="#dashboard" onclick="event.preventDefault();setRoute('dashboard');setTimeout(()=>showDashboardDetail('${escapeHtml(asset.dashId)}'),50)" title="${status}"><span>${label}</span><small>${state}</small></a>`;
  }
  const href=asset.href||'#';
  return `<a class="leaf-tag active" data-link-type="${key}" href="${href}" title="${status}"><span>${label}</span><small>${state}</small></a>`;}).join('')}</div>`;}
function mapNodeOwnMatch(node){const q=mapAssetText(mapSearchDraft);if(!q)return false;return mapAssetText([node.title,...(node.path||[])].join(' ')).includes(q);}
function mapNodeVisible(node){const q=mapAssetText(mapSearchDraft);if(!q)return true;if(mapNodeOwnMatch(node))return true;return (node.children||[]).some(mapNodeVisible);}
function industryNode(node){if(!mapNodeVisible(node))return '';const children=node.children||[];const leaf=children.length===0;const open=mapSearchDraft||node.depth<mapOpenDepth;const childHtml=children.map(industryNode).join('');return `<li class="mind-node depth-${node.depth} ${leaf?'leaf':''} ${mapNodeOwnMatch(node)?'match':''}"><details ${open?'open':''}><summary class="mind-card"><span class="mind-title${node.title.length>=20?' len-xl':node.title.length>=12?' len-lg':''}">${escapeHtml(node.title)}</span></summary>${leaf?leafDots(node):childHtml?`<ul>${childHtml}</ul>`:''}</details></li>`;}
async function loadIndustryMap(){const root=document.getElementById('industryTree');const meta=document.getElementById('industryMapMeta');if(!root)return;const group=parseHash().params.get('group')||'zero-carbon';const titleMap={"zero-carbon":"零碳产业","ai-intelligent":"AI与智能科技","general-tech":"通用技术"};if(meta)meta.textContent=`${titleMap[group]||'零碳产业'}：正在加载 XMind 数据…`;try{const [mapRes,assets]=await Promise.all([apiFetch(`/api/industry-map?group=${encodeURIComponent(group==='zero-carbon'?'零碳产业':group==='ai-intelligent'?'AI与智能科技':'通用技术')}`),loadMapAssets()]);const data=await mapRes.json();const sheet=data.sheet||data.root||data;const rootNode=decorateIndustryAssets(sheet.root||sheet,assets);const sheetTitle=sheet.title||titleMap[group]||'行业图景';if(meta)meta.textContent=`${sheetTitle}：共 ${sheet.node_count||countNodes(rootNode)} 个节点，${countLeaves(rootNode)} 个叶子，最大层级 ${sheet.max_depth||maxDepth(rootNode)}`;root.innerHTML=`<div class="mindmap-canvas"><ul class="mindmap-root">${industryNode(rootNode)}</ul></div>`;requestAnimationFrame(initMapHorizontalScroll);}catch(err){root.innerHTML='<div class="status-note">图景加载失败，请检查 XMind 解析数据。</div>';if(meta)meta.textContent='图景加载失败';}}
function commercialStatusBadge(status,reason=''){
  const map={
    commercial_ready:['✓ 已达商用','commercial-status-ready','当前行业水平已达到可商业应用标准'],
    below_commercial:['! 未达商用','commercial-status-caution','当前行业水平尚未达到可商业应用标准'],
    data_missing:['? 缺数据','commercial-status-missing','缺少判断该指标能否商用的关键数据'],
    theoretical_shortfall:['? 理论不可达','commercial-status-missing','该指标在当前理论边界下无法达到商用标准'],
  };
  if(!map[status])return '';
  const [label,className,defaultReason]=map[status];
  const description=reason?`${defaultReason}：${reason}`:defaultReason;
  return `<span class="commercial-status ${className}" title="${escapeHtml(description)}" aria-label="${escapeHtml(description)}">${label}</span>`;
}

function researchCommercialStatusBadge(status){
  const text=String(status||'');
  const reason=text.replace(/[✅⚠❓]/g,'').trim().replace(/^(已达商用|未达商用|缺数据|理论不可达)\s*[：:]?\s*/,'').trim();
  if(text.includes('✅')||text.includes('已达商用'))return commercialStatusBadge('commercial_ready',reason);
  if(text.includes('⚠')||text.includes('未达商用'))return commercialStatusBadge('below_commercial',reason);
  if(text.includes('理论不可达'))return commercialStatusBadge('theoretical_shortfall',reason);
  if(text.includes('❓')||text.includes('缺数据'))return commercialStatusBadge('data_missing',reason);
  return '';
}
function dashboardCard(item){
  const isKB=item.source==='knowledge_base';
  const indicators=item.key_indicators||[];
  const metricHtml=indicators.length?indicators.slice(0,4).map(ind=>{
    const val=escapeHtml(ind.value||'—');
    const unit=ind.unit&&ind.unit!=='—'?` <span class="metric-unit">${escapeHtml(ind.unit)}</span>`:'';
    const vbadge=commercialStatusBadge(ind.commercial_status||'',ind.commercial_status_reason||'');
    return `<div class="metric-row"><span class="metric-name">${escapeHtml(ind.name)}</span><span class="metric-val">${val}${unit} ${vbadge}</span></div>`;
  }).join(''):'<div class="metric-row"><span class="metric-name" style="color:var(--text-quaternary)">暂无结构化指标</span></div>';
  const reviewed=item.featured&&item.review_status==='validated';
  const sourceTag=reviewed?'<span class="source-tag reviewed">已审核深研</span>':isKB?'<span class="source-tag kb">研究草稿</span>':'<span class="source-tag legacy">基础</span>';
  const scopeHtml=item.scope?`<p>${escapeHtml(item.scope)}</p>`:'';
  const verdictHtml=reviewed&&item.verdict?`<div class="card-verdict"><span>判断</span>${escapeHtml(item.verdict)}</div>`:'';
  const taxonomyHtml=reviewed&&item.taxonomy_leaf?`<div class="card-taxonomy">行业图景 · ${escapeHtml(item.taxonomy_leaf.split('/').slice(-2).join(' › '))}</div>`:'';
  const updated=isKB&&item.updated_at?`<span class="updated-time">更新于 ${new Date(item.updated_at).toLocaleDateString('zh-CN')}</span>`:'';
  const expandable=isKB?` data-dashboard-id="${escapeHtml(item.id)}" style="cursor:pointer" onclick="showDashboardDetail('${escapeHtml(item.id)}')"`:'';
  const intelLink=isKB?'':`<a href="#intel?q=${encodeURIComponent(item.query||item.id)}" class="card-link">查看相关情报 →</a>`;
  return `<article class="dashboard-card${isKB?' kb-card':''}${reviewed?' reviewed-card':''}"${expandable}>${sourceTag}${taxonomyHtml}<h3>${escapeHtml(item.name)}</h3>${scopeHtml}${verdictHtml}<div class="metric-list">${metricHtml}</div>${indicators.length>4?`<div class="more-metrics">还有 ${indicators.length-4} 项指标，点击查看 →</div>`:''}<div class="card-footer">${updated}${intelLink}</div></article>`;
}
function countNodes(node){return 1+((node.children||[]).reduce((sum,child)=>sum+countNodes(child),0));}
function maxDepth(node){const children=node.children||[];return children.length?Math.max(...children.map(maxDepth)):Number(node.depth||0);}
async function showDashboardDetail(dashId){
  if(!dashId)return;
  const main=document.getElementById('main');
  if(!main)return;
  dashboardReturnRoute=parseHash().route==='home'?'home':'dashboard';
  const backLabel=dashboardReturnRoute==='home'?'返回首页':'返回列表';

  main.innerHTML=`<div class="dash-fullview">
    <div class="dash-fv-header">
      <button class="ghost-btn" onclick="closeDashboardDetail()">← ${backLabel}</button>
      <span class="dash-fv-title" id="dashFvTitle">正在加载…</span>
    </div>
    <div class="dash-fv-loading" id="dashFvBody">正在加载行业仪表盘…</div>
  </div>`;

  try{
    const [detailRes, contentRes] = await Promise.all([
      apiFetch(`/api/dashboards/${encodeURIComponent(dashId)}`),
      apiFetch(`/api/dashboards/${encodeURIComponent(dashId)}/content`),
    ]);
    if(!detailRes||!detailRes.ok){document.getElementById('dashFvBody').innerHTML='<div class="status-note">加载失败</div>';return;}
    const detail=await detailRes.json();
    const content=contentRes&&contentRes.ok?await contentRes.json():{};

    document.getElementById('dashFvTitle').textContent=detail.name||dashId;

    // ─── Decision-first hero ───
    const confidenceMap={high:'高',medium:'中',low:'低'};
    const decisionHero=content.featured?`<section class="research-hero"><div class="research-kicker"><span>已审核深度报告</span><span>判断置信度：${escapeHtml(confidenceMap[content.confidence]||content.confidence||'待标注')}</span></div><div class="research-path">主分类 · ${escapeHtml((content.taxonomy_leaf||'').split('/').join(' › '))}${content.cross_ref?`<br>场景交叉 · ${escapeHtml(content.cross_ref.split('/').join(' › '))}`:''}</div><h1>${escapeHtml(content.decision_question||detail.name||'')}</h1><div class="research-verdict"><strong>当前结论</strong><p>${escapeHtml(content.verdict||'')}</p></div></section>`:'';
    const summaryHtml=content.summary?`<div class="dash-card summary-card"><div class="dash-card-head"><h4>为什么这样判断</h4></div><div class="dash-card-body"><p>${escapeHtml(content.summary)}</p></div></div>`:'';

    // ─── Value anchor card ───
    const anchors=content.value_anchor||[];
    const anchorHtml=anchors.length?`<div class="dash-card"><div class="dash-card-head"><h4>判断链：证据如何导向结论</h4></div><div class="dash-card-body"><table class="dash-table"><thead><tr>${Object.keys(anchors[0]).map(h=>`<th>${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${anchors.map(r=>`<tr>${Object.values(r).map(v=>`<td>${escapeHtml(String(v))}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>`:'';

    // ─── Key indicators (from structured DB data) ───
    const indicators=detail.detailed_indicators||[];
    const techInds=indicators.filter(i=>i.type==='technical');
    const econInds=indicators.filter(i=>i.type==='economic');
    const isSofcReport=/SOFC/i.test(`${detail.name||''} ${content.decision_question||''}`);
    const indicatorGrid=(title,list)=>list.length?`<div class="dash-card"><div class="dash-card-head"><h4>${title}</h4><span class="dash-card-sub">${list.length} 项</span></div><div class="dash-card-body"><div class="ind-grid">${list.map(i=>{
      const val=i.value_text||((i.value_min!==null&&i.value_max!==null)?(i.value_min===i.value_max?i.value_min:`${i.value_min}–${i.value_max}`):(i.value_min!==null?i.value_min:'—'));
      const unit=i.unit&&i.unit!=='—'?` ${escapeHtml(i.unit)}`:'';
      return `<div class="ind-tile"><div class="ind-tile-name">${escapeHtml(i.name)}</div><div class="ind-tile-val">${escapeHtml(String(val))}<span class="ind-tile-unit">${escapeHtml(unit)}</span></div>${i.notes?`<div class="ind-tile-note">${escapeHtml(i.notes)}</div>`:''}<div class="ind-tile-badge">${commercialStatusBadge(i.commercial_status||'',i.commercial_status_reason||'')}</div></div>`;
    }).join('')}</div></div></div>`:'';

    const docIndicators=content.indicators||[];
    const researchIndicatorHtml=docIndicators.length?`<div class="dash-card research-indicators"><div class="dash-card-head"><h4>关键技术指标</h4><span class="dash-card-sub">理论值 / 需求值 / 实际值分列</span></div><div class="dash-card-body"><div class="research-indicator-list">${docIndicators.map(i=>{const commercialStatus=i['商用状态']||'';return `<article class="research-indicator"><div class="research-indicator-head"><strong>${escapeHtml(i['关键指标']||i['指标']||'')}</strong>${researchCommercialStatusBadge(commercialStatus)}</div><div class="research-indicator-values"><div><span>理论值 / 物理边界</span><b>${escapeHtml(i['理论值/物理边界']||'未提供')}</b></div><div><span>需求值</span><b>${escapeHtml(i['场景需求值']||'未提供')}</b></div><div><span>实际值 / 公开披露</span><b>${escapeHtml(i['实际值/公开披露']||i['当前实测/披露']||'未提供')}</b></div></div>${i['条件/口径']?`<p class="research-indicator-scope"><span>口径</span>${escapeHtml(i['条件/口径'])}</p>`:''}${i['进一步调研方向']&&commercialStatus.includes('❓')?`<p class="research-next"><span>进一步调研方向</span>${escapeHtml(i['进一步调研方向'])}</p>`:''}</article>`}).join('')}</div></div></div>`:'';

    // ─── Roadmap card ───
    const roads=content.roadmap||[];
    const roadmapHtml=roads.length?`<div class="dash-card"><div class="dash-card-head"><h4>技术路线图</h4></div><div class="dash-card-body"><div class="roadmap-list">${roads.map((r,i)=>{
      const routeName=r['路线']||r['Roadmap']||Object.values(r)[0]||'';
      const principle=r['原理']||'';
      const maturity=r['成熟度']||'';
      const rep=r['代表项目']||r['代表团队/企业']||'';
      return `<div class="roadmap-item"><div class="roadmap-badge">${String.fromCharCode(65+i)}</div><div class="roadmap-content"><div class="roadmap-name">${escapeHtml(routeName)}</div><div class="roadmap-desc">${escapeHtml(principle)}</div><div class="roadmap-tags"><span class="tag-maturity">${escapeHtml(maturity)}</span>${rep?`<span class="tag-rep">${escapeHtml(rep)}</span>`:''}</div></div></div>`;
    }).join('')}</div></div></div>`:'';

    // ─── Feasibility verification card (§2.5) ───
    const feas=content.feasibility||[];
    const feasibilityHtml=feas.length?`<div class="dash-card feas-card"><div class="dash-card-head"><h4>指标物理可达性验证</h4><span class="dash-card-sub">场景需求 vs 物理极限</span></div><div class="dash-card-body"><div class="feas-list">${feas.map(f=>{
      const metric=f['关键指标']||'';
      const demand=f['场景需求（倒推）']||'';
      const actual=f['当前实测']||'';
      const limit=f['物理理论极限']||'';
      const gap=f['差距性质']||'';
      const verdictRaw=f['结论']||'';
      const verdict=String(verdictRaw).replace(/[✅❌❓⚠️]/g,'').trim();
      // Color by verdict
      let vColor='var(--text-tertiary)',vBg='var(--bg-surface)';
      if(verdictRaw.includes('✅')){vColor='var(--green)';vBg='var(--green-bg)';}
      else if(verdictRaw.includes('❌')){vColor='var(--red)';vBg='var(--red-bg)';}
      else if(verdictRaw.includes('⚠')){vColor='var(--amber)';vBg='var(--amber-bg)';}
      else if(verdictRaw.includes('❓')){vColor='var(--red)';vBg='var(--red-bg)';}
      return `<div class="feas-item"><div class="feas-head"><span class="feas-metric">${escapeHtml(metric)}</span><span class="feas-verdict" style="color:${vColor};background:${vBg}">${escapeHtml(verdict)}</span></div><div class="feas-grid"><div class="feas-cell"><span class="feas-label">场景需求</span><span class="feas-val">${escapeHtml(demand)}</span></div><div class="feas-cell"><span class="feas-label">当前实测</span><span class="feas-val">${escapeHtml(actual)}</span></div><div class="feas-cell"><span class="feas-label">物理极限</span><span class="feas-val feas-limit">${escapeHtml(limit)}</span></div><div class="feas-cell"><span class="feas-label">差距</span><span class="feas-val">${escapeHtml(gap)}</span></div></div></div>`;
    }).join('')}</div></div></div>`:'';

    // ─── Bottlenecks card ───
    const bns=content.bottlenecks||[];
    const bottleneckHtml=bns.length?`<div class="dash-card"><div class="dash-card-head"><h4>卡脖子分析</h4><span class="dash-card-sub">${bns.length} 个卡点</span></div><div class="dash-card-body"><div class="bn-list">${bns.map(b=>{
      // Determine nature color
      let natureColor='var(--text-tertiary)';
      let natureIcon='🔧';
      if(b.nature.includes('物理')){natureColor='var(--red)';natureIcon='⛔';}
      else if(b.nature.includes('经济')){natureColor='var(--amber)';natureIcon='💰';}
      else if(b.nature.includes('工程')){natureColor='var(--brand)';natureIcon='⚙️';}
      return `<div class="bn-item"><div class="bn-head"><span class="bn-icon">${natureIcon}</span><span class="bn-title">${escapeHtml(b.title)}</span></div>${b.blockage?`<div class="bn-row"><span class="bn-label">卡点</span><span class="bn-text">${escapeHtml(b.blockage)}</span></div>`:''}${b.nature?`<div class="bn-row"><span class="bn-label" style="color:${natureColor}">性质</span><span class="bn-text">${escapeHtml(b.nature)}</span></div>`:''}${b.signals?`<div class="bn-row"><span class="bn-label">突破信号</span><span class="bn-text bn-signal">${escapeHtml(b.signals)}</span></div>`:''}</div>`;
    }).join('')}</div></div></div>`:'';

    // ─── Alerts card ───
    const alerts=content.alerts||[];
    const alertHtml=alerts.length?`<div class="dash-card"><div class="dash-card-head"><h4>突破预警</h4></div><div class="dash-card-body"><table class="dash-table"><thead><tr>${Object.keys(alerts[0]).map(h=>`<th>${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${alerts.map(r=>`<tr>${Object.values(r).map(v=>{const s=String(v);let cls='';if(s.includes('🔴'))cls='alert-red';else if(s.includes('🟡'))cls='alert-yellow';else if(s.includes('🟢'))cls='alert-green';return `<td class="${cls}">${escapeHtml(s)}</td>`;}).join('')}</tr>`).join('')}</tbody></table></div></div>`:'';

    // ─── Doc indicators from §2 table (legacy fallback) ───
    const docIndHtml=docIndicators.length&&techInds.length<3?`<div class="dash-card"><div class="dash-card-head"><h4>关键指标清单</h4></div><div class="dash-card-body"><table class="dash-table"><thead><tr>${Object.keys(docIndicators[0]).map(h=>`<th>${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${docIndicators.slice(0,8).map(r=>`<tr>${Object.values(r).map(v=>`<td>${escapeHtml(String(v))}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>`:'';

    // ─── §4 Common technology analysis ───
    const commonItems=content.common_tech||[];
    const commonHtml=commonItems.length?`<div class="dash-card"><div class="dash-card-head"><h4>共性技术分析</h4></div><div class="dash-card-body"><ul class="common-list">${commonItems.map(c=>`<li>${escapeHtml(c)}</li>`).join('')}</ul></div></div>`:'';

    // ─── §6 To-verify checklist ───
    const verifyItems=content.to_verify||[];
    const verifyHtml=verifyItems.length?`<div class="dash-card verify-card"><div class="dash-card-head"><h4>待核实清单</h4><span class="dash-card-sub">${verifyItems.length} 项</span></div><div class="dash-card-body"><ul class="verify-list">${verifyItems.map(v=>`<li>${escapeHtml(v)}</li>`).join('')}</ul></div></div>`:'';

    // ─── Full report sections (raw markdown rendered) ───
    const rawSections=content.raw_sections||{};
    const sectionOrder=['§0','§0.5','§1','§2','§2.5','§3','§4','§5','§6','§7','附录'];
    const sectionLabels={
      '§0':'§0 定位摘要','§0.5':'§0.5 价值锚点收敛','§1':'§1 技术路线图','§2':'§2 关键指标清单',
      '§2.5':'§2.5 物理可达性验证','§3':'§3 卡脖子技术分析','§4':'§4 共性技术分析',
      '§5':'§5 信息源与文献追踪','§6':'§6 待核实清单','§7':'§7 突破预警指标','附录':'附录'
    };
    const fullReportHtml=Object.keys(rawSections).length?`<div class="full-report-divider"><span>完整报告</span></div>${Object.keys(rawSections).map(secTitle=>{
      // Find a display label
      let label=secTitle;
      for(const[key,val]of Object.entries(sectionLabels)){if(secTitle.includes(key)){label=secTitle;break;}}
      const body=rawSections[secTitle];
      if(!body||!body.trim())return '';
      return `<div class="dash-card md-section"><div class="dash-card-head"><h4>${escapeHtml(label)}</h4></div><div class="dash-card-body md-body">${mdToHtml(body)}</div></div>`;
    }).join('')}`:'';

    document.getElementById('dashFvBody').innerHTML=`
      ${decisionHero}
      ${summaryHtml}
      ${anchorHtml}
      ${isSofcReport?researchIndicatorHtml:indicatorGrid('关键指标（技术）',techInds)}
      ${isSofcReport?'':indicatorGrid('关键指标（经济）',econInds)}
      ${feasibilityHtml}
      ${roadmapHtml}
      ${bottleneckHtml}
      ${commonHtml}
      ${isSofcReport?'':docIndHtml}
      ${alertHtml}
      ${verifyHtml}
      ${fullReportHtml}
    `;
  }catch(err){
    document.getElementById('dashFvBody').innerHTML='<div class="status-note">加载失败，请稍后重试</div>';
  }
}
function indicatorText(item){const indicators=item.draft_data&&Array.isArray(item.draft_data.indicators)?item.draft_data.indicators:[];return indicators.length?escapeHtml(indicators.slice(0,3).map(x=>`${x.name||'指标'} ${x.value||''}${x.unit||''}`).join('；')):'—';}
function updatePanels(extra){assistantPanels=(extra&&extra.panel_recommendations)||emptyPanels();}
function renderInlineResources(extra){
  const citations=(extra&&Array.isArray(extra.citations))?extra.citations:[];
  const stats=(extra&&extra.retrieval_summary)||{};
  return citations.length?renderCitations(citations,stats):'';
}
function refreshConversationSurface(){
  const answer=document.getElementById('answer');
  if(!answer)return;
  answer.innerHTML=renderHomeMessages();
  answer.scrollTop=answer.scrollHeight;
}
async function handleConversationAction(action,msgIdx){
  const msg=activeSessionMessages[msgIdx];
  if(!msg||msg.role!=='assistant')return;
  if(action==='copy'){
    try{await navigator.clipboard.writeText(msg.text||'');showToast('回答已复制');}catch(_){showToast('浏览器未允许复制');}
    return;
  }
  if(action==='export'){
    exportConversationAnswer(msg,msgIdx);
    return;
  }
  const previous=activeSessionMessages[msgIdx-1];
  if(!previous||previous.role!=='user')return;
  if(action==='regenerate'&&msgIdx===activeSessionMessages.length-1){
    submitQuery({query:previous.text,regenerate:true});
  }else if(action==='retry'&&msgIdx===activeSessionMessages.length-1){
    submitQuery({query:previous.text,retry:true});
  }
}
function exportConversationAnswer(msg,msgIdx){
  const question=activeSessionMessages[msgIdx-1]?.text||'';
  let markdown=`# 技术情报问答\n\n**时间：** ${new Date().toLocaleString('zh-CN')}\n\n## 问题\n\n${question}\n\n## 回答\n\n${msg.text||''}\n`;
  const citations=(msg.extra&&msg.extra.citations)||[];
  if(citations.length){markdown+='\n## 来源引用\n\n';citations.forEach(c=>{markdown+=`[${c.id}] ${c.title||'未命名情报'} (${c.date||'日期未知'}, ${c.source||'来源未知'})\n`;if(c.body_snippet)markdown+=`> ${c.body_snippet}\n`;if(c.url)markdown+=`> ${c.url}\n`;markdown+='\n';});}
  const blob=new Blob([markdown],{type:'text/markdown;charset=utf-8'});
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');link.href=url;link.download=`techdb-qa-${Date.now()}.md`;link.click();URL.revokeObjectURL(url);
  showToast('已导出 Markdown');
}
function showToast(message){
  const old=document.querySelector('.qa-toast');if(old)old.remove();
  const toast=document.createElement('div');toast.className='qa-toast';toast.textContent=message;document.body.appendChild(toast);
  setTimeout(()=>toast.remove(),2200);
}
async function submitQuery(options={}){
  const input=document.getElementById("queryInput");
  const answer=document.getElementById("answer");
  const query=String(options.query??input?.value??'').trim();
  if(!query){input?.focus();return;}
  if(activeRequestController)return;

  const regenerate=Boolean(options.regenerate);
  const retry=Boolean(options.retry);
  let replacedMessage=null;
  if(regenerate||retry)replacedMessage=activeSessionMessages.pop()||null;
  if(!regenerate&&!retry)activeSessionMessages.push({role:'user',text:query});
  const assistantMsg={role:'assistant',text:'',extra:null,streaming:true,status:'正在连接检索服务…'};
  activeSessionMessages.push(assistantMsg);
  if(input){input.value="";input.style.height='auto';}
  homeDraft="";localStorage.removeItem('home_query_draft');
  refreshConversationSurface();

  let streamCompleted=false;
  const controller=new AbortController();
  activeRequestController=controller;
  const askBtn=document.getElementById('askBtn');
  const stopBtn=document.getElementById('stopBtn');
  const retryBtn=document.getElementById('retryBtn');
  if(askBtn){askBtn.disabled=true;askBtn.textContent='回答中…';}
  if(stopBtn)stopBtn.hidden=false;
  if(retryBtn)retryBtn.hidden=true;

  try{
    const res=await fetch('/api/assistant/stream',{
      method:'POST',
      headers:{...authHeaders(),'Content-Type':'application/json'},
      body:JSON.stringify({query,model:selectedModel,session_id:activeSessionId||null,regenerate,retry}),
      signal:controller.signal,
    });
    if(!res.ok){
      const errData=await res.json().catch(()=>({detail:`HTTP ${res.status}`}));
      throw new Error(errData.detail||'请求失败');
    }
    activeSessionId=res.headers.get('X-Conversation-Id')||activeSessionId;
    const deleteBtn=document.getElementById('deleteConversationBtn');if(deleteBtn)deleteBtn.disabled=!activeSessionId;
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
            assistantMsg.status=data.message||'处理中…';
            refreshConversationSurface();

          }else if(currentEvent==="token"){
            assistantMsg.text+=data.content||'';
            assistantMsg.status='';
            refreshConversationSurface();

          }else if(currentEvent==="replace"){
            // The backend may have emitted a partial stream before switching
            // to a complete non-streaming response. Replace the partial text
            // so the persisted answer and the visible answer stay identical.
            assistantMsg.text=String(data.content||'');
            assistantMsg.status='';
            refreshConversationSurface();

          }else if(currentEvent==="done"){
            const stats=data.retrieval_summary||{};
            assistantMsg.text=data.response||assistantMsg.text;
            assistantMsg.streaming=false;
            assistantMsg.status=data.truncated?'回答达到输出上限，内容可能未完。':'';
            activeSessionId=data.session_id||activeSessionId;
            assistantMsg.extra={citations:data.citations||[],retrieval_summary:stats,panel_recommendations:{},truncated:Boolean(data.truncated),finish_reason:data.finish_reason||null,fallback_used:Boolean(data.fallback_used)};
            streamCompleted=true;
            refreshConversationSurface();

          }else if(currentEvent==="error"){
            throw new Error(data.error||'LLM 调用失败');
          }
        }
      }
    }

    if(!streamCompleted)throw new Error('回答流提前结束');
    lastFailedQuery='';
    await loadConversations(activeSessionId);

  }catch(err){
    lastFailedQuery=query;
    const stopped=err?.name==='AbortError';
    assistantMsg.streaming=false;
    assistantMsg.status='';
    assistantMsg.error=stopped?'已停止生成。':(err?.message||'连接失败，请稍后重试。');
    if(regenerate&&replacedMessage){activeSessionMessages.pop();activeSessionMessages.push(replacedMessage);showToast(assistantMsg.error);}
    else refreshConversationSurface();
    if(retryBtn)retryBtn.hidden=false;
  }finally{
    activeRequestController=null;
    if(askBtn){askBtn.disabled=false;askBtn.textContent='发送';}
    if(stopBtn)stopBtn.hidden=true;
  }
}

function normalizeChatSoftBreaks(text){
  const lines=String(text||'').replace(/\r\n?/g,'\n').split('\n');
  const result=[];
  let inFence=false;
  const isBlockStart=line=>/^\s*(?:```|#{1,6}\s|[-*+]\s+|\d+[.)]\s+|>)/.test(line);
  const isSentenceEnd=line=>{
    const cleaned=line.trim()
      .replace(/(?:\s*\[[A-Za-z]+\d+\])+\s*$/g,'')
      .replace(/[\s*_`"'”’）】」』]+$/g,'');
    return /[。！？!?；;：:.]$/.test(cleaned);
  };

  for(let i=0;i<lines.length;i++){
    const line=lines[i];
    if(/^\s*```/.test(line)){
      inFence=!inFence;
      result.push(line);
      continue;
    }
    if(inFence||line.trim()){
      result.push(line);
      continue;
    }

    let nextIndex=i+1;
    while(nextIndex<lines.length&&!lines[nextIndex].trim())nextIndex++;
    const previous=[...result].reverse().find(item=>item.trim())||'';
    const next=lines[nextIndex]||'';
    // A blank line in the middle of an unfinished sentence is model formatting
    // noise, not a real paragraph boundary.  Drop it; renderMarkdown will join
    // the adjacent text lines with a normal space.
    if(previous&&!isSentenceEnd(previous)&&next&&!isBlockStart(next))continue;
    result.push(line);
  }
  return result.join('\n');
}

function renderMarkdown(text){
  if(!text)return '';
  // 1. Escape all HTML first
  let t=escapeHtml(normalizeChatSoftBreaks(text));
  // 2. Fenced code blocks ```...```
  t=t.replace(/```([\s\S]*?)```/g,(m,p1)=>`<pre><code>${p1.replace(/^\n/,'')}</code></pre>`);
  // 3. Protect code blocks from further processing
  const codeBlocks=[];
  t=t.replace(/<pre><code>[\s\S]*?<\/code><\/pre>/g,m=>{codeBlocks.push(m);return `\x00CB${codeBlocks.length-1}\x00`;});
  // 4. Split into lines for block-level processing
  const lines=t.split('\n');
  let html='';
  let inList=null; // 'ul' | 'ol' | null
  let para=[];
  const flushPara=()=>{if(para.length){html+=`<p>${para.join(' ')}</p>`;para=[];}};
  const flushList=()=>{if(inList){html+=`</${inList}>`;inList=null;}};

  for(const line of lines){
    const trimmed=line.trim();
    if(!trimmed){flushPara();flushList();continue;}
    // Ignore decorative Markdown separators in chat answers; they create visual noise.
    if(/^[-*_]{3,}$/.test(trimmed)){flushPara();flushList();continue;}
    // Heading
    let m;
    if(m=trimmed.match(/^###\s+(.+)/)){flushPara();flushList();html+=`<h4>${inlineMd(m[1])}</h4>`;continue;}
    if(m=trimmed.match(/^##\s+(.+)/)){flushPara();flushList();html+=`<h3>${inlineMd(m[1])}</h3>`;continue;}
    if(m=trimmed.match(/^#\s+(.+)/)){flushPara();flushList();html+=`<h3>${inlineMd(m[1])}</h3>`;continue;}
    // Unordered list
    if(m=trimmed.match(/^[-*]\s+(.+)/)){
      flushPara();
      if(inList!=='ul'){flushList();html+='<ul>';inList='ul';}
      html+=`<li>${inlineMd(m[1])}</li>`;
      continue;
    }
    // Ordered list
    if(m=trimmed.match(/^\d+[.)]\s+(.+)/)){
      flushPara();
      if(inList!=='ol'){flushList();html+='<ol>';inList='ol';}
      html+=`<li>${inlineMd(m[1])}</li>`;
      continue;
    }
    // Blockquote
    if(m=trimmed.match(/^>\s*(.*)/)){
      flushPara();flushList();
      html+=`<blockquote>${inlineMd(m[1])}</blockquote>`;
      continue;
    }
    // Regular text — collect into paragraph buffer
    flushList();
    para.push(inlineMd(trimmed));
  }
  flushPara();flushList();

  // 5. Restore code blocks
  html=html.replace(/\x00CB(\d+)\x00/g,(_,i)=>codeBlocks[parseInt(i)]);
  return html;

  function inlineMd(s){
    return s
      .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
      .replace(/\*(.+?)\*/g,'<em>$1</em>')
      .replace(/`(.+?)`/g,'<code>$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
  }
}

function renderCitations(citations,stats){
  const count=Number(stats.knowledge_base||citations.length||0);
  return `<div class="qa-citations-block"><div class="qa-citations-title"><strong>来源引用</strong><span>检索 ${count} 条索引记录</span></div>${citations.map((c,index)=>{const id=Number(c.id||index+1);const meta=[c.date,c.source,c.tag].filter(Boolean).map(item=>`<span>${escapeHtml(item)}</span>`).join('');const link=c.url?`<a class="qa-citation-link" href="${escapeHtml(c.url)}" target="_blank" rel="noopener noreferrer">原文</a>`:'';return `<article class="qa-citation-item" data-citation-card="${id}"><div class="qa-citation-header"><span class="qa-citation-number">[${id}]</span><span class="qa-citation-title">${escapeHtml(c.title||'未命名情报')}</span></div><div class="qa-citation-meta">${meta}${link}</div>${c.body_snippet?`<p class="qa-citation-snippet">${escapeHtml(c.body_snippet)}</p>`:''}</article>`;}).join('')}</div>`;
}
function escapeHtml(s){return String(s).replace(/[&<>\"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));}

// ═══════════════════════════════════════════════════════
// USER MANAGEMENT
// ═══════════════════════════════════════════════════════

function usersView(){
  return `<section class="panel content-panel">
    <h1 class="section-title">管理系统用户账号、角色和启用状态</h1>
    <div style="margin-bottom:14px"><button class="primary-btn" id="createUserBtn">+ 创建用户</button></div>
    <div class="table-card"><table>
      <thead><tr><th>用户名</th><th>显示名</th><th>角色</th><th>状态</th><th>最后登录</th><th>操作</th></tr></thead>
      <tbody id="usersTbody"><tr><td colspan="6" style="color:#667085;padding:20px">正在加载用户列表…</td></tr></tbody>
    </table></div>
  </section>`;
}

async function loadUsers(){
  const tbody=document.getElementById('usersTbody');
  if(!tbody)return;
  try{
    const res=await apiFetch('/api/users');
    if(!res||!res.ok){tbody.innerHTML=`<tr><td colspan="6" style="color:#dc2626">加载失败</td></tr>`;return;}
    const data=await res.json();
    const users=data.users||[];
    if(!users.length){tbody.innerHTML='<tr><td colspan="6">暂无用户</td></tr>';return;}
    tbody.innerHTML=users.map(u=>{
      const isMe=currentUser&&u.username===currentUser.username;
      const roleLabel=u.role==='admin'?'<span style="background:#dbeafe;color:#1e40af;border:1px solid #93c5fd;border-radius:999px;padding:2px 8px;font-size:11px">管理员</span>':'<span style="background:#f1f5f9;color:#475467;border:1px solid #e2e8f0;border-radius:999px;padding:2px 8px;font-size:11px">普通用户</span>';
      const statusLabel=u.is_active?'<span style="color:#16a34a">● 启用</span>':'<span style="color:#dc2626">● 禁用</span>';
      const login=u.last_login_at?new Date(u.last_login_at).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
      const meTag=isMe?' <span style="color:#0e7490;font-weight:600">(我)</span>':'';
      const delDisabled=isMe?'disabled style="opacity:.4;cursor:not-allowed"':'';
      return `<tr>
        <td><strong>${escapeHtml(u.username)}</strong>${meTag}</td>
        <td>${escapeHtml(u.display_name||'—')}</td>
        <td>${roleLabel}</td>
        <td>${statusLabel}</td>
        <td style="font-size:12px;color:#667085">${login}</td>
        <td style="white-space:nowrap">
          <button class="ghost-btn user-edit" data-u="${escapeHtml(u.username)}" style="font-size:12px">编辑</button>
          <button class="ghost-btn user-reset" data-u="${escapeHtml(u.username)}" style="font-size:12px">重置密码</button>
          <button class="ghost-btn user-delete" data-u="${escapeHtml(u.username)}" ${delDisabled} style="font-size:12px;color:#dc2626">删除</button>
        </td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('.user-edit').forEach(b=>b.addEventListener('click',()=>showEditUserModal(b.dataset.u)));
    tbody.querySelectorAll('.user-reset').forEach(b=>b.addEventListener('click',()=>showResetPwdModal(b.dataset.u)));
    tbody.querySelectorAll('.user-delete').forEach(b=>b.addEventListener('click',()=>confirmDeleteUser(b.dataset.u)));
  }catch(e){tbody.innerHTML='<tr><td colspan="6" style="color:#dc2626">加载失败</td></tr>';}
}

function _userModal(html){
  let m=document.getElementById('_userModal');
  if(!m){m=document.createElement('div');m.id='_userModal';m.style.cssText='position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.55);backdrop-filter:blur(3px)';document.body.appendChild(m);}
  m.innerHTML=`<div style="background:#fff;border-radius:16px;padding:28px 30px;width:400px;max-width:92vw;box-shadow:0 24px 64px rgba(0,0,0,.18)">${html}</div>`;
  m.style.display='flex';
  return m;
}

function showCreateUserModal(){
  const m=_userModal(`
    <div style="font-size:17px;font-weight:700;margin-bottom:20px">创建新用户</div>
    <div style="display:grid;gap:12px">
      <div><label style="font-size:13px;color:#667085;display:block;margin-bottom:4px">用户名 *</label><input id="_cuUsername" style="width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box" /></div>
      <div><label style="font-size:13px;color:#667085;display:block;margin-bottom:4px">密码 *</label><input id="_cuPassword" type="password" style="width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box" /></div>
      <div><label style="font-size:13px;color:#667085;display:block;margin-bottom:4px">显示名</label><input id="_cuDisplayName" style="width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box" /></div>
      <div><label style="font-size:13px;color:#667085;display:block;margin-bottom:4px">角色</label><select id="_cuRole" style="width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box"><option value="user">普通用户</option><option value="admin">管理员</option></select></div>
    </div>
    <div id="_cuMsg" style="font-size:13px;min-height:18px;margin-top:12px"></div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:16px">
      <button class="ghost-btn" id="_cuCancel">取消</button>
      <button class="primary-btn" id="_cuSubmit">创建</button>
    </div>`);
  m.addEventListener('click',e=>{if(e.target===m)m.style.display='none';});
  document.getElementById('_cuCancel').onclick=()=>{m.style.display='none';};
  document.getElementById('_cuSubmit').onclick=async()=>{
    const username=document.getElementById('_cuUsername').value.trim();
    const password=document.getElementById('_cuPassword').value;
    const display_name=document.getElementById('_cuDisplayName').value.trim();
    const role=document.getElementById('_cuRole').value;
    const msg=document.getElementById('_cuMsg');
    msg.style.color='#dc2626';msg.textContent='';
    if(!username||!password){msg.textContent='用户名和密码不能为空';return;}
    if(password.length<6){msg.textContent='密码不能少于6位';return;}
    const btn=document.getElementById('_cuSubmit');btn.disabled=true;btn.textContent='创建中…';
    try{
      const res=await apiFetch('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password,display_name:display_name||undefined,role})});
      if(!res){return;}
      if(res.ok){m.style.display='none';loadUsers();}
      else{const d=await res.json().catch(()=>({}));msg.textContent=d.detail||'创建失败';}
    }catch(e){msg.textContent='网络错误';}
    btn.disabled=false;btn.textContent='创建';
  };
  document.getElementById('_cuUsername').focus();
}

function showEditUserModal(username){
  apiFetch('/api/users').then(r=>r.ok?r.json():null).then(data=>{
    if(!data)return;
    const u=data.users.find(x=>x.username===username);
    if(!u)return;
    const m=_userModal(`
      <div style="font-size:17px;font-weight:700;margin-bottom:20px">编辑用户：${escapeHtml(username)}</div>
      <div style="display:grid;gap:12px">
        <div><label style="font-size:13px;color:#667085;display:block;margin-bottom:4px">显示名</label><input id="_euDisplayName" value="${escapeHtml(u.display_name||'')}" style="width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box" /></div>
        <div><label style="font-size:13px;color:#667085;display:block;margin-bottom:4px">角色</label><select id="_euRole" style="width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box"><option value="user" ${u.role==='user'?'selected':''}>普通用户</option><option value="admin" ${u.role==='admin'?'selected':''}>管理员</option></select></div>
        <div><label style="font-size:13px;color:#667085;display:block;margin-bottom:4px">账号状态</label><select id="_euActive" style="width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box"><option value="true" ${u.is_active?'selected':''}>启用</option><option value="false" ${!u.is_active?'selected':''}>禁用</option></select></div>
      </div>
      <div id="_euMsg" style="font-size:13px;min-height:18px;margin-top:12px"></div>
      <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:16px">
        <button class="ghost-btn" id="_euCancel">取消</button>
        <button class="primary-btn" id="_euSubmit">保存</button>
      </div>`);
    m.addEventListener('click',e=>{if(e.target===m)m.style.display='none';});
    document.getElementById('_euCancel').onclick=()=>{m.style.display='none';};
    document.getElementById('_euSubmit').onclick=async()=>{
      const body={
        display_name:document.getElementById('_euDisplayName').value.trim()||null,
        role:document.getElementById('_euRole').value,
        is_active:document.getElementById('_euActive').value==='true',
      };
      const msg=document.getElementById('_euMsg');msg.style.color='#dc2626';msg.textContent='';
      const btn=document.getElementById('_euSubmit');btn.disabled=true;btn.textContent='保存中…';
      try{
        const res=await apiFetch(`/api/users/${encodeURIComponent(username)}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        if(!res)return;
        if(res.ok){m.style.display='none';loadUsers();}
        else{const d=await res.json().catch(()=>({}));msg.textContent=d.detail||'保存失败';}
      }catch(e){msg.textContent='网络错误';}
      btn.disabled=false;btn.textContent='保存';
    };
  });
}

function showResetPwdModal(username){
  const m=_userModal(`
    <div style="font-size:17px;font-weight:700;margin-bottom:20px">重置密码：${escapeHtml(username)}</div>
    <div><label style="font-size:13px;color:#667085;display:block;margin-bottom:4px">新密码 *</label><input id="_rpPassword" type="password" style="width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box" /></div>
    <p style="font-size:12px;color:#667085;margin:8px 0 0">重置后该用户的所有已登录会话将失效，需要用新密码重新登录。</p>
    <div id="_rpMsg" style="font-size:13px;min-height:18px;margin-top:12px"></div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:16px">
      <button class="ghost-btn" id="_rpCancel">取消</button>
      <button class="primary-btn" id="_rpSubmit">重置</button>
    </div>`);
  m.addEventListener('click',e=>{if(e.target===m)m.style.display='none';});
  document.getElementById('_rpCancel').onclick=()=>{m.style.display='none';};
  document.getElementById('_rpSubmit').onclick=async()=>{
    const password=document.getElementById('_rpPassword').value;
    const msg=document.getElementById('_rpMsg');msg.style.color='#dc2626';msg.textContent='';
    if(password.length<6){msg.textContent='密码不能少于6位';return;}
    const btn=document.getElementById('_rpSubmit');btn.disabled=true;btn.textContent='重置中…';
    try{
      const res=await apiFetch(`/api/users/${encodeURIComponent(username)}/reset-password`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({new_password:password})});
      if(!res)return;
      if(res.ok){m.style.display='none';loadUsers();}
      else{const d=await res.json().catch(()=>({}));msg.textContent=d.detail||'重置失败';}
    }catch(e){msg.textContent='网络错误';}
    btn.disabled=false;btn.textContent='重置';
  };
  document.getElementById('_rpPassword').focus();
}

function confirmDeleteUser(username){
  const m=_userModal(`
    <div style="font-size:17px;font-weight:700;margin-bottom:12px;color:#dc2626">确认删除</div>
    <p style="font-size:14px;color:#475467;line-height:1.6">确定要删除用户 <strong>${escapeHtml(username)}</strong> 吗？此操作不可撤销，该用户的所有数据将被永久移除。</p>
    <div id="_dlMsg" style="font-size:13px;min-height:18px;margin-top:12px"></div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:20px">
      <button class="ghost-btn" id="_dlCancel">取消</button>
      <button id="_dlConfirm" style="border:0;border-radius:11px;cursor:pointer;font-weight:650;background:#dc2626;color:#fff;padding:0 18px;height:38px">删除</button>
    </div>`);
  m.addEventListener('click',e=>{if(e.target===m)m.style.display='none';});
  document.getElementById('_dlCancel').onclick=()=>{m.style.display='none';};
  document.getElementById('_dlConfirm').onclick=async()=>{
    const btn=document.getElementById('_dlConfirm');btn.disabled=true;btn.textContent='删除中…';
    try{
      const res=await apiFetch(`/api/users/${encodeURIComponent(username)}`,{method:'DELETE'});
      if(!res)return;
      if(res.status===204){m.style.display='none';loadUsers();}
      else{const d=await res.json().catch(()=>({}));document.getElementById('_dlMsg').textContent=d.detail||'删除失败';}
    }catch(e){document.getElementById('_dlMsg').textContent='网络错误';}
    btn.disabled=false;btn.textContent='删除';
  };
}
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
window.addEventListener("hashchange",render);
window.addEventListener("DOMContentLoaded",async()=>{await loadCurrentUser();render();});

/* ── 资料库（in-app 视图，替代独立页跳转，保留左侧导航） ── */
let libRefreshTimer=null,libOffset=0,libTotal=0,libIsAdmin=false;
const libStatusLabels={pending:"待分类",processing:"分类中",classified:"已分类",unclassified:"未分类",irrelevant:"不相关",failed:"分类失败",legacy_unclassified:"历史未分类",embedding_pending:"待索引",embedding_processing:"索引中",embedding_failed:"索引失败",embedding_skipped:"未索引",embedding_legacy_unindexed:"历史未索引",ready:"可检索"};
function reviewedEmptyCard(){return `<div class="dashboard-card reviewed-empty"><div class="reviewed-empty-mark">无</div><strong>暂无已审核报告</strong><span>深度调研完成审核后将展示在这里</span></div>`;}
function libraryView(){return `<section class="flat-content library"><div class="lib-head"><div><h1 class="section-title">管理员上传的资料，登录用户可下载</h1></div><div class="filter-row"><select id="srcFilter" aria-label="来源类型"><option value="">全部来源</option><option>论文</option><option>专利</option><option>研报</option><option>网页快照</option><option>同事材料</option><option>付费数据库</option><option>其他</option></select><select id="categoryFilter" aria-label="业务分类"><option value="">全部分类</option></select><select id="statusFilter" aria-label="分类状态"><option value="">全部状态</option><option value="pending">待分类</option><option value="processing">分类中</option><option value="classified">已分类</option><option value="unclassified">未分类</option><option value="irrelevant">不相关</option><option value="failed">分类失败</option><option value="legacy_unclassified">历史未分类</option></select><a class="secondary-btn" id="uploadLink" href="uploads_admin.html" style="display:none;">上传资料</a></div></div><div class="table-scroll lib-table-scroll"><table><thead><tr><th>资料</th><th>分类</th><th>状态</th><th>来源类型</th><th>密级</th><th>大小</th><th>上传者</th><th>时间</th><th></th></tr></thead><tbody id="rows"></tbody></table></div><div id="emptyMsg" class="lib-empty" style="display:none;">暂无资料</div><div class="lib-foot"><span class="lib-count" id="countInfo"></span><div class="row-actions"><button class="secondary-btn" id="prevBtn" type="button">上一页</button><button class="secondary-btn" id="nextBtn" type="button">下一页</button></div></div></section>`;}
function libFmtSize(n){if(!n)return "-";const u=["B","KB","MB","GB"];let i=0,s=n;while(s>=1024&&i<3){s/=1024;i++;}return s.toFixed(s<10?1:0)+" "+u[i];}
function libFmtTime(iso){if(!iso)return "-";const d=new Date(iso);return isNaN(d)?"-":d.toLocaleString("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"});}
async function initLibrary(){
  libOffset=0;
  ["srcFilter","categoryFilter","statusFilter"].forEach(id=>{const el=document.getElementById(id);if(el)el.onchange=()=>{libOffset=0;loadLibrary();};});
  const prev=document.getElementById("prevBtn"),next=document.getElementById("nextBtn");
  if(prev)prev.onclick=()=>{libOffset=Math.max(0,libOffset-30);loadLibrary();};
  if(next)next.onclick=()=>{if(libOffset+30<libTotal){libOffset+=30;loadLibrary();}};
  try{const me=await apiFetch("/api/auth/me");if(me&&me.ok){const j=await me.json();libIsAdmin=j.role==="admin";const link=document.getElementById("uploadLink");if(libIsAdmin&&link)link.style.display="";}}catch(e){}
  try{const r=await apiFetch("/api/uploads/taxonomy");if(r&&r.ok){const data=await r.json();const select=document.getElementById("categoryFilter");if(select)select.innerHTML='<option value="">全部分类</option>'+data.categories.map(c=>`<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");}}catch(e){}
  loadLibrary();
}
async function loadLibrary(){
  if(libRefreshTimer){clearTimeout(libRefreshTimer);libRefreshTimer=null;}
  const tb=document.getElementById("rows");if(!tb)return;
  const src=document.getElementById("srcFilter")?.value||"";
  const category=document.getElementById("categoryFilter")?.value||"";
  const status=document.getElementById("statusFilter")?.value||"";
  let url="/api/uploads?limit=30&offset="+libOffset;
  if(src)url+="&source_type="+encodeURIComponent(src);
  if(category)url+="&primary_category="+encodeURIComponent(category);
  if(status)url+="&classification_status="+encodeURIComponent(status);
  let r=null;
  try{r=await apiFetch(url);}catch(e){tb.innerHTML='<tr><td colspan="9">资料列表加载失败，请稍后重试</td></tr>';return;}
  if(!r)return;
  if(!r.ok){tb.innerHTML=`<tr><td colspan="9">资料列表加载失败 ${r.status}</td></tr>`;return;}
  let data=null;
  try{data=await r.json();}catch(e){tb.innerHTML='<tr><td colspan="9">资料列表解析失败</td></tr>';return;}
  libTotal=data.count;
  if(libOffset>0&&!data.files.length){libOffset=Math.max(0,libOffset-30);return loadLibrary();}
  const emptyMsg=document.getElementById("emptyMsg");
  if(emptyMsg)emptyMsg.style.display=data.files.length?"none":"block";
  tb.innerHTML=data.files.map(f=>{
    const conf=f.confidentiality?`<span class="tag conf-${escapeHtml(f.confidentiality)}">${escapeHtml(f.confidentiality)}</span>`:"-";
    const aiMark=f.title_source==="manual"?"":`<span class="ai-mark ${escapeHtml(f.title_source||"")}">${f.title_source==="ai_filled"?"AI":"…"}</span>`;
    const canRetry=libIsAdmin&&["failed","unclassified","legacy_unclassified"].includes(f.classification_status);
    const canRetryEmbedding=libIsAdmin&&f.embedding_status==="failed";
    const category=f.primary_category||"-";
    const status=f.ingestion_status||f.classification_status||"legacy_unclassified";
    const statusDetail=f.embedding_error||f.classification_error||f.classification_reason||"";
    return `<tr>
      <td class="fname">${escapeHtml(f.title||f.original_filename)}${aiMark}<small>${escapeHtml(f.original_filename)}${f.note?" · "+escapeHtml(f.note):""}</small></td>
      <td class="category-cell" title="${escapeHtml(category)}">${escapeHtml(category)}</td>
      <td><span class="status ${escapeHtml(status)}" title="${escapeHtml(statusDetail)}">${escapeHtml(libStatusLabels[status]||status)}</span></td>
      <td><span class="src-badge">${escapeHtml(f.source_type||"-")}</span></td>
      <td>${conf}</td>
      <td class="size-cell">${libFmtSize(f.size_bytes)}</td>
      <td>${escapeHtml(f.submitted_by)}</td>
      <td class="size-cell">${libFmtTime(f.created_at)}</td>
      <td><div class="row-actions"><button class="secondary-btn" data-download="${escapeHtml(f.id)}">下载</button>${canRetry?`<button class="secondary-btn" data-retry="${escapeHtml(f.id)}">重试分类</button>`:""}${canRetryEmbedding?`<button class="secondary-btn" data-retry-embedding="${escapeHtml(f.id)}">重试索引</button>`:""}</div></td>
    </tr>`;
  }).join("");
  const start=libTotal?libOffset+1:0,end=Math.min(libOffset+data.files.length,libTotal);
  const count=document.getElementById("countInfo");
  if(count)count.textContent=`共 ${libTotal} 条，当前 ${start}-${end}`;
  const prevBtnEl=document.getElementById("prevBtn"),nextBtnEl=document.getElementById("nextBtn");
  if(prevBtnEl)prevBtnEl.disabled=libOffset===0;
  if(nextBtnEl)nextBtnEl.disabled=libOffset+30>=libTotal;
  tb.querySelectorAll("button[data-download]").forEach(b=>b.onclick=()=>libDownload(b.dataset.download));
  tb.querySelectorAll("button[data-retry]").forEach(b=>b.onclick=()=>libRetry(b.dataset.retry,"classification/retry",b));
  tb.querySelectorAll("button[data-retry-embedding]").forEach(b=>b.onclick=()=>libRetry(b.dataset.retryEmbedding,"embedding/retry",b));
  if(data.files.some(f=>["pending","processing"].includes(f.classification_status)||["pending","processing"].includes(f.embedding_status)))libRefreshTimer=setTimeout(loadLibrary,3000);
}
async function libRetry(id,path,button){
  button.disabled=true;
  try{
    const r=await apiFetch("/api/uploads/"+encodeURIComponent(id)+"/"+path,{method:"POST"});
    if(!r||!r.ok){const data=r?await r.json().catch(()=>({})):{};throw new Error(data.detail||"重试失败");}
    await loadLibrary();
  }catch(e){alert(e.message);button.disabled=false;}
}
function libDownload(id){
  const token=window.Auth&&Auth.getToken?Auth.getToken():"";
  fetch("/api/uploads/"+encodeURIComponent(id)+"/download",{headers:{Authorization:"Bearer "+token}})
    .then(r=>{if(!r.ok)throw new Error("下载失败 "+r.status);return r.blob().then(b=>{const cd=r.headers.get("Content-Disposition")||"";let name="download";const utf8=cd.match(/filename\*=UTF-8''([^;]+)/i);const plain=cd.match(/filename="([^"]+)"/);if(utf8){try{name=decodeURIComponent(utf8[1]);}catch(e){name=utf8[1];}}else if(plain){name=plain[1];}const u=URL.createObjectURL(b);const a=document.createElement("a");a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),0);});})
    .catch(e=>alert(e.message));
}
