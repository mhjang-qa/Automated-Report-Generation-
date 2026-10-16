/* Deterministic native-link fallback tests; no app launches or network traffic. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('static/notion-open.js', 'utf8');
function boot(id) {
  const elements = new Map(); const listeners = {}; const timers = new Map();
  const result = {href:null,replaced:null}; let next=1;
  for(const key of ['#landingMessage','#landingApp','#landingWeb']) elements.set(key,{textContent:'',addEventListener(name,handler){this[name]=handler;}});
  const document={hidden:false,querySelector:key=>elements.get(key),addEventListener:(name,handler)=>{listeners[name]=handler;}};
  const location={search:'?id='+encodeURIComponent(id),replace:value=>{result.replaced=value;},set href(value){result.href=value;}};
  vm.runInNewContext(source,{URLSearchParams,document,location,window:{addEventListener:(name,handler)=>{listeners[name]=handler;}},setTimeout:callback=>{const id=next++;timers.set(id,callback);return id;},clearTimeout:id=>timers.delete(id)});
  return {result,elements,document,listeners,fire(){for(const cb of [...timers.values()])cb();}};
}
const id='12345678123412341234123456789abc';
let state=boot(id); assert.equal(state.result.href,'notion://www.notion.so/'+id); state.fire();assert.equal(state.result.replaced,'https://www.notion.so/'+id);
state=boot('12345678-1234-1234-1234-123456789abc');assert.equal(state.result.href,'notion://www.notion.so/'+id);
state=boot(id);state.document.hidden=true;state.listeners.visibilitychange();state.fire();assert.equal(state.result.replaced,null);
state=boot(id);state.listeners.pagehide();state.fire();assert.equal(state.result.replaced,null);
state=boot('javascript:alert(1)');state.fire();assert.equal(state.result.href,null);assert.match(state.elements.get('#landingMessage').textContent,/올바르지/);
state=boot(id);state.elements.get('#landingApp').click();state.fire();assert.equal(state.result.replaced,'https://www.notion.so/'+id);
console.log('Notion landing: 6 scenarios passed.');
