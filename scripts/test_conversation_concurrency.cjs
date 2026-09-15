const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// Actual app.js and real ReadableStream; only DOM and remote model/API are doubles.
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {value:'', style:{}, hidden:false,
    innerHTML:'', scrollTop:0, scrollHeight:100, focus(){}, addEventListener(){}});
  return elements.get(id);
}
const streams = [];
const context = vm.createContext({
  console, AbortController, TextDecoder, URLSearchParams, setTimeout, clearTimeout,
  localStorage:{getItem(){return '';},setItem(){},removeItem(){}},
  location:{hash:'#home'},
  window:{addEventListener(){},confirm(){return true;}},
  document:{getElementById:element,addEventListener(){},querySelector(){return null;}},
  fetch: async (url, options) => {
    assert.equal(url, '/api/assistant/stream');
    let output;
    const body = new ReadableStream({start(controller){output=controller;}});
    options.signal.addEventListener('abort',()=>output.error(
      Object.assign(new Error('stopped'),{name:'AbortError'})));
    const stream = {options,output};
    streams.push(stream);
    // Hold headers until the test explicitly releases them.
    return await new Promise(resolve => {stream.headers=()=>resolve({
      ok:true,headers:{get(){return 'session-'+streams.indexOf(stream);}},body
    });});
  },
});
const source = fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
vm.runInContext(source,context);
const run = code => vm.runInContext(code,context);
run("loadConversations=async()=>{}; bindEvents=()=>{}; shell=()=>''; loadAssistantModels=()=>{}; loadHomeBoundaries=()=>{}; loadAlertIntel=()=>{}; loadKnowledgeGraph=()=>{}; closeUploadModal=()=>{}; loadDashboards=()=>{};");
const tick = () => new Promise(resolve=>setImmediate(resolve));
function event(index,type,data) {
  streams[index].output.enqueue(new TextEncoder().encode(
    'event: '+type+'\ndata: '+JSON.stringify(data)+'\n\n'));
}

(async()=>{
  const a=run("submitQuery({query:'A'})");
  run('startNewConversation()');
  const b=run("submitQuery({query:'B'})");
  assert.equal(streams.length,2);
  assert.equal(streams[0].options.signal.aborted,false);
  assert.equal(streams[1].options.signal.aborted,false);
  await run("loadConversationMessages('pending-1')");
  streams[1].headers(); streams[0].headers(); await tick();
  event(0,'token',{content:'answer A'}); event(1,'token',{content:'answer B'});
  await tick();
  assert.equal(run('activeSessionId'),'session-0');
  assert.equal(run('activeSessionMessages[1].text'),'answer A');
  assert.equal(run('conversationRequests.size'),2);
  // SPA navigation keeps the same message array and latest controls.
  run("location.hash='#dashboard'; render(); location.hash='#home'; render()");
  assert.equal(run('activeSessionMessages[1].text'),'answer A');
  assert.equal(element('askBtn').disabled,true);
  await run("loadConversationMessages('session-1')");
  event(0,'done',{response:'complete A',session_id:'session-0'});
  streams[0].output.close(); await a;
  assert.equal(run('activeSessionId'),'session-1');
  assert.equal(run('activeSessionMessages[1].text'),'answer B');
  assert.equal(element('askBtn').disabled,true);
  await run("loadConversationMessages('session-0')");
  assert.equal(run('activeSessionMessages[1].text'),'complete A');
  assert.equal(element('askBtn').disabled,false);
  // Starting C and stopping it must leave B alive.
  run('startNewConversation()');
  const c=run("submitQuery({query:'C'})"); streams[2].headers(); await tick();
  run('currentConversationRequest().controller.abort()');
  await c;
  assert.equal(streams[1].options.signal.aborted,false);
  event(1,'done',{response:'complete B',session_id:'session-1'});
  streams[1].output.close(); await b;
  await run("loadConversationMessages('session-1')");
  assert.equal(run('activeSessionMessages[1].text'),'complete B');
  assert.equal(run('conversationRequests.size'),0);
  console.log('PASS: simultaneous streams, delayed headers, navigation, background completion, isolated stop');
})().catch(error=>{console.error(error);process.exitCode=1;});
