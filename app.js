const routes = {
  home: { label: "门户", title: "技术边界门户" },
  breadth: { label: "广度追踪", title: "广度追踪" },
  dashboard: { label: "深度调研", title: "深度调研" },
  map: { label: "行业图景", title: "行业图景" },
  users: { label: "用户管理", title: "用户管理" },
  library: { label: "资料库", title: "资料库" }
};
const navItems = [["home","HOME"],["breadth","BRD"],["dashboard","DDY"],["library","LIB"],["users","USR"]];
/* 侧边栏图标（收起条 + 展开态共用）。
   正式素材：《..AAA UI设计》品牌logo/按键logo 裁切 → assets/nav/*.png；
   图片加载失败时回退内联 SVG。 */
/* 导航图标全部为镂空图片素材；图片加载失败时隐藏，不显示占位符号 */
const NAV_IMG = { home: "assets/nav/portal.png", breadth: "assets/nav/breadth.png", dashboard: "assets/nav/depth.png", library: "assets/nav/lib.png", users: "assets/nav/users.png" };
const navIcon = key => `<img class="sidebar-nav-img" src="${NAV_IMG[key]}" alt="" onerror="this.style.display='none'">`;
/* 品牌 logo：镂空素材（assets/nav/brand.png），与导航图标同尺寸；失败隐藏不显示占位符号 */
const BRAND_LOGO = `<img class="sidebar-brand-img" src="assets/nav/brand.png" alt="" onerror="this.style.display='none'">`;
/* 收起/展开：镂空素材（assets/nav/collapse.png） */
const COLLAPSE_IMG = `<img class="sidebar-collapse-img" src="assets/nav/collapse.png" alt="" onerror="this.style.display='none'">`;
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
let mapUploadsByPath = new Map();
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
  if(!scroller)return;
  const track=document.getElementById('mapXScroll');
  const thumb=document.getElementById('mapXThumb');
  if(track&&thumb){
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
  }
  let dragging=false;
  let startX=0;
  let startY=0;
  let startScroll=0;
  let startTop=0;
  scroller.onpointerdown=event=>{
    if(event.target.closest('a,button,summary,input'))return;
    dragging=true;
    startX=event.clientX;
    startY=event.clientY;
    startScroll=scroller.scrollLeft;
    startTop=scroller.scrollTop;
    scroller.classList.add('dragging');
    scroller.setPointerCapture(event.pointerId);
  };
  scroller.onpointermove=event=>{
    if(!dragging)return;
    scroller.scrollLeft=startScroll-(event.clientX-startX);
    scroller.scrollTop=startTop-(event.clientY-startY);
  };
  scroller.onpointerup=scroller.onpointercancel=()=>{
    dragging=false;
    scroller.classList.remove('dragging');
  };
  syncMapHorizontalBar();
}
window.addEventListener('resize',syncMapHorizontalBar);
let activeSessionId = null;
const conversationRequests = new Set();
const conversationCache = new Map();
let conversationLoadEpoch = 0;
function currentConversationRequest(){return [...conversationRequests].find(request=>request.messages===activeSessionMessages)||null;}
let activeRequestEpoch = 0;
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
  if(msg.role==='user')return `<div class="qa-message user user-msg"><div class="qa-message-content"><div class="qa-message-bubble">${escapeHtml(msg.text||'')}</div></div></div>`;
  const content=msg.text||'';
  const citations=(msg.extra&&msg.extra.citations)||[];
  const isStreaming=Boolean(msg.streaming);
  const isLast=index===activeSessionMessages.length-1;
  const rendered=renderMarkdown(content).replace(/\[(\d+)\]/g,(match,num)=>citations.some(c=>Number(c.id)===Number(num)?true:false)?`<button type="button" class="qa-citation-ref" data-citation="${Number(num)}">[${num}]</button>`:match);
  const body=msg.error?`<div class="qa-error-state"><span>${escapeHtml(msg.error)}</span><button type="button" class="ghost-btn" data-qa-action="retry" data-msg-idx="${index}">重试</button></div>`:`${rendered}${isStreaming?'<span class="qa-typing-cursor"></span>':''}`;
  const actions=!isStreaming&&!msg.error&&content?`<div class="qa-actions"><button class="qa-action-btn" type="button" data-qa-action="copy" data-msg-idx="${index}" title="复制回答">复制</button>${isLast?`<button class="qa-action-btn" type="button" data-qa-action="regenerate" data-msg-idx="${index}" title="重新生成最后一条回答">重新生成</button>`:''}<button class="qa-action-btn" type="button" data-qa-action="export" data-msg-idx="${index}" title="导出 Markdown">导出</button></div>`:'';
  return `<div class="qa-message assistant assistant-msg ${isStreaming?'streaming':''}" data-message-index="${index}"><div class="qa-message-content"><div class="qa-message-bubble"><div class="response-text">${body}</div></div>${msg.status?`<div class="qa-status-line">${escapeHtml(msg.status)}</div>`:''}${!isStreaming&&!msg.error?renderInlineResources(msg.extra):''}${actions}</div></div>`;
}
/* 模型显示名：网关返回的模型 ID 大小写不一（各厂商官方命名不同，值不可改），
   展示层统一为「全大写型号 + 已知能力描述」，value 仍发送原始 ID。 */
