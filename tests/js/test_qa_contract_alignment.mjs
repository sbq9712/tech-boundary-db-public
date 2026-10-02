// T6（2026-10-02）广度 qa.js 与 canonical-qa done 新契约对齐测试：
//   node tests/js/test_qa_contract_alignment.mjs
// done 载荷实有字段（server.py）：answer/citations(supports_claim_ids)/
// answer_status/stop_reason/knowledge_boundary/claim_check(紧凑)/safety_hits/
// evidence/retrieval_trace。已不含：claims 明细/reference_cards/evidence_summary/
// grounding_status。覆盖：claim_check 派生 evidence_summary、supports_claim_ids
// 派生主张映射、边界条/安全提示渲染、done 存储与持久化、死字段不渲染。
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
let failures = 0;
function check(name, cond) {
  if (cond) { console.log(`  ok - ${name}`); }
  else { failures++; console.error(`  FAIL - ${name}`); }
}

// ── 浏览器桩（同 test_qa_sse_parser.mjs） ──
function stubEl() {
  const el = {
    style: {}, dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener() {}, removeEventListener() {},
    appendChild(c) { return c; }, removeChild() {}, remove() {},
    focus() {}, click() {}, scrollTo() {},
    setAttribute() {}, getAttribute() { return null; },
    querySelector: () => stubEl(), querySelectorAll: () => [],
    _t: '', get innerHTML() { return this._t.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); },
    set innerHTML(v) { this._t = String(v); },
    set textContent(v) { this._t = String(v); }, get textContent() { return this._t; },
  };
  return el;
}
globalThis.window = { TECH_DB_CONFIG: undefined, addEventListener: () => {}, parent: null };
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
globalThis.document = {
  createElement: () => stubEl(), querySelector: () => stubEl(),
  getElementById: () => stubEl(), addEventListener() {}, body: stubEl(),
};

const src = readFileSync(join(root, 'breadth', 'qa.js'), 'utf8');
(0, eval)(src.replace(/^window\.qaModule/m, 'globalThis.qaModule'));
const hooks = globalThis.qaModule.__testHooks ?? window.qaModule.__testHooks;
const { handleSSEData, deriveEvidenceSummary, deriveClaimsFromCheck, renderBoundaryAndSafety } = hooks;

// ═══ 1. done 事件存储新契约字段 ═══
console.log('done 存储');
const mk = () => ({ role: 'assistant', content: '', streaming: true });
let msg = mk();
handleSSEData({
  answer: '答',
  citations: [{ id: 1, title: 't', url: 'https://x/1', supports_claim_ids: ['c1', 'c2'] },
              { id: 2, title: 't2', url: 'https://x/2', supports_claim_ids: ['c1'] }],
  answer_status: 'PARTIALLY_SUPPORTED',
  knowledge_boundary: '库内资料截止 2026-09-30',
  claim_check: { claims_total: 3, claims_supported: 2, unsupported_major_claims: ['c3'] },
  safety_hits: [{ type: 'leak_hint' }, { type: 'pii' }],
}, msg, 'done');
check('claim_check 存储', msg.claim_check && msg.claim_check.claims_total === 3);
check('knowledge_boundary 存储', msg.knowledge_boundary === '库内资料截止 2026-09-30');
check('safety_hits 存储', Array.isArray(msg.safety_hits) && msg.safety_hits.length === 2);

// ═══ 2. deriveEvidenceSummary：claim_check → 徽标摘要行形态 ═══
console.log('派生 evidence_summary');
const es = deriveEvidenceSummary({ claims_total: 6, claims_supported: 4, unsupported_major_claims: ['c2', 'c5'] });
check('总数/已支持/未支持', es.requirements_total === 6 && es.requirements_supported === 4 && es.requirements_unsupported === 2);
check('空 claim_check → null（不渲染）', deriveEvidenceSummary(null) === null && deriveEvidenceSummary({}) === null);
check('总数 0 → null', deriveEvidenceSummary({ claims_total: 0 }) === null);

// ═══ 3. deriveClaimsFromCheck：supports_claim_ids → 主张→引用映射 ═══
console.log('派生主张映射');
const cites = [
  { id: 1, supports_claim_ids: ['c1', 'c2'] },
  { id: 2, supports_claim_ids: ['c1'] },
];
const claims = deriveClaimsFromCheck({ claim_check: { unsupported_major_claims: ['c2', 'c9'] } }, cites);
const byId = Object.fromEntries(claims.map(c => [c.id, c]));
check('主张宇宙 = 支撑并集 ∪ 未支持集', byId.c1 && byId.c2 && byId.c9);
check('c1 有两条支撑引用', byId.c1.relations.length === 2);
check('c1 状态 SUPPORTED', byId.c1.status === 'SUPPORTED');
check('c2/c9 状态 UNSUPPORTED', byId.c2.status === 'UNSUPPORTED' && byId.c9.status === 'UNSUPPORTED');
check('无 claim_check → 空数组', deriveClaimsFromCheck(null, cites).length === 0);
check('无 supports_claim_ids 只剩未支持行',
  deriveClaimsFromCheck({ claim_check: { unsupported_major_claims: ['c3'] } }, [{ id: 1 }]).length === 1);

