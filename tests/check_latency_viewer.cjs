const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {JSDOM,VirtualConsole}=require(process.env.FLOW_XRAY_JSDOM);
const html=fs.readFileSync(process.argv[2],'utf8'),errors=[];
const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(html,{runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:vc});
const w=dom.window,d=w.document;
w.HTMLElement.prototype.scrollIntoView=function(){};
let dot='';
w.__GRAPHVIZ={Graphviz:{load:async()=>({dot(value){dot=value;return '<svg>'+['root','fast','at','above','gap','error'].map(id=>`<g class="node"><title>${id}</title><text>${id}</text></g>`).join('')+'</svg>';}})}};
const source=html.match(/<script type="module">([\s\S]*?)<\/script>/)[1];
const code=source.replace('await import("https://cdn.jsdelivr.net/npm/@hpcc-js/wasm-graphviz@1.6.1/+esm")','await window.__GRAPHVIZ');
assert.notEqual(code,source,'only the network renderer is stubbed');
vm.runInContext(code,dom.getInternalVMContext());
setTimeout(()=>{
 try{
  const level=id=>d.querySelector(`.timeline-item[data-node-id="${id}"]`).dataset.level;
  assert.equal(level('fast'),'ok');assert.equal(level('at'),'ok');
  assert.equal(level('above'),'warning');assert.equal(level('gap'),'warning');
  assert.equal(level('root'),'warning');assert.equal(level('error'),'error');
  const findings=[...d.querySelectorAll('#latency-findings [data-nid]')];
  assert.deepEqual(findings.map(e=>e.dataset.nid),['gap','above','root']);
  assert.equal(d.getElementById('sslow').textContent,'3');
  assert.match(findings[1].textContent,/50\.001 ms/);
  findings[0].click();assert.match(d.getElementById('det').textContent,/self wall time: 60\.000 ms/);
  assert.match(d.getElementById('det').textContent,/threshold: 50 ms/);
  findings[2].click();assert.match(d.getElementById('det').textContent,/self wall time: 8\.000 ms/);
  assert.match(d.getElementById('det').textContent,/includes untraced work and waits/);
  for(const [id,color] of [['fast','#238636'],['at','#238636'],['above','#d29922'],['error','#da3633']]){
   assert.ok(dot.split('\n').find(line=>line.includes(`  ${id} [`)).includes(`fillcolor="${color}"`),id);
  }
  assert.match(d.getElementById('overview').textContent,/140\.0 ms in root span/);
  assert.match(d.getElementById('rawtrace').textContent,/__LATENCY_JSON__/);
  assert.equal(d.querySelectorAll('script').length,1,'trace data did not escape its script');
  assert.deepEqual(errors,[]);
  console.log('PASS: 50 ms boundary, all parents/leaves, red errors, ordered hotspots, detail jumps, self time, DOT colors and full raw data');
 }catch(e){console.error(e.stack);process.exitCode=1;}finally{w.close();}
},0);
