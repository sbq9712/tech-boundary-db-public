// Exercise the production renderer, not a copy of its state mapping.
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import assert from 'node:assert/strict';
const source = readFileSync(new URL('../../app.js', import.meta.url), 'utf8');
const renderer = source.slice(source.indexOf('const LIB_ROUTE_STATE_LABELS='), source.indexOf('async function libOpenIdxDetail('));
const escape = source.split('\n').find(line => line.startsWith('function escapeHtml('));
const render = runInNewContext(`${escape}\n${renderer}\nlibIdxDetailRowHtml`);
for (const [state, label] of [['complete', '完成'], ['queued', '排队中'], ['partial', '部分'], ['unknown', '未知']]) {
  test(`actual detail renderer: ${state}`, () => {
    const detail = { observed_at: '2026-10-08T13:00:00+00:00', searchable: state === 'complete' ? true : null,
      states: Object.fromEntries(['breadth_visible', 'vector', 'keyword', 'graph'].map(k => [k, {state, reason: '<failure>'}])),
      index: {documents_checked: 3, documents_found: 2} };
    const html = render(detail, 7);
    for (const route of ['广度可见', '向量索引', '关键词索引', '知识图谱']) assert.ok(html.includes(route));
    assert.ok(html.includes(label));
    assert.ok(html.includes('观察时间 2026-10-08T13:00:00+00:00'));
    assert.ok(html.includes('文档 2/3'));
    assert.ok(html.includes('&lt;failure&gt;'));
    assert.ok(!html.includes('<failure>'));
  });
}
test('unreachable is not complete', () => assert.ok(render(null, 7).includes('服务不可达')));