// ═══ 4. 边界条 + 安全提示渲染 ═══
console.log('边界与安全');
const bOut = renderBoundaryAndSafety({ knowledge_boundary: '库内资料截止 2026-09-30' });
check('边界条渲染', bOut.includes('库内边界') && bOut.includes('2026-09-30'));
const sOut = renderBoundaryAndSafety({ safety_hits: [{ type: 'leak_hint' }] });
check('安全提示计数', sOut.includes('命中 1 处') && sOut.includes('leak_hint'));
check('全空 → 不渲染', renderBoundaryAndSafety({}) === '' && renderBoundaryAndSafety(null) === '');
const xssOut = renderBoundaryAndSafety({ knowledge_boundary: '<img src=x onerror=alert(1)>' });
check('边界条 HTML 转义', !xssOut.includes('<img') && xssOut.includes('&lt;img'));
const xssOut2 = renderBoundaryAndSafety({ safety_hits: [{ type: '<script>x</script>' }] });
check('安全类型转义', !xssOut2.includes('<script>'));

// ═══ 5. 源契约：死字段不再渲染；新字段持久化 ═══
console.log('源契约');
check('reference_cards 渲染已删（保留兼容存储）',
  !src.includes('referenceCards.find') && !src.includes('qa-reference-role') && !src.includes('SOURCE_SNAPSHOT_DRIFT'));
check('grounding 徽标模板已删（防御性过滤保留给旧缓存）',
  !src.includes('grounding_status.toLowerCase')
  && !src.includes('📍 精确对位') && !src.includes('相似对位</span>'));
check('supports_claim_ids 契约字段仍用（支撑主张徽标）', src.includes('支撑主张'));
check('claim_check 持久化到 localStorage', /claim_check:\s*m\.claim_check/.test(src));
check('boundary/safety 持久化', /knowledge_boundary:\s*m\.knowledge_boundary/.test(src) && /safety_hits:\s*Array\.isArray\(m\.safety_hits\)/.test(src));


// ═══ 6. 端到端验收：真实 done 契约载荷 → 证据区有内容 ═══
console.log('端到端验收（renderAssistantMessage 全链路）');
const { renderAssistantMessage } = hooks;
const liveMsg = mk();
handleSSEData({
  answer: '固态电池 2026 年进入中试线阶段[1]，但量产时间表仍存争议[2]。',
  citations: [
    { id: 1, title: '固态电池中试进展', url: 'https://example.com/a', date: '2026-08-01', source: '来源A', supports_claim_ids: ['claim_1', 'claim_2'] },
    { id: 2, title: '量产争议', url: 'https://example.com/b', date: '2026-08-02', source: '来源B', supports_claim_ids: ['claim_1'] },
  ],
  answer_status: 'PARTIALLY_SUPPORTED',
  stop_reason: 'max_claims',
  knowledge_boundary: '库内资料截止 2026-09-30，之后进展未覆盖',
  claim_check: { claims_total: 3, claims_supported: 2, unsupported_major_claims: ['claim_3'] },
  safety_hits: [{ type: 'forward_looking' }],
  evidence: { status: 'sufficient' },
  retrieval_trace: { stages: [] },
}, liveMsg, 'done');
liveMsg.streaming = false;
const html = renderAssistantMessage(liveMsg, 0);
check('徽标渲染（部分支持）', html.includes('部分支持'));
check('摘要行含主张计数（派生）', html.includes('主张3条') && html.includes('已支持2条') && html.includes('关键未支持1条'));
check('边界条渲染', html.includes('库内边界') && html.includes('2026-09-30'));
check('安全提示渲染', html.includes('命中 1 处'));
check('证据卡片渲染（派生主张→引用映射，未支持主张成行）',
  html.includes('证据卡片') && html.includes('主张3') && html.includes('关键未支持'));
check('支撑主张徽标（supports_claim_ids 实契约字段）', html.includes('支撑主张'));
check('引用条目渲染（无 grounding/reference_cards 死字段）', html.includes('来源引用（2条）') && !html.includes('精确对位') && !html.includes('来源角色'));
check('正文 [N] 引用映射', html.includes('data-citation="1"'));

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
