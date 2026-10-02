// 任务一 1.2：GitHub 页轮询 + 索引详情四态（真实函数执行测试）。
//   node --test tests/js/test_library_polling_ui.mjs
// 方式：从 app.js 截取真实函数源码（scheduleLibPolling / stopLibPolling /
// libToggleIndexDetail / LIB_ROUTE_STATE_LABELS）在受控 DOM/网络桩下执行
// —— 不复刻实现，只断言真实页面函数的行为。
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import assert from 'node:assert/strict';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const src = readFileSync(join(root, 'app.js'), 'utf8');

function extractFn(name) {
  const re = new RegExp(
    `(?:async )?function ${name}\\(`, 'g');
  let m; const starts = [];
  while ((m = re.exec(src))) starts.push(m.index);
  assert.ok(starts.length >= 1, `${name} 未定义`);
  const start = starts[starts.length - 1];
  // brace matching from the first '{' after the signature
  let i = src.indexOf('{', start), depth = 0, end = -1;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
  }
  assert.ok(end > 0, `${name} 截取失败`);
  return src.slice(start, end);
}
function extractConst(name) {
  // 对象字面量（{...};）或 Set 字面量（new Set();）
  let m = src.match(new RegExp(`const ${name}=\\{[^;]*\\};`));
  if (!m) m = src.match(new RegExp(`const ${name}=new Set\\(\\);`));
  assert.ok(m, `${name} 未定义`);
  return m[0];
}

const moduleSrc = [
  extractFn('scheduleLibPolling'),
  extractFn('stopLibPolling'),
  extractConst('LIB_ROUTE_STATE_LABELS'),
  extractConst('libIdxDetailOpen'),
  extractFn('libIdxDetailRowHtml'),
  extractFn('libOpenIdxDetail'),
  extractFn('libToggleIndexDetail'),
  extractFn('libRestoreIdxDetails'),
].join('\n');

function makeEnv({ files, rowsExists = true, detailPayload, detailOk = true }) {
  const state = { timer: null, polls: 0 };
  const env = {
    libRefreshTimer: null,
    loadLibrary: () => { state.polls++; },
    document: {
      getElementById: (id) => (id === 'rows' && rowsExists ? {} : null),
      createElement: () => ({ dataset: {}, innerHTML: '', _html: '' }),
    },
    apiFetch: async (url) => {
      env.requested.push(String(url));
      return { ok: detailOk, json: async () => detailPayload };
    },
    requested: [],
    setTimeout: (fn, ms) => { state.timer = { fn, ms }; return 1; },
    clearTimeout: () => { state.timer = null; },
    CSS: { escape: (s) => s },
    escapeHtml: (s) => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])),
  };
  return { env, state };
}

function loadModule(env) {
  const fn = new Function(
    'libRefreshTimer', 'loadLibrary', 'document', 'apiFetch',
    'setTimeout', 'clearTimeout', 'CSS', 'escapeHtml',
    `${moduleSrc}
     return { scheduleLibPolling, stopLibPolling, libToggleIndexDetail, libOpenIdxDetail, libRestoreIdxDetails, libIdxDetailOpen, LIB_ROUTE_STATE_LABELS };`);
  return fn(
    env.libRefreshTimer, env.loadLibrary, env.document, env.apiFetch,
    env.setTimeout, env.clearTimeout, env.CSS, env.escapeHtml);
}

test('scheduleLibPolling：index_queued 时建立轮询定时器（历史缺陷：GitHub 分支提前 return 永不建立）', () => {
  const { env, state } = makeEnv({ files: [{ ingestion_status: 'index_queued' }] });
  const mod = loadModule(env);
  mod.scheduleLibPolling([{ ingestion_status: 'index_queued' }]);
  assert.ok(state.timer, '应建立轮询定时器');
  assert.equal(state.timer.ms, 3000);
});

test('scheduleLibPolling：全部终态不轮询；#rows 不在（离开页面）不轮询', () => {
  const { env, state } = makeEnv({ files: [] });
  const mod = loadModule(env);
  mod.scheduleLibPolling([{ ingestion_status: 'indexed' }, { ingestion_status: 'no_new_records' }]);
  assert.equal(state.timer, null, '全部终态不应轮询');
  mod.scheduleLibPolling([{ ingestion_status: 'index_queued' }]);
  assert.ok(state.timer, '活跃状态应轮询');
  const env2 = makeEnv({ files: [], rowsExists: false });
  const mod2 = loadModule(env2.env);
  mod2.scheduleLibPolling([{ ingestion_status: 'index_queued' }]);
  assert.equal(env2.state.timer, null, '页面已离开（#rows 不存在）不应轮询');
});

