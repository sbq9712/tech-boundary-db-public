// T7/G11（2026-10-02）共享 URL 消毒器 + 门户/广度两页接线的行为与契约测试：
//   node tests/js/test_safe_url.mjs
// 覆盖：safe_url.js 本体（scheme 白名单/控制字符剔除/引号编码/实体转义）、
// app.js inlineMd 与动态 href 注入点、HTML 加载顺序。
// 2026-10-03：qa.js 委托段随广度「数据库问答」视图移除而删除。
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const require_ = createRequire(import.meta.url);

let failures = 0;
function check(name, cond) {
  if (cond) { console.log(`  ok - ${name}`); }
  else { failures++; console.error(`  FAIL - ${name}`); }
}

// ── 浏览器桩（qa.js/app.js 顶层只读 window/localStorage/DOM 惰性） ──
function stubEl() {
  const el = {
    style: {}, dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener() {}, removeEventListener() {},
    appendChild(c) { return c; }, removeChild() {}, remove() {},
    focus() {}, click() {}, scrollTo() {},
    setAttribute() {}, getAttribute() { return null; },
    querySelector: () => stubEl(), querySelectorAll: () => [],
    _t: '',
    get innerHTML() { return this._t; },
    set innerHTML(v) { this._t = String(v); },
    set textContent(v) { this._t = String(v); },
    get textContent() { return this._t; },
  };
  return el;
}
function installStubs() {
  globalThis.window = globalThis;
  globalThis.document = {
    createElement: () => stubEl(),
    querySelector: () => stubEl(),
    querySelectorAll: () => [],
    getElementById: () => stubEl(),
    addEventListener() {},
    body: stubEl(), head: stubEl(), documentElement: stubEl(),
  };
  globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
  globalThis.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
  globalThis.addEventListener = () => {};
  globalThis.removeEventListener = () => {};
  globalThis.matchMedia = () => ({ matches: false, addEventListener() {} });
  globalThis.location = { href: 'http://x/', origin: 'http://x', pathname: '/', search: '', hash: '' };
  globalThis.history = { replaceState() {}, pushState() {} };
}

// ═══ 1. safe_url.js 本体（CommonJS 导出，Node 直测） ═══
console.log('safe_url.js 本体');
const safe = require_(join(root, 'assets', 'lib', 'safe_url.js'));
check('javascript: → #', safe.safeUrl('javascript:alert(1)') === '#');
check('java\\tscript: 控制字符剔除后 → #', safe.safeUrl('java\tscript:alert(1)') === '#');
check('\\0javascript: NUL 剔除后 → #', safe.safeUrl('\0javascript:alert(1)') === '#');
check('java\\nscript: LF 剔除后 → #', safe.safeUrl('java\nscript:alert(1)') === '#');
check('data:text/html → #', safe.safeUrl('data:text/html,<script>alert(1)</script>') === '#');
check('vbscript: → #', safe.safeUrl('vbscript:msgbox(1)') === '#');
check('JaVaScRiPt: 大小写 → #', safe.safeUrl('JaVaScRiPt:alert(1)') === '#');
check('https:// 放行', safe.safeUrl('https://example.com/a?b=1') === 'https://example.com/a?b=1');
check('HTTP:// 大小写放行', safe.safeUrl('HTTP://example.com/') === 'HTTP://example.com/');
check('mailto: 放行', safe.safeUrl('mailto:a@b.example') === 'mailto:a@b.example');
check('相对地址放行', safe.safeUrl('/rel/path') === '/rel/path');
check('#anchor 放行', safe.safeUrl('#frag') === '#frag');
check('空/None → 空串', safe.safeUrl('') === '' && safe.safeUrl(null) === '' && safe.safeUrl(undefined) === '');
check('前后空格剔除后判定', safe.safeUrl('  javascript:alert(1)  ') === '#');

// safeHref：属性插值安全
check('safeHref 引号百分号编码（无裸引号）',
  !safe.safeHref('/a" onmouseover="alert(1)').includes('"'));
// 实体绕过：字符串里的 & 一律实体化，浏览器属性解码后仍是字面 &…，
// 不会还原成 javascript:（scheme 判定也不会命中 & 开头中断的序列）
const entOut = safe.safeHref('javascript&colon;alert(1)');
// 每个 & 都必须是 &amp;（属性解码后仍是字面 &，scheme 判定不成立）
const everyAmpEncoded = !/[&](?!amp;)/.test(entOut);
check('safeHref & 实体转义（防 &colon;/&#58; 实体绕过）',
  entOut === 'javascript&amp;colon;alert(1)' && everyAmpEncoded
  && !entOut.startsWith('javascript:'));
check('safeHref < > 转义', !safe.safeHref('https://x/<b>').includes('<'));

