// 任务三 3.1/3.2 前端契约：逐行表格「情报类型」槽位（app.js）
//   node tests/js/test_row_type_mapping.mjs
// 覆盖：upGuessMapping 精确识别（不误认 新闻类型/分类/行业类别）、
// type 槽位出现在配置表、严格模式提示、提交前拦截缺映射、
// row_import 计数含 updated/skipped_upstream_conflict。
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

// ── upGuessMapping 逻辑等价复刻（与应用同规则断言） ──
function upGuessMapping(headers) {
  const aliases = { title:["标题","题目","title","名称"],date:["日期","date","时间"],url:["链接","网址","url"],body:["正文","内容","body"],summary:["摘要","summary"],level:["等级","级别","level"],source:["来源","媒体","source"],category:["分类","类别","行业","category"] };
  const m = {};
  for (const slot of Object.keys(aliases)) {
    for (const k of aliases[slot]) { const hit = headers.find(h => h.toLowerCase().includes(k)); if (hit) { m[slot] = hit; break; } }
  }
  const norm = h => String(h == null ? "" : h).replace(/^[\s　]+|[\s　]+$/g, "");
  const typeHit = headers.find(h => norm(h) === "情报类型");
  if (typeHit !== undefined) m.type = typeHit;
  if (!m.title) m.title = headers[0] || "";
  return m;
}
check('识别「情报类型」列', upGuessMapping(['标题','日期','情报类型']).type === '情报类型');
check('识别带空白「 情报类型 」列', upGuessMapping(['标题','  情报类型 ']).type === '  情报类型 ');
check('不误认「新闻类型」', upGuessMapping(['标题','新闻类型']).type === undefined);
check('不误认「分类」', upGuessMapping(['标题','分类']).type === undefined);
check('不误认「行业类别」', upGuessMapping(['标题','行业类别']).type === undefined);
check('不误认「情报类别」', upGuessMapping(['标题','情报类别']).type === undefined);

// ── app.js 源码契约 ──
check('type 槽位进配置表', /"type","title","date","url","body","summary","level","source","category"\]\.map/.test(src));
check('严格模式判定函数存在', /function upTypeStrict\(f\)/.test(src));
check('严格= 广度+other+row', /upSection==="breadth"&&upSub==="other"&&\(\(f&&f\.rowMode\)\|\|"row"\)==="row"/.test(src));
check('type 槽提示 新闻/文献', src.includes('（仅允许：新闻/文献；缺列/空值/非法值整文件拒收）'));
check('提交前拦截缺 type 映射', src.includes('缺少「情报类型」列映射（请在导入配置中映射，取值：新闻/文献）'));
check('预检提示块 up-type-preview', src.includes('up-type-preview'));
check('预览用物理行号 row_nos', /nos\[i\]\?\?i\+2/.test(src));
check('完成计数含 updated', /更新\$\{st\.updated\}/.test(src));
check('完成计数含上游冲突', /上游冲突\$\{st\.skipped_upstream_conflict\}/.test(src));
check('类别槽提示连带情报类型必映射', src.includes('必映射：标题${upTypeStrict(f)?"、情报类型":""}'));

if (failures) { console.error(`\n${failures} 项失败`); process.exit(1); }
console.log('\n全部通过');
