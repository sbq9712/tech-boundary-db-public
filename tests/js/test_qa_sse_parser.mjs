// 广度页 qa.js SSE 解析链的 Node 单测（无框架，node 直跑）：
//   node tests/js/test_qa_sse_parser.mjs
// 覆盖 codex 审查修复：事件名感知派发（replace/error 不再被形状猜测丢弃）、
// 任意 chunk 切分重组、javascript: 链接降级。
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');

// ── 浏览器环境桩（qa.js 顶层只读 window/localStorage；测试中触达的
//    DOM 函数（updateStreamingMessage/showStatusIndicator）需要可写元素桩）──
function stubEl() {
  const el = {
    style: {},
    dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    addEventListener() {}, removeEventListener() {},
    appendChild(child) { return child; }, removeChild() {}, remove() {},
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
globalThis.window = {
  TECH_DB_CONFIG: undefined,
  addEventListener: () => {},
  parent: null,
};
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.document = {
  createElement: () => stubEl(),
  querySelector: () => stubEl(),
  getElementById: () => stubEl(),
  addEventListener: () => {},
  body: stubEl(),
};
globalThis.setInterval = globalThis.setInterval; // no-op 保留原语义
globalThis.clearInterval = globalThis.clearInterval;

const src = readFileSync(join(root, 'breadth', 'qa.js'), 'utf8');
// eslint-disable-next-line no-eval
(0, eval)(src.replace(/^window\.qaModule/m, 'globalThis.qaModule'));
const hooks = globalThis.qaModule.__testHooks ?? window.qaModule.__testHooks;
const { sseFrameParser, handleSSEData, renderMarkdown, _qaSafeUrl } = hooks;

let failures = 0;
function check(name, cond) {
  if (cond) { console.log(`  ok - ${name}`); }
  else { failures++; console.error(`  FAIL - ${name}`); }
}

// ── 1. chunk 切分重组 + 事件名派发 ──────────────────────────────
{
  const events = [];
  const feed = sseFrameParser();
  const full = [
    'event: status\ndata: {"step":"retrieving","message":"检索"}\n\n',
    'event: token\ndata: {"text":"固态"}\n\n',
    'event: token\ndata: {"text":"电解质"}\n\n',
    'event: citations\ndata: {"citations":[{"id":1}]}\n\n',
    'event: replace\ndata: {"content":"修复链改写后的答案"}\n\n',
    'event: done\ndata: {"answer":"终稿","citations":[]}\n\n',
  ].join('');
  const bytes = Buffer.from(full, 'utf8');
  const decoder = new TextDecoder();
  // 硬切 5 字节一块：data: 行与多字节 UTF-8 都会被切断
  let err = null;
  for (let i = 0; i < bytes.length; i += 5) {
    err = feed(decoder.decode(bytes.subarray(i, i + 5), { stream: true }), (d, ev) => {
      events.push([ev, d]);
      return null;
    });
    if (err) break;
  }
  check('chunk 切分后事件数完整（6）', events.length === 6);
  check('事件名正确传递', events.map(e => e[0]).join(',') === 'status,token,token,citations,replace,done');
}

// ── 2. handleSSEData：replace 事件整体替换内容 ─────────────────
{
  const msg = { content: '流式中的旧内容' };
  handleSSEData({ content: '修复链改写后的答案' }, msg, 'replace');
  check('replace 事件替换 content 键载荷', msg.content === '修复链改写后的答案');
}
{
  // 无事件名时回退形状猜测（旧流兼容）
  const msg = { content: '' };
  handleSSEData({ step: 'retrieving', message: '检索中' }, msg, null);
  check('无事件名回退 status', msg.content === '');
}

// ── 3. handleSSEData：error 事件返回错误（不再静默吞掉）────────
{
  const msg = { content: '部分' };
  const err = handleSSEData({ message: '向量索引尚未构建' }, msg, 'error');
  check('error 事件返回错误消息', err === '向量索引尚未构建');
}
{
  const feed = sseFrameParser();
  const msg = { content: '' };
  let got = null;
  const stream = 'event: error\ndata: {"message":"生成失败"}\n\n';
  got = feed(stream, (d, ev) => handleSSEData(d, msg, ev));
  check('解析器透传 error 终止信号', got === '生成失败');
}

// ── 4. done 事件：citations 提取 cited ids（idx=0 不丢）────────
{
  const msg = { content: '' };
  handleSSEData(
    { answer: '答', citations: [{ id: 1, record_id: 0 }, { id: 2, record_id: 5 }] },
    msg, 'done'
  );
  check('record_id=0 不被 truthy 过滤丢弃', JSON.stringify(msg.cited_record_ids) === '[0,5]');
}

// ── 5. markdown 链接 scheme 白名单 ─────────────────────────────
{
  const evil = renderMarkdown('[点我](javascript:alert(1))');
  check('javascript: 链接降级为纯文本', !evil.includes('javascript:') && evil.includes('点我'));
  const good = renderMarkdown('[论文](https://example.com/a?b=1)');
  check('https 链接保留', good.includes('href="https://example.com/a?b=1"'));
  const rel = renderMarkdown('[x](/docs/1)');
  check('相对链接保留', rel.includes('href="/docs/1"'));
  const data = renderMarkdown('[x](data:text/html,hi)');
  check('data: 链接降级', !data.includes('data:'));
  check('_qaSafeUrl 拦截 javascript:', _qaSafeUrl('javascript:alert(1)') === '#');
  check('_qaSafeUrl 放行 http:', _qaSafeUrl('http://a.b/c').startsWith('http://'));
  // codex 复审 R2-1：浏览器 URL 解析剔除 TAB/NUL/首尾控制字符，
  // `java\tscript:` / `\0javascript:` 会归一成 javascript: —— 必须拦截
  check('TAB 混淆 scheme 拦截', _qaSafeUrl('java\tscript:alert(1)') === '#');
  check('NUL 前缀混淆拦截', _qaSafeUrl('\0javascript:alert(1)') === '#');
  check('大写 scheme 拦截', _qaSafeUrl('JaVaScRiPt:alert(1)') === '#');
  const tabMd = renderMarkdown('[x](java\tscript:alert(1))');
  check('markdown 内 TAB 混淆拦截', !tabMd.includes('ascript:') || !tabMd.includes('<a href'));
  const nulMd = renderMarkdown('[x](\0javascript:alert(1))');
  check('markdown 内 NUL 混淆拦截', !nulMd.includes('<a href'));
}

// ── 6. SSE 空行复位事件名（codex 复审 R2-2）─────────────────────
{
  const feed = sseFrameParser();
  const seen = [];
  // replace 事件后仅空行分隔，下一个无名 data 事件不得继承 'replace'
  const stream = 'event: replace\ndata: {"content":"A"}\n\ndata: {"text":"t"}\n\n';
  feed(stream, (d, ev) => { seen.push(ev); return null; });
  check('空行后事件名复位为 null', seen.length === 2 && seen[1] === null);
}
{
  const feed = sseFrameParser();
  const seen = [];
  // CRLF 行尾同样复位；data 内容不受 \r 污染
  const stream = 'event: token\r\ndata: {"text":"x"}\r\n\r\ndata: {"text":"y"}\n\n';
  feed(stream, (d, ev) => { seen.push([ev, d]); return null; });
  check('CRLF 兼容：事件派发正确', seen.length === 2
    && seen[0][0] === 'token' && seen[0][1].text === 'x'
    && seen[1][0] === null && seen[1][1].text === 'y');
}

console.log(failures === 0 ? '\nALL PASS' : `\n${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
