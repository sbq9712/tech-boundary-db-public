import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const source=readFileSync(new URL('../../app.js', import.meta.url),'utf8');
const start=source.indexOf('function upRenderList(){');
const end=source.indexOf('/* 输入框变化写回',start);
function render(rowMode, section='industry'){
  const list={innerHTML:'',querySelectorAll:()=>[]};
  const nodes={upList:list,upTableWrap:{},upSubmit:{}};
  const context={document:{getElementById:id=>nodes[id],querySelector:()=>null},
    upPending:[{name:'sample.csv',size:20,rowMode}],upTaxonomy:[],
    upRowStateMeta:()=>({cls:'',text:''}),upIsTableRowFile:()=>true,
    escapeHtml:s=>String(s??''),libFmtSize:()=> '20 B',upTaxonomyOptions:()=>'',
    upSyncColVisible:()=>['industry','atsc'].includes(section),upRowCfgLabel:()=> 'Sheet1',
    upBindRowInputs:()=>{},upFillTaxonomy:()=>{}};
  vm.runInNewContext(source.slice(start,end)+'\nupRenderList();',context);
  return list.innerHTML;
}
test('row mode is a visible column and file date is hidden before preview',()=>{
  const html=render('row');
  assert.match(html,/<td class="lib-up-mode-cell">\s*<div class="lib-up-mode"/);
  assert.ok(html.includes('每行一个情报')&&html.includes('整个文件一个情报'));
  assert.match(html,/data-up-datebox="0" hidden/);
  assert.ok(html.includes('取自每行'));
});
test('file mode restores date and synchronization defaults to No in both sections',()=>{
  for(const section of ['industry','atsc']){
    const html=render('file',section);
    assert.doesNotMatch(html,/data-up-datebox="0" hidden/);
    const checkbox=html.match(/<input type="checkbox"[^>]*>/)[0];
    assert.ok(!checkbox.includes('checked'));
    assert.ok(!html.includes('data-up-cfg'));
  }
});