test('scheduleLibPolling：替换旧定时器（不叠加）', () => {
  const { env, state } = makeEnv({ files: [] });
  const mod = loadModule(env);
  mod.scheduleLibPolling([{ ingestion_status: 'index_queued' }]);
  mod.scheduleLibPolling([{ ingestion_status: 'index_queued' }]);
  assert.equal(state.polls, 0);
  assert.ok(state.timer, '仍是单一待触发定时器');
});

test('stopLibPolling：显式终止（离开页面）', () => {
  const { env, state } = makeEnv({ files: [] });
  const mod = loadModule(env);
  mod.scheduleLibPolling([{ ingestion_status: 'index_queued' }]);
  assert.ok(state.timer);
  mod.stopLibPolling();
  assert.equal(state.timer, null);
});

function makeDetailDom() {
  const made = { rows: [] };
  const tr = {
    children: [{}, {}, {}, {}, {}, {}], // 6 列 → colspan=6
    after: (el) => made.rows.push(el),
  };
  const btn = { disabled: false, textContent: '', dataset: { libIdxDetail: null } };
  const tb = {
    // 真实选择器语义：tr[data-idx-detail-for]/button[data-lib-idx-detail]
    querySelector: (sel) => {
      let m = /data-idx-detail-for="(.*)"/.exec(sel);
      if (m) {
        const hit = made.rows.find(r => r.dataset?.idxDetailFor === m[1]);
        if (!hit) return null;
        hit.remove = () => { made.rows = made.rows.filter(r => r !== hit); };
        return hit;
      }
      m = /button\[data-lib-idx-detail="(.*)"\]/.exec(sel);
      if (m) { btn.dataset.libIdxDetail = m[1]; return btn; } // 模拟当前行的按钮
      return null;
    },
    querySelectorAll: (sel) => {
      const m = /data-idx-detail-for="(.*)"/.exec(sel);
      if (!m) return [];
      return made.rows.filter(r => r.dataset?.idxDetailFor === m[1]);
    },
  };
  btn.closest = () => tr;
  return { tb, tr, btn, made };
}

test('libToggleIndexDetail：展开渲染四态详情并请求详情端点', async () => {
  const payload = {
    ingestion_mode: 'row_records',
    searchable: true,
    states: {
      breadth_visible: { state: 'complete' },
      vector: { state: 'complete' },
      keyword: { state: 'partial', reason: '1/2 documents healthy' },
      graph: { state: 'complete', note: '无可抽取实体（不构成构建失败）' },
    },
    index: { documents_checked: 2, documents_found: 2, chunks: 5, entity_count: 0,
             documents_missing: 0 },
  };
  const dom = makeDetailDom();
  const { env } = makeEnv({ files: [], detailPayload: payload });
  env.document.getElementById = (id) => (id === 'rows' ? dom.tb : null);
  const mod = loadModule(env);
  await mod.libToggleIndexDetail('file-1', dom.btn);
  assert.deepEqual(env.requested, ['/api/uploads/file-1/index-status']);
  assert.equal(dom.made.rows.length, 1, '详情行已插入');
  const html = dom.made.rows[0].innerHTML;
  assert.ok(html.includes('广度可见'), '四态之一：广度可见');
  assert.ok(html.includes('向量索引'), '四态之一：向量');
  assert.ok(html.includes('关键词索引'), '四态之一：关键词');
  assert.ok(html.includes('知识图谱'), '四态之一：图谱');
  assert.ok(html.includes('部分'), 'partial 状态如实显示');
  assert.ok(html.includes('无可抽取实体'), '图谱零实体注记如实显示');
  assert.ok(html.includes('分块 5'));
  assert.equal(dom.btn.textContent, '索引详情');
});

test('libToggleIndexDetail：再次点击收起详情行', async () => {
  const payload = { states: {}, index: {}, ingestion_mode: 'document', searchable: null };
  const dom = makeDetailDom();
  const { env } = makeEnv({ files: [], detailPayload: payload });
  env.document.getElementById = (id) => (id === 'rows' ? dom.tb : null);
  const mod = loadModule(env);
  await mod.libToggleIndexDetail('file-2', dom.btn);
  assert.equal(dom.made.rows.length, 1);
  // 再次点击：existing 命中 → remove，不重新请求
  const before = env.requested.length;
  await mod.libToggleIndexDetail('file-2', dom.btn);
  assert.equal(env.requested.length, before, '收起不应再次请求');
});