const MODEL_LABELS={
  'glm-5.2':'GLM-5.2 深度',
  'glm-5.1':'GLM-5.1 Agent',
  'glm-4.5-flash':'GLM-4.5 Flash 快速',
  'kimi-k2.6':'KIMI-K2.6',
  'deepseek-v4-pro':'DEEPSEEK-V4-PRO',
  'minimax-m2.7':'MINIMAX-M2.7',
};
function modelLabel(model){
  const key=String(model||'').trim().toLowerCase();
  if(MODEL_LABELS[key])return MODEL_LABELS[key];
  return String(model||'').trim().toUpperCase();
}
function renderModelMenu(){return assistantModels.map(model=>`<button type="button" role="option" class="model-menu-item${model===selectedModel?' selected':''}" data-model="${escapeHtml(model)}" aria-selected="${model===selectedModel}"><span class="model-menu-name">${escapeHtml(modelLabel(model))}</span><svg class="model-menu-check" viewBox="0 0 12 10" aria-hidden="true"><path d="M1 5.2 4.4 8.6 11 1.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`).join('');}
function syncModelPicker(){
  const name=document.getElementById('modelPickerName');
  if(name)name.textContent=modelLabel(selectedModel);
  const menu=document.getElementById('modelMenu');
  if(menu)menu.innerHTML=renderModelMenu();
  setModelMenu(false);
}
function setModelMenu(open){
  const menu=document.getElementById('modelMenu');
  const btn=document.getElementById('modelPickerBtn');
  if(!menu||!btn)return;
  menu.hidden=!open;
  btn.setAttribute('aria-expanded',open?'true':'false');
  menu.parentElement.classList.toggle('open',open);
}
async function loadAssistantModels(){
  try{
    const res=await apiFetch('/api/assistant/models');
    if(!res.ok)return;
    const data=await res.json();
    if(Array.isArray(data.models)&&data.models.length){
      assistantModels=data.models;
      if(!assistantModels.includes(selectedModel))selectedModel=data.default_model||assistantModels[0];
      syncModelPicker();
    }
  }catch(_err){}
}
let activeSessionMessages = [];
let conversationSessions = [];
let pendingConversation = null;
/* v7 历史对话游标分页状态 */
let convNextCursor = null;
let convHasMore = false;
let convLoadingMore = false;
let convListFailed = false;
function renderSidebarConversations(){
  const list=document.getElementById('sidebarConversationList');
  if(!list)return;
  const prevScroll=list.scrollTop||convListScrollTop;
  const live=[...conversationRequests].map(request=>({id:request.sessionId||request.localId,title:conversationSessions.find(item=>item.id===request.sessionId)?.title||'新对话'}));
  const items=[...live,...conversationSessions.filter(item=>!live.some(request=>request.id===item.id))];
  if(!items.length){
    list.innerHTML=convListFailed
      ?'<div class="sidebar-conversation-empty">历史对话加载失败 <button type="button" class="conv-retry-btn" id="convRetryBtn">重试</button></div>'
      :'<div class="sidebar-conversation-empty">暂无历史对话</div>';
    bindConvFooter();
    return;
  }
  let footer='';
  if(convListFailed)footer='<div class="conv-list-more conv-list-error">加载失败 <button type="button" class="conv-retry-btn" id="convRetryBtn">重试</button></div>';
  else if(convLoadingMore)footer='<div class="conv-list-more">正在加载…</div>';
  else if(convHasMore)footer='<div class="conv-list-more">向下滚动加载更多</div>';
  else footer='<div class="conv-list-more conv-list-end">没有更多对话了</div>';
  list.innerHTML=items.map(item=>{
    const id=escapeHtml(String(item.id||''));
    const title=escapeHtml(item.title||'未命名对话');
    const pending=Boolean(item.pending);
    const active=pending||item.id===activeSessionId;
    if(pending)return `<div class="sidebar-conversation-row active pending"><div class="sidebar-conversation-item" aria-current="page"><span class="sidebar-conversation-pendot" aria-hidden="true"></span><span class="sidebar-conversation-text">${title}</span></div></div>`;
    return `<div class="sidebar-conversation-row ${active?'active':''}"><button class="sidebar-conversation-item" type="button" data-conversation-id="${id}" title="${title}" aria-current="${active?'page':'false'}"><span class="sidebar-conversation-text">${title}</span></button><button class="sidebar-conversation-delete" type="button" data-delete-conversation="${id}" title="删除此对话" aria-label="删除对话：${title}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg></button></div>`;
  }).join('');
  list.innerHTML+=footer;
  list.scrollTop=prevScroll;
  bindConvFooter();
  /* v7 自动补页：视口过高时首批可能不足以撑出滚动条（触底永远无法触发）。
     内容未溢出且有下一页时自动补一页，直到出现滚动条或没有更多。
     clientHeight>0 排除列表被 hidden（display:none）时的误触发。 */
  if(convHasMore&&!convLoadingMore&&list.clientHeight>0&&list.scrollHeight<=list.clientHeight+4){
    queueMicrotask(()=>loadMoreConversations());
  }
}
/* v7: 底部状态行事件（重试按钮）+ 触底加载 */
function bindConvFooter(){
  const list=document.getElementById('sidebarConversationList');
  if(!list)return;
  const retry=document.getElementById('convRetryBtn');
  if(retry)retry.addEventListener('click',()=>loadMoreConversations(true));
  if(list.dataset.scrollBound!=='1'){
    list.dataset.scrollBound='1';
    list.addEventListener('scroll',()=>{
      convListScrollTop=list.scrollTop;
      if(list.scrollHeight-list.scrollTop-list.clientHeight<24)loadMoreConversations();
    });
  }
}
async function loadMoreConversations(forceRetry=false){
  if(convLoadingMore)return;
  if(!forceRetry&&!convHasMore)return;
  const epoch=conversationLoadEpoch;
  const list=document.getElementById('sidebarConversationList');
  const cursor=convNextCursor;
  if(!cursor&&!forceRetry)return;
  convLoadingMore=true;convListFailed=false;
  renderSidebarConversations();
  try{
    const q=new URLSearchParams({limit:'20'});
    if(cursor)q.set('cursor',cursor);
    const res=await apiFetch('/api/conversations?'+q.toString());
    if(!res.ok)throw new Error(`HTTP ${res.status}`);
    const data=await res.json();
    if(epoch!==conversationLoadEpoch)return; // 切换账号/页面后旧响应作废
    const byId=new Map(conversationSessions.map(s=>[s.id,s]));
    for(const s of (data.sessions||[])){if(!byId.has(s.id))byId.set(s.id,s);}
    conversationSessions=[...byId.values()].sort((a,b)=>(b.updated_at||'').localeCompare(a.updated_at||''));
    convNextCursor=data.next_cursor||null;
    convHasMore=Boolean(data.has_more);
    convLoadingMore=false;convListFailed=false;
    renderSidebarConversations();
  }catch(_err){
    if(epoch!==conversationLoadEpoch)return;
    convLoadingMore=false;convListFailed=true;
    renderSidebarConversations();
  }
}
async function loadConversations(preferredId=null){
  const loadEpoch=conversationLoadEpoch;
  /* v7 修复：侧边栏默认收起时列表元素不存在，但不能因此跳过数据加载——
     否则展开后永远是"暂无历史对话"。渲染由 renderSidebarConversations 自行判空。 */
  try{
    const res=await apiFetch('/api/conversations?limit=20');
    if(!res.ok)throw new Error(`HTTP ${res.status}`);
    const data=await res.json();
    if(loadEpoch!==conversationLoadEpoch)return;
    conversationSessions=data.sessions||[];
    convNextCursor=data.next_cursor||null;
    convHasMore=Boolean(data.has_more);
    convLoadingMore=false;convListFailed=false;
    if(pendingConversation&&conversationSessions.some(item=>item.id===pendingConversation.id))pendingConversation=null;
    const target=preferredId&&conversationSessions.some(item=>item.id===preferredId)
      ?preferredId
      :(activeSessionId&&conversationSessions.some(item=>item.id===activeSessionId)?activeSessionId:null);
    renderSidebarConversations();
    /* v7 刷新即回到列表顶部：旧的长列表滚动位置落到新的 20 条列表上会被钳在
       底部附近，立刻误触"触底加载"，导致刷新后首批就超过 20 条 */
    const freshList=document.getElementById('sidebarConversationList');
    if(freshList){convListScrollTop=0;freshList.scrollTop=0;}
    if(loadEpoch===conversationLoadEpoch&&target&&target!==activeSessionId)await loadConversationMessages(target);
  }catch(_err){
    if(loadEpoch!==conversationLoadEpoch)return;
    convListFailed=true;convLoadingMore=false;convNextCursor=null;convHasMore=false;
    renderSidebarConversations();
  }
}
async function loadConversationMessages(sessionId){
  const loadEpoch=++conversationLoadEpoch;
  const cached=conversationCache.get(sessionId);
  if(cached){
    activeSessionId=sessionId;
    activeSessionMessages=cached;
    renderSidebarConversations();
    refreshConversationSurface();
    syncConversationRequestControls();
    return;
  }
  const res=await apiFetch(`/api/conversations/${encodeURIComponent(sessionId)}/messages?limit=40`);
  if(!res.ok)return;
  const data=await res.json();
  if(loadEpoch!==conversationLoadEpoch)return;
  activeSessionId=sessionId;
  activeSessionMessages=(data.messages||[]).map(message=>({
    role:message.role,text:message.content,
    extra:{citations:message.citations||[],panel_recommendations:message.panel_recommendations||{},retrieval_summary:message.retrieval_summary||{}},
  }));
  renderSidebarConversations();
  refreshConversationSurface();
  syncConversationRequestControls();
}
async function deleteConversation(sessionId){
  if(!sessionId)return;
  const deletingActive=sessionId===activeSessionId;
  const res=await apiFetch(`/api/conversations/${encodeURIComponent(sessionId)}`,{method:'DELETE'});
  if(!res.ok){showToast('删除会话失败');return;}
  const request=[...conversationRequests].find(item=>item.sessionId===sessionId);
  if(request){request.controller.abort();conversationRequests.delete(request);}
  conversationCache.delete(sessionId);
  if(deletingActive)startNewConversation();
  conversationSessions=conversationSessions.filter(item=>item.id!==sessionId);
  renderSidebarConversations();
  await loadConversations(deletingActive?null:activeSessionId);
  showToast('会话已删除');
}
function startNewConversation(){
  conversationLoadEpoch+=1;
  activeSessionId=null;
  activeSessionMessages=[];
  pendingConversation=null;
  const answer=document.getElementById('answer');
  const askBtn=document.getElementById('askBtn');
  const stopBtn=document.getElementById('stopBtn');
  const retryBtn=document.getElementById('retryBtn');
  if(answer)answer.innerHTML=renderHomeMessages();
  if(askBtn){askBtn.disabled=false;askBtn.textContent='发送';}
  if(stopBtn)stopBtn.hidden=true;
  if(retryBtn)retryBtn.hidden=true;
  renderSidebarConversations();
  document.getElementById('queryInput')?.focus();
}
document.addEventListener('click',event=>{
  const deleteAction=event.target?.closest?.('[data-delete-conversation]');
  if(deleteAction){
    event.preventDefault();
    event.stopPropagation();
    deleteConversation(deleteAction.dataset.deleteConversation);
    return;
  }
  const conversationAction=event.target?.closest?.('[data-conversation-id]');
  if(conversationAction){
    const sessionId=conversationAction.dataset.conversationId;
    if(parseHash().route!=='home')setRoute('home');
    if(sessionId&&sessionId!==activeSessionId){activeSessionId=sessionId;loadConversationMessages(sessionId);}
    syncNavHomeActive();
  }
  if(event.target?.id==='stopBtn')currentConversationRequest()?.controller.abort();
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
function render(){if(libRefreshTimer){clearTimeout(libRefreshTimer);libRefreshTimer=null;}closeUploadModal();closeAccountMenu();if(libClassifyClose)libClassifyClose();if(window.Auth&&typeof Auth.requireAuth==="function")Auth.requireAuth();const state=parseHash();document.title=`${routes[state.route].title} · 技术边界数据库`;if(state.route!=="home"&&knowledgeGraphCleanup){knowledgeGraphCleanup();knowledgeGraphCleanup=null;}document.getElementById("app").innerHTML=shell(state);bindEvents();loadConversations();if(state.route==="home"){syncConversationRequestControls();loadAssistantModels();loadHomeBoundaries();loadAlertIntel();loadMeetings();loadKnowledgeGraph();}if(state.route==="dashboard"&&dashTab()==="map")loadIndustryMap();else if(state.route==="dashboard")loadDashboards();if(state.route==="map")loadIndustryMap();if(state.route==="users")loadUsers();if(state.route==="library")initLibrary();}
async function ensureCurrentUser(){if(!currentUser){await loadCurrentUser();}return currentUser;}
function loadCurrentUser(){return apiFetch("/api/auth/me").then(r=>r.ok?r.json():null).then(d=>{if(d){currentUser=d;}}).catch(()=>{});}
function isAdmin(){return currentUser&&currentUser.role==="admin";}
// 资料库权限三级：管理员(上传/下载/删除) > ATSC用户(上传/下载) > 普通用户(仅查看)
const ROLE_LABELS={admin:"管理员",atsc:"ATSC用户",user:"普通用户"};
function canManageFiles(){const r=currentUser&&currentUser.role;return r==="admin"||r==="atsc";}
/* 侧边栏收起/展开：点击切换；每次进入页面一律从收起态开始——
   不再读取/持久化展开偏好（旧版本写过的 sidebar_collapsed 存储一律忽略） */
let sidebarCollapsed=true;
/* v7：切换只重建侧边栏自身（#sidebar 整个 aside），不触碰 .workspace/#main——
   广度 iframe、输入草稿、流式回答、上传/分类弹窗、滚动位置全部原样保留 */
function renderSidebarOnly(){
  const old=document.getElementById('sidebar');
  if(!old){render();return;}
  const accName=(currentUser&&(currentUser.display_name||currentUser.username))||'加载中…';
  const avatarLetter=(accName||'?')[0].toUpperCase();
  const tmp=document.createElement('div');
  tmp.innerHTML=sidebarHtml(parseHash(),accName,avatarLetter);
  const fresh=tmp.firstElementChild;
  old.replaceWith(fresh);
  bindSidebarEvents();
}
function toggleSidebarCollapsed(){sidebarCollapsed=!sidebarCollapsed;renderSidebarOnly();}
/* v5：历史对话列表折叠（仅折叠列表，不动侧边栏宽度） */
let convListCollapsed=false;
function toggleConversationListCollapsed(){convListCollapsed=!convListCollapsed;const btn=document.getElementById("convListToggleBtn");if(btn){btn.setAttribute("aria-expanded",convListCollapsed?"false":"true");btn.querySelector(".sidebar-toggle-chevron")?.classList.toggle("is-down",convListCollapsed);}const list=document.getElementById("sidebarConversationList");if(list)list.hidden=convListCollapsed;}
/* v4：品牌行的收起/展开控件——展开态贴左的 collapse 图标按钮负责收起；
   收起态顶部品牌 logo 悬停变收起/展开图标，点击展开（翻转状态后整行重渲染） */
function collapseSidebar(){if(sidebarCollapsed)return;sidebarCollapsed=true;renderSidebarOnly();}
function expandSidebar(){if(sidebarCollapsed){sidebarCollapsed=false;renderSidebarOnly();}}
/* 导航切换时清除历史对话高亮（深灰底/深蓝字只在正查看该对话时存在） */
function clearActiveConversation(){if(activeSessionId===null)return;activeSessionId=null;renderSidebarConversations();}
/* v5：门户按钮高亮与「是否正查看历史对话」同步 */
function syncNavHomeActive(){const on=parseHash().route==='home'&&activeSessionId===null;document.querySelectorAll('[data-route="home"]').forEach(b=>b.classList.toggle('active',on));}
/* v7：侧边栏 markup 独立成函数——shell 与局部更新（renderSidebarOnly）共用 */
function sidebarHtml(state,accName,avatarLetter){
  const visibleNav=navItems.filter(([key])=>key!=='users'||isAdmin());
  const navHtml=visibleNav.map(([key,code])=>{
    const r=routes[key];
    const icon=`<span class="sidebar-nav-icon" aria-hidden="true">${navIcon(key)}</span>`;
    const label=`<span class="sidebar-nav-label">${r.label}</span>`;
    if(r&&r.href){return `<a class="sidebar-nav-item" href="${r.href}">${icon}${label}</a>`;}
    /* v5：门户高亮=处于门户且未在查看历史对话（点历史对话时门户不亮） */
    const active=state.route===key&&!(key==='home'&&activeSessionId!==null);
    return `<button class="sidebar-nav-item ${active?'active':''}" data-route="${key}">${icon}${label}</button>`;
  }).join("");
  const convHub=sidebarCollapsed
    ?`<section class="sidebar-conversation-hub" aria-label="门户会话" hidden></section>`
    :`<section class="sidebar-conversation-hub" aria-label="门户会话">
      <button class="sidebar-toggle" id="convListToggleBtn" type="button" title="折叠历史对话" aria-expanded="${convListCollapsed?'false':'true'}" aria-controls="sidebarConversationList"><span class="sidebar-nav-label">历史对话</span><svg class="sidebar-toggle-chevron ${convListCollapsed?'is-down':''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 15l-6-6-6 6"/></svg></button>
      <div class="sidebar-conversation-list" id="sidebarConversationList" tabindex="0" aria-label="历史对话列表" ${convListCollapsed?'hidden':''}><div class="sidebar-conversation-empty">正在加载…</div></div>
    </section>`;
  const brandHeader=`<div class="sidebar-brand"><button class="sidebar-brand-btn sidebar-brand-toggle" id="brandToggleBtn" type="button" title="${sidebarCollapsed?'展开侧边栏':'收起侧边栏'}" aria-expanded="${!sidebarCollapsed}" aria-controls="sidebar"><span class="sidebar-nav-icon sidebar-brand-icon"><span class="sidebar-brand-face">${BRAND_LOGO}</span><span class="sidebar-brand-hover">${COLLAPSE_IMG}</span></span><span class="sidebar-nav-label sidebar-title">技术边界数据库</span></button><button class="sidebar-collapse-side" id="collapseSideBtn" type="button" title="${sidebarCollapsed?'展开侧边栏':'收起侧边栏'}" aria-expanded="${!sidebarCollapsed}" aria-controls="sidebar">${COLLAPSE_IMG}</button></div>`;
  return `<aside class="sidebar ${sidebarCollapsed?'collapsed':''}" id="sidebar" aria-label="主导航">${brandHeader}<nav class="sidebar-nav">${navHtml}${convHub}</nav><div class="sidebar-account"><button class="sidebar-account-btn" id="accountBtn" type="button" aria-haspopup="menu" aria-expanded="false" title="${escapeHtml(accName)}"><span class="sidebar-avatar">${escapeHtml(avatarLetter)}</span><span class="sidebar-nav-label sidebar-account-name">${escapeHtml(accName)}</span></button></div></aside>`;
}
function shell(state){
  const data=routes[state.route];
  const accName=(currentUser&&(currentUser.display_name||currentUser.username))||'加载中…';
  const accRole=currentUser?(ROLE_LABELS[currentUser.role]||currentUser.role):'';
  const avatarLetter=(accName||'?')[0].toUpperCase();
  return `${sidebarHtml(state,accName,avatarLetter)}<section class="workspace"><main class="main ${state.route==='home'?'home-main':state.route==='breadth'?'breadth-main':''}" id="main" tabindex="-1">${view(state.route)}</main></section>`;
}
function view(route){const m={home:homeView,breadth:breadthView,dashboard:dashboardView,map:mapView,users:usersView,library:libraryView};return (m[route]||homeView)();}
function closeAccountMenu(){const menu=document.getElementById("accountMenu");if(menu)menu.remove();const btn=document.getElementById("accountBtn");if(btn)btn.setAttribute("aria-expanded","false");}
function toggleAccountMenu(btn){if(document.getElementById("accountMenu")){closeAccountMenu();return;}const menu=document.createElement("div");menu.className="account-menu";menu.id="accountMenu";menu.setAttribute("role","menu");menu.innerHTML=`<button type="button" id="settingsItem" role="menuitem"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33 1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82 1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg><span>设置</span></button><button type="button" id="logoutItem" role="menuitem"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg><span>退出登录</span></button>`;document.body.appendChild(menu);menu.querySelector("#settingsItem").addEventListener("click",()=>{closeAccountMenu();if(window.Auth&&Auth.showChangePassword)Auth.showChangePassword();});menu.querySelector("#logoutItem").addEventListener("click",()=>{closeAccountMenu();if(window.Auth&&Auth.logout)Auth.logout();else location.href="login.html";});const rect=btn.getBoundingClientRect();const menuW=176;const menuH=100;let left=rect.right+10;if(left+menuW>window.innerWidth-8)left=rect.left-menuW-10;let top=Math.min(rect.top,window.innerHeight-menuH-8);menu.style.left=`${Math.max(8,left)}px`;menu.style.top=`${Math.max(8,top)}px`;btn.setAttribute("aria-expanded","true");if(!window.__accountMenuOutsideBound){window.__accountMenuOutsideBound=true;document.addEventListener("click",e=>{if(!e.target.closest("#accountMenu,#accountBtn"))closeAccountMenu();});document.addEventListener("keydown",e=>{if(e.key==="Escape")closeAccountMenu();});window.addEventListener("resize",closeAccountMenu);}}
function homeView(){
  return `<div class="home-body">
  <aside class="home-drawer" id="homeDrawer" aria-label="技术预警、近期会议与技术边界">
    <div class="home-drawer-body">
  <section class="home-section home-alert-section" aria-labelledby="homeAlertTitle">
    <div class="home-section-heading compact">
      <div class="home-alert-heading"><div class="home-alert-title-group"><h2 id="homeAlertTitle">技术预警</h2><span class="home-alert-count" id="homeAlertCount" hidden></span></div><div class="home-alert-pagination" aria-label="技术预警翻页"><button id="homeAlertPrev" type="button" aria-label="上一页" title="上一页"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg></button><span id="homeAlertPageLabel">—</span><button id="homeAlertNext" type="button" aria-label="下一页" title="下一页"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg></button></div></div>
    </div>
    <div class="home-alert-table-wrap" id="alertPanelBody">
      <div class="alert-empty">正在加载技术预警…</div>
    </div>
  </section>
  <section class="home-section home-meeting-section" aria-labelledby="homeMeetingTitle">
    <div class="home-section-heading compact">
      <div class="home-alert-heading"><div class="home-alert-title-group"><h2 id="homeMeetingTitle">近期会议</h2><span class="home-alert-count" id="homeMeetingCount" hidden></span></div><div class="home-alert-pagination" id="homeMeetingPagination" hidden aria-label="近期会议翻页"><button id="homeMeetingPrev" type="button" aria-label="上一页" title="上一页"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg></button><span id="homeMeetingPageLabel">—</span><button id="homeMeetingNext" type="button" aria-label="下一页" title="下一页"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg></button></div></div>
    </div>
    <div class="home-meeting-list" id="homeMeetingList">
      <div class="alert-empty">正在加载会议…</div>
    </div>
  </section>
  <section class="home-section home-boundary-section" aria-labelledby="homeBoundaryTitle">
    <div class="home-section-heading">
      <div class="home-alert-title-group"><h2 id="homeBoundaryTitle">技术边界</h2></div>
      <button class="home-section-link" type="button" data-route="dashboard">查看全部<span aria-hidden="true">→</span></button>
    </div>
    <div class="home-boundary-grid" id="homeBoundaryCards">
      <div class="home-loading-card">正在加载技术边界…</div>
    </div>
  </section>
    </div>
  </aside>
  <button class="home-drawer-tab" id="homeDrawerOpen" type="button" aria-expanded="false" aria-controls="homeDrawer"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg><span>技术预警 · 近期会议 · 技术边界</span></button>
  <section class="home-section home-knowledge-section" aria-label="技术边界数据库问答">
    <div class="panel conversation-panel" id="knowledgeConversation">
      <div class="qa-graph-container" id="qaGraphContainer"><div class="qa-graph-placeholder">正在读取关系图谱…</div></div>
        <div class="model-picker model-picker-top" id="modelPicker">
        <button type="button" class="model-picker-btn" id="modelPickerBtn" aria-haspopup="listbox" aria-expanded="false" title="选择本次回答使用的模型"><span class="model-picker-name" id="modelPickerName">${escapeHtml(modelLabel(selectedModel))}</span><svg class="model-picker-caret" viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        <div class="model-menu" id="modelMenu" role="listbox" aria-label="选择本次回答使用的模型" hidden>${renderModelMenu()}</div>
      </div>
      <div class="qa-empty-state" id="knowledgeEmptyState" ${activeSessionMessages.length?'hidden':''}>
        <div class="qa-empty-copy"><strong>技术边界数据库</strong></div>
        <div class="qa-example-questions"><button type="button" data-example-query="固态电池最新研究进展有哪些？">固态电池最新研究进展有哪些？</button><button type="button" data-example-query="钙钛矿太阳能电池的效率纪录是多少？">钙钛矿太阳能电池的效率纪录是多少？</button><button type="button" data-example-query="锂电池回收技术有哪些新突破？">锂电池回收技术有哪些新突破？</button></div>
      </div>
      <div class="conversation-history" id="answer" ${activeSessionMessages.length?'':'hidden'}>${renderHomeMessages()}</div>
      <div class="query-box qa-input-area">
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
function breadthView(){const source=parseHash().params;const forwarded=new URLSearchParams();['alert','focus_title','focus_date','focus_url','view','cal_year','cal_month'].forEach(key=>{const value=source.get(key);if(value)forwarded.set(key,value);});const query=forwarded.size?`?${forwarded.toString()}`:'';return `<section style="padding:0;overflow:hidden;height:100%;display:flex;flex-direction:column"><div style="flex:1;overflow:hidden;display:block" id="breadthFrameWrap"><iframe src="/breadth/index.html${query}" style="width:100%;height:100%;border:none;display:block" title="广度追踪" allowfullscreen></iframe></div></section>`;}
function dashTab(){return parseHash().params.get('tab')==='map'?'map':'report';}
function dashboardView(){const tab=dashTab();const tabs=[["report","深度调研报告"],["map","行业图景"]];return `<section class="flat-content ${tab==='map'?'map-content-panel':''}"><div class="dash-head"><div class="dash-tabs" role="tablist" aria-label="深度调研视图切换" id="dashTabs">${tabs.map(([key,label])=>`<button class="dash-tab ${tab===key?'active':''}" data-dash-tab="${key}" role="tab" id="dashTab-${key}" aria-selected="${tab===key}" aria-controls="dashPanel" tabindex="${tab===key?0:-1}">${label}</button>`).join('')}</div></div><div role="tabpanel" id="dashPanel" aria-labelledby="dashTab-${tab}">${tab==='map'?mapBody():`<form class="dashboard-search" id="dashboardFilter"><input id="dashboardQ" placeholder="搜索技术、行业或指标，例如 压缩空气、超导、钠电池"/><button class="secondary-btn" type="submit">检索</button></form><div class="dashboard-grid" id="dashboardRows"><div class="status-note">正在加载仪表盘…</div></div>`}</div></section>`;}
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
function mapBody(){const state=parseHash();const group=state.params.get('group')||'zero-carbon';const tabs=[["zero-carbon","零碳产业"],["ai-intelligent","AI与智能科技"],["general-tech","通用技术"]];const titleMap={"zero-carbon":"零碳产业","ai-intelligent":"AI与智能科技","general-tech":"通用技术"};return `<div class="map-head"><div class="map-tools"><input id="mapSearch" value="${escapeHtml(mapSearchDraft)}" placeholder="搜索节点" aria-label="搜索行业图景节点"/><button class="secondary-btn" id="mapExpandAll" type="button">展开全部</button><button class="secondary-btn" id="mapCollapse" type="button">折叠到二级</button></div></div><div class="bookmark-tabs">${tabs.map(([key,label])=>`<button class="bookmark-tab ${group===key?'active':''}" data-map-group="${key}">${label}</button>`).join('')}</div><div class="map-shell"><header class="map-summary"><strong>${titleMap[group]||'零碳产业'}</strong><span id="industryMapMeta">正在加载图景…</span><span class="map-hint">按住空白处拖动平移 · 点击叶子节点查看关联内容</span></header><div class="industry-tree" id="industryTree"><div class="status-note">正在加载图景…</div></div></div>`;}
function mapView(){return `<section class="flat-content map-content-panel"><div class="dash-head"><div class="dash-tabs" role="tablist" aria-label="深度调研视图切换"><button class="dash-tab" data-dash-tab="report" role="tab" aria-selected="false">深度调研报告</button><button class="dash-tab active" data-dash-tab="map" role="tab" aria-selected="true">行业图景</button></div></div>${mapBody()}</section>`;}
/* v7：侧边栏局部事件绑定——renderSidebarOnly 后只重绑 sidebar 内部控件；
   同时恢复历史对话列表内容与滚动位置（侧边栏切换不丢列表/位置） */
let convListScrollTop=0;
function bindSidebarEvents(){
  const collapseSide=document.getElementById("collapseSideBtn");
  if(collapseSide)collapseSide.addEventListener("click",collapseSidebar);
  const brandToggle=document.getElementById("brandToggleBtn");
  if(brandToggle)brandToggle.addEventListener("click",expandSidebar);
  const accountBtn=document.getElementById("accountBtn");
  if(accountBtn)accountBtn.addEventListener("click",e=>{e.stopPropagation();toggleAccountMenu(accountBtn);});
  const convListToggle=document.getElementById("convListToggleBtn");
  if(convListToggle)convListToggle.addEventListener("click",toggleConversationListCollapsed);
  document.querySelectorAll("#sidebar [data-route]").forEach(btn=>btn.addEventListener("click",()=>{const target=btn.dataset.route;const cur=parseHash().route;clearActiveConversation();syncNavHomeActive();if(target==='home'&&cur==='home'){startNewConversation();return;}setRoute(target);}));
  renderSidebarConversations();
  const list=document.getElementById('sidebarConversationList');
  if(list&&convListScrollTop)list.scrollTop=convListScrollTop;
}
function bindEvents(){document.querySelectorAll("[data-route]").forEach(btn=>btn.addEventListener("click",()=>{const target=btn.dataset.route;const cur=parseHash().route;clearActiveConversation();syncNavHomeActive();if(target==='home'&&cur==='home'){startNewConversation();return;}setRoute(target);}));document.querySelectorAll("[data-dash-tab]").forEach(btn=>btn.addEventListener("click",()=>{const p=new URLSearchParams(parseHash().params.toString());p.set('tab',btn.dataset.dashTab);setRoute('dashboard',p);}));bindSidebarEvents();const dashTabs=document.getElementById('dashTabs');if(dashTabs)dashTabs.addEventListener('keydown',e=>{if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;const order=['report','map'];const cur=order.indexOf(dashTab());const next=order[(cur+(e.key==='ArrowRight'?1:order.length-1))%order.length];const p=new URLSearchParams(parseHash().params.toString());p.set('tab',next);setRoute('dashboard',p);});document.querySelectorAll("[data-map-group]").forEach(btn=>btn.addEventListener("click",()=>{const cur=parseHash();const p=new URLSearchParams(cur.params.toString());p.set('group',btn.dataset.mapGroup);p.set('tab','map');setRoute(cur.route==='map'?'map':'dashboard',p);}));const ask=document.getElementById("askBtn");const input=document.getElementById("queryInput");const modelPickerBtn=document.getElementById('modelPickerBtn');const modelMenu=document.getElementById('modelMenu');if(modelPickerBtn&&modelMenu){modelPickerBtn.addEventListener('click',()=>setModelMenu(modelMenu.hidden));modelMenu.addEventListener('click',event=>{const item=event.target.closest('.model-menu-item');if(!item)return;selectedModel=item.dataset.model;localStorage.setItem('assistant_model',selectedModel);syncModelPicker();});}if(!window.__modelMenuOutsideBound){window.__modelMenuOutsideBound=true;document.addEventListener('click',event=>{if(!event.target.closest('.model-picker-top'))setModelMenu(false);});document.addEventListener('keydown',event=>{if(event.key==='Escape')setModelMenu(false);});}if(input){input.value=homeDraft;if(!input.dataset.bound){input.addEventListener('input',()=>{homeDraft=input.value;localStorage.setItem('home_query_draft',homeDraft);input.style.height='auto';input.style.height=`${Math.min(input.scrollHeight,120)}px`;});input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submitQuery();}});input.dataset.bound='1';}}if(ask)ask.addEventListener("click",submitQuery);const homeBodyEl=document.querySelector('.home-body');const homeDrawerOpenBtn=document.getElementById('homeDrawerOpen');const setDrawerCollapsed=(body,collapsed)=>{body.classList.toggle('drawer-collapsed',collapsed);if(homeDrawerOpenBtn)homeDrawerOpenBtn.setAttribute('aria-expanded',collapsed?'true':'false');};if(homeDrawerOpenBtn&&homeBodyEl)homeDrawerOpenBtn.addEventListener('click',()=>setDrawerCollapsed(homeBodyEl,false));if(homeBodyEl&&!window.__homeDrawerOutsideBound){window.__homeDrawerOutsideBound=true;document.addEventListener('click',event=>{const body=document.querySelector('.home-body');if(!body||body.classList.contains('drawer-collapsed'))return;if(!event.target.closest('.home-drawer,.home-drawer-tab'))setDrawerCollapsed(body,true);});}const dashboardFilter=document.getElementById("dashboardFilter");if(dashboardFilter)dashboardFilter.addEventListener("submit",e=>{e.preventDefault();loadDashboards();});const createUserBtn=document.getElementById("createUserBtn");if(createUserBtn)createUserBtn.addEventListener("click",showCreateUserModal);}
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
  const colors={'公司':'#6366f1','机构':'#8b5cf6','技术':'#3b82f6','材料':'#10b981','产品':'#f59e0b','人物':'#ef4444','政策':'#ec4899','指标':'#14b8a6','organization':'#6366f1','artifact':'#f59e0b','concept':'#3b82f6','person':'#ef4444','method':'#a855f7','event':'#f97316','data':'#14b8a6','other':'#94a3b8','UNKNOWN':'#94a3b8'};
  /* 星穹配色工具：高光/暗部/透明色，用于珠光球体与光晕 */
  const lighten=hex=>{const n=parseInt(hex.slice(1),16);return `rgb(${Math.round((n>>16&255)*.45+140.25)},${Math.round((n>>8&255)*.45+140.25)},${Math.round((n&255)*.45+140.25)})`;};
  const deepen=hex=>{const n=parseInt(hex.slice(1),16);return `rgb(${Math.round((n>>16&255)*.76)},${Math.round((n>>8&255)*.76)},${Math.round((n&255)*.76)})`;};
  const withAlpha=(hex,a)=>{const n=parseInt(hex.slice(1),16);return `rgba(${n>>16&255},${n>>8&255},${n&255},${a})`;};
  let width=0,height=0,raf=0,temperature=1,hover=null,drag=null,panning=false,panStart=null,pinned=null,downInfo=null;
  const transform={x:0,y:0,scale:1};
  const nodes=(data.nodes||[]).slice(0,200).map((node,index)=>{const angle=index*2.399963;const radius=18*Math.sqrt(index);const c=colors[node.type]||'#94a3b8';return {...node,x:Math.cos(angle)*radius,y:Math.sin(angle)*radius,vx:0,vy:0,radius:Math.max(4,Math.min(14,4+Number(node.degree||0)*.45)),color:c,light:lighten(c),deep:deepen(c),tw:.6+((index*137)%100)/100*.9,phase:(index*97)%628/100};});
  const nodeMap=new Map(nodes.map(node=>[node.label,node]));
  const edges=(data.edges||[]).filter(edge=>nodeMap.has(edge.source)&&nodeMap.has(edge.target)).slice(0,500);
  const neighborSet=new Map();edges.forEach(edge=>{if(!neighborSet.has(edge.source))neighborSet.set(edge.source,new Set());neighborSet.get(edge.source).add(edge.target);if(!neighborSet.has(edge.target))neighborSet.set(edge.target,new Set());neighborSet.get(edge.target).add(edge.source);});
  let pulses=[];
  function edgeGeom(ei){const edge=edges[ei];const a=nodeMap.get(edge.source),b=nodeMap.get(edge.target);const dx=b.x-a.x,dy=b.y-a.y;const dist=Math.hypot(dx,dy)||1;const bend=(((ei+1)*7919)%997)/997-.5;const off=dist*.14*bend;return {a,b,cx:(a.x+b.x)/2-dy/dist*off,cy:(a.y+b.y)/2+dx/dist*off};}
  function resize(){const rect=container.getBoundingClientRect();width=Math.max(1,Math.round(rect.width));height=Math.max(1,Math.round(rect.height));const ratio=Math.min(window.devicePixelRatio||1,2);canvas.width=width*ratio;canvas.height=height*ratio;canvas.style.width=`${width}px`;canvas.style.height=`${height}px`;ctx.setTransform(ratio,0,0,ratio,0,0);}
  /* ── 星空背景：缓慢漂移的晨曦光斑（无离散星点）+ 偶发流星 ── */
  let meteors=[];
  function drawSky(t){
    const blobs=[
      {c:'129,140,248',ax:width*.78,ay:height*.16,rx:width*.16,ry:height*.2,px:0,py:1.7,w:9e-5,a:.075},
      {c:'56,189,248',ax:width*.12,ay:height*.78,rx:width*.13,ry:height*.18,px:2.1,py:4.2,w:7e-5,a:.06},
      {c:'232,121,249',ax:width*.9,ay:height*.88,rx:width*.11,ry:height*.15,px:4.4,py:.9,w:5.5e-5,a:.05}
    ];
    for(const b of blobs){
      const x=b.ax+Math.sin(t*b.w+b.px)*b.rx;
      const y=b.ay+Math.cos(t*b.w*.8+b.py)*b.ry;
      const r=Math.max(width,height)*.42;
      const g=ctx.createRadialGradient(x,y,0,x,y,r);
      g.addColorStop(0,`rgba(${b.c},${(b.a*(0.8+0.2*Math.sin(t*.0003+b.px*3))).toFixed(3)})`);
      g.addColorStop(1,`rgba(${b.c},0)`);
      ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();
    }
    if(meteors.length<2&&Math.random()<.005)meteors.push({x:width*(.25+Math.random()*.7),y:height*Math.random()*.32,vx:-(4.2+Math.random()*3),vy:2.1+Math.random()*1.4,life:1});
    for(let i=meteors.length-1;i>=0;i--){const m=meteors[i];m.x+=m.vx;m.y+=m.vy;m.life-=.016;if(m.life<=0){meteors.splice(i,1);continue;}
      const tail=9;const grad=ctx.createLinearGradient(m.x,m.y,m.x-m.vx*tail,m.y-m.vy*tail);grad.addColorStop(0,`rgba(99,102,241,${.8*m.life})`);grad.addColorStop(1,'rgba(99,102,241,0)');ctx.strokeStyle=grad;ctx.lineWidth=1.3;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(m.x,m.y);ctx.lineTo(m.x-m.vx*tail,m.y-m.vy*tail);ctx.stroke();}
  }
  function point(event){const rect=canvas.getBoundingClientRect();return {screenX:event.clientX-rect.left,screenY:event.clientY-rect.top,x:(event.clientX-rect.left-transform.x-width/2)/transform.scale,y:(event.clientY-rect.top-transform.y-height/2)/transform.scale};}
  function hit(position){return [...nodes].reverse().find(node=>Math.hypot(position.x-node.x,position.y-node.y)<=node.radius+4)||null;}
  function simulate(){
    if(temperature>.025){for(let i=0;i<nodes.length;i++){for(let j=i+1;j<nodes.length;j++){const a=nodes[i],b=nodes[j],dx=b.x-a.x,dy=b.y-a.y,d2=Math.max(36,dx*dx+dy*dy),force=120/d2*temperature;a.vx-=dx*force;a.vy-=dy*force;b.vx+=dx*force;b.vy+=dy*force;}}edges.forEach(edge=>{const a=nodeMap.get(edge.source),b=nodeMap.get(edge.target),dx=b.x-a.x,dy=b.y-a.y,dist=Math.max(1,Math.hypot(dx,dy)),force=(dist-48)*.0025*temperature;a.vx+=dx/dist*force;a.vy+=dy/dist*force;b.vx-=dx/dist*force;b.vy-=dy/dist*force;});nodes.forEach(node=>{if(node===drag)return;node.vx+=-node.x*.0005*temperature;node.vy+=-node.y*.0005*temperature;node.vx*=.86;node.vy*=.86;node.x+=node.vx;node.y+=node.vy;});temperature*=.994;}
  }
  function draw(){const t=performance.now();const focus=hover||pinned;const nbr=focus?neighborSet.get(focus.label):null;ctx.clearRect(0,0,width,height);drawSky(t);ctx.save();ctx.translate(width/2+transform.x,height/2+transform.y);ctx.scale(transform.scale,transform.scale);edges.forEach((edge,ei)=>{const geo=edgeGeom(ei);const a=geo.a,b=geo.b;const lit=focus&&(a===focus||b===focus);const dim=focus&&!lit;const g=ctx.createLinearGradient(a.x,a.y,b.x,b.y);const al=dim?.06:(lit?.55:.17);g.addColorStop(0,withAlpha(a.color,al));g.addColorStop(1,withAlpha(b.color,al));ctx.strokeStyle=g;ctx.lineWidth=(lit?1.7:1.1)/transform.scale;ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.quadraticCurveTo(geo.cx,geo.cy,b.x,b.y);ctx.stroke();});if(edges.length){if(pulses.length<24&&Math.random()<.1)pulses.push({ei:(Math.random()*edges.length)|0,t:0,sp:.005+Math.random()*.007});for(let pi=pulses.length-1;pi>=0;pi--){const pu=pulses[pi];pu.t+=pu.sp;if(pu.t>=1){pulses.splice(pi,1);continue;}const geo=edgeGeom(pu.ei);const u=1-pu.t;const px=u*u*geo.a.x+2*u*pu.t*geo.cx+pu.t*pu.t*geo.b.x;const py=u*u*geo.a.y+2*u*pu.t*geo.cy+pu.t*pu.t*geo.b.y;const pg=ctx.createRadialGradient(px,py,0,px,py,5);pg.addColorStop(0,'rgba(129,140,248,.55)');pg.addColorStop(1,'rgba(129,140,248,0)');ctx.fillStyle=pg;ctx.beginPath();ctx.arc(px,py,5,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.arc(px,py,1.7,0,Math.PI*2);ctx.fillStyle='rgba(165,180,252,.95)';ctx.fill();ctx.beginPath();ctx.arc(px,py,.85,0,Math.PI*2);ctx.fillStyle='rgba(255,255,255,.95)';ctx.fill();}}nodes.forEach(node=>{const tw=.8+.2*Math.sin(t*.0012*node.tw+node.phase);if(node===focus){ctx.beginPath();ctx.arc(node.x,node.y,node.radius+6,0,Math.PI*2);ctx.fillStyle='rgba(99,102,241,.08)';ctx.fill();ctx.beginPath();ctx.arc(node.x,node.y,node.radius+3.5,0,Math.PI*2);ctx.strokeStyle='rgba(99,102,241,.45)';ctx.lineWidth=1.4/transform.scale;ctx.stroke();}if(node.radius>=5.5){const halo=ctx.createRadialGradient(node.x,node.y,node.radius*.4,node.x,node.y,node.radius*2.6);halo.addColorStop(0,withAlpha(node.color,.2*tw));halo.addColorStop(1,withAlpha(node.color,0));ctx.fillStyle=halo;ctx.beginPath();ctx.arc(node.x,node.y,node.radius*2.6,0,Math.PI*2);ctx.fill();}const rr=node.radius*(node===focus?1.14:1);const orb=ctx.createRadialGradient(node.x-rr*.32,node.y-rr*.36,rr*.1,node.x+rr*.08,node.y+rr*.1,rr*1.02);orb.addColorStop(0,node.light);orb.addColorStop(.52,node.color);orb.addColorStop(1,node.deep);ctx.globalAlpha=tw;ctx.beginPath();ctx.arc(node.x,node.y,rr,0,Math.PI*2);ctx.fillStyle=orb;ctx.fill();ctx.globalAlpha=1;ctx.strokeStyle='rgba(255,255,255,.6)';ctx.lineWidth=1.1/transform.scale;ctx.stroke();if(node===focus||node.radius>9||(nbr&&nbr.has(node.label))){const labelFont=`${10/Math.max(.8,transform.scale)}px -apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif`;ctx.font=labelFont;ctx.textAlign='center';ctx.lineWidth=3/Math.max(.8,transform.scale);ctx.strokeStyle='rgba(255,255,255,.85)';ctx.lineJoin='round';ctx.strokeText(String(node.label||'').slice(0,14),node.x,node.y-node.radius-6);ctx.fillStyle='#475569';ctx.fillText(String(node.label||'').slice(0,14),node.x,node.y-node.radius-6);}});ctx.restore();}
  function animate(){simulate();draw();raf=requestAnimationFrame(animate);}
  function pointerDown(event){const p=point(event);const target=hit(p);downInfo={x:event.clientX,y:event.clientY,node:target};drag=target;if(drag){temperature=Math.max(temperature,.25);}else{panning=true;panStart={x:event.clientX-transform.x,y:event.clientY-transform.y};}canvas.setPointerCapture?.(event.pointerId);}
  function pointerMove(event){const p=point(event);if(drag){drag.x=p.x;drag.y=p.y;drag.vx=0;drag.vy=0;}else if(panning){transform.x=event.clientX-panStart.x;transform.y=event.clientY-panStart.y;}else{hover=hit(p);canvas.style.cursor=hover?'pointer':'grab';if(hover){tooltip.textContent=`${hover.label}（${hover.type||'未知'}） · 连接度 ${hover.degree||0}`;tooltip.style.left=`${p.screenX+12}px`;tooltip.style.top=`${p.screenY+12}px`;tooltip.classList.add('visible');}else tooltip.classList.remove('visible');}}
  function pointerUp(event){if(event&&downInfo&&Math.hypot(event.clientX-downInfo.x,event.clientY-downInfo.y)<=5){if(downInfo.node)pinned=(pinned===downInfo.node?null:downInfo.node);else pinned=null;}drag=null;panning=false;downInfo=null;}
  function wheel(event){event.preventDefault();const before=point(event),next=Math.max(.15,Math.min(4,transform.scale*(event.deltaY>0?.9:1.1)));transform.x+=before.x*(transform.scale-next);transform.y+=before.y*(transform.scale-next);transform.scale=next;}
  resize();canvas.addEventListener('pointerdown',pointerDown);canvas.addEventListener('pointermove',pointerMove);canvas.addEventListener('pointerup',pointerUp);canvas.addEventListener('pointercancel',pointerUp);canvas.addEventListener('pointerleave',()=>{pointerUp();hover=null;tooltip.classList.remove('visible');});canvas.addEventListener('wheel',wheel,{passive:false});window.addEventListener('resize',resize);transform.scale=.85;transform.x=(Math.random()*2-1)*width*.12;transform.y=(Math.random()*2-1)*height*.16;animate();
  return ()=>{cancelAnimationFrame(raf);window.removeEventListener('resize',resize);};
}
function applyIntelParams(params){const qEl=document.getElementById('intelQ');if(qEl&&params.has('q'))qEl.value=params.get('q');const domEl=document.getElementById('intelDomain');if(domEl&&params.has('leaf'))domEl.value=params.get('leaf');const srcEl=document.getElementById('intelSource');if(srcEl&&params.has('source_type'))srcEl.value=params.get('source_type');}

function formatHomeDate(value,fallback='持续更新'){if(!value)return fallback;const date=new Date(value);return Number.isNaN(date.getTime())?String(value).slice(0,10):date.toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'}).replaceAll('/','-');}
function compactHomeText(value,limit=10){const text=String(value||'').replace(/\s+/g,'').trim();return text.length>limit?`${text.slice(0,Math.max(1,limit-1))}…`:text;}
function homeBoundaryDefinition(item){const name=item.name||'该技术';const scope=String(item.scope||'').trim();if(scope&&scope!=='深度调研')return `${name}聚焦${scope.replace(/[。；;]+$/,'')}。`;const verdict=String(item.verdict||'').split(/[。；;]/).map(text=>text.trim()).find(Boolean);return verdict?`${verdict}。`:`${name}的技术定义与适用边界正在持续完善。`;}
function homeBoundaryLines(item){const indicators=(item.key_indicators||[]).slice(0,3).map(ind=>`${ind.name||''}${ind.value&&ind.value!=='—'?`：${ind.value}${ind.unit&&ind.unit!=='—'?ind.unit:''}`:''}`);if(indicators.length)return indicators;const metrics=(item.metrics||[]).slice(0,3);return metrics.length?metrics:['关键指标边界待补充'];}
async function loadHomeBoundaries(){const root=document.getElementById('homeBoundaryCards');if(!root)return;try{const res=await apiFetch('/api/dashboards');const data=await res.json();const all=data.items||[];const items=all.slice().sort((a,b)=>new Date(b.updated_at||0)-new Date(a.updated_at||0)).slice(0,3);if(!items.length){root.innerHTML='<div class="home-loading-card">尚无已发布的技术边界</div>';return;}root.innerHTML=items.map((item,index)=>{const reviewLabel=item.review_status==='validated'?'已审核':item.metric_review_status==='reviewed'?'指标已审阅':'持续更新';return `<button class="home-boundary-card ${index===0?'primary':''}" type="button" data-home-dashboard="${escapeHtml(item.id)}"><div class="boundary-card-meta"><time>${escapeHtml(formatHomeDate(item.updated_at))}</time><span class="boundary-review ${item.review_status==='validated'?'is-ok':'is-live'}">${reviewLabel}</span></div><h3>${escapeHtml(item.name||'未命名技术')}</h3><p class="boundary-card-definition"><strong>是什么</strong><span class="boundary-card-def-text">${escapeHtml(homeBoundaryDefinition(item))}</span></p><div class="boundary-card-label">关键指标边界</div><ol>${homeBoundaryLines(item).map(line=>`<li>${escapeHtml(line)}</li>`).join('')}</ol><div class="boundary-card-action">查看边界详情 <span aria-hidden="true">→</span></div></button>`}).join('');root.querySelectorAll('[data-home-dashboard]').forEach(card=>card.addEventListener('click',()=>showDashboardDetail(card.dataset.homeDashboard)));}catch(err){root.innerHTML='<div class="home-loading-card">技术边界加载失败</div>';}}

const HOME_ALERT_PAGE_SIZE=5;
const HOME_ALERT_TAG_CLASS={'技术突破':'t-breakthrough','政策监管':'t-policy','产业进展':'t-industry','行业观察':'t-watch'};
let homeAlertItems=[];
let homeAlertPage=1;
function homeAlertTarget(item){
  const params=new URLSearchParams({alert:'alert',focus_title:String(item.alert_title||item.title||''),focus_date:String(item.published_at||item.publish_date||''),focus_url:String(item.url||'')});
  return `#breadth?${params.toString()}`;
}
function homeAlertTimestamp(item){
  const value=item.published_at||item.publish_date||'';
  const parsed=Date.parse(value);
  return Number.isFinite(parsed)?parsed:Number.NEGATIVE_INFINITY;
}
function renderHomeAlertPage(){
  const body=document.getElementById('alertPanelBody');
  if(!body)return;
  const pages=Math.max(1,Math.ceil(homeAlertItems.length/HOME_ALERT_PAGE_SIZE));
  homeAlertPage=Math.min(Math.max(1,homeAlertPage),pages);
  const start=(homeAlertPage-1)*HOME_ALERT_PAGE_SIZE;
  const rows=homeAlertItems.slice(start,start+HOME_ALERT_PAGE_SIZE);
  const pageLabel=document.getElementById('homeAlertPageLabel');
  const previous=document.getElementById('homeAlertPrev');
  const next=document.getElementById('homeAlertNext');
  if(pageLabel)pageLabel.textContent=`${homeAlertPage} / ${pages}`;
  if(previous)previous.disabled=homeAlertPage<=1;
  if(next)next.disabled=homeAlertPage>=pages;
  const countLabel=document.getElementById('homeAlertCount');
  if(countLabel){countLabel.textContent=`${homeAlertItems.length} 条`;countLabel.hidden=false;}
  body.innerHTML=`<div class="home-alert-list">${rows.map((item,index)=>{
    const title=item.alert_title||item.title||'未命名情报';
    const publishedTime=item.published_at||item.publish_date||'';
    const domain=item.domain_name||item.domain||String(item.info_item_id||'').split('_')[1]||'待归类';
    const tag=String(item.tag||'').trim();
    /* 预警原因：与广度追踪同源（wr 字段「类别||标题⏎⏎正文」），
       门户版式改写为「类别⏎标题：正文」，红色加粗前缀"预警原因"与全角冒号由标签渲染 */
    const rawReason=String(item.alert_reason||'').replace(/\r\n?/g,'\n').trim();
    let reasonText='';
    const reasonSep=rawReason.indexOf('||');
    if(reasonSep>=0){
      const cat=rawReason.slice(0,reasonSep).trim();
      const rest=rawReason.slice(reasonSep+2).trim();
      const nl=rest.search(/\n/);
      if(nl>=0){
        const title=rest.slice(0,nl).trim();
        const body=rest.slice(nl+1).replace(/^[\n]+/,'').trim();
        reasonText=((cat?cat+'\n':'')+(title?title+'：' : '')+body).trim();
      }else{
        reasonText=((cat?cat+'\n':'')+rest).trim();
      }
    }
    reasonText=(reasonText||rawReason||String(item.reviewer_comment||item.alert_body||item.summary||(item.content||'').slice(0,240)||'').trim())||'持续跟踪';
    const target=homeAlertTarget(item);
    const reasonId=`home-alert-reason-${start+index}`;
    const tagClass=HOME_ALERT_TAG_CLASS[tag]||'';
    const sev=String(item.alert_color||'').toLowerCase().replace(/[^a-z]/g,'')||'normal';
    return `<article class="home-alert-item sev-${sev}"><div class="home-alert-primary">${tag?`<span class="home-alert-tag ${tagClass}">${escapeHtml(tag)}</span>`:''}<span class="home-alert-domain">${escapeHtml(domain)}</span><time datetime="${escapeHtml(publishedTime)}">${escapeHtml(formatHomeDate(publishedTime,'—'))}</time></div><a class="home-alert-title" href="${escapeHtml(target)}" title="${escapeHtml(title)}">${escapeHtml(title)}</a><div class="home-alert-reason"><span class="home-alert-reason-text" id="${reasonId}"><span class="home-alert-reason-label">预警原因</span>：${escapeHtml(reasonText)}</span><button class="home-alert-reason-toggle" type="button" data-alert-reason-toggle aria-controls="${reasonId}" aria-expanded="false" hidden>展开全部</button></div></article>`;
  }).join('')}</div>`;
  requestAnimationFrame(()=>body.querySelectorAll('.home-alert-reason-text').forEach(reason=>{
    const toggle=reason.parentElement?.querySelector('[data-alert-reason-toggle]');
    if(toggle)toggle.hidden=reason.scrollHeight<=reason.clientHeight+1;
  }));
}
async function loadAlertIntel(){
  const body=document.getElementById('alertPanelBody');
  if(!body)return;
  if(!body.dataset.bound){
    body.addEventListener('click',event=>{
      const toggle=event.target.closest?.('[data-alert-reason-toggle]');
      if(!toggle)return;
      const reason=document.getElementById(toggle.getAttribute('aria-controls'));
      if(!reason)return;
      const expanded=toggle.getAttribute('aria-expanded')==='true';
      reason.classList.toggle('expanded',!expanded);
      reason.closest('.home-alert-reason')?.classList.toggle('expanded',!expanded);
      toggle.setAttribute('aria-expanded',expanded?'false':'true');
      toggle.textContent=expanded?'展开全部':'收起';
    });
    body.dataset.bound='1';
  }
  document.getElementById('homeAlertPrev')?.addEventListener('click',()=>{homeAlertPage-=1;renderHomeAlertPage();});
  document.getElementById('homeAlertNext')?.addEventListener('click',()=>{homeAlertPage+=1;renderHomeAlertPage();});
  try{
    const res=await fetch('/breadth/data/processed/alert-records.json',{cache:'no-store'});
    if(!res.ok)throw new Error(`alert snapshot ${res.status}`);
    const data=await res.json();
    homeAlertItems=(Array.isArray(data.items)?data.items:[]).slice().sort((a,b)=>homeAlertTimestamp(b)-homeAlertTimestamp(a));
    homeAlertPage=1;
    if(!homeAlertItems.length){
      body.innerHTML='<div class="alert-empty">当前没有活跃预警情报</div>';
      const pageLabel=document.getElementById('homeAlertPageLabel');
      if(pageLabel)pageLabel.textContent='0 / 0';
      const emptyCount=document.getElementById('homeAlertCount');
      if(emptyCount){emptyCount.textContent='0 条';emptyCount.hidden=false;}
      return;
    }
    renderHomeAlertPage();
  }catch(err){
    body.innerHTML='<div class="alert-empty">技术预警加载失败</div>';
    const failCount=document.getElementById('homeAlertCount');
    if(failCount)failCount.hidden=true;
  }
}

/* ── 近期会议：只显示今天及以后，按日期升序，每页 5 条，单行显示 ── */
const HOME_MEETING_PAGE_SIZE=5;
let homeMeetingItems=[];
let homeMeetingPage=1;
async function loadMeetings(){
  const list=document.getElementById('homeMeetingList');
  if(!list)return;
  document.getElementById('homeMeetingPrev')?.addEventListener('click',()=>{homeMeetingPage-=1;renderHomeMeetingPage();});
  document.getElementById('homeMeetingNext')?.addEventListener('click',()=>{homeMeetingPage+=1;renderHomeMeetingPage();});
  try{
    const res=await fetch('/breadth/data/processed/conferences.json',{cache:'no-store'});
    if(!res.ok)throw new Error(`conferences ${res.status}`);
    const data=await res.json();
    const today=new Date();
    const todayIso=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
    homeMeetingItems=(Array.isArray(data)?data:[])
      .filter(c=>{
        if(!c||!c.name)return false;
        const start=String(c.start_date||'');
        const end=String(c.end_date||'');
        // 今天及以后：未开始的，或已开始但尚未结束（进行中）的都算
        return start>=todayIso||(end&&end>=todayIso);
      })
      .sort((a,b)=>String(a.start_date||'').localeCompare(String(b.start_date||'')));
    homeMeetingPage=1;
    renderHomeMeetingPage();
  }catch(err){
    list.innerHTML='<div class="alert-empty">会议加载失败</div>';
    const count=document.getElementById('homeMeetingCount');
    if(count)count.hidden=true;
  }
}
function renderHomeMeetingPage(){
  const list=document.getElementById('homeMeetingList');
  if(!list)return;
  const total=homeMeetingItems.length;
  const count=document.getElementById('homeMeetingCount');
  if(count){count.textContent=`${total} 场`;count.hidden=total===0;}
  const pagination=document.getElementById('homeMeetingPagination');
  if(pagination)pagination.hidden=total<=HOME_MEETING_PAGE_SIZE;
  if(!total){
    list.innerHTML='<div class="alert-empty">近期暂无会议</div>';
    const pageLabel=document.getElementById('homeMeetingPageLabel');
    if(pageLabel)pageLabel.textContent='0 / 0';
    return;
  }
  const pages=Math.max(1,Math.ceil(total/HOME_MEETING_PAGE_SIZE));
  homeMeetingPage=Math.min(Math.max(1,homeMeetingPage),pages);
  const pageLabel=document.getElementById('homeMeetingPageLabel');
  if(pageLabel)pageLabel.textContent=`${homeMeetingPage} / ${pages}`;
  const start=(homeMeetingPage-1)*HOME_MEETING_PAGE_SIZE;
  list.innerHTML=homeMeetingItems.slice(start,start+HOME_MEETING_PAGE_SIZE).map(item=>{
    const name=String(item.name||'');
    const date=String(item.start_date||'').slice(0,10);
    const end=String(item.end_date||'').slice(0,10);
    const label=end&&end!==date?`${date} ~ ${end}`:date;
    const year=new Date(`${date}T00:00:00`);
    const month=Number.isNaN(year.getTime())?null:year.getMonth()+1;
    const query=new URLSearchParams({view:'calendar'});
    query.set('cal_year',date.slice(0,4));
    if(month)query.set('cal_month',String(month));
    return `<button class="home-meeting-item" type="button" data-meeting-query="${escapeHtml(query.toString())}" title="${escapeHtml(name)}（${escapeHtml(label)}）"><span class="home-meeting-name">${escapeHtml(name)}</span><time class="home-meeting-date">${escapeHtml(label)}</time></button>`;
  }).join('');
  list.querySelectorAll('.home-meeting-item').forEach(btn=>{
    btn.addEventListener('click',()=>{
      // 跳转广度追踪 · 会议日历，并定位到会议所在月份
      setRoute('breadth',new URLSearchParams(btn.dataset.meetingQuery||''));
    });
  });
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
async function loadMapAssets(){const [intelMeta,dashboards,uploadsMeta]=await Promise.allSettled([apiFetch('/api/delivery-intel/category-counts').then(r=>r.ok?r.json():{category_counts:[]}),apiFetch('/api/dashboards').then(r=>r.ok?r.json():{items:[]}),apiFetch('/api/uploads?limit=500').then(r=>r.ok?r.json():{files:[]})]);const intelCounts=intelMeta.status==='fulfilled'&&Array.isArray(intelMeta.value.category_counts)?intelMeta.value.category_counts:[];const uploads=uploadsMeta.status==='fulfilled'&&Array.isArray(uploadsMeta.value.files)?uploadsMeta.value.files:[];return {intelCounts,dashboards:dashboards.status==='fulfilled'&&Array.isArray(dashboards.value.items)?dashboards.value.items:[],uploads};}
function decorateIndustryAssets(node,assets){const children=node.children||[];const skipLabels=new Set(["未分类","不相关",""]);const uploadsByPath=new Map();(assets.uploads||[]).forEach(f=>{const cat=String(f.primary_category||"");if(skipLabels.has(cat))return;if(!uploadsByPath.has(cat))uploadsByPath.set(cat,[]);uploadsByPath.get(cat).push(f);});mapUploadsByPath=uploadsByPath;const decorate=(node)=>{const nodePath=(node.path||[]).join("/");const matched=uploadsByPath.get(nodePath)||[];const kids=node.children||[];const deep=kids.map(decorate).some(Boolean)||matched.length>0;if(!kids.length){const intelLeaf=findIntelLeaf(node,assets.intelCounts);const intelCount=Number(intelLeaf?.count)||0;const dashboards=mapMatchesNode(node,assets.dashboards,dashboardMapText);const matchedDash=dashboards[0];const dashId=matchedDash?.id;node.assets={intel:{active:intelCount>0,count:intelCount,href:'#breadth'},special_issue:{active:false,count:0,href:''},dashboard:{active:!!dashId,count:dashboards.length,dashId:dashId||null},upload:{active:matched.length>0,count:matched.length,files:matched},uploadDeep:deep};}else{node.assets={upload:{active:matched.length>0,count:matched.length,files:matched},uploadDeep:deep};}return deep;};decorate(node);return node;}
function countLeaves(node){const children=node.children||[];return children.length?children.reduce((sum,child)=>sum+countLeaves(child),0):1;}
function leafDots(node){const assets=node.assets||{};const fallbackCoverage=node.coverage||{};const fallbackLinks=node.links||{};const items=[['special_issue','专刊'],['dashboard','行业仪表盘']];const available=items.map(([key,label])=>{const asset=assets[key]||{active:!!fallbackCoverage[key],href:fallbackLinks[key]||'#',count:0};return {key,label,asset,active:!!asset.active};}).filter(item=>item.active);if(!available.length)return '';return `<div class="leaf-tags">${available.map(({key,label,asset})=>{const status=`${label}：${asset.count||1}项`;const state=`${asset.count||1} 项`;
  // Dashboard tag: open full-screen detail directly instead of navigating
  if(key==='dashboard'&&asset.dashId){
    return `<a class="leaf-tag active" data-link-type="${key}" href="#dashboard" onclick="event.preventDefault();setRoute('dashboard');setTimeout(()=>showDashboardDetail('${escapeHtml(asset.dashId)}'),50)" title="${status}"><span>${label}</span><small>${state}</small></a>`;
  }
  const href=asset.href||'#';
  return `<a class="leaf-tag active" data-link-type="${key}" href="${href}" title="${status}"><span>${label}</span><small>${state}</small></a>`;}).join('')}</div>`;}
function mapNodeOwnMatch(node){const q=mapAssetText(mapSearchDraft);if(!q)return false;return mapAssetText([node.title,...(node.path||[])].join(' ')).includes(q);}
function mapNodeVisible(node){const q=mapAssetText(mapSearchDraft);if(!q)return true;if(mapNodeOwnMatch(node))return true;return (node.children||[]).some(mapNodeVisible);}
function nodeReportBtn(node){const up=node.assets&&node.assets.upload;if(!up||!up.active)return '';const path=(node.path||[]).join("/");return `<button type="button" class="node-report-btn" data-report-node="${escapeHtml(path)}" title="查看此节点的专题报告（${up.count} 份）"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>专题报告<span class="n">${up.count}</span></button>`;}
function industryNode(node){if(!mapNodeVisible(node))return '';const children=node.children||[];const leaf=children.length===0;const open=mapSearchDraft||node.depth<mapOpenDepth||!!(node.assets&&node.assets.uploadDeep);const childHtml=children.map(industryNode).join('');const hasReport=!!(node.assets&&node.assets.upload&&node.assets.upload.active);return `<li class="mind-node depth-${node.depth} ${leaf?'leaf':''} ${mapNodeOwnMatch(node)?'match':''} ${hasReport?'has-report':''}"><details ${open?'open':''}><summary class="mind-card"><span class="mind-title${node.title.length>=20?' len-xl':node.title.length>=12?' len-lg':''}">${escapeHtml(node.title)}</span>${nodeReportBtn(node)}</summary>${leaf?leafDots(node):childHtml?`<ul>${childHtml}</ul>`:''}</details></li>`;}
async function loadIndustryMap(){const root=document.getElementById('industryTree');const meta=document.getElementById('industryMapMeta');if(!root)return;const group=parseHash().params.get('group')||'zero-carbon';const titleMap={"zero-carbon":"零碳产业","ai-intelligent":"AI与智能科技","general-tech":"通用技术"};if(meta)meta.textContent=`${titleMap[group]||'零碳产业'}：正在加载 XMind 数据…`;try{const [mapRes,assets]=await Promise.all([apiFetch(`/api/industry-map?group=${encodeURIComponent(group==='zero-carbon'?'零碳产业':group==='ai-intelligent'?'AI与智能科技':'通用技术')}`),loadMapAssets()]);const data=await mapRes.json();const sheet=data.sheet||data.root||data;const rootNode=decorateIndustryAssets(sheet.root||sheet,assets);const sheetTitle=sheet.title||titleMap[group]||'行业图景';if(meta)meta.textContent=`${sheetTitle}：共 ${sheet.node_count||countNodes(rootNode)} 个节点，${countLeaves(rootNode)} 个叶子，最大层级 ${sheet.max_depth||maxDepth(rootNode)}`;root.innerHTML=`<div class="mindmap-canvas"><ul class="mindmap-root">${industryNode(rootNode)}</ul></div>`;root.querySelectorAll("button[data-report-node]").forEach(b=>b.onclick=e=>{e.preventDefault();e.stopPropagation();openReportModal(b.dataset.reportNode);});requestAnimationFrame(initMapHorizontalScroll);}catch(err){root.innerHTML='<div class="status-note">图景加载失败，请检查 XMind 解析数据。</div>';if(meta)meta.textContent='图景加载失败';}}
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
function requestConversationIsVisible(requestState){
  return Boolean(requestState&&activeSessionMessages===requestState.messages);
}
function refreshRequestConversationSurface(requestState){
  if(requestConversationIsVisible(requestState))refreshConversationSurface();
}
function syncConversationRequestControls(){
  const busy=Boolean(currentConversationRequest());
  const askBtn=document.getElementById('askBtn');
  const stopBtn=document.getElementById('stopBtn');
  if(askBtn){askBtn.disabled=busy;askBtn.textContent=busy?'回答中…':'发送';}
  if(stopBtn)stopBtn.hidden=!busy;
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
  if(currentConversationRequest())return;
  conversationLoadEpoch+=1;

  const requestEpoch=++activeRequestEpoch;
  const regenerate=Boolean(options.regenerate);
  const retry=Boolean(options.retry);
  const requestedSessionId=activeSessionId?.startsWith('pending-')?null:activeSessionId;
  const creatingConversation=!requestedSessionId&&!regenerate&&!retry;
  if(creatingConversation){
    pendingConversation={id:`pending-${requestEpoch}`,title:'新对话',pending:true};
    renderSidebarConversations();
  }
  let replacedMessage=null;
  if(regenerate||retry)replacedMessage=activeSessionMessages.pop()||null;
  if(!regenerate&&!retry)activeSessionMessages.push({role:'user',text:query});
  const assistantMsg={role:'assistant',text:'',extra:null,streaming:true,status:'正在连接检索服务…'};
  activeSessionMessages.push(assistantMsg);
  const controller=new AbortController();
  const requestState={epoch:requestEpoch,localId:`pending-${requestEpoch}`,sessionId:requestedSessionId,messages:activeSessionMessages,assistantMsg,controller};
  conversationRequests.add(requestState);
  conversationCache.set(requestedSessionId||requestState.localId,requestState.messages);
  if(!requestedSessionId)activeSessionId=requestState.localId;
  renderSidebarConversations();
  if(input){input.value="";input.style.height='auto';}
  homeDraft="";localStorage.removeItem('home_query_draft');
  refreshConversationSurface();

  let streamCompleted=false;

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
      body:JSON.stringify({query,model:selectedModel,session_id:requestedSessionId||null,regenerate,retry}),
      signal:controller.signal,
    });
    if(!res.ok){
      const errData=await res.json().catch(()=>({detail:`HTTP ${res.status}`}));
      throw new Error(errData.detail||'请求失败');
    }
    requestState.sessionId=res.headers.get('X-Conversation-Id')||requestState.sessionId;
    if(requestState.sessionId)conversationCache.set(requestState.sessionId,requestState.messages);
    if(requestConversationIsVisible(requestState))activeSessionId=requestState.sessionId;
    if(pendingConversation&&requestState.sessionId)pendingConversation={...pendingConversation,id:requestState.sessionId};
    renderSidebarConversations();
    if(creatingConversation)void loadConversations(requestConversationIsVisible(requestState)?requestState.sessionId:null);
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
            refreshRequestConversationSurface(requestState);

          }else if(currentEvent==="token"){
            assistantMsg.text+=data.content||'';
            assistantMsg.status='';
            refreshRequestConversationSurface(requestState);

          }else if(currentEvent==="replace"){
            // The backend may have emitted a partial stream before switching
            // to a complete non-streaming response. Replace the partial text
            // so the persisted answer and the visible answer stay identical.
            assistantMsg.text=String(data.content||'');
            assistantMsg.status='';
            refreshRequestConversationSurface(requestState);

          }else if(currentEvent==="done"){
            const stats=data.retrieval_summary||{};
            assistantMsg.text=data.response||assistantMsg.text;
            assistantMsg.streaming=false;
            assistantMsg.status=data.truncated?'回答达到输出上限，内容可能未完。':'';
            requestState.sessionId=data.session_id||requestState.sessionId;
            if(requestState.sessionId)conversationCache.set(requestState.sessionId,requestState.messages);
            if(requestConversationIsVisible(requestState))activeSessionId=requestState.sessionId;
            assistantMsg.extra={citations:data.citations||[],retrieval_summary:stats,panel_recommendations:{},truncated:Boolean(data.truncated),finish_reason:data.finish_reason||null,fallback_used:Boolean(data.fallback_used)};
            streamCompleted=true;
            refreshRequestConversationSurface(requestState);

          }else if(currentEvent==="error"){
            throw new Error(data.error||'LLM 调用失败');
          }
        }
      }
    }

    if(!streamCompleted)throw new Error('回答流提前结束');
    if(requestConversationIsVisible(requestState))lastFailedQuery='';
    await loadConversations(requestConversationIsVisible(requestState)?requestState.sessionId:null);

  }catch(err){

    if(requestConversationIsVisible(requestState))lastFailedQuery=query;
    const stopped=err?.name==='AbortError';
    if(creatingConversation&&!requestState.sessionId)pendingConversation=null;
    assistantMsg.streaming=false;
    assistantMsg.status='';
    assistantMsg.error=stopped?'已停止生成。':(err?.message||'连接失败，请稍后重试。');
    if(regenerate&&replacedMessage){requestState.messages.pop();requestState.messages.push(replacedMessage);showToast(assistantMsg.error);}
    else refreshRequestConversationSurface(requestState);
    if(retryBtn)retryBtn.hidden=false;
  }finally{
    conversationRequests.delete(requestState);
    renderSidebarConversations();
    syncConversationRequestControls();
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
  return `<div class="qa-citations-block"><div class="qa-citations-title"><strong>来源引用</strong><span>检索 ${count} 条索引记录</span></div>${citations.map((c,index)=>{const id=Number(c.id||index+1);const cm=c.chunk_metadata||{};const location=[cm.page_numbers?.length?`第 ${cm.page_numbers.join("、")} 页`:"",cm.section_title].filter(Boolean).join(" · ");const meta=[c.date,c.source,c.tag,location].filter(Boolean).map(item=>`<span>${escapeHtml(item)}</span>`).join('');const link=c.url?`<a class="qa-citation-link" href="${escapeHtml(c.url)}" target="_blank" rel="noopener noreferrer">原文</a>`:'';return `<article class="qa-citation-item" data-citation-card="${id}"><div class="qa-citation-header"><span class="qa-citation-number">[${id}]</span><span class="qa-citation-title">${escapeHtml(c.title||'未命名情报')}</span></div><div class="qa-citation-meta">${meta}${link}</div>${c.body_snippet?`<p class="qa-citation-snippet">${escapeHtml(c.body_snippet)}</p>`:''}</article>`;}).join('')}</div>`;
}
function escapeHtml(s){return String(s).replace(/[&<>\"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));}

// ═══════════════════════════════════════════════════════
// USER MANAGEMENT
// ═══════════════════════════════════════════════════════

function usersView(){
  return `<section class="panel content-panel">
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
      const roleBadge={admin:'<span style="background:#dbeafe;color:#1e40af;border:1px solid #93c5fd;border-radius:999px;padding:2px 8px;font-size:11px">管理员</span>',atsc:'<span style="background:#e0f2fe;color:#0369a1;border:1px solid #7dd3fc;border-radius:999px;padding:2px 8px;font-size:11px">ATSC用户</span>',user:'<span style="background:#f1f5f9;color:#475467;border:1px solid #e2e8f0;border-radius:999px;padding:2px 8px;font-size:11px">普通用户</span>'};
      const roleLabel=roleBadge[u.role]||esc(u.role);
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
      <div><label style="font-size:13px;color:#667085;display:block;margin-bottom:4px">角色</label><select id="_cuRole" style="width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box"><option value="user">普通用户</option><option value="atsc">ATSC用户</option><option value="admin">管理员</option></select></div>
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
        <div><label style="font-size:13px;color:#667085;display:block;margin-bottom:4px">角色</label><select id="_euRole" style="width:100%;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;box-sizing:border-box"><option value="user" ${u.role==='user'?'selected':''}>普通用户</option><option value="atsc" ${u.role==='atsc'?'selected':''}>ATSC用户</option><option value="admin" ${u.role==='admin'?'selected':''}>管理员</option></select></div>
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
let libRefreshTimer=null,libOffset=0,libTotal=0,libIsAdmin=false,libCanManage=false;
const libStatusLabels={pending:"待分类",processing:"分类中",document_processing:"文档解析中",classified:"已分类",unclassified:"未分类",irrelevant:"不相关",failed:"分类失败",legacy_unclassified:"历史未分类",embedding_pending:"待索引",embedding_processing:"索引中",embedding_failed:"索引未完成",embedding_skipped:"索引未完成",embedding_legacy_unindexed:"历史未索引",ready:"可检索"};
function reviewedEmptyCard(){return `<div class="dashboard-card reviewed-empty"><div class="reviewed-empty-mark">无</div><strong>暂无已审核报告</strong><span>深度调研完成审核后将展示在这里</span></div>`;}
/* v7 资料库三分区：广度追踪(breadth) / 行业追踪(industry) / ATSC内部报告(atsc)。
   广度追踪下再分 GitHub广度情报(github) / 其他广度情报(other)。
   路由约定（hash query）：
     #library                          一级三选一
     #library?section=breadth          广度二级二选一
     #library?section=breadth&sub=github|other   广度子页列表
     #library?section=industry|atsc    列表
   无返回按钮、无面包屑；再点已选中的「广度追踪」回到二级二选一。 */
function libSectionFromParams(params){
  const s=(params.get("section")||"").toLowerCase();
  return ["breadth","industry","atsc"].includes(s)?s:"";
}
function libSubFromParams(params){
  const b=(params.get("sub")||"").toLowerCase();
  return ["github","other"].includes(b)?b:"";
}
function libSectionLabel(section){
  return {breadth:"广度追踪",industry:"行业追踪",atsc:"ATSC内部报告"}[section]||"";
}
function libraryView(){
  const state=parseHash();
  const section=libSectionFromParams(state.params);
  const sub=libSubFromParams(state.params);
  /* 顶部三个一级按钮（无论处于哪层都恒定展示） */
  const navBtn=`<div class="lib-section-nav" role="tablist" aria-label="资料库分区">
    <button class="lib-section-btn${section==="breadth"?" active":""}" type="button" data-lib-section="breadth" aria-pressed="${section==="breadth"}">广度追踪</button>
    <button class="lib-section-btn${section==="industry"?" active":""}" type="button" data-lib-section="industry" aria-pressed="${section==="industry"}">行业追踪</button>
    <button class="lib-section-btn${section==="atsc"?" active":""}" type="button" data-lib-section="atsc" aria-pressed="${section==="atsc"}">ATSC内部报告</button>
  </div>`;
  /* 一级三选一页 */
  if(!section){
    return `<section class="flat-content library"><div class="lib-section-chooser">
      ${navBtn}
      <div class="lib-chooser-hint">请选择要查看的资料分区</div>
    </div></section>`;
  }
  /* 广度二级二选一页 */
  if(section==="breadth"&&!sub){
    return `<section class="flat-content library"><div class="lib-section-chooser">
      ${navBtn}
      <div class="lib-breadth-entries">
        <button class="lib-breadth-entry" type="button" data-lib-sub="github"><span class="lib-breadth-entry-name">GitHub广度情报</span><span class="lib-breadth-entry-desc">来自 GitHub 的广度情报增量包</span></button>
        <button class="lib-breadth-entry" type="button" data-lib-sub="other"><span class="lib-breadth-entry-name">其他广度情报</span><span class="lib-breadth-entry-desc">人工上传整理的广度情报资料</span></button>
      </div>
    </div></section>`;
  }
  /* GitHub增量包页：列头固定为 资料/状态/上传者/上传时间/原文件；无人工等级控件；
     导入协议未接入 → 明确展示"待接入"状态，正式提交入口禁用 */
  if(section==="breadth"&&sub==="github"){
    return `<section class="flat-content library">${navBtn}
      <div class="lib-github-pending">
        <span class="lib-github-pending-badge">待接入</span>
        <span>增量包导入待接入：导入协议尚未确定，正式提交暂未开放。页面就绪不代表导入已完成。</span>
      </div>
      <div class="table-scroll lib-table-scroll"><table><thead><tr><th>资料</th><th>状态</th><th>上传者</th><th>上传时间</th><th>原文件</th></tr></thead><tbody id="rows"></tbody></table></div>
      <div id="emptyMsg" class="lib-empty" style="display:none;"><div class="lib-empty-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></div><div class="lib-empty-title">暂无增量包</div><div class="lib-empty-hint">GitHub 增量包导入协议接入后，此处将展示导入的增量包及其处理状态</div></div>
    </section>`;
  }
  /* 列表页（广度子页或 industry/atsc）：顶部三分区按钮恒定展示 */
  return `<section class="flat-content library">${navBtn}<div class="lib-head"><div class="filter-row"><select id="categoryFilter" aria-label="行业图景节点"><option value="">全部节点</option></select><select id="statusFilter" aria-label="分类状态"><option value="">全部状态</option><option value="pending">待分类</option><option value="processing">分类中</option><option value="classified">已分类</option><option value="unclassified">未分类</option><option value="irrelevant">不相关</option><option value="failed">分类失败</option><option value="legacy_unclassified">历史未分类</option></select><button class="primary-btn" id="uploadLink" type="button" style="display:none;">上传资料</button></div></div><div class="table-scroll lib-table-scroll"><table><thead><tr><th>资料</th><th>行业图景节点</th><th>状态</th><th>资料时间</th><th>上传者</th><th>上传时间</th><th></th></tr></thead><tbody id="rows"></tbody></table></div><div id="emptyMsg" class="lib-empty" style="display:none;"><div class="lib-empty-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></div><div class="lib-empty-title">暂无资料</div><div class="lib-empty-hint">ATSC用户与管理员上传的文档经分类与索引后会显示在这里</div></div><div class="lib-foot"><span class="lib-count" id="countInfo"></span><div class="row-actions"><button class="secondary-btn" id="prevBtn" type="button">上一页</button><button class="secondary-btn" id="nextBtn" type="button">下一页</button></div></div></section>`;
}
function libFmtSize(n){if(!n)return "-";const u=["B","KB","MB","GB"];let i=0,s=n;while(s>=1024&&i<3){s/=1024;i++;}return s.toFixed(s<10?1:0)+" "+u[i];}
function libFmtTime(iso){if(!iso)return "-";const d=new Date(iso);return isNaN(d)?"-":d.toLocaleString("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"});}
async function initLibrary(){
  libOffset=0;libIsAdmin=false;libCanManage=false;
  const state=parseHash();
  const section=libSectionFromParams(state.params);
  const sub=libSubFromParams(state.params);
  /* 一级按钮：广度追踪在子页被再点 → 回二级二选一（去掉 sub）；
     其余按钮 → 进入对应分区；已选中且无子级的按钮不再动作 */
  document.querySelectorAll("[data-lib-section]").forEach(btn=>{
    btn.onclick=()=>{
      const target=btn.dataset.libSection;
      const cur=parseHash();
      const curSection=libSectionFromParams(cur.params);
      const curSub=libSubFromParams(cur.params);
      if(target==="breadth"){
        /* 从子页再点「广度追踪」→ 回到二级二选一（去掉 sub）；
           从一级入口首次点选 → 进入二级二选一 */
        if(!(curSection==="breadth"&&!curSub)){
          const p=new URLSearchParams();p.set("section","breadth");setRoute("library",p);
        }
        return;
      }
      if(curSection===target&&!curSub)return;
      const p=new URLSearchParams();p.set("section",target);setRoute("library",p);
    };
  });
  /* 广度二级入口 → 子页列表（入口随之隐藏，由重渲染完成） */
  document.querySelectorAll("[data-lib-sub]").forEach(btn=>{
    btn.onclick=()=>{
      const p=new URLSearchParams();p.set("section","breadth");p.set("sub",btn.dataset.libSub);setRoute("library",p);
    };
  });
  /* 二选一页没有列表元素，直接返回 */
  if(!section||(section==="breadth"&&!sub))return;
  const isGithub=section==="breadth"&&sub==="github";
  ["categoryFilter","statusFilter"].forEach(id=>{const el=document.getElementById(id);if(el)el.onchange=()=>{libOffset=0;loadLibrary();};});
  const prev=document.getElementById("prevBtn"),next=document.getElementById("nextBtn");
  if(prev)prev.onclick=()=>{libOffset=Math.max(0,libOffset-30);loadLibrary();};
  if(next)next.onclick=()=>{if(libOffset+30<libTotal){libOffset+=30;loadLibrary();}};
  try{const me=await apiFetch("/api/auth/me");if(me&&me.ok){const j=await me.json();libIsAdmin=j.role==="admin";libCanManage=j.role==="admin"||j.role==="atsc";
    /* GitHub增量包页：导入协议未接入 → 不提供上传入口 */
    const link=document.getElementById("uploadLink");if(libCanManage&&link&&!isGithub){link.style.display="";link.onclick=()=>openUploadModal(section,sub);}}}catch(e){}
  try{const r=await apiFetch("/api/uploads/taxonomy");if(r&&r.ok){const data=await r.json();upTaxonomy=data.categories||[];const select=document.getElementById("categoryFilter");if(select){const treePaths=data.all_paths||(data.categories||[]).filter(c=>c.includes("/"));select.innerHTML='<option value="">全部节点</option>'+treePaths.map(c=>`<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("")+'<option value="不相关">不相关</option><option value="未分类">未分类</option>';}}}catch(e){}
  loadLibrary();
}
async function loadLibrary(){
  if(libRefreshTimer){clearTimeout(libRefreshTimer);libRefreshTimer=null;}
  const tb=document.getElementById("rows");if(!tb)return;
  const state=parseHash();
  const section=libSectionFromParams(state.params);
  const sub=libSubFromParams(state.params);
  if(!section||(section==="breadth"&&!sub))return; /* 二选一页无列表 */
  const category=document.getElementById("categoryFilter")?.value||"";
  const status=document.getElementById("statusFilter")?.value||"";
  let url="/api/uploads?limit=30&offset="+libOffset+"&section="+encodeURIComponent(section);
  if(section==="breadth")url+="&breadth_source="+encodeURIComponent(sub);
  if(category)url+="&primary_category="+encodeURIComponent(category);
  if(status)url+="&classification_status="+encodeURIComponent(status);
  let r=null;
  try{r=await apiFetch(url);}catch(e){tb.innerHTML='<tr><td colspan="7">资料列表加载失败，请稍后重试</td></tr>';return;}
  if(!r)return;
  if(!r.ok){tb.innerHTML=`<tr><td colspan="7">资料列表加载失败 ${r.status}</td></tr>`;return;}
  let data=null;
  try{data=await r.json();}catch(e){tb.innerHTML='<tr><td colspan="7">资料列表解析失败</td></tr>';return;}
  libTotal=data.count;
  if(libOffset>0&&!data.files.length){libOffset=Math.max(0,libOffset-30);return loadLibrary();}
  const emptyMsg=document.getElementById("emptyMsg");
  if(emptyMsg)emptyMsg.style.display=data.files.length?"none":"block";
  const tableWrap=tb.closest(".lib-table-scroll"),footEl=document.querySelector(".library .lib-foot");
  if(tableWrap)tableWrap.style.display=data.files.length?"":"none";
  if(footEl)footEl.style.display=data.files.length?"":"none";
  if(isGithub){
    /* GitHub增量包页：仅 5 列（资料/状态/上传者/上传时间/原文件），无人工等级与分类控件 */
    tb.innerHTML=data.files.map(f=>{
      const status=f.ingestion_status||f.classification_status||"legacy_unclassified";
      return `<tr>
      <td class="fname">${escapeHtml(f.title||f.original_filename)}</td>
      <td><span class="status ${escapeHtml(status)}">${escapeHtml(libStatusLabels[status]||status)}</span></td>
      <td>${escapeHtml(f.submitted_by)}</td>
      <td class="size-cell">${libFmtTime(f.created_at)}</td>
      <td>${escapeHtml(f.original_filename)}</td>
    </tr>`;}).join("");
    const countInfo=document.getElementById("countInfo");
    if(countInfo)countInfo.textContent="共 "+libTotal+" 个增量包";
    return;
  }
  tb.innerHTML=data.files.map(f=>{
    const aiMark=f.title_source==="manual"?"":`<span class="ai-mark ${escapeHtml(f.title_source||"")}">${f.title_source==="ai_filled"?"AI":"…"}</span>`;
    const canClassify=libIsAdmin&&["classified","unclassified","irrelevant","legacy_unclassified","failed"].includes(f.classification_status);
    const canRetry=libIsAdmin&&["failed","unclassified","legacy_unclassified"].includes(f.classification_status);
    const canRetryIndex=libIsAdmin&&["failed","skipped"].includes(f.embedding_status);
    const category=f.primary_category||"-";
    const categoryTitle=category.includes("/")?category:"";
    const nodeName=category.includes("/")?category.split("/").pop():category;
    const status=f.ingestion_status||f.classification_status||"legacy_unclassified";
    const statusDetail=f.embedding_error||f.classification_error||f.classification_reason||(status==="document_processing"?"正在执行 Docling 文档理解；首次使用前模型已由启动脚本准备":"");
    const statusSub=(status==="embedding_skipped"||status==="embedding_failed")?"索引未完成，点击「重试构建索引」重新建立":status==="document_processing"?"Docling 解析中":"";
    const docDate=f.document_date||"—";
    const baseName=f.title||f.original_filename||"资料";
    const breadthViewBtn=(section==="breadth"&&sub==="other"&&libCanManage)
      ?`<button class="secondary-btn" data-lib-breadth-view="${escapeHtml(f.id)}" data-bv-title="${escapeHtml(f.title||f.original_filename||"")}" data-bv-date="${escapeHtml(f.document_date||"")}">在广度总表中查看</button>`:"";
    const assetBtns=libCanManage&&f.document_assets?`<button class="secondary-btn" data-lib-asset="${escapeHtml(f.id)}|markdown" data-lib-name="${escapeHtml(baseName+"-document.md")}">Markdown</button><button class="secondary-btn" data-lib-asset="${escapeHtml(f.id)}|chunks" data-lib-name="${escapeHtml(baseName+"-chunks.jsonl")}">Chunk</button>`:"";
    const catActions=(canClassify||canRetry)?`<div class="cat-actions">${canClassify?`<button class="secondary-btn" data-lib-classify="${escapeHtml(f.id)}" data-lib-name="${escapeHtml(baseName)}">人工分类</button>`:""}${canRetry?`<button class="secondary-btn" data-retry="${escapeHtml(f.id)}">重试分类</button>`:""}</div>`:"";
    return `<tr>
      <td class="fname">${escapeHtml(f.title||f.original_filename)}${aiMark}${f.note?`<small>${escapeHtml(f.note)}</small>`:""}</td>
      <td class="category-cell" title="${escapeHtml(categoryTitle||nodeName)}">${escapeHtml(nodeName)}${catActions}</td>
      <td><span class="status ${escapeHtml(status)}" title="${escapeHtml(statusDetail)}">${escapeHtml(libStatusLabels[status]||status)}</span>${statusSub?`<div class="status-sub">${escapeHtml(statusSub)}</div>`:""}${canRetryIndex?`<div class="cat-actions"><button class="secondary-btn" data-retry-index="${escapeHtml(f.id)}">重试构建索引</button></div>`:""}</td>
      <td>${escapeHtml(docDate)}</td>
      <td>${escapeHtml(f.submitted_by)}</td>
      <td class="size-cell">${libFmtTime(f.created_at)}</td>
      <td><div class="row-actions">${breadthViewBtn}${libCanManage?`<button class="secondary-btn" data-lib-rename="${escapeHtml(f.id)}" data-lib-name="${escapeHtml(baseName)}">重命名</button><button class="secondary-btn" data-download="${escapeHtml(f.id)}">原文件</button>${assetBtns}`:""}${libIsAdmin?`<button class="secondary-btn lib-delete-btn" data-lib-delete="${escapeHtml(f.id)}" data-lib-name="${escapeHtml(f.title||f.original_filename)}">删除</button>`:""}</div></td>
    </tr>`;
  }).join("");
  const start=libTotal?libOffset+1:0,end=Math.min(libOffset+data.files.length,libTotal);
  const count=document.getElementById("countInfo");
  if(count)count.textContent=`共 ${libTotal} 条，当前 ${start}-${end}`;
  const prevBtnEl=document.getElementById("prevBtn"),nextBtnEl=document.getElementById("nextBtn");
  if(prevBtnEl)prevBtnEl.disabled=libOffset===0;
  if(nextBtnEl)nextBtnEl.disabled=libOffset+30>=libTotal;
  tb.querySelectorAll("button[data-lib-breadth-view]").forEach(b=>b.onclick=()=>{
    const p=new URLSearchParams();p.set("alert","all");p.set("focus_title",b.dataset.bvTitle);if(b.dataset.bvDate)p.set("focus_date",b.dataset.bvDate);setRoute("breadth",p);
  });
  tb.querySelectorAll("button[data-lib-rename]").forEach(b=>b.onclick=()=>libRename(b.dataset.libRename,b.dataset.libName,b));
  tb.querySelectorAll("button[data-download]").forEach(b=>b.onclick=()=>libDownload(b.dataset.download));
  tb.querySelectorAll("button[data-retry]").forEach(b=>b.onclick=()=>libRetry(b.dataset.retry,"classification/retry",b));
  tb.querySelectorAll("button[data-retry-index]").forEach(b=>b.onclick=()=>libRetry(b.dataset.retryIndex,"embedding/retry",b));
  tb.querySelectorAll("button[data-lib-delete]").forEach(b=>b.onclick=()=>libDelete(b.dataset.libDelete,b.dataset.libName,b));
  tb.querySelectorAll("button[data-lib-classify]").forEach(b=>b.onclick=()=>libClassify(b.dataset.libClassify,b.dataset.libName,b));
  tb.querySelectorAll("button[data-lib-asset]").forEach(b=>b.onclick=()=>{const [id,asset]=b.dataset.libAsset.split("|");libAsset(id,asset,b.dataset.libName,b);});
  if(data.files.some(f=>["pending","processing"].includes(f.classification_status)||["pending","processing"].includes(f.embedding_status)))libRefreshTimer=setTimeout(loadLibrary,3000);
}
function libAsset(id,asset,name,button){
  if(button)button.disabled=true;
  apiFetch(`/api/uploads/${encodeURIComponent(id)}/assets/${encodeURIComponent(asset)}`)
    .then(r=>{if(!r||!r.ok)throw new Error("资产下载失败 "+(r?r.status:""));return r.blob().then(b=>{const u=URL.createObjectURL(b);const a=document.createElement("a");a.href=u;a.download=name||asset;a.click();setTimeout(()=>URL.revokeObjectURL(u),0);});})
    .catch(e=>alert(e.message))
    .finally(()=>{if(button)button.disabled=false;});
}
function reportExtTile(ext){return `<div class="report-ext"><strong>${escapeHtml((ext||"文件").toUpperCase().slice(0,5))}</strong><small>该格式暂无预览</small></div>`;}
function reportCard(f){
  const card=document.createElement("div");card.className="report-card";
  const ext=((f.original_filename||"").split(".").pop()||"").toLowerCase();
  const thumb=document.createElement("div");thumb.className="report-thumb";
  thumb.innerHTML='<div class="report-loading">正在生成首页预览…</div>';
  apiFetch("/api/uploads/"+encodeURIComponent(f.id)+"/preview")
    .then(r=>{if(!r||!r.ok)throw new Error("preview unavailable");return r.blob();})
    .then(b=>{const url=URL.createObjectURL(b);const img=document.createElement("img");img.alt=f.title||f.original_filename||"首页预览";img.onload=()=>URL.revokeObjectURL(url);img.src=url;thumb.innerHTML="";thumb.appendChild(img);})
    .catch(()=>{thumb.innerHTML=reportExtTile(ext);});
  card.appendChild(thumb);
  const body=document.createElement("div");body.className="report-card-body";
  const title=document.createElement("div");title.className="report-title";const titleText=f.title||f.original_filename||"未命名资料";title.textContent=titleText;title.title=titleText;
  const meta=document.createElement("div");meta.className="report-meta";
  meta.innerHTML=`<span>${escapeHtml(libFmtTime(f.created_at))}</span>`;
  body.appendChild(title);body.appendChild(meta);
  const actions=document.createElement("div");actions.className="report-card-actions";
  if(canManageFiles()){
    const btn=document.createElement("button");btn.className="secondary-btn";btn.type="button";btn.textContent="下载原文件";
    btn.onclick=async()=>{btn.disabled=true;try{const r=await apiFetch("/api/uploads/"+encodeURIComponent(f.id)+"/download");if(!r||!r.ok)throw new Error("下载失败 "+(r?r.status:""));const b=await r.blob();const u=URL.createObjectURL(b);const a=document.createElement("a");a.href=u;a.download=f.original_filename||f.title||"资料";a.click();setTimeout(()=>URL.revokeObjectURL(u),0);}catch(e){window.alert(e.message||"下载失败");}finally{btn.disabled=false;}};
    actions.appendChild(btn);
  }
  body.appendChild(actions);
  card.appendChild(body);
  return card;
}
function openReportModal(path){
  if(document.getElementById("reportModalOverlay"))return;
  const files=(mapUploadsByPath instanceof Map?mapUploadsByPath.get(path):null)||[];
  const overlay=document.createElement("div");
  overlay.id="reportModalOverlay";
  overlay.style.cssText="position:fixed;inset:0;z-index:1000;background:rgba(15,23,42,.55);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:24px 16px;overflow-y:auto;";
  overlay.innerHTML=`<div class="lib-upload-dialog" role="dialog" aria-modal="true" aria-label="专题报告" style="width:min(920px,100%);margin:auto;">
    <div class="lib-upload-head"><div><h2>专题报告</h2><div class="report-sub">${escapeHtml(path.split("/").join(" › "))} · ${files.length} 份资料</div></div><button class="lib-upload-close" id="rpCloseBtn" type="button" aria-label="关闭"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button></div>
    <div class="lib-upload-body"><div class="report-grid" id="reportGrid"></div></div>
  </div>`;
  document.body.appendChild(overlay);
  const onEsc=e=>{if(e.key==="Escape")close();};
  const close=()=>{overlay.remove();document.removeEventListener("keydown",onEsc);};
  document.getElementById("rpCloseBtn").onclick=close;
  overlay.addEventListener("click",e=>{if(e.target===overlay)close();});
  document.addEventListener("keydown",onEsc);
  const grid=document.getElementById("reportGrid");
  files.forEach(f=>grid.appendChild(reportCard(f)));
}
function libClassify(id,name,button){
  if(document.getElementById("classifyModalOverlay"))return;
  const overlay=document.createElement("div");
  overlay.id="classifyModalOverlay";
  overlay.style.cssText="position:fixed;inset:0;z-index:1000;background:rgba(15,23,42,.55);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:24px 16px;overflow-y:auto;";
  overlay.innerHTML=`<div class="lib-upload-dialog" role="dialog" aria-modal="true" aria-label="人工分类" style="width:min(460px,100%);margin:auto;">
    <div class="lib-upload-head"><h2>人工分类${name?"："+escapeHtml(name):""}</h2><button class="lib-upload-close" id="clsCloseBtn" type="button" aria-label="关闭"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button></div>
    <div class="lib-upload-body">
      <div class="lib-upload-field"><label for="clsCategory">行业图景节点</label><select id="clsCategory" class="lib-upload-input"><option value="">加载中…</option></select></div>
      <div class="lib-upload-hint" style="font-size:12px;color:var(--text-tertiary);line-height:1.6;">为资料指定行业图景节点（任意层级节点均可）；保存后立即重新建立问答索引（复用已解析资产，不重新解析）。节点仅作标注，不影响资料是否可被检索。</div>
      <div class="lib-upload-result" id="clsResult" style="display:none;"></div>
    </div>
    <div class="lib-upload-actions"><button class="secondary-btn" id="clsCancel" type="button">取消</button><button class="primary-btn" id="clsSubmit" type="button" disabled>保存并重建索引</button></div>
  </div>`;
  document.body.appendChild(overlay);
  const select=document.getElementById("clsCategory"),submit=document.getElementById("clsSubmit");
  apiFetch("/api/uploads/taxonomy").then(r=>r&&r.ok?r.json():null).then(data=>{
    const treePaths=(data&&data.all_paths)||((data&&data.categories)||[]).filter(c=>c.includes("/"));
    const ordered=treePaths.concat(["不相关"]);
    select.innerHTML='<option value="">请选择行业图景节点…</option>'+ordered.map(c=>`<option value="${escapeHtml(c)}">${escapeHtml(c.includes("/")?c.split("/").join(" › "):c)}</option>`).join("");
    submit.disabled=false;
  }).catch(()=>{select.innerHTML='<option value="">分类目录加载失败</option>';});
  select.onchange=()=>{if(select.value==="")submit.disabled=true;};
  const close=()=>{overlay.remove();document.removeEventListener("keydown",onEsc);libClassifyClose=null;};
  libClassifyClose=close;
  const onEsc=e=>{if(e.key==="Escape")close();};
  document.getElementById("clsCloseBtn").onclick=close;
  document.getElementById("clsCancel").onclick=close;
  overlay.addEventListener("click",e=>{if(e.target===overlay)close();});
  document.addEventListener("keydown",onEsc);
  submit.onclick=async()=>{
    const category=select.value;
    if(!category){const result=document.getElementById("clsResult");result.textContent="请先选择行业图景节点";result.className="lib-upload-result err";result.style.display="block";return;}
    submit.disabled=true;
    document.getElementById("clsCancel").disabled=true;
    const result=document.getElementById("clsResult");
    result.style.display="none";
    try{
      const r=await apiFetch("/api/uploads/"+encodeURIComponent(id)+"/classification",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({primary_category:category})});
      if(r&&r.ok){
        close();loadLibrary();
      }else{
        const j=r?await r.json().catch(()=>({})):{};
        result.textContent=j.detail||("保存失败 "+(r?r.status:""));
        result.className="lib-upload-result err";result.style.display="block";
        submit.disabled=false;document.getElementById("clsCancel").disabled=false;
      }
    }catch(e){
      result.textContent="网络错误："+e.message;
      result.className="lib-upload-result err";result.style.display="block";
      submit.disabled=false;document.getElementById("clsCancel").disabled=false;
    }
  };
}
let libClassifyClose=null;
async function libRename(id,name,button){
  if(document.getElementById("libRenameOverlay"))return;
  const overlay=document.createElement("div");
  overlay.id="libRenameOverlay";
  overlay.style.cssText="position:fixed;inset:0;z-index:1001;background:rgba(15,23,42,.55);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:24px 16px;";
  overlay.innerHTML=`<div class="lib-rename-dialog" role="dialog" aria-modal="true" aria-label="重命名资料" style="width:min(460px,100%);margin:auto;background:var(--bg-panel,#fff);border-radius:12px;padding:20px 22px;box-shadow:0 24px 64px rgba(15,23,42,.25);">
    <h2 style="margin:0 0 14px;font-size:16px;">重命名资料</h2>
    <input id="libRenameInput" class="lib-upload-input" style="width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid var(--border-subtle,#d0d5dd);border-radius:8px;font-size:14px;" maxlength="500" value="${escapeHtml(name||"")}" aria-label="资料标题">
    <div id="libRenameMsg" style="min-height:18px;font-size:12px;color:#b42318;margin-top:8px;"></div>
    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:6px;">
      <button class="secondary-btn" id="libRenameCancel" type="button">取消</button>
      <button class="primary-btn" id="libRenameSave" type="button">保存</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  const input=overlay.querySelector("#libRenameInput");
  const msg=overlay.querySelector("#libRenameMsg");
  const save=overlay.querySelector("#libRenameSave");
  const cancel=overlay.querySelector("#libRenameCancel");
  input.focus();input.select();
  const close=()=>{overlay.remove();document.removeEventListener("keydown",onKey);};
  const onKey=(e)=>{if(e.key==="Escape")close();};
  const submit=async()=>{
    const title=input.value.trim();
    if(!title){msg.textContent="标题不能为空";return;}
    save.disabled=true;msg.style.color="#667085";msg.textContent="保存中…（同时同步问答索引）";
    try{
      const r=await apiFetch(`/api/uploads/${encodeURIComponent(id)}/title`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({title})});
      const j=await r.json().catch(()=>({}));
      if(r&&r.ok){close();loadLibrary();}
      else{msg.style.color="#b42318";msg.textContent=j.detail||("保存失败 "+(r?r.status:""));save.disabled=false;}
    }catch(e){msg.style.color="#b42318";msg.textContent="网络错误："+e.message;save.disabled=false;}
  };
  save.onclick=submit;
  cancel.onclick=close;
  input.addEventListener("keydown",(e)=>{if(e.key==="Enter")submit();});
  overlay.addEventListener("click",(e)=>{if(e.target===overlay)close();});
  document.addEventListener("keydown",onKey);
}
async function libDelete(id,name,button){
  if(!window.confirm(`删除「${name||"未命名资料"}」？将同时删除文件与问答索引，不可恢复。`))return;
  button.disabled=true;
  try{
    const r=await apiFetch("/api/uploads/"+encodeURIComponent(id),{method:"DELETE"});
    if(r&&r.ok){ loadLibrary(); }
    else{ const j=await r.json().catch(()=>({})); window.alert(j.detail||("删除失败 "+r.status)); button.disabled=false; }
  }catch(e){ window.alert("网络错误："+e.message); button.disabled=false; }
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
// ── 上传资料：in-app 弹窗，替代 uploads_admin.html 独立页跳转，保留左侧导航 ──
let upPending=[],upTaxonomy=null,upCloseTimer=null;

let upSection="",upSub=""; /* 上传模态框打开时的分区上下文（归属持久化到后端） */
function openUploadModal(section,sub){
  if(!libCanManage&&!canManageFiles())return;
  upSection=section||(parseHash().params.get("section")||"");
  upSub=sub||(parseHash().params.get("sub")||"");
  if(upSection==="breadth"&&!["github","other"].includes(upSub))upSub="";
  /* GitHub增量包导入协议未接入：上传弹窗一律不打开（后端同样拒绝该组合提交） */
  if(upSection==="breadth"&&upSub==="github")return;
  if(!["breadth","industry","atsc"].includes(upSection))upSection="industry";
  if(document.getElementById("uploadModalOverlay"))return;
  const overlay=document.createElement("div");
  overlay.id="uploadModalOverlay";
  overlay.style.cssText="position:fixed;inset:0;z-index:1000;background:rgba(15,23,42,.55);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:24px 16px;overflow-y:auto;";
  /* v6 改版：初始只有拖拽区；选定文件后出现表格（一行一文件，逐行填写元数据）；
     密级/来源类型字段移除；自定义日历替换为原生 date 输入 */
  overlay.innerHTML=`<div class="lib-upload-dialog" role="dialog" aria-modal="true" aria-label="上传资料" style="margin:auto;">
    <div class="lib-upload-head"><h2>上传资料</h2><button class="lib-upload-close" id="upCloseBtn" type="button" aria-label="关闭"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button></div>
    <div class="lib-upload-body">
      <div class="lib-upload-drop" id="upDrop"><input id="upInput" type="file" multiple hidden><div class="lib-upload-hint">拖曳文件至此处，或 <button class="lib-upload-pick" id="upPick" type="button">点击选择文件</button></div><div class="lib-upload-types">支持当前 Docling 文档格式（含扫描件、图片与演示文稿），后台完成解析与索引</div></div>
      <div class="lib-upload-tablewrap" id="upTableWrap" hidden><table class="lib-upload-table"><thead><tr><th>文件</th><th>资料标题</th><th>资料日期</th><th>行业图景节点</th><th>备注</th><th></th></tr></thead><tbody id="upList"></tbody></table></div>
      <div class="lib-upload-result" id="upResult" style="display:none;"></div>
    </div>
    <div class="lib-upload-actions"><button class="secondary-btn" id="upCancel" type="button">取消</button><button class="primary-btn" id="upSubmit" type="button" disabled>上传</button></div>
  </div>`;
  document.body.appendChild(overlay);
  const drop=document.getElementById("upDrop"),input=document.getElementById("upInput");
  apiFetch("/api/uploads/formats").then(r=>r&&r.ok?r.json():null).then(data=>{
    if(!data)return;
    const extensions=[...new Set(Object.values(data.formats).flatMap(f=>f.extensions))];
    overlay.querySelector(".lib-upload-types").title=extensions.join(", ");
    // Do not restrict the picker: MIME-only and newly registered formats stay usable.
  }).catch(()=>{});
  drop.addEventListener("dragover",e=>{e.preventDefault();drop.classList.add("drag");});
  drop.addEventListener("dragleave",()=>drop.classList.remove("drag"));
  drop.addEventListener("drop",e=>{e.preventDefault();drop.classList.remove("drag");upAddFiles(e.dataTransfer.files);});
  document.getElementById("upPick").onclick=()=>input.click();
  input.onchange=()=>{upAddFiles(input.files);input.value="";};
  document.getElementById("upCloseBtn").onclick=closeUploadModal;
  document.getElementById("upCancel").onclick=closeUploadModal;
  document.getElementById("upSubmit").onclick=upSubmit;
  overlay.addEventListener("click",e=>{if(e.target===overlay)closeUploadModal();});
  document.addEventListener("keydown",upEscClose);
  upEnsureTaxonomy();
}
function closeUploadModal(){
  if(upCloseTimer){clearTimeout(upCloseTimer);upCloseTimer=null;}
  const overlay=document.getElementById("uploadModalOverlay");
  if(overlay)overlay.remove();
  upPending=[];
  document.removeEventListener("keydown",upEscClose);
}
function upEscClose(e){if(e.key==="Escape")closeUploadModal();}

/* ── 资料日期：表格内每行原生 date 输入；upNormalizeDate 仅做格式校验兜底 ── */
function upNormalizeDate(value){
  const text=String(value||"").trim();
  if(!text)return "";
  const m=text.match(/^(\d{4})([年\/\-\.])(\d{1,2})\2(\d{1,2})日?(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?$/);
  if(!m)return null;
  const y=+m[1],mo=+m[3],d=+m[4];
  if(mo<1||mo>12||d<1||d>31||y<1970||y>2100)return null;
  const dt=new Date(y,mo-1,d);
  if(dt.getFullYear()!==y||dt.getMonth()!==mo-1||dt.getDate()!==d)return null;
  const pad=n=>String(n).padStart(2,"0");
  return `${y}-${pad(mo)}-${pad(d)}`;
}
/* v7 分段式资料日期输入：YYYY/MM/DD 逐段、自动跳段、整串粘贴、日历选择；
   空值允许（f.upDate=""），只有三段齐全才生成 YYYY-MM-DD 并做日历级校验 */
function upSegmentsToDate(f){
  const y=(f.upY||"").trim(),m=(f.upM||"").trim(),d=(f.upD||"").trim();
  if(!y&&!m&&!d)return "";
  if(y.length===4&&m.length===2&&d.length===2)return upNormalizeDate(`${y}/${m}/${d}`);
  return null; /* 残缺：视为未完成 */
}
function bindUpDateSegments(tr,f){
  const box=tr.querySelector("[data-up-datebox]");
  if(!box)return;
  const segs={
    y:box.querySelector(".lib-up-seg-y"),
    m:box.querySelector(".lib-up-seg-m"),
    d:box.querySelector(".lib-up-seg-d"),
  };
  const native=box.querySelector(".lib-up-native-date");
  const cal=box.querySelector(".lib-up-cal");
  const order=["y","m","d"];
  const syncState=()=>{
    f.upY=segs.y.value;f.upM=segs.m.value;f.upD=segs.d.value;
    const v=upSegmentsToDate(f);
    f.upDate=v===null?"":v; /* 残缺不写入正式值；非法（如13月）也视为空 */
    box.classList.toggle("invalid",v===null||(f.upDate===""&&(f.upY||f.upM||f.upD)));
  };
  const digitsOnly=(el)=>{el.addEventListener("input",()=>{el.value=el.value.replace(/\D/g,"").slice(0,el.maxLength);});};
  Object.values(segs).forEach(digitsOnly);
  order.forEach((k,idx)=>{
    const el=segs[k];
    el.addEventListener("input",()=>{
      el.value=el.value.replace(/\D/g,"");
      if(el.value.length===el.maxLength&&idx<2){segs[order[idx+1]].focus();segs[order[idx+1]].select();}
      syncState();
    });
    el.addEventListener("keydown",(e)=>{
      if(e.key==="Backspace"&&!el.value&&idx>0){segs[order[idx-1]].focus();segs[order[idx-1]].value=segs[order[idx-1]].value.slice(0,-1);syncState();e.preventDefault();}
    });
    el.addEventListener("paste",(e)=>{
      const text=String(e.clipboardData.getData("text")||"").trim();
      const norm=upNormalizeDate(text);
      if(!norm&&!/^\d{1,4}\/\d{1,2}\/\d{1,2}$/.test(text))return; /* 非日期串按默认粘贴 */
      e.preventDefault();
      if(norm){
        const [Y,M,D]=norm.split("-");
        segs.y.value=Y;segs.m.value=M;segs.d.value=D;syncState();
      }else{
        const parts=text.split("/");
        segs.y.value=parts[0].padStart(4,"0").slice(0,4);
        segs.m.value=(parts[1]||"").padStart(2,"0").slice(0,2);
        segs.d.value=(parts[2]||"").padStart(2,"0").slice(0,2);
        syncState();
      }
    });
    el.addEventListener("blur",()=>{ /* 失焦补齐两位（年份除外） */
      if(k!=="y"&&el.value){el.value=el.value.padStart(2,"0");syncState();}
    });
  });
  if(cal){cal.addEventListener("click",()=>{
    if(f.upDate){native.value=f.upDate;}
    else{native.value="";}
    try{native.showPicker();}catch(_e){native.click();}
  });}
  if(native){native.addEventListener("change",()=>{
    const v=native.value; /* YYYY-MM-DD */
    if(!v)return;
    const [Y,M,D]=v.split("-");
    segs.y.value=Y;segs.m.value=M;segs.d.value=D;syncState();
  });}
  box.classList.add("bound");
}
function upAddFiles(fileList){
  const duplicated=[];
  for(const f of fileList){

    if(upPending.some(x=>x.name===f.name&&x.size===f.size)){duplicated.push(f.name);continue;}
    upPending.push(f);
  }
  if(duplicated.length)upShowResult("已添加过（未重复加入）："+duplicated.join("、"),"");
  upRenderList();
}
function upTaxonomyOptions(){
  return '<option value="">不指定，通过AI自动识别</option>'+upTaxonomy.filter(c=>c.includes("/")).map(c=>`<option value="${escapeHtml(c)}">${escapeHtml(c.split("/").join(" › "))}</option>`).join("");
}
/* 单行状态以 upPending 条目为唯一事实源（Codex P1：重渲染不得丢失 done/err 状态）：
   f.upState ∈ ""|"uploading"|"done"|"err"；f.upMsg 为状态列文本 */
function upRowStateMeta(f){
  return {cls:f.upState==="done"?" up-row-done":f.upState==="err"?" up-row-err":"",text:f.upState==="uploading"?"上传中…":(f.upMsg||"")};
}
function upRenderList(){
  const wrap=document.getElementById("upTableWrap"),list=document.getElementById("upList");
  if(!wrap||!list)return;
  const dialog=document.querySelector("#uploadModalOverlay .lib-upload-dialog");
  const has=upPending.length>0;
  wrap.hidden=!has;
  if(dialog)dialog.classList.toggle("has-table",has);
  list.innerHTML=upPending.map((f,i)=>{
    const meta=upRowStateMeta(f);
    return `<tr data-up-row="${i}" class="${meta.cls.trim()}">
      <td class="lib-up-fname" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}<small>${libFmtSize(f.size)}</small></td>
      <td><input class="lib-upload-input lib-up-title" type="text" placeholder="留空则自动识别" aria-label="资料标题" value="${escapeHtml(f.upTitle||"")}"></td>
      <td><div class="lib-up-datebox" data-up-datebox="${i}">
        <input class="lib-upload-input lib-up-seg lib-up-seg-y" inputmode="numeric" maxlength="4" placeholder="YYYY" aria-label="资料日期 年" value="${escapeHtml(f.upY||"")}">/<input class="lib-upload-input lib-up-seg lib-up-seg-m" inputmode="numeric" maxlength="2" placeholder="MM" aria-label="资料日期 月" value="${escapeHtml(f.upM||"")}">/<input class="lib-upload-input lib-up-seg lib-up-seg-d" inputmode="numeric" maxlength="2" placeholder="DD" aria-label="资料日期 日" value="${escapeHtml(f.upD||"")}">
        <input class="lib-up-native-date" type="date" tabindex="-1" aria-hidden="true" value="${escapeHtml(f.upDate||"")}">
        <button class="lib-up-cal" type="button" aria-label="打开日历选择资料日期" title="日历选择"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg></button>
      </div></td>
      <td><select class="lib-upload-input lib-up-cat" aria-label="行业图景节点">${upTaxonomy?upTaxonomyOptions():'<option value="">不指定，通过AI自动识别</option>'}</select></td>
      <td><input class="lib-upload-input lib-up-note" type="text" placeholder="选填" aria-label="备注" value="${escapeHtml(f.upNote||"")}"></td>
      <td class="lib-up-op"><span class="lib-up-state">${escapeHtml(meta.text)}</span><button class="lib-upload-rm" type="button" data-up-rm="${i}">移除</button></td>
    </tr>`;}).join("");
  /* 已选分类回显（value 不能直接内联在 select 上） */
  list.querySelectorAll("[data-up-row]").forEach(tr=>{
    const f=upPending[Number(tr.dataset.upRow)];
    if(f&&f.upCat){const sel=tr.querySelector(".lib-up-cat");if(sel)sel.value=f.upCat;}
  });
  list.querySelectorAll("button[data-up-rm]").forEach(b=>b.onclick=()=>{upPending.splice(Number(b.dataset.upRm),1);upRenderList();});
  upBindRowInputs();
  const submit=document.getElementById("upSubmit");
  if(submit)submit.disabled=upPending.length===0;
  upFillTaxonomy();
}
/* 输入框变化写回 upPending——状态源迁移的配套（编辑后重渲染不丢用户输入） */
function upBindRowInputs(){
  const list=document.getElementById("upList");if(!list)return;
  list.querySelectorAll("[data-up-row]").forEach(tr=>{
    const f=upPending[Number(tr.dataset.upRow)];if(!f)return;
    const bind=(sel,key,trim)=>{const el=tr.querySelector(sel);if(!el)return;
      el.addEventListener("input",()=>{f[key]=trim?el.value.trim():el.value;});};
    bind(".lib-up-title","upTitle",true);
    bind(".lib-up-note","upNote",true);
    bindUpDateSegments(tr,f);
    const cat=tr.querySelector(".lib-up-cat");
    if(cat)cat.addEventListener("change",()=>{f.upCat=cat.value;});
  });
}
function upShowResult(msg,cls){
  const el=document.getElementById("upResult");if(!el)return;
  el.textContent=msg||"";
  el.className="lib-upload-result"+(msg&&cls?" "+cls:"");
  el.style.display=msg?"block":"none";
}
function upFillTaxonomy(){
  document.querySelectorAll("#upList .lib-up-cat").forEach(select=>{
    if(select.options.length>1)return;
    select.innerHTML=upTaxonomyOptions();
  });
}
async function upEnsureTaxonomy(){
  if(upTaxonomy){upFillTaxonomy();return;}
  try{
    const r=await apiFetch("/api/uploads/taxonomy");
    if(r&&r.ok){const data=await r.json();upTaxonomy=data.all_paths||data.categories||[];upFillTaxonomy();return;}
    throw new Error("taxonomy "+(r?r.status:""));
  }catch(e){upShowResult("行业图景节点目录加载失败：可稍后重开弹窗重试，或留空由系统自动分类","err");}
}
async function upSubmit(){
  if(!upPending.length)return;
  const submit=document.getElementById("upSubmit"),cancel=document.getElementById("upCancel");
  if(!submit||submit.disabled)return;
  /* v6.1（Codex P1 修复）：行状态以 upPending 条目为唯一事实源（f.upState/upMsg/upTitle…），
     DOM 仅为投影——重渲染（追加文件/移除行）不会丢失已完成状态与用户输入；
     已成功行（upState==="done"）重试时自动跳过，避免重复创建资料。 */
  const targets=upPending.filter(f=>f.upState!=="done");
  if(!targets.length)return;
  let dateErr=0;
  for(const f of targets){
    if(upNormalizeDate(f.upDate)==null){f.upState="err";f.upMsg="✗ 日期";dateErr++;}
  }
  if(dateErr){upRenderList();upShowResult(`${dateErr} 行的资料日期不合法——已标红，请修正后再上传`,"err");submit.disabled=false;return;}
  submit.disabled=true;cancel.disabled=true;
  upShowResult("正在上传…","");
  let ok=0,fail=0;
  for(const f of targets){
    const fd=new FormData();
    fd.append("files",f);
    if(f.upTitle)fd.append("title",f.upTitle);
    if(f.upCat)fd.append("primary_category",f.upCat);
    if(f.upNote)fd.append("note",f.upNote);
    /* 分区归属：由当前入口决定，持久化到后端 */
    if(upSection)fd.append("primary_section",upSection);
    if(upSection==="breadth"&&upSub)fd.append("breadth_source",upSub);
    const docDate=upNormalizeDate(f.upDate);
    if(docDate)fd.append("document_date",docDate);
    f.upState="uploading";f.upMsg="";
    upRenderList();
    try{
      const r=await apiFetch("/api/uploads",{method:"POST",body:fd});
      if(r&&r.ok){ok++;f.upState="done";f.upMsg="✓";}
      else{fail++;const j=r?await r.json().catch(()=>({})):{};f.upState="err";f.upMsg="✗ "+(j.detail||("HTTP "+(r?r.status:"")));}
    }catch(e){fail++;f.upState="err";f.upMsg="✗ 网络错误";}
    upRenderList();
  }
  const doneCount=upPending.filter(f=>f.upState==="done").length;
  if(fail===0){
    upShowResult(`成功上传 ${ok} 个文件，后台正在分类和索引`,"ok");
    upCloseTimer=setTimeout(()=>{upCloseTimer=null;closeUploadModal();loadLibrary();},1200);
  }else if(doneCount>0){
    upShowResult(`成功 ${doneCount} 个、失败 ${fail} 个——修正标红行后再次点击「上传」，已成功的行不会重复上传`,"err");
    submit.disabled=false;cancel.disabled=false;
  }else{
    upShowResult("上传失败——请修正标红行后重试","err");
    submit.disabled=false;cancel.disabled=false;
  }
}
