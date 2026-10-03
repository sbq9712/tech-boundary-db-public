// 2026-10-03 Codex 评审采纳（P3-4/P3-5）：断连文案 + 行预览并发去重契约。
//   node tests/js/test_review_hardening_ui.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const src = readFileSync(join(root, 'app.js'), 'utf8');
let failures = 0;
function check(name, cond) {
  if (cond) console.log(`  ok - ${name}`);
  else { failures++; console.error(`  FAIL - ${name}`); }
}

// ── P3-4：断连文案不得暗示后台仍在生成（断开后端会取消 run）──
check('断连文案不再声称「可能仍在后台生成」',
  !src.includes('可能仍在后台生成'));
check('断连文案引导点击重试', src.includes('连接已中断，请点击"重试"重新提问。'));

// ── P3-5：行预览 in-flight 去重 + 数据性失败不自动重试 ──
const fnStart = src.indexOf('async function upLoadRowPreview');
const fnEnd = src.indexOf('/* 单个表格文件的独立配置弹窗', fnStart);
check('upLoadRowPreview 存在且边界可定位', fnStart >= 0 && fnEnd > fnStart);
const fn = src.slice(fnStart, fnEnd);
check('预览请求 in-flight 去重（复用进行中 Promise）',
  fn.includes('if(f._previewReq)return f._previewReq') &&
  fn.includes('f._previewReq=(async()=>{') &&
  fn.includes('})().finally(()=>{f._previewReq=null;});'));
check('「没有可用工作表」标记为数据性结论（_previewNoSheets）',
  fn.includes('f._previewNoSheets=true'));
const radioIdx = src.indexOf('r.value==="row"&&!f._previewSheets');
check('单选切回逐行自动补拉预览（传输失败可重试）', radioIdx > 0);
check('单选重试条件排除数据性失败（无工作表不重试）',
  src.includes('!f._previewSheets&&!f._previewNoSheets'));

console.log(failures === 0 ? '\nALL PASSED' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