// ═══ 2.（已删除）qa.js 委托段 ═══
// 2026-10-03：广度页「数据库问答」视图整体移除（问答入口统一收敛到门户
// index.html /api/assistant/stream），breadth/qa.js 随之删除；其安全行为
// （safeUrl 委托）由共享 assets/lib/safe_url.js 本体（第 1 节）与门户
// app.js 注入点（第 3 节）继续覆盖。

// ═══ 3. app.js inlineMd / 动态 href 注入点（整文件 eval + 全局函数） ═══
console.log('app.js 注入点');
installStubs();
globalThis.TechDBSafeUrl = safe; // 模拟 index.html 先加载 safe_url.js
const appSrc = readFileSync(join(root, 'app.js'), 'utf8');
(0, eval)(appSrc);
check('app.js eval 后 inlineMd 可用', typeof globalThis.inlineMd === 'function');
const out1 = globalThis.inlineMd('[点我](javascript:alert(1))');
check('inlineMd javascript: → href="#"', out1.includes('href="#"') && !out1.includes('javascript:'));
const out2 = globalThis.inlineMd('[x](java\tscript:alert(1))');
check('inlineMd java\\tscript: → href="#"', out2.includes('href="#"'));
const out3 = globalThis.inlineMd('[ok](https://example.com/a)');
check('inlineMd https 正常链接', out3.includes('href="https://example.com/a"'));
const out4 = globalThis.inlineMd('[q](/a" onmouseover="alert(1))');
check('inlineMd 引号不出现在 href', !(/href="[^"]*"[^ >]/.test(out4)) && !out4.includes('" onmouseover'));
const out5 = globalThis.inlineMd('[d](data:text/html,<script>alert(1)</script>)');
check('inlineMd data:text/html → #', out5.includes('href="#"'));

// renderMarkdown（app 内 QA 用的第二个 inlineMd）同样走消毒器
if (typeof globalThis.renderMarkdown === 'function') {
  const rm = globalThis.renderMarkdown('[md](javascript:alert(1))');
  check('renderMarkdown javascript: → href="#"', rm.includes('href="#"') && !rm.includes('javascript:'));
} else {
  check('renderMarkdown 存在', false);
}

// ═══ 4. 源契约：无残留裸插值 + HTML 加载顺序 ═══
console.log('源契约');
const appSrcRaw = readFileSync(join(root, 'app.js'), 'utf8');
check('app.js 无裸 href="$2" 链接插值', !appSrcRaw.includes("'<a href=\"$2\""));
check('app.js 动态 href 全部走 techdbSafeHref',
  !appSrcRaw.includes('href="${escapeHtml(target)}"')
  && !appSrcRaw.includes('href="${escapeHtml(c.url)}"')
  && !appSrcRaw.includes('href="${escapeHtml(d.url)}"'));
const idxHtml = readFileSync(join(root, 'index.html'), 'utf8');
check('index.html 加载 safe_url.js',
  idxHtml.includes('assets/lib/safe_url.js'));
check('index.html safe_url.js 先于 app.js',
  idxHtml.indexOf('assets/lib/safe_url.js') < idxHtml.indexOf('app.js?v='));
const brHtml = readFileSync(join(root, 'breadth', 'index.html'), 'utf8');
check('breadth/index.html 加载 ../assets/lib/safe_url.js',
  brHtml.includes('../assets/lib/safe_url.js'));
check('breadth safe_url.js 先于 app.js',
  brHtml.indexOf('../assets/lib/safe_url.js') < brHtml.indexOf('app.js?v='));
// 2026-10-03：qa.js 已随广度「数据库问答」视图移除——确保不再被页面引用。
check('breadth/index.html 不再加载 qa.js', !brHtml.includes('qa.js'));

// ═══ 2026-10-03 Codex P1/P2 采纳：同步广度区块的安全与数据完整性契约 ═══
const appSrc2 = readFileSync(join(root, 'app.js'), 'utf8');
const fnStart = appSrc2.indexOf('async function loadSyncedBreadthBlock');
const fnEnd = appSrc2.indexOf('function libFmtSize', fnStart);
check('loadSyncedBreadthBlock 存在', fnStart >= 0 && fnEnd > fnStart);
const fnSrc = appSrc.slice(fnStart, fnEnd);
// P1：同步记录 rec.url 必须过 safeHref 白名单（escapeHtml 不拦 javascript:）
check('同步广度区块 rec.url 使用 techdbSafeHref',
  fnSrc.includes('href="${techdbSafeHref(rec.url)}"') &&
  !fnSrc.includes('href="${escapeHtml(rec.url)}"'));
// P2：服务端 origin_section 过滤 + 截断提示
check('同步广度区块走服务端 origin_section 过滤',
  fnSrc.includes('origin_section=industry,atsc'));
check('同步广度区块展示截断提示（count>rows 时）',
  fnSrc.includes('total>rows.length') && fnSrc.includes('当前显示最新'));

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
