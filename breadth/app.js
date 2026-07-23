const PAGE_SIZE = 50;
const HIDDEN_AUTHORS = '手动导入';

// Theme: restore saved preference before anything renders
(function initTheme() {
  // Always default to light, ignore any previously saved preference
  document.documentElement.setAttribute('data-theme', 'light');
})();

const requestedAlertLevel = new URLSearchParams(location.search).get('alert');
const initialAlertLevel = ['crawl', 'filtered', 'aicurated', 'curated', 'key', 'alert'].includes(requestedAlertLevel)
  ? requestedAlertLevel
  : 'aicurated';

const state = {
  manifest: null,
  records: [],
  filtered: [],
  categoryOrder: [],
  page: 1,
  query: '',
  dateFrom: '',
  dateTo: '',
  alertLevel: initialAlertLevel,
  selectedTypes: { news: true, literature: true },
  selectedTags: { news: new Set(), literature: new Set() }, // empty = all
  selectedCategories: null, // null = all selected; Set = specific selection
  categoryQuery: '',
  collapsedGroups: new Set(),
  expandedClusters: new Set(),
  sortBy: 'date',
};

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"]/g, (s) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[s]));

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path} ${response.status}`);
  return response.json();
}

function normalizeCategory(value) {
  return String(value || '');
}

function parseCategoryPath(cat) {
  const parts = cat.split('/');
  return { top: parts[0], full: cat };
}

function buildCategoryTree(useFiltered = false) {
  const counts = new Map();
  for (const item of (useFiltered ? state.filtered : state.records)) {
    const cat = item.category || '未分类';
    counts.set(cat, (counts.get(cat) || 0) + 1);
  }
  const orderedCats = [];
  const seen = new Set();
  for (const path of state.categoryOrder) {
    const normalized = normalizeCategory(path);
    orderedCats.push(normalized);
    seen.add(normalized);
  }
  // Taxonomy is immutable: never append categories invented by data/LLM.
  // Records outside categoryOrder must be repaired by the pipeline, not shown as new tree nodes.

  const q = state.categoryQuery.trim().toLowerCase();
  // Build multi-level tree using / as separator
  const tree = {}; // top-level group name → nested tree
  for (const cat of orderedCats) {
    const count = counts.get(cat) || 0;
    if (q && !cat.toLowerCase().includes(q)) continue;
    const parts = cat.split('/');
    const top = parts[0];
    if (!tree[top]) tree[top] = { count: 0, children: {} };
    // Walk/create nested children
    let node = tree[top];
    node.count += count;
    for (let i = 1; i < parts.length; i++) {
      const key = parts.slice(0, i + 1).join('/');
      if (!node.children[key]) node.children[key] = { count: 0, children: {}, label: parts[i], cat: key };
      node = node.children[key];
      node.count += count;
    }
  }
  // Compute group totals
  const groupTotals = {};
  for (const [top, node] of Object.entries(tree)) groupTotals[top] = node.count;
  return { tree, groupTotals };
}

function renderTreeNode(node, level) {
  const childKeys = Object.keys(node.children).sort((a, b) => node.children[b].count - node.children[a].count);
  if (!childKeys.length) return '';
  const pad = level * 12;
  const html = childKeys.map(key => {
    const child = node.children[key];
    const grandChildren = Object.keys(child.children);
    const hasChildren = grandChildren.length > 0;
    const collapsed = state.collapsedGroups.has(key);
    const fullyChecked = isCategoryFullySelected(key);
    const partialChecked = isCategoryPartiallySelected(key);
    const checkedClass = fullyChecked ? 'checked' : (partialChecked ? 'partial' : '');
    let inner = `<div class="tree-node tree-lvl-${level}" style="padding-left:${pad}px">`;
    if (hasChildren) {
      inner += `<span class="tree-arrow" data-toggle="${esc(key)}">${collapsed ? '▸' : '▾'}</span>`;
    } else {
      inner += `<span class="tree-arrow-spacer"></span>`;
    }
    inner += `<span class="tree-checkbox ${checkedClass}" data-category="${esc(key)}"></span>`;
    inner += `<span class="tree-label" data-category="${esc(key)}">${esc(child.label)}</span><span class="leaf-count">${child.count}</span></div>`;
    if (hasChildren && !collapsed) {
      inner += renderTreeNode(child, level + 1);
    }
    return inner;
  }).join('');
  return html;
}

function getLatestDate() {
  const today = new Date().toISOString().slice(0, 10);
  const dates = [...new Set(state.records.map((r) => r.date).filter(Boolean))].sort();
  // Find latest date that is today or earlier
  const valid = dates.filter(d => d <= today);
  return valid[valid.length - 1] || dates[dates.length - 1] || '';
}

async function load() {
  const loadingHint = document.querySelector('.loading-hint');
  // Inline data (file:// protocol) or fetch (http:// protocol)
  if (window.__MANIFEST__) {
    state.manifest = window.__MANIFEST__;
  } else {
    state.manifest = await getJson('./data/processed/manifest.json');
  }
  if (window.__CATEGORY_ORDER__) {
    state.categoryOrder = window.__CATEGORY_ORDER__.categories || [];
  } else {
    state.categoryOrder = (await getJson('./data/category-order.json').catch(() => ({ categories: [] }))).categories || [];
  }
  state.allRecords = [];
  try {
    let raw;
    if (window.__LITE_LOADED__ && window.__LITE_DATA__) {
      raw = window.__LITE_DATA__;
    } else if (!window.__LITE_LOADED__) {
      // Wait for async lite data to finish loading.
      await loadLiteData();
      raw = window.__LITE_DATA__ || [];
    } else {
      raw = await getJson('./data/processed/all-records-lite.json');
    }
    const arr = Array.isArray(raw) ? raw : (raw.records || []);
    // Expand short keys to full names
    state.allRecords = arr.map(r => ({
      title: r.t || '',
      body: r.b || '',
      date: r.d || '',
      intelligence_type: r.i === 'l' ? 'literature' : 'news',
      url: r.u || '',
      category: r.c || '未分类',
      authors: r.a || '',
      tag: r.tg || '',
      topic: r.tp || '',
      key_params: r.kp || [],
      level: r.lv || 0,
      is_dup: r.dp || 0,
      full_body: r.fb || '',
      comment: r.cm || '',
      alert_reason: r.wr || '',
      ai_summary: r.as || '',
      score: r.sc || 0,
      score_dims: r.scd || null,
      ai_picked: r.aip || 0,
      ai_summary_pending: !r.as && r.b ? 1 : 0,
      cluster_id: r.cl || '',
      cluster_name: r.cln || '',
      cluster_parent: r.cp === undefined ? 0 : r.cp,
    }));
  } catch (e) {
    console.error('Failed to load data:', e);
    if (loadingHint) loadingHint.textContent = '数据加载失败，请刷新页面重试。';
    return;
  }
  state.records = state.allRecords;
  state.filtered = state.records;

  // Pre-compute display total (excluding cluster children and duplicates)
  state._displayTotal = state.records.filter(r => r.cluster_parent !== 1 && !r.is_dup).length;

  // Pre-compute performance maps
  state.clusterChildCounts = new Map();
  state.categoryLeaves = new Map();
  for (const r of state.records) {
    // Cluster child counts: cp=1 is a hidden child; count children by cluster id.
    if (r.cluster_id && r.cluster_parent === 1) {
      state.clusterChildCounts.set(r.cluster_id, (state.clusterChildCounts.get(r.cluster_id) || 0) + 1);
    }
    // Category leaves
    const cat = r.category || '未分类';
    if (!state.categoryLeaves.has(cat)) state.categoryLeaves.set(cat, new Set([cat]));
    else state.categoryLeaves.get(cat).add(cat);
  }

  renderHeader();
  bindEvents();
  // Set initial sort active state
  const w1 = $('sortWord1'); if (w1) w1.classList.add('active');
  applyFilters();
}

const ALERT_LEVELS = [
  { id: 'crawl', label: '信息爬取', desc: '收集到的全量情报（含重复）', test: () => true },
  { id: 'filtered', label: '信息筛选', desc: '全量情报中去除不相关情报及重复情报', test: (r) => (r.category || '') !== '不相关' && !r.is_dup },
  { id: 'aicurated', label: 'AI精选', desc: '相关且AI评分超过领域精选阈值的情报', test: (r) => (r.category || '') !== '不相关' && r.ai_picked === 1 },
  { id: 'curated', label: '精选情报', desc: '入选前沿技术追踪月报的情报', test: (r) => r.level >= 1 },
  { id: 'key', label: '重点情报', desc: '需要重点关注的重要情报', test: (r) => r.level >= 2 },
  { id: 'alert', label: '预警情报', desc: '值得高度关注的预警情报', test: (r) => r.level >= 3 },
];

function getAlertLevelCounts() {
  const records = getFilteredForCounts('alert');
  const counts = { crawl: 0, filtered: 0, aicurated: 0, curated: 0, key: 0, alert: 0 };
  for (const r of records) {
    // 信息爬取: count ALL records (including cp=1, dp=1)
    counts.crawl++;
    // All other counts: skip cluster children and duplicates (matching list display)
    if (r.cluster_parent === 1) continue;
    if (r.is_dup) continue;
    if ((r.category || '') !== '不相关') counts.filtered++;
    if ((r.category || '') !== '不相关' && r.ai_picked === 1) counts.aicurated++;
    if (r.level >= 1) counts.curated++;
    if (r.level >= 2) counts.key++;
    if (r.level >= 3) counts.alert++;
  }
  return counts;
}

function renderAlertLevels() {
  const counts = getAlertLevelCounts();
  const max = Math.max(...Object.values(counts), 1);
  const activeId = state.alertLevel;
  const html = ALERT_LEVELS.map(level => {
    const cnt = counts[level.id] || 0;
    const pct = (cnt / max * 100).toFixed(1);
    const isActive = activeId === level.id;
    return `<div class="alert-level-row ${isActive ? 'active' : ''}" data-alert-level="${level.id}" title="${esc(level.desc)}">
      <div class="alert-level-info">
        <span class="alert-level-label">${esc(level.label)}</span>
        <span class="alert-level-tooltip">${esc(level.desc)}</span>
      </div>
      <div class="alert-level-bar-wrap">
        <div class="alert-level-bar" style="width:${pct}%"></div>
      </div>
      <span class="alert-level-count">${cnt.toLocaleString()}</span>
    </div>`;
  }).join('');
  $('alertLevels').innerHTML = html;
}

function isAlertLevelMatch(item) {
  if (state.alertLevel === 'all' || state.alertLevel === 'crawl') return true;
  const level = ALERT_LEVELS.find(l => l.id === state.alertLevel);
  if (!level) return true;
  return level.test(item);
}

// Get filtered records excluding a specific filter (for cross-filter count linking)
// exclude: 'category' | 'type' | 'alert' | 'none'
function getFilteredForCounts(exclude = 'none') {
  const q = state.query.trim().toLowerCase();
  const cq = state.categoryQuery.trim().toLowerCase();
  return state.records.filter((item) => {
    if (state.dateFrom && (!item.date || item.date < state.dateFrom)) return false;
    if (state.dateTo && (!item.date || item.date > state.dateTo)) return false;
    if (exclude !== 'category' && state.selectedCategories && !state.selectedCategories.has(item.category || '未分类')) return false;
    if (exclude !== 'category' && cq) {
      const cat = (item.category || '未分类').toLowerCase();
      if (!cat.includes(cq)) return false;
    }
    if (exclude !== 'type' && !isTypeSelected(item.intelligence_type, item.tag)) return false;
    if (exclude !== 'alert' && !isAlertLevelMatch(item)) return false;
    if (!q) return true;
    return [item.title, item.body, item.category, item.authors, item.url].join(' ').toLowerCase().includes(q);
  });
}

function renderHeader() {
  // Count by type/tag — exclude 'type' filter so type counts reflect other filters
  const filtered = getFilteredForCounts('type');
  const tagCounts = {};
  let newsTotal = 0, litTotal = 0;
  const isCrawl = state.alertLevel === 'crawl';
  for (const item of filtered) {
    // Skip cluster children and duplicates — except in crawl mode which shows everything
    if (!isCrawl) {
      if (item.cluster_parent === 1) continue;
      if (item.is_dup) continue;
    }
    if (item.intelligence_type === 'news') newsTotal++;
    if (item.intelligence_type === 'literature') litTotal++;
    if (item.tag) tagCounts[item.tag] = (tagCounts[item.tag] || 0) + 1;
  }

  // Update counts
  const setCnt = (id, val) => { const el = $(id); if (el) el.textContent = val || ''; };
  setCnt('newsCount', newsTotal.toLocaleString());
  setCnt('litCount', litTotal.toLocaleString());
  setCnt('cnt-tech', tagCounts['技术突破'] || 0);
  setCnt('cnt-industry', tagCounts['产业进展'] || 0);
  setCnt('cnt-policy', tagCounts['政策监管'] || 0);
  setCnt('cnt-capital', tagCounts['资本运作'] || 0);
  setCnt('cnt-observe', tagCounts['行业观察'] || 0);
  setCnt('cnt-paper', tagCounts['研究论文'] || 0);
  setCnt('cnt-review', tagCounts['观点评论'] || 0);

  // Sync checkbox visual state with state
  document.querySelectorAll('[data-type-toggle]').forEach((cb) => {
    const t = cb.dataset.typeToggle;
    cb.classList.toggle('checked', !!state.selectedTypes[t]);
  });
  // Sync popover sub-tag checkboxes
  document.querySelectorAll('.type-popover-item').forEach((item) => {
    const t = item.dataset.type;
    const tag = item.dataset.tag;
    const cb = item.querySelector('.tree-checkbox');
    if (cb) {
      const tags = state.selectedTags[t];
      // Checked if type is on and (no specific tags selected = all, OR this tag is selected)
      const isChecked = state.selectedTypes[t] && (!tags || tags.size === 0 || tags.has(tag));
      cb.classList.toggle('checked', isChecked);
    }
  });
}

function isCategorySelected(cat) {
  if (!state.selectedCategories) return true; // null = all
  // Check if cat is a selected leaf
  if (state.selectedCategories.has(cat)) return true;
  // For intermediate nodes: selected if ANY descendant leaf is selected
  for (const s of state.selectedCategories) {
    if (s.startsWith(cat + '/')) return true;
  }
  return false;
}

// Get all leaf categories (full paths) under a prefix
function getDescendantLeaves(prefix) {
  const leaves = new Set();
  for (const item of state.records) {
    const cat = item.category || '未分类';
    if (cat === prefix || cat.startsWith(prefix + '/')) {
      leaves.add(cat);
    }
  }
  for (const path of state.categoryOrder) {
    const normalized = normalizeCategory(path);
    if (normalized === prefix || normalized.startsWith(prefix + '/')) {
      leaves.add(normalized);
    }
  }
  return [...leaves];
}

// Lazy-init: convert null (all) to a Set of all leaf categories
function materializeSelection() {
  if (!state.selectedCategories) {
    state.selectedCategories = new Set();
    const seen = new Set();
    for (const item of state.records) {
      const cat = item.category || '未分类';
      if (!seen.has(cat)) { seen.add(cat); state.selectedCategories.add(cat); }
    }
  }
}

function selectCategory(cat) {
  materializeSelection();
  const leaves = getDescendantLeaves(cat);
  if (leaves.length === 0) leaves.push(cat);
  for (const l of leaves) state.selectedCategories.add(l);
}

function deselectCategory(cat) {
  materializeSelection();
  const leaves = getDescendantLeaves(cat);
  if (leaves.length === 0) leaves.push(cat);
  for (const l of leaves) state.selectedCategories.delete(l);
}

function isCategoryFullySelected(cat) {
  if (!state.selectedCategories) return true; // null = all
  const leaves = getDescendantLeaves(cat);
  if (leaves.length === 0) return state.selectedCategories.has(cat);
  return leaves.every(l => state.selectedCategories.has(l));
}

function isCategoryPartiallySelected(cat) {
  if (!state.selectedCategories) return false; // null = all fully selected
  const leaves = getDescendantLeaves(cat);
  if (leaves.length === 0) return false;
  const selected = leaves.filter(l => state.selectedCategories.has(l));
  return selected.length > 0 && selected.length < leaves.length;
}

function selectAllCategories() {
  state.selectedCategories = null; // null = all
}

function deselectAllCategories() {
  state.selectedCategories = new Set();
}

function isTypeSelected(intelligenceType, tag) {
  if (!state.selectedTypes[intelligenceType]) return false;
  const tags = state.selectedTags[intelligenceType];
  if (!tags || tags.size === 0) return true; // empty = all tags
  return tags.has(tag);
}

function applyFilters() {
  const q = state.query.trim().toLowerCase();
  const cq = state.categoryQuery.trim().toLowerCase();
  state.filtered = state.records.filter((item) => {
    if (state.dateFrom && (!item.date || item.date < state.dateFrom)) return false;
    if (state.dateTo && (!item.date || item.date > state.dateTo)) return false;
    if (state.selectedCategories && !state.selectedCategories.has(item.category || '未分类')) return false;
    if (!isTypeSelected(item.intelligence_type, item.tag)) return false;
    if (!isAlertLevelMatch(item)) return false;
    // Hide cluster children and duplicates (matching alert level bar counts)
    // But NOT when viewing "信息爬取" (crawl) - that shows everything
    if (state.alertLevel !== 'crawl') {
      if (item.cluster_parent === 1) return false;
      if (item.is_dup) return false;
    }
    if (cq) {
      const cat = (item.category || '未分类').toLowerCase();
      if (!cat.includes(cq)) return false;
    }
    if (!q) return true;
    return [item.title, item.body, item.category, item.authors, item.url].join(' ').toLowerCase().includes(q);
  });
  // Sort
  const sortBy = state.sortBy || 'date';
  if (sortBy === 'score') {
    state.filtered.sort((a, b) => (b.score || 0) - (a.score || 0) || (b.date || '').localeCompare(a.date || ''));
  } else {
    state.filtered.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  }
  state.page = 1;
  renderAll();
}

function renderAll() {
  renderCategoryTree();
  renderAlertLevels();
  renderHeader();
  renderToolbar();
  renderRecords();
}

function renderToolbar() {
  const totalLabel = state.alertLevel === 'crawl' ? state.allRecords.length : (state._displayTotal || state.allRecords.length);
  $('resultCount').innerHTML = `共 <strong>${state.filtered.length.toLocaleString()}</strong> 条结果`;
  // Alert level clear button removed (now in top bar)
  const chips = [];
  if (state.query.trim()) chips.push({ label: '检索', value: state.query.trim(), key: 'query' });
  if (state.dateFrom || state.dateTo) {
    let dv = state.dateFrom === state.dateTo ? state.dateFrom : `${state.dateFrom || '…'} ~ ${state.dateTo || '…'}`;
    chips.push({ label: '日期', value: dv, key: 'date' });
  }
  if (state.alertLevel !== 'all') {
    const lvl = ALERT_LEVELS.find(l => l.id === state.alertLevel);
    if (lvl) chips.push({ label: '情报等级', value: lvl.label, key: 'alert' });
  }
  if (state.selectedCategories && state.selectedCategories.size < state.records.length) {
    const cnt = state.selectedCategories.size;
    chips.push({ label: '分类', value: `已选 ${cnt} 类`, key: 'category' });
  }
  const typeChips = [];
  if (!state.selectedTypes.news && !state.selectedTypes.literature) {
    typeChips.push('无');
  } else {
    const parts = [];
    if (state.selectedTypes.news) parts.push('新闻');
    if (state.selectedTypes.literature) parts.push('文献');
    if (parts.length < 2) typeChips.push(parts.join('+'));
  }
  const newsTags = state.selectedTags.news;
  const litTags = state.selectedTags.literature;
  const tagParts = [];
  if (newsTags && newsTags.size > 0) tagParts.push(`新闻: ${[...newsTags].join('/')}`);
  if (litTags && litTags.size > 0) tagParts.push(`文献: ${[...litTags].join('/')}`);
  if (typeChips.length) chips.push({ label: '情报类型', value: typeChips[0], key: 'type' });
  if (tagParts.length) chips.push({ label: '标签', value: tagParts.join(', '), key: 'type' });
  $('activeChips').innerHTML = chips.length
    ? chips.map((c) => `<button class="chip" data-clear="${c.key}" type="button">${esc(c.label)}: ${esc(c.value)} ×</button>`).join('')
    : '';
  $('clearDateBtn').style.display = (state.dateFrom || state.dateTo) ? '' : 'none';
}

function renderCategoryTree() {
  const filtered = getFilteredForCounts('category');
  const origRecords = state.records;
  state.records = filtered;
  const { tree, groupTotals } = buildCategoryTree(false);
  state.records = origRecords;
  const groupOrder = ['零碳产业', 'AI与智能科技', '通用技术', '不相关', '未分类'];
  const allGroups = [...Object.keys(tree)].sort((a, b) => {
    const ia = groupOrder.indexOf(a), ib = groupOrder.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  const html = allGroups.map((group) => {
    const node = tree[group];
    if (!node) return '';
    const collapsed = state.collapsedGroups.has(group);
    const childrenHtml = collapsed ? '' : renderTreeNode(node, 1);
    const fullyChecked = isCategoryFullySelected(group);
    const partialChecked = isCategoryPartiallySelected(group);
    const checkedClass = fullyChecked ? 'checked' : (partialChecked ? 'partial' : '');
    return `<div class="tree-group" data-group="${esc(group)}">
      <div class="tree-group-head" data-toggle="${esc(group)}">
        <span class="group-arrow">${collapsed ? '▸' : '▾'}</span>
        <span class="tree-checkbox ${checkedClass}" data-category="${esc(group)}"></span>
        <span class="group-label">${esc(group)}</span>
        <span class="group-count">${groupTotals[group]}</span>
      </div>
      <div class="tree-children">${childrenHtml}</div>
    </div>`;
  }).join('');
  $('categoryTree').innerHTML = html;
}

function renderRecords() {
  const pages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  state.page = Math.min(state.page, pages);
  const start = (state.page - 1) * PAGE_SIZE;
  const rows = state.filtered.slice(start, start + PAGE_SIZE);
  $('pageLabel').textContent = `第 ${state.page} / ${pages} 页`;
  $('prevPage').disabled = state.page <= 1;
  $('nextPage').disabled = state.page >= pages;
  if (!rows.length) {
    $('recordList').innerHTML = '<div class="empty-hint"><strong>没有匹配的情报</strong>请清除部分筛选条件或更换关键词。</div>';
    return;
  }
  $('recordList').innerHTML = rows.map(renderRecordCard).join('');
}

function renderRecordCard(item) {
  const typeLabel = item.intelligence_type === 'literature' ? '文献' : '新闻';
  const typeClass = item.intelligence_type === 'literature' ? 'literature' : 'news';
  const url = item.url;
  const titleHtml = url
    ? `<a class="record-title-link" href="${esc(url)}" target="_blank" rel="noreferrer">${esc(item.title || '未命名情报')}</a>`
    : `<span class="record-title-link">${esc(item.title || '未命名情报')}</span>`;
  const summary = item.ai_summary || item.body || '';
  const isUnrelated = (item.category || '') === '不相关';
  const typeTagLabel = `${typeLabel}${item.tag ? '-' + item.tag : ''}`;
  const catStr = item.category || '未分类';
  const topicHtml = item.topic ? `<div class="record-topic">${esc(item.topic)}</div>` : '';
  const lv = item.level || 0;

  // AI score box (score + AI精选 in one frame, before level badges)
  let scoreBox = '';
  if (!isUnrelated && item.score > 0) {
    const s = item.score;
    const scoreCls = s >= 7.0 ? 'hi' : s >= 5.0 ? 'mid' : 'lo';
    const aiLabel = item.ai_picked ? '<span class="score-box-ai">AI精选</span>' : '';
    const dims = item.score_dims;
    // Build tooltip data as data-attributes (no nested HTML)
    const tipData = dims ? `data-tip-score="${s.toFixed(1)}" data-tip-b="${(dims.b||0).toFixed(1)}" data-tip-i="${(dims.i||0).toFixed(1)}" data-tip-r="${(dims.r||0).toFixed(1)}" data-tip-d="${(dims.d||0).toFixed(1)}" data-tip-t="${(dims.t||0).toFixed(1)}"` : '';
    scoreBox = `<span class="score-box ${scoreCls}" tabindex="0" ${tipData}>${aiLabel}<span class="score-box-num">${s.toFixed(1)}</span></span>`;
  }

  const levelBadges = scoreBox + [
    lv >= 3 ? '<span class="level-badge alert">预警</span>' : '',
    lv >= 2 ? '<span class="level-badge key">重点</span>' : '',
    lv >= 1 ? '<span class="level-badge curated">精选</span>' : '',
  ].join('');

  // Meta line
  const metaParts = [];
  if (item.date) metaParts.push(`<span class="meta-item">📅&nbsp;${esc(item.date)}</span>`);
  if (item.authors && item.authors !== HIDDEN_AUTHORS) metaParts.push(`<span class="meta-item">✍️&nbsp;${esc(item.authors)}</span>`);
  const metaLine = metaParts.length ? `<div class="record-meta-info">${metaParts.join('<span class="meta-sep"></span>')}</div>` : '';

  // Badges
  const typeBadge = isUnrelated ? '' : `<span class="type-tag ${typeClass}">${esc(typeTagLabel)}</span>`;

  let paramsHtml = '';
  if (Array.isArray(item.key_params) && item.key_params.length) {
    paramsHtml = '<div class="key-params">' +
      item.key_params.map(p => `<span class="param-chip">${esc(p)}</span>`).join('') +
      '</div>';
  }

  // Body: AI summary + expand full text + comment + alert reason
  let bodyHtml = '';
  const cardId = 'c' + Math.random().toString(36).slice(2, 9);
  const aiSummary = item.ai_summary || summary;
  const hasFullBody = item.full_body && item.full_body.length > summary.length;

  if (lv > 0 || item.comment || item.alert_reason) {
    bodyHtml = `<div class="record-body-wrap">`;
    if (aiSummary && aiSummary.trim()) {
      bodyHtml += `<p class="record-ai-summary"><span class="summary-label">AI摘要</span>${esc(aiSummary)}`;
    } else if (item.ai_summary_pending) {
      bodyHtml += `<p class="record-ai-summary record-ai-pending">AI摘要生成中…`;
    } else {
      bodyHtml += `<p class="record-ai-summary record-ai-pending">AI摘要生成中…`;
    }
    if (hasFullBody) {
      bodyHtml += ` <span class="expand-btn" data-target="${cardId}-full" data-action="expand">[展开全文]</span>`;
    }
    bodyHtml += `</p>`;
    // Full text (hidden initially)
    if (hasFullBody) {
      bodyHtml += `<div class="record-full-text" id="${cardId}-full" style="display:none">`;
      bodyHtml += `<div class="full-text-inner">${esc(item.full_body)}</div>`;
      bodyHtml += `</div>`;
    }
    // Comment (full, no truncation)
    if (item.comment) {
      bodyHtml += `<div class="record-comment-full-block"><span class="comment-label">Comment</span><p class="record-comment-text">${esc(item.comment)}</p></div>`;
    }
    // Alert reason (独立模块, Comment下方, 红色系)
    if (item.alert_reason) {
      const wrParts = item.alert_reason.split('||');
      const wrLabel = wrParts.length === 2 ? `预警原因：${wrParts[0]}` : '预警原因：';
      const wrText = wrParts.length === 2 ? wrParts[1] : item.alert_reason;
      bodyHtml += `<div class="alert-reason-block"><span class="alert-reason-label">${esc(wrLabel)}</span><span class="alert-reason-text">${esc(wrText)}</span></div>`;
    }
    bodyHtml += `</div>`;
  } else {
    if (aiSummary && aiSummary.trim()) {
      bodyHtml = `<p class="record-summary"><span class="summary-label">AI摘要</span>${esc(aiSummary)}</p>`;
    } else if (item.ai_summary_pending) {
      bodyHtml = `<p class="record-summary record-ai-pending">AI摘要生成中…</p>`;
    } else {
      bodyHtml = `<p class="record-summary record-ai-pending">AI摘要生成中…</p>`;
    }
  }

  // Cluster indicator (rendered next to title)
  let clusterHtml = '';
  if (item.cluster_id && item.cluster_parent === 0) {
    const childCount = state.clusterChildCounts ? (state.clusterChildCounts.get(item.cluster_id) || 0) : 0;
    if (childCount > 0) {
      clusterHtml = `<span class="cluster-badge" data-cluster="${esc(item.cluster_id)}" title="${esc(item.cluster_name || '')}">展开事件聚类 · ${childCount}</span>`;
    }
  }

  return `<article class="record-card">
    <div class="record-title">${levelBadges}${titleHtml}${clusterHtml}</div>
    ${topicHtml}
    ${metaLine}
    <div class="record-badges">
      <span class="type-tag cat-tag">${esc(catStr)}</span>
      ${typeBadge}
    </div>
    ${bodyHtml}
    ${paramsHtml}
  </article>`;
}

function clearFilter(key) {
  if (key === 'query') { state.query = ''; $('searchInput').value = ''; }
  if (key === 'date') { state.dateFrom = ''; state.dateTo = ''; $('dateFrom').value = ''; $('dateTo').value = ''; }
  if (key === 'category') selectAllCategories();
  if (key === 'type') { state.selectedTypes = { news: true, literature: true }; state.selectedTags = { news: new Set(), literature: new Set() }; }
  if (key === 'alert') { state.alertLevel = 'all'; }
  applyFilters();
}

function setQuickDate(type) {
  const today = new Date();
  const fmt = (d) => d.toISOString().slice(0, 10);
  if (type === 'today') { state.dateFrom = fmt(today); state.dateTo = fmt(today); }
  else if (type === '7d') {
    const past = new Date(today); past.setDate(past.getDate() - 6);
    state.dateFrom = fmt(past); state.dateTo = fmt(today);
  } else if (type === '30d') {
    const past = new Date(today); past.setDate(past.getDate() - 29);
    state.dateFrom = fmt(past); state.dateTo = fmt(today);
  } else { state.dateFrom = ''; state.dateTo = ''; }
  $('dateFrom').value = state.dateFrom;
  $('dateTo').value = state.dateTo;
  applyFilters();
}

  // Detail modal code removed

function bindEvents() {
  // Expand/collapse full text
  document.addEventListener('click', (e) => {
    if (e.target.classList.contains('expand-btn')) {
      const targetId = e.target.dataset.target;
      const action = e.target.dataset.action;
      const el = document.getElementById(targetId);
      if (!el) return;
      if (action === 'expand') {
        el.style.display = '';
        e.target.dataset.action = 'collapse';
        e.target.textContent = '[收起全文]';
      } else {
        el.style.display = 'none';
        e.target.dataset.action = 'expand';
        e.target.textContent = '[展开全文]';
      }    }
  });
  // Close popovers when clicking outside
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.type-inline-item')) {
      document.querySelectorAll('.type-popover.show').forEach(p => p.classList.remove('show'));
    }
  });

  // Safe event binding helper
  const on = (id, evt, fn) => { const el = $(id); if (el) el.addEventListener(evt, fn); };

  on('themeToggle', 'click', () => {
    const cur = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
    const next = cur === 'dark' ? 'light' : 'dark';
    if (next === 'light') document.documentElement.setAttribute('data-theme', 'light');
    else document.documentElement.removeAttribute('data-theme');
    localStorage.setItem('techdb-theme', next);
  });
  let searchTimer = null;
  on('searchInput', 'input', (e) => { 
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.query = e.target.value; applyFilters(); }, 200);
  });
  let catSearchTimer = null;
  on('categorySearch', 'input', (e) => { 
    state.categoryQuery = e.target.value;
    clearTimeout(catSearchTimer);
    catSearchTimer = setTimeout(() => { applyFilters(); }, 200);
  });
  on('sortToggle', 'click', () => {
    state.sortBy = state.sortBy === 'date' ? 'score' : 'date';
    const w1 = $('sortWord1'), w2 = $('sortWord2');
    if (w1 && w2) {
      if (state.sortBy === 'date') {
        w1.classList.add('active'); w2.classList.remove('active');
      } else {
        w1.classList.remove('active'); w2.classList.add('active');
      }
    }
    applyFilters();
  });
  on('clearDateBtn', 'click', () => clearFilter('date'));
  on('dateFrom', 'change', (e) => { state.dateFrom = e.target.value; applyFilters(); });
  on('dateTo', 'change', (e) => { state.dateTo = e.target.value; applyFilters(); });
  document.querySelectorAll('.date-quick button').forEach((btn) => {
    btn.addEventListener('click', () => setQuickDate(btn.dataset.quick));
  });
  on('prevPage', 'click', () => { if (state.page > 1) { state.page -= 1; renderRecords(); } });
  on('nextPage', 'click', () => { const pages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE)); if (state.page < pages) { state.page += 1; renderRecords(); } });

  // ── Global score tooltip (single floating div, not a child of score-box) ──
  const scoreTooltip = document.createElement('div');
  scoreTooltip.className = 'score-float-tip';
  scoreTooltip.style.display = 'none';
  document.body.appendChild(scoreTooltip);

  document.addEventListener('mouseover', (e) => {
    const sb = e.target.closest('.score-box[data-tip-score]');
    if (!sb) { return; }
    const b = sb.dataset.tipB, i = sb.dataset.tipI, r = sb.dataset.tipR, d = sb.dataset.tipD, t = sb.dataset.tipT;
    const score = sb.dataset.tipScore;
    scoreTooltip.innerHTML =
      `<div class="sft-total">质量分 ${score}</div>` +
      `<div class="sft-row"><span>突破性</span><span>${b}</span></div>` +
      `<div class="sft-row"><span>产业力</span><span>${i}</span></div>` +
      `<div class="sft-row"><span>稀缺性</span><span>${r}</span></div>` +
      `<div class="sft-row"><span>数据量</span><span>${d}</span></div>` +
      `<div class="sft-row"><span>时效性</span><span>${t}</span></div>` +
      `<div class="sft-note">总分=加权分+ATSC偏好附加分</div>`;
    const rect = sb.getBoundingClientRect();
    scoreTooltip.style.display = 'block';
    // Position: below the score-box, left-aligned
    let left = rect.left;
    let top = rect.bottom + 6;
    // Keep within viewport
    const tipW = scoreTooltip.offsetWidth;
    if (left + tipW > window.innerWidth - 8) left = window.innerWidth - tipW - 8;
    scoreTooltip.style.left = left + 'px';
    scoreTooltip.style.top = top + 'px';
  });
  document.addEventListener('mouseout', (e) => {
    const sb = e.target.closest('.score-box[data-tip-score]');
    if (sb) scoreTooltip.style.display = 'none';
  });

  document.addEventListener('click', (e) => {
    const chip = e.target.closest('[data-clear]');
    if (chip) { clearFilter(chip.dataset.clear); return; }

    // Alert level click — cannot deselect AI精选 (stays as minimum)
    const alRow = e.target.closest('[data-alert-level]');
    if (alRow) {
      const lvl = alRow.dataset.alertLevel;
      // 点击当前已选中的等级不会取消，而是保持选中
      state.alertLevel = lvl;
      applyFilters();
      return;
    }

    // Cluster toggle - directly manipulate DOM without full re-render
    const clusterTog = e.target.closest('[data-cluster]');
    if (clusterTog) {
      e.preventDefault();
      e.stopPropagation();
      const cid = clusterTog.dataset.cluster;
      const parentCard = clusterTog.closest('.record-card');
      
      if (state.expandedClusters.has(cid)) {
        // Collapse: remove child cards after parent
        state.expandedClusters.delete(cid);
        let next = parentCard.nextElementSibling;
        while (next && next.classList.contains('cluster-child') && next.dataset.clusterChild === cid) {
          const toRemove = next;
          next = next.nextElementSibling;
          toRemove.remove();
        }
        // Update badge text
        const childCount = state.clusterChildCounts ? (state.clusterChildCounts.get(cid) || 0) : 0;
        clusterTog.textContent = `展开事件聚类 · ${childCount}`;
        clusterTog.classList.remove('expanded');
      } else {
        // Expand: find child records and insert compact cards after parent
        state.expandedClusters.add(cid);
        const children = state.records.filter(r => r.cluster_id === cid && r.cluster_parent === 1);
        const frag = document.createDocumentFragment();
        for (const child of children) {
          const div = document.createElement('article');
          div.className = 'record-card cluster-child';
          div.dataset.clusterChild = cid;
          const metaParts = [];
          if (child.date) metaParts.push(`📅&nbsp;${esc(child.date)}`);
          if (child.authors && child.authors !== HIDDEN_AUTHORS) metaParts.push(`✍️&nbsp;${esc(child.authors)}`);
          const metaLine = metaParts.length ? `<div class="record-meta-info">${metaParts.join('<span class="meta-sep"></span>')}</div>` : '';
          div.innerHTML = `<div class="record-title"><a class="record-title-link" href="${esc(child.url || '#')}" target="_blank" rel="noreferrer">${esc(child.title || '未命名情报')}</a></div>${metaLine}`;
          frag.appendChild(div);
        }
        parentCard.after(frag);
        // Update badge text
        clusterTog.textContent = `收起事件聚类 · ${children.length}`;
        clusterTog.classList.add('expanded');
      }
      return;
    }

    // Click checkbox → toggle category selection
    const checkbox = e.target.closest('.tree-checkbox[data-category]');
    if (checkbox) {
      const cat = checkbox.dataset.category;
      // If fully selected or partially selected → deselect; if unselected → select
      if (isCategoryFullySelected(cat) || isCategoryPartiallySelected(cat)) {
        deselectCategory(cat);
      } else {
        selectCategory(cat);
      }
      renderCategoryTree();
      applyFilters();
      return;
    }

    // Click tree arrow → toggle expand/collapse
    const arrow = e.target.closest('.tree-arrow, .group-arrow');
    if (arrow) {
      const key = arrow.dataset.toggle || arrow.closest('.tree-group-head')?.dataset.toggle;
      if (key) {
        if (state.collapsedGroups.has(key)) state.collapsedGroups.delete(key);
        else state.collapsedGroups.add(key);
        renderCategoryTree();
      }
      return;
    }

    // Click tree label → toggle selection (same as checkbox)
    const label = e.target.closest('.tree-label[data-category]');
    if (label) {
      const cat = label.dataset.category;
      if (isCategoryFullySelected(cat) || isCategoryPartiallySelected(cat)) {
        deselectCategory(cat);
      } else {
        selectCategory(cat);
      }
      renderCategoryTree();
      applyFilters();
      return;
    }

    // Click group label → toggle expand
    const groupLabel = e.target.closest('.group-label');
    if (groupLabel) {
      const head = groupLabel.closest('.tree-group-head');
      if (head) {
        const key = head.dataset.toggle;
        if (state.collapsedGroups.has(key)) state.collapsedGroups.delete(key);
        else state.collapsedGroups.add(key);
        renderCategoryTree();
      }
      return;
    }

    // Click select-all / deselect-all
    const selAll = e.target.closest('[data-cat-action="all"]');
    if (selAll) { selectAllCategories(); renderCategoryTree(); applyFilters(); return; }
    const selNone = e.target.closest('[data-cat-action="none"]');
    if (selNone) { deselectAllCategories(); renderCategoryTree(); applyFilters(); return; }

    // Type checkbox toggle (news/literature)
    const typeCheckbox = e.target.closest('[data-type-toggle]');
    if (typeCheckbox) {
      const t = typeCheckbox.dataset.typeToggle;
      state.selectedTypes[t] = !state.selectedTypes[t];
      applyFilters();
      return;
    }

    // Type popover arrow toggle
    const typeArrow = e.target.closest('[data-type-popover]');
    if (typeArrow) {
      e.stopPropagation();
      const popId = 'popover-' + typeArrow.dataset.typePopover;
      document.querySelectorAll('.type-popover').forEach(p => { if (p.id !== popId) p.classList.remove('show'); });
      $(popId).classList.toggle('show');
      return;
    }

    // Type popover item checkbox
    const popItem = e.target.closest('.type-popover-item');
    if (popItem) {
      const t = popItem.dataset.type;
      const tag = popItem.dataset.tag;
      const tags = state.selectedTags[t];
      if (tags.has(tag)) { tags.delete(tag); }
      else { tags.add(tag); }
      applyFilters();
      return;
    }
  });

  // Source panel
  if (window.__SOURCES__) {
    renderSourcePanel();
    $('sourceTrigger').addEventListener('click', () => {
      $('sourcePanel').classList.add('open');
      $('sourceOverlay').classList.add('show');
    });
    $('sourceClose').addEventListener('click', closeSourcePanel);
    $('sourceOverlay').addEventListener('click', closeSourcePanel);
  }
}

function closeSourcePanel() {
  $('sourcePanel').classList.remove('open');
  $('sourceOverlay').classList.remove('show');
}

function renderSourcePanel() {
  const data = window.__SOURCES__;
  if (!data) return;
  $('sourceSummary').innerHTML = `本数据库共捕获 <strong>${data.total}</strong> 个信息来源`;
  const html = data.categories.map(cat => {
    const groupsHtml = cat.groups.map(g => {
      const items = g.items.map(s => `<span class="source-item">${esc(s)}</span>`).join('');
      return `<div class="source-group">
        <div class="source-group-head"><span>${esc(g.name)}</span><span class="source-group-count">${g.count}</span></div>
        <div class="source-items">${items}</div>
      </div>`;
    }).join('');
    return `<div class="source-category">
      <div class="source-cat-head"><span class="source-cat-icon">${cat.icon}</span><span class="source-cat-name">${esc(cat.name)}</span><span class="source-cat-count">${cat.count}个来源</span></div>
      ${groupsHtml}
    </div>`;
  }).join('');
  $('sourceBody').innerHTML = html;
}

load().catch((error) => {
  document.body.innerHTML = `<main class="content"><div class="empty-hint"><strong>页面载入失败</strong>${esc(error.message)}</div></main>`;
});
