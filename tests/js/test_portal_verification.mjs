// T5（2026-10-02）门户答案核验摘要测试：
//   node tests/js/test_portal_verification.mjs
// 覆盖：done 四件套保留（源契约）、历史 retrieval_summary 提升（源契约）、
// renderVerificationSummary 四态徽标/计数/边界条/安全提示/优雅降级行为。
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
let failures = 0;
function check(name, cond) {
  if (cond) { console.log(`  ok - ${name}`); }
  else { failures++; console.error(`  FAIL - ${name}`); }
}

// ── 浏览器桩（与 test_safe_url.mjs 同法：app.js 顶层惰性 DOM） ──
function stubEl() {
  const el = {
    style: {}, dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener() {}, removeEventListener() {},
    appendChild(c) { return c; }, removeChild() {}, remove() {},
    focus() {}, click() {}, scrollTo() {},
    setAttribute() {}, getAttribute() { return null; },
    querySelector: () => stubEl(), querySelectorAll: () => [],
    _t: '', get innerHTML() { return this._t; }, set innerHTML(v) { this._t = String(v); },
    set textContent(v) { this._t = String(v); }, get textContent() { return this._t; },
  };
  return el;
}
globalThis.window = globalThis;
globalThis.document = {
  createElement: () => stubEl(), querySelector: () => stubEl(), querySelectorAll: () => [],
  getElementById: () => stubEl(), addEventListener() {}, body: stubEl(), head: stubEl(),
  documentElement: stubEl(),
};
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
globalThis.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
globalThis.addEventListener = () => {}; globalThis.removeEventListener = () => {};
globalThis.matchMedia = () => ({ matches: false, addEventListener() {} });
globalThis.location = { href: 'http://x/', origin: 'http://x', pathname: '/', search: '', hash: '' };
globalThis.history = { replaceState() {}, pushState() {} };
globalThis.TechDBSafeUrl = { safeUrl: (u) => String(u || ''), safeHref: (u) => String(u || '') };

const appSrc = readFileSync(join(root, 'app.js'), 'utf8');
(0, eval)(appSrc);

// ═══ 1. 源契约：done 保留四件套 / 历史提升 ═══
console.log('源契约');
check('done extra 保留 answer_status', appSrc.includes('answer_status:data.answer_status||null'));
check('done extra 保留 knowledge_boundary', appSrc.includes('knowledge_boundary:data.knowledge_boundary||null'));
check('done extra 保留 claim_check', appSrc.includes('claim_check:(data.claim_check&&typeof data.claim_check===\'object\')?data.claim_check:null'));
check('done extra 保留 safety_hits', appSrc.includes('safety_hits:Array.isArray(data.safety_hits)?data.safety_hits:[]'));
check('历史加载从 retrieval_summary 提升 answer_status',
  appSrc.includes('retrieval_summary.answer_status'));
check('历史加载从 summary 提升 claim_check/boundary',
  appSrc.includes('retrieval_summary.claim_check'));

// ═══ 2. renderVerificationSummary 行为 ═══
console.log('四态徽标');
const rvs = globalThis.renderVerificationSummary;
check('renderVerificationSummary 全局可用', typeof rvs === 'function');

check('SUPPORTED → 证据充分支持', rvs({ answer_status: 'SUPPORTED' }).includes('证据充分支持'));
check('PARTIALLY_SUPPORTED → 部分支持', rvs({ answer_status: 'PARTIALLY_SUPPORTED' }).includes('部分支持'));
check('UNSUPPORTED → 证据不支持', rvs({ answer_status: 'UNSUPPORTED' }).includes('证据不支持'));
check('UNVERIFIED → 未能验证', rvs({ answer_status: 'UNVERIFIED' }).includes('未能验证'));
check('小写状态归一', rvs({ answer_status: 'supported' }).includes('证据充分支持'));

console.log('计数与边界');
const cc = { claims_total: 6, claims_supported: 4, unsupported_major_claims: ['c2', 'c5'], boundary_message: '库内资料截止 2026-09' };
const out = rvs({ answer_status: 'PARTIALLY_SUPPORTED', claim_check: cc, knowledge_boundary: '库内资料截止 2026-09' });
check('主张计数行', out.includes('主张 6 条') && out.includes('已支持 4') && out.includes('关键未支持 2'));
check('边界条渲染（转义）', out.includes('库内资料截止 2026-09'));
check('未知状态不渲染', rvs({ answer_status: 'WEIRD' }) === '');
check('空 extra 不渲染', rvs(null) === '' && rvs({}) === '');
check('旧后端（无任何核验字段）不渲染', rvs({ citations: [], retrieval_summary: { knowledge_base: 3 } }) === '');

console.log('历史回退');
const hist = { retrieval_summary: { answer_status: 'UNSUPPORTED', claim_check: cc, safety_hits: [{ type: 'leak_hint' }] } };
const hout = rvs(hist);
check('历史 retrieval_summary 回退渲染', hout.includes('证据不支持') && hout.includes('主张 6 条'));
check('历史安全提示计数', hout.includes('命中 1 处') && hout.includes('leak_hint'));

console.log('安全提示');
const withHits = rvs({ answer_status: 'SUPPORTED', safety_hits: [{ type: 'secret_leak' }, { type: 'pii' }] });
check('safety_hits 计数与示例类型', withHits.includes('命中 2 处') && withHits.includes('secret_leak'));

console.log('注入防御');
const xss = rvs({ answer_status: 'SUPPORTED', knowledge_boundary: '<img src=x onerror=alert(1)>边界' });
check('boundary HTML 转义', !xss.includes('<img') && xss.includes('&lt;img'));
const xss2 = rvs({ answer_status: 'SUPPORTED', safety_hits: [{ type: '<script>x</script>' }] });
check('safety type 转义', !xss2.includes('<script>'));

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
