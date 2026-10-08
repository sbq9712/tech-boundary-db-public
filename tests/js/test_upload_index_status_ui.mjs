// 任务一 1.1/1.3 前端契约：上传状态真实化（app.js GitHub 分支）
//   node tests/js/test_upload_index_status_ui.mjs
// 覆盖：新状态词表、GitHub 分支渲染 index_detail 计数子行、失败/未知
// 可重试按钮、排队/构建中自动轮询、重试按钮在提前 return 的分支内绑定。
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

// ── 状态词表 ──
const labelsMatch = src.match(/const libStatusLabels=\{[^}]*\};/);
check('libStatusLabels 存在', !!labelsMatch);
const labels = labelsMatch ? labelsMatch[0] : '';
for (const [k, v] of [
  ['indexed', '队列完成，待核验'], ['index_failed', '索引失败'],
  ['index_processing', '索引构建中'], ['index_queued', '排队待索引'],
  ['import_failed', '导入失败'], ['no_new_records', '零新增记录'],
  ['legacy_unknown', '状态未知'],
]) {
  check(`词表含 ${k}=${v}`, labels.includes(`${k}:"${v}"`));
}

// ── GitHub 分支渲染逻辑（逻辑等价复刻断言）──
// 状态子行拼接规则：任务 done/total、失败数、会话 flags 与计数
function githubStatusSub(f, libIsAdmin) {
  const status = f.ingestion_status || 'legacy_unclassified';
  const idx = f.index_detail || {};
  const parts = [];
  if (idx.tasks_total != null) {
    parts.push(`任务 ${idx.tasks_done || 0}/${idx.tasks_total}`);
    if (idx.tasks_failed) parts.push(`失败 ${idx.tasks_failed}`);
  }
  if (idx.session) {
    const s = idx.session;
    if (s.replayed) parts.push('重复包回放');
    if (s.package_deduplicated) parts.push('包级去重');
    if (s.imported) parts.push(`导入 ${s.imported}`);
    if (s.skipped_duplicate) parts.push(`重复 ${s.skipped_duplicate}`);
    if (s.skipped_upstream_conflict) parts.push(`上游持有 ${s.skipped_upstream_conflict}`);
    if (s.failed) parts.push(`失败 ${s.failed}`);
  }
  const statusSub = parts.length ? parts.join(' · ') : '';
  const canRetryIdx = libIsAdmin && ['index_failed', 'import_failed', 'legacy_unknown', 'index_queued'].includes(status);
  return { statusSub, canRetryIdx };
}

let r = githubStatusSub({ ingestion_status: 'no_new_records', index_detail: { tasks_total: 0, session: { skipped_upstream_conflict: 383 } } }, true);
check('零新增显示上游持有计数', r.statusSub === '任务 0/0 · 上游持有 383');
check('零新增不可重试（无可索引内容）', r.canRetryIdx === false);

r = githubStatusSub({ ingestion_status: 'index_failed', index_detail: { tasks_total: 5, tasks_done: 3, tasks_failed: 2 } }, true);
check('索引失败显示任务与失败数', r.statusSub === '任务 3/5 · 失败 2');
check('索引失败可重试', r.canRetryIdx === true);

r = githubStatusSub({ ingestion_status: 'index_failed' }, false);
check('非管理员不可重试', r.canRetryIdx === false);

r = githubStatusSub({ ingestion_status: 'indexed', index_detail: { tasks_total: 2, tasks_done: 2, session: { imported: 2, replayed: true } } }, true);
check('已入索引显示计数与回放标记', r.statusSub === '任务 2/2 · 重复包回放 · 导入 2');

// ── 源码契约 ──
check('GitHub 分支读取 index_detail', /const idx=f\.index_detail\|\|\{\};/.test(src));
check('重试条件含四个失败态', /\["index_failed","import_failed","legacy_unknown","index_queued"\]\.includes\(status\)/.test(src));
check('GitHub 分支内绑定重试按钮（提前 return 前）', /增量包";\s*\n\s*\/\* 任务一 1\.3：GitHub 分支提前 return，重试按钮需在此绑定 \*\/\s*\n\s*tb\.querySelectorAll\("button\[data-retry-index\]"\)/.test(src) || /GitHub 分支提前 return[\s\S]{0,120}querySelectorAll\("button\[data-retry-index\]"\)/.test(src));
check('轮询条件含 index_queued/index_processing/import_processing', /\["index_queued","index_processing","import_processing"\]\.includes\(f\.ingestion_status\)/.test(src));
check('GitHub 行渲染状态子行', /\$\{statusSub\}\$\{canRetryIdx\?`<div class="cat-actions"><button class="secondary-btn" data-retry-index="/.test(src));

if (failures) { console.error(`\n${failures} 个断言失败`); process.exit(1); }
console.log('\n全部通过');