test('libToggleIndexDetail：服务不可达如实提示（不显示伪数据）', async () => {
  const dom = makeDetailDom();
  const { env } = makeEnv({ files: [], detailOk: false });
  env.document.getElementById = (id) => (id === 'rows' ? dom.tb : null);
  const mod = loadModule(env);
  await mod.libToggleIndexDetail('file-3', dom.btn);
  assert.ok(dom.made.rows[0].innerHTML.includes('暂不可用'));
});

test('libRestoreIdxDetails：轮询重渲染后恢复展开行（E2E 发现的丢行缺陷）', async () => {
  const payload = {
    states: { vector: { state: 'processing' } },
    index: { chunks: 3 },
    ingestion_mode: 'row_records',
    searchable: false,
  };
  const dom = makeDetailDom();
  const { env } = makeEnv({ files: [], detailPayload: payload });
  env.document.getElementById = (id) => (id === 'rows' ? dom.tb : null);
  const mod = loadModule(env);
  await mod.libToggleIndexDetail('file-9', dom.btn);
  assert.equal(dom.made.rows.length, 1, '首次展开');
  assert.ok(mod.libIdxDetailOpen.has('file-9'), '登记展开集合');
  // 模拟轮询重渲染：tbody 被清空重建
  dom.made.rows.length = 0;
  mod.libRestoreIdxDetails(dom.tb);
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(dom.made.rows.length, 1, '重渲染后自动恢复详情行');
  assert.ok(dom.made.rows[0].innerHTML.includes('构建中'), '恢复行携带最新状态');
  // 收起后重渲染不再恢复
  await mod.libToggleIndexDetail('file-9', dom.btn);
  assert.equal(dom.made.rows.length, 0);
  dom.made.rows.length = 0;
  mod.libRestoreIdxDetails(dom.tb);
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(dom.made.rows.length, 0, '收起状态不被恢复');
});

test('GitHub 分支接线：轮询在提前 return 之前调用（源码结构断言）', () => {
  // 历史缺陷：isGithub 分支 return 早于轮询建立。现在分支内必须调用
  // scheduleLibPolling，且调用点位于 return 之前。
  const iG = src.indexOf('if(isGithub){');
  const regionEnd = src.indexOf('return;\n  }', iG);
  const region = src.slice(iG, regionEnd);
  assert.ok(region.includes('scheduleLibPolling(data.files)'),
    'GitHub 分支必须在 return 前调用 scheduleLibPolling');
  assert.ok(region.includes('data-lib-idx-detail'), 'GitHub 行应提供索引详情入口');
});

test('libRestoreIdxDetails：快照迭代——中间条目缺失不跳过后续条目（Codex#5）', async () => {
  const payload = { states: { vector: { state: 'complete' } }, index: {}, ingestion_mode: 'row_records', searchable: true };
  const dom = makeDetailDom();
  const { env } = makeEnv({ files: [], detailPayload: payload });
  env.document.getElementById = (id) => (id === 'rows' ? dom.tb : null);
  const mod = loadModule(env);
  // 三个上传都展开
  await mod.libToggleIndexDetail('file-a', dom.btn);
  await mod.libToggleIndexDetail('file-b', dom.btn);
  await mod.libToggleIndexDetail('file-c', dom.btn);
  assert.equal(dom.made.rows.length, 3);
  assert.equal(mod.libIdxDetailOpen.size, 3);
  // 模拟轮询重渲染：清空 tbody；b 不再渲染（如翻页），a/c 仍在
  dom.made.rows.length = 0;
  // stub 的按钮按 data-lib-idx-detail 匹配任意 id——把 b 从匹配中排除：
  const origQs = dom.tb.querySelector;
  dom.tb.querySelector = (sel) => {
    if (/data-lib-idx-detail="file-b"/.test(sel)) return null;
    return origQs.call(dom.tb, sel);
  };
  mod.libRestoreIdxDetails(dom.tb);
  await new Promise((r) => setTimeout(r, 0));
  dom.tb.querySelector = origQs;
  assert.equal(dom.made.rows.length, 2, 'a 与 c 都必须恢复（迭代不因 b 缺席跳过 c）');
  assert.equal(mod.libIdxDetailOpen.size, 2, 'b 从展开集合清出');
});
