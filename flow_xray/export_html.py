"""Single-file HTML viewer: embedded DOT + WASM Graphviz (no local ``dot``, no server)."""

from __future__ import annotations

import html
import json
from pathlib import Path


def standalone_viewer_html(dot: str, *, title: str = "flow-xray graph") -> str:
    """
    Return one HTML document that inlines ``dot`` as JSON so ``file://`` works.

    Rendering uses ``@hpcc-js/wasm-graphviz`` from jsDelivr (needs network once).
    If WASM fails, the raw DOT is shown in a ``<pre>``.
    """
    dot_js = json.dumps(dot)
    safe_title = html.escape(title, quote=True)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1rem; }}
    #host {{ overflow: auto; border: 1px solid #ccc; padding: 0.5rem; min-height: 200px; }}
    #fallback {{ white-space: pre-wrap; font-size: 12px; display: none; }}
    .err {{ color: #b00; }}
  </style>
</head>
<body>
  <h1>{safe_title}</h1>
  <p id="status">Rendering…</p>
  <div id="host"></div>
  <pre id="fallback"></pre>
  <script type="module">
    const status = document.getElementById("status");
    const host = document.getElementById("host");
    const fallback = document.getElementById("fallback");
    const dot = {dot_js};
    async function run() {{
      try {{
        const {{ Graphviz }} = await import(
          "https://cdn.jsdelivr.net/npm/@hpcc-js/wasm-graphviz@1.6.1/+esm"
        );
        const gv = await Graphviz.load();
        const svg = gv.dot(dot);
        host.innerHTML = svg;
        status.textContent = "Rendered (WASM Graphviz). Opened as local HTML — no PNG/dot CLI.";
      }} catch (e) {{
        status.innerHTML =
          "<span class='err'>WASM render failed (offline or blocked CDN).</span> DOT below.";
        console.error(e);
        fallback.style.display = "block";
        fallback.textContent = dot;
      }}
    }}
    run();
  </script>
</body>
</html>
"""


def write_standalone_viewer_html(path: str | Path, dot: str, *, title: str = "flow-xray graph") -> None:
    Path(path).write_text(standalone_viewer_html(dot, title=title), encoding="utf-8")


# ---------------------------------------------------------------------------
# Execution-trace viewer (dark theme, interactive)
# ---------------------------------------------------------------------------

def trace_to_standalone_html(
    trace_result: object,
    *,
    title: str = "flow-xray trace",
) -> str:
    """
    Return a self-contained HTML document that renders a ``TraceResult``
    as an interactive execution DAG (dark theme, Graphviz WASM, click-to-inspect).
    """
    trace_json = json.dumps(trace_result.to_dict(), ensure_ascii=False)  # type: ignore[union-attr]
    safe_title = html.escape(title, quote=True)
    return _TRACE_HTML_TEMPLATE.replace("__TITLE__", safe_title).replace("__TRACE_JSON__", trace_json)


_TRACE_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;display:flex;flex-direction:column;height:100vh}
header{padding:10px 20px;background:#161b22;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:18px;flex-wrap:wrap;flex-shrink:0}
header h1{font-size:15px;font-weight:600}
.st{font-size:13px;color:#8b949e}.st b{color:#c9d1d9}.st b.err{color:#f85149}
.ctl{margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.ctl input,.subctl input{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;border-radius:6px;padding:6px 8px;font-size:12px;min-width:170px}
.ctl button,.modebtn,.subctl button{background:#21262d;border:1px solid #30363d;color:#c9d1d9;border-radius:6px;padding:6px 10px;font-size:12px;cursor:pointer}
.ctl button:hover,.modebtn:hover,.subctl button:hover{background:#30363d}
.modebar{padding:10px 20px;background:#0f141b;border-bottom:1px solid #30363d;display:flex;gap:8px;flex-wrap:wrap}
.modebtn.active{background:#1f6feb;border-color:#1f6feb;color:#fff}
#main{display:flex;flex:1;overflow:hidden}
#content{flex:1;overflow:hidden;display:flex;flex-direction:column}
.view{display:none;flex:1;overflow:auto}
.view.active{display:block}
#overview{padding:18px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px}
.card{border:1px solid #30363d;border-radius:10px;background:#161b22;padding:12px}
.card .k{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#8b949e;margin-bottom:6px}
.card .v{font-size:20px;font-weight:700;color:#f0f6fc}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.panel{border:1px solid #30363d;border-radius:10px;background:#161b22;padding:12px}
.panel h3{font-size:13px;margin-bottom:10px;color:#f0f6fc}
.list{display:flex;flex-direction:column;gap:8px}
.rowitem{border:1px solid #30363d;border-radius:8px;background:#0d1117;padding:10px}
.rowitem .top{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:4px}
.small{font-size:12px;color:#8b949e}
.mono{font-family:'SF Mono','Fira Code',monospace}
#graphview{padding:20px}
#graphwrap{height:100%;border:1px solid #30363d;border-radius:10px;background:#0d1117;overflow:auto;display:flex;align-items:center;justify-content:center;padding:20px}
#graphwrap svg{max-width:100%;height:auto;cursor:grab}
#timelineview{padding:18px}
.timeline{display:flex;flex-direction:column;gap:10px}
.timeline-item{border:1px solid #30363d;border-radius:8px;background:#161b22;padding:10px;cursor:pointer}
.timeline-item.match{border-color:#d29922}
.timeline-item.selected{border-color:#58a6ff;box-shadow:0 0 0 1px #58a6ff inset}
.timeline-item .kind{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#8b949e}
.timeline-item .summary{margin-top:4px}
#rawview{padding:18px}
.subctl{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
#rawstats{font-size:12px;color:#8b949e}
#rawtrace{white-space:pre-wrap;font-size:12px;color:#c9d1d9;border:1px solid #30363d;border-radius:10px;background:#0d1117;padding:12px;overflow:auto;max-height:100%}
#det{width:390px;background:#161b22;border-left:1px solid #30363d;overflow-y:auto;padding:16px;font-size:13px;flex-shrink:0}
.dt{font-size:14px;font-weight:600;margin-bottom:10px;color:#f0f6fc}
.ds{margin-bottom:14px}
.dl{font-size:10px;text-transform:uppercase;color:#8b949e;margin-bottom:3px;letter-spacing:.5px}
.dv{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:8px 10px;font-family:'SF Mono','Fira Code',monospace;font-size:12px;white-space:pre-wrap;word-break:break-all;max-height:220px;overflow-y:auto;color:#c9d1d9}
.ok{color:#3fb950}.er{color:#f85149}.warn{color:#d29922}
#graphwrap .node{cursor:pointer}
#graphwrap .node:hover polygon{stroke:#58a6ff!important;stroke-width:2}
#graphwrap .selected polygon{stroke:#58a6ff!important;stroke-width:2.5}
#graphwrap .match polygon{stroke:#d29922!important;stroke-width:2.5}
#graphwrap .edge path{stroke:#30363d!important}
#graphwrap .edge polygon{fill:#30363d!important;stroke:#30363d!important}
#graphwrap text{fill:#fff!important}
#hint{color:#484f58;text-align:center;padding:40px 20px;line-height:1.6}
@media (max-width: 960px){
  #main{flex-direction:column}
  #det{width:auto;border-left:none;border-top:1px solid #30363d;max-height:42vh}
  .grid2{grid-template-columns:1fr}
}
</style>
</head>
<body>
<header>
 <h1>__TITLE__</h1>
 <span class="st">Nodes: <b id="sn">-</b></span>
 <span class="st">Total: <b id="stm">-</b></span>
 <span class="st">Errors: <b id="se" class="err">-</b></span>
 <span class="st" id="stok" style="display:none">Tokens: <b id="stokv">-</b></span>
 <span class="st" id="scost" style="display:none">Cost: <b id="scostv" class="warn">-</b></span>
 <div class="ctl">
  <input id="search" type="search" placeholder="Search/filter">
  <button id="zoomout" type="button">-</button>
  <button id="zoomin" type="button">+</button>
  <button id="zoomfit" type="button">Fit</button>
  <button id="zoomreset" type="button">Reset</button>
  <button id="copydet" type="button">Copy details</button>
 </div>
</header>
<div class="modebar">
 <button class="modebtn active" id="mode-overview" data-mode="overview" type="button">Overview</button>
 <button class="modebtn" id="mode-graph" data-mode="graph" type="button">Graph</button>
 <button class="modebtn" id="mode-timeline" data-mode="timeline" type="button">Timeline</button>
 <button class="modebtn" id="mode-raw" data-mode="raw" type="button">Raw</button>
</div>
<div id="main">
 <div id="content">
  <section class="view active" id="overview"></section>
  <section class="view" id="graphview"><div id="graphwrap"><div id="hint">Rendering graph…</div></div></section>
  <section class="view" id="timelineview"><div id="timeline" class="timeline"></div></section>
  <section class="view" id="rawview">
   <div class="subctl">
    <input id="rawfilter" type="search" placeholder="Filter raw JSON lines">
    <button id="copyraw" type="button">Copy raw JSON</button>
    <span id="rawstats"></span>
   </div>
   <pre id="rawtrace"></pre>
  </section>
 </div>
 <aside id="det"><div id="hint">Click a node or timeline item to inspect</div></aside>
</div>
<script type="module">
const TRACE=__TRACE_JSON__;
function flat(roots,pid=null,depth=0,acc=[]){
  (roots||[]).forEach((n,index)=>{
    const entry={...n,pid,depth,order:acc.length,root_index:depth===0?index:null};
    acc.push(entry);
    flat(n.children||[],n.id,depth+1,acc);
  });
  return acc;
}
const nodes=flat(TRACE.nodes);
const byId=Object.fromEntries(nodes.map(n=>[n.id,n]));
function esc(s){const d=document.createElement('div');d.textContent=String(s);return d.innerHTML}
function fmtMs(v){return v<1?v.toFixed(2):v<100?v.toFixed(1):Math.round(v)}
function nodeText(n){return JSON.stringify({name:n.name,inputs:n.inputs,output:n.output,error:n.error,meta:n.meta})}
function isRedactedValue(v){return typeof v==="string"&&v.includes("[redacted]")}
function countRedactions(obj){
  if(isRedactedValue(obj))return 1;
  if(Array.isArray(obj))return obj.reduce((s,v)=>s+countRedactions(v),0);
  if(obj&&typeof obj==="object")return Object.values(obj).reduce((s,v)=>s+countRedactions(v),0);
  return 0;
}
const subtreeStats=new Map();
function computeSubtree(node){
  let totalLatency=node.latency_ms||0;
  let totalTokens=node.meta&&node.meta.total_tokens?node.meta.total_tokens:0;
  let count=1;
  for(const child of node.children||[]){
    const sub=computeSubtree(child);
    totalLatency+=sub.totalLatency;
    totalTokens+=sub.totalTokens;
    count+=sub.count;
  }
  const result={totalLatency,totalTokens,count};
  subtreeStats.set(node.id,result);
  return result;
}
(TRACE.nodes||[]).forEach(computeSubtree);
const totals=nodes.reduce((acc,n)=>{
  acc.latency+=n.latency_ms||0;
  acc.errors+=n.error?1:0;
  acc.tokens+=n.meta&&n.meta.total_tokens?n.meta.total_tokens:0;
  acc.cost+=n.meta&&n.meta.estimated_cost_usd?n.meta.estimated_cost_usd:0;
  acc.redactions+=countRedactions(n.inputs)+countRedactions(n.output)+countRedactions(n.meta);
  acc.maxDepth=Math.max(acc.maxDepth,n.depth||0);
  if(n.meta&&(n.meta.model||n.meta.total_tokens!=null))acc.llmCalls+=1;
  return acc;
},{latency:0,errors:0,tokens:0,cost:0,redactions:0,maxDepth:0,llmCalls:0});
const modelTotals={};
nodes.forEach(n=>{
  const model=n.meta&&n.meta.model;
  if(!model)return;
  if(!modelTotals[model])modelTotals[model]={tokens:0,cost:0,calls:0};
  modelTotals[model].calls+=1;
  modelTotals[model].tokens+=n.meta&&n.meta.total_tokens?n.meta.total_tokens:0;
  modelTotals[model].cost+=n.meta&&n.meta.estimated_cost_usd?n.meta.estimated_cost_usd:0;
});
document.getElementById("sn").textContent=nodes.length;
document.getElementById("se").textContent=totals.errors;
const total=nodes.reduce((s,n)=>s+n.latency_ms,0);
document.getElementById("stm").textContent=total.toFixed(1)+"ms";
if(totals.tokens){document.getElementById("stok").style.display="";document.getElementById("stokv").textContent=totals.tokens}
if(totals.cost){document.getElementById("scost").style.display="";document.getElementById("scostv").textContent="$"+totals.cost.toFixed(6)}

function mkDot(){
  let d='digraph G {\n  rankdir="TB";\n  bgcolor="transparent";\n';
  d+='  node [shape=box,style="rounded,filled",fontname="Helvetica",fontsize=11,margin="0.3,0.15"];\n';
  d+='  edge [color="#30363d",arrowsize=0.7];\n';
  for(const n of nodes){
    const c=n.error?"#da3633":n.latency_ms>1000?"#9e6a03":"#238636";
    let lb=n.name+"\\n"+fmtMs(n.latency_ms)+"ms";
    if(n.meta&&n.meta.total_tokens!=null)lb+="\\n"+n.meta.total_tokens+" tok";
    d+=`  ${n.id} [label="${lb}",fillcolor="${c}",fontcolor="white",tooltip="${n.id}"];\n`;
  }
  for(const n of nodes){if(n.pid)d+=`  ${n.pid} -> ${n.id};\n`}
  d+='}';return d;
}

function topNodes(selector, limit=5){
  return [...nodes].sort((a,b)=>selector(b)-selector(a)).slice(0,limit);
}

function renderOverview(){
  const overview=document.getElementById("overview");
  const modelRows=Object.entries(modelTotals).sort((a,b)=>b[1].tokens-a[1].tokens);
  const slowRows=topNodes(n=>n.latency_ms||0).map(n=>`
    <div class="rowitem">
      <div class="top"><b>${esc(n.name)}</b><span class="small mono">${fmtMs(n.latency_ms)} ms</span></div>
      <div class="small mono">${esc(n.id)} · depth ${n.depth}</div>
    </div>`).join("");
  const tokenRows=topNodes(n=>n.meta&&n.meta.total_tokens?n.meta.total_tokens:0).filter(n=>n.meta&&n.meta.total_tokens).map(n=>`
    <div class="rowitem">
      <div class="top"><b>${esc(n.name)}</b><span class="small mono">${n.meta.total_tokens} tok</span></div>
      <div class="small mono">${esc(n.id)}${n.meta&&n.meta.model?` · ${esc(n.meta.model)}`:""}</div>
    </div>`).join("") || '<div class="small">No token-tracked nodes</div>';
  const modelCards=modelRows.map(([model,data])=>`
    <div class="rowitem">
      <div class="top"><b>${esc(model)}</b><span class="small mono">${data.calls} calls</span></div>
      <div class="small mono">${data.tokens} tok · $${data.cost.toFixed(6)}</div>
    </div>`).join("") || '<div class="small">No model metadata</div>';
  overview.innerHTML=`
    <div class="cards">
      <div class="card"><div class="k">Roots</div><div class="v">${TRACE.nodes.length}</div></div>
      <div class="card"><div class="k">LLM Calls</div><div class="v">${totals.llmCalls}</div></div>
      <div class="card"><div class="k">Max Depth</div><div class="v">${totals.maxDepth}</div></div>
      <div class="card"><div class="k">Redactions</div><div class="v">${totals.redactions}</div></div>
      <div class="card"><div class="k">Errors</div><div class="v">${totals.errors}</div></div>
      <div class="card"><div class="k">Tokens</div><div class="v">${totals.tokens||0}</div></div>
    </div>
    <div class="grid2">
      <div class="panel">
        <h3>Slowest Nodes</h3>
        <div class="list">${slowRows}</div>
      </div>
      <div class="panel">
        <h3>Token-Heavy Nodes</h3>
        <div class="list">${tokenRows}</div>
      </div>
      <div class="panel">
        <h3>Models</h3>
        <div class="list">${modelCards}</div>
      </div>
      <div class="panel">
        <h3>Trace Summary</h3>
        <div class="list">
          <div class="rowitem"><div class="top"><b>Total Latency</b><span class="small mono">${total.toFixed(1)} ms</span></div></div>
          <div class="rowitem"><div class="top"><b>Estimated Cost</b><span class="small mono">$${totals.cost.toFixed(6)}</span></div></div>
          <div class="rowitem"><div class="top"><b>Search Tip</b><span class="small">Use the top search box to filter graph, timeline, and raw JSON.</span></div></div>
        </div>
      </div>
    </div>`;
}

function renderTimeline(query=""){
  const q=query.trim().toLowerCase();
  const items=nodes.filter(n=>!q||nodeText(n).toLowerCase().includes(q)).map(n=>`
    <div class="timeline-item${q?' match':''}" data-node-id="${esc(n.id)}" style="margin-left:${Math.min((n.depth||0)*18,72)}px">
      <div class="kind">step ${n.order+1} · ${n.error?"error":"ok"} · depth ${n.depth}</div>
      <div class="summary"><b>${esc(n.name)}</b> <span class="small mono">${fmtMs(n.latency_ms)} ms</span></div>
      <div class="small mono">${esc(n.id)}${n.meta&&n.meta.total_tokens!=null?` · ${n.meta.total_tokens} tok`:""}</div>
    </div>`).join("") || '<div id="hint">No timeline items match the current filter.</div>';
  document.getElementById("timeline").innerHTML=items;
  document.querySelectorAll('.timeline-item[data-node-id]').forEach(el=>{
    el.addEventListener('click',()=>selectNode(el.getAttribute('data-node-id')));
  });
  if(selectedNode)syncSelection(selectedNode.id);
}

const rawtrace=document.getElementById("rawtrace");
const rawstats=document.getElementById("rawstats");
const rawfilter=document.getElementById("rawfilter");
const prettyTrace=JSON.stringify(TRACE,null,2);
function renderRaw(query=""){
  const lines=prettyTrace.split("\n");
  const q=query.trim().toLowerCase();
  const shown=q?lines.filter(line=>line.toLowerCase().includes(q)):lines;
  rawtrace.textContent=shown.join("\n");
  rawstats.textContent=q?`${shown.length} matching lines`:`${lines.length} lines`;
}

const det=document.getElementById("det");
const searchInput=document.getElementById("search");
const copyButton=document.getElementById("copydet");
let selectedNode=null;
let zoomLevel=1;
let graphContainer=null;

function detailText(n){
  if(!n)return "No node selected";
  const sub=subtreeStats.get(n.id)||{totalLatency:n.latency_ms||0,totalTokens:n.meta&&n.meta.total_tokens?n.meta.total_tokens:0,count:1};
  const parts=[
    `name: ${n.name}`,
    `node_id: ${n.id}`,
    `parent_id: ${n.pid || "(root)"}`,
    `depth: ${n.depth}`,
    `child_count: ${(n.children||[]).length}`,
    `subtree_nodes: ${sub.count}`,
    `latency_ms: ${n.latency_ms.toFixed(2)}`,
    `subtree_latency_ms: ${sub.totalLatency.toFixed(2)}`,
    `status: ${n.error ? "ERROR" : "OK"}`,
  ];
  if(sub.totalTokens)parts.push(`subtree_tokens: ${sub.totalTokens}`);
  if(n.error)parts.push(`error: ${n.error}`);
  parts.push(`inputs: ${JSON.stringify(n.inputs || {}, null, 2)}`);
  if(n.output!=null)parts.push(`output: ${JSON.stringify(n.output, null, 2)}`);
  if(n.meta)parts.push(`meta: ${JSON.stringify(n.meta, null, 2)}`);
  parts.push(`raw_node: ${JSON.stringify(n, null, 2)}`);
  return parts.join("\n\n");
}

function showDet(n){
  selectedNode=n||null;
  if(!n){det.innerHTML='<div id="hint">Click a node or timeline item to inspect</div>';return}
  const sub=subtreeStats.get(n.id)||{totalLatency:n.latency_ms||0,totalTokens:n.meta&&n.meta.total_tokens?n.meta.total_tokens:0,count:1};
  const st=n.error?`<span class="er">ERROR</span>`:`<span class="ok">OK</span>`;
  const ms=n.latency_ms.toFixed(2);
  let h=`<div class="dt">${esc(n.name)}</div>`;
  h+=`<div class="ds"><div class="dl">Summary</div><div class="dv">status: ${n.error?"ERROR":"OK"}\nnode: ${esc(n.id)}\nparent: ${esc(n.pid || "(root)")}\ndepth: ${n.depth}\nchildren: ${(n.children||[]).length}\nlatency: ${ms} ms\nsubtree latency: ${sub.totalLatency.toFixed(2)} ms\nsubtree nodes: ${sub.count}${sub.totalTokens?`\nsubtree tokens: ${sub.totalTokens}`:""}</div></div>`;
  h+=`<div class="ds"><div class="dl">Status</div><div class="dv">${st}</div></div>`;
  if(n.error)h+=`<div class="ds"><div class="dl">Error</div><div class="dv er">${esc(n.error)}</div></div>`;
  const inp=Object.entries(n.inputs||{});
  if(inp.length){h+=`<div class="ds"><div class="dl">Input</div>`;inp.forEach(([k,v])=>{h+=`<div class="dv"><b>${esc(k)}</b>: ${esc(v)}</div>`});h+=`</div>`}
  if(n.output!=null)h+=`<div class="ds"><div class="dl">Output</div><div class="dv">${esc(String(n.output))}</div></div>`;
  if(n.meta){
    const m=n.meta;
    if(m.model)h+=`<div class="ds"><div class="dl">Model</div><div class="dv">${esc(m.model)}</div></div>`;
    const toks=[];
    if(m.prompt_tokens!=null)toks.push("prompt: "+m.prompt_tokens);
    if(m.completion_tokens!=null)toks.push("completion: "+m.completion_tokens);
    if(m.total_tokens!=null)toks.push("total: "+m.total_tokens);
    if(toks.length)h+=`<div class="ds"><div class="dl">Tokens</div><div class="dv">${esc(toks.join("  ·  "))}</div></div>`;
    if(m.estimated_cost_usd!=null)h+=`<div class="ds"><div class="dl">Est. cost</div><div class="dv warn">$${m.estimated_cost_usd.toFixed(6)}</div></div>`;
  }
  h+=`<div class="ds"><div class="dl">Raw Node JSON</div><div class="dv">${esc(JSON.stringify(n,null,2))}</div></div>`;
  det.innerHTML=h;
}

function syncSelection(nodeId){
  document.querySelectorAll('#graphwrap .selected').forEach(el=>el.classList.remove('selected'));
  document.querySelectorAll('.timeline-item.selected').forEach(el=>el.classList.remove('selected'));
  if(!nodeId)return;
  const graphNode=document.querySelector(`#graphwrap .node[data-node-id="${nodeId}"]`);
  if(graphNode)graphNode.classList.add('selected');
  const timelineNode=document.querySelector(`.timeline-item[data-node-id="${nodeId}"]`);
  if(timelineNode){
    timelineNode.classList.add('selected');
    timelineNode.scrollIntoView({block:"nearest"});
  }
}

function selectNode(nodeId){
  const node=byId[nodeId];
  if(!node)return;
  showDet(node);
  syncSelection(nodeId);
}

async function copyDetails(){
  const text=detailText(selectedNode);
  try{
    await navigator.clipboard.writeText(text);
    copyButton.textContent="Copied";
    setTimeout(()=>{copyButton.textContent="Copy details"},1200);
  }catch(_err){
    copyButton.textContent="Copy failed";
    setTimeout(()=>{copyButton.textContent="Copy details"},1200);
  }
}

async function copyRaw(){
  try{
    await navigator.clipboard.writeText(prettyTrace);
    const btn=document.getElementById("copyraw");
    btn.textContent="Copied";
    setTimeout(()=>{btn.textContent="Copy raw JSON"},1200);
  }catch(_err){}
}

function updateZoom(){
  const svg=document.querySelector('#graphwrap svg');
  if(!svg)return;
  svg.style.transform=`scale(${zoomLevel})`;
  svg.style.transformOrigin='center center';
}

function fitGraph(){
  const svg=document.querySelector('#graphwrap svg');
  const host=graphContainer || document.getElementById("graphwrap");
  if(!svg || !host)return;
  const svgWidth=parseFloat(svg.getAttribute('width') || "0") || svg.getBBox().width || svg.clientWidth;
  const svgHeight=parseFloat(svg.getAttribute('height') || "0") || svg.getBBox().height || svg.clientHeight;
  if(!svgWidth || !svgHeight)return;
  const availW=Math.max(host.clientWidth - 40, 120);
  const availH=Math.max(host.clientHeight - 40, 120);
  zoomLevel=Math.max(0.2, Math.min(2.5, Math.min(availW / svgWidth, availH / svgHeight)));
  updateZoom();
}

function applySearch(){
  const q=searchInput.value.trim().toLowerCase();
  document.querySelectorAll('#graphwrap .node').forEach(el=>{
    const text=(el.textContent || '').toLowerCase();
    el.classList.toggle('match', !!q && text.includes(q));
  });
  renderTimeline(q);
  renderRaw(q || rawfilter.value);
  if(selectedNode)syncSelection(selectedNode.id);
}

function setMode(mode){
  document.querySelectorAll('.modebtn').forEach(btn=>btn.classList.toggle('active',btn.dataset.mode===mode));
  document.querySelectorAll('.view').forEach(view=>view.classList.toggle('active',view.id===`${mode}` || view.id===`${mode}view`));
}

function bindToolbar(){
  document.getElementById("zoomin").addEventListener("click",()=>{zoomLevel=Math.min(zoomLevel+0.15,3);updateZoom()});
  document.getElementById("zoomout").addEventListener("click",()=>{zoomLevel=Math.max(zoomLevel-0.15,0.4);updateZoom()});
  document.getElementById("zoomfit").addEventListener("click",fitGraph);
  document.getElementById("zoomreset").addEventListener("click",()=>{zoomLevel=1;updateZoom()});
  copyButton.addEventListener("click",copyDetails);
  document.getElementById("copyraw").addEventListener("click",copyRaw);
  searchInput.addEventListener("input",applySearch);
  rawfilter.addEventListener("input",()=>renderRaw(rawfilter.value || searchInput.value));
  document.querySelectorAll('.modebtn').forEach(btn=>btn.addEventListener('click',()=>setMode(btn.dataset.mode)));
}

async function renderGraph(){
  const dot=mkDot();
  const gc=document.getElementById("graphwrap");
  graphContainer=gc;
  try{
    const {Graphviz}=await import("https://cdn.jsdelivr.net/npm/@hpcc-js/wasm-graphviz@1.6.1/+esm");
    const gv=await Graphviz.load();
    const svg=gv.dot(dot);
    gc.innerHTML=svg;
    gc.querySelectorAll('.node').forEach(el=>{
      const title=el.querySelector('title');
      if(!title)return;
      const nid=title.textContent.trim();
      el.setAttribute('data-node-id', nid);
      el.addEventListener('click',()=>{
        selectNode(nid);
      });
    });
    zoomLevel=1;
    updateZoom();
    applySearch();
  }catch(e){
    console.error(e);
    gc.innerHTML='<div id="hint" style="color:#f85149">WASM render failed, likely due to offline or blocked CDN access. Graph mode is unavailable, but Timeline and Raw modes still work below.</div>';
  }
}

renderOverview();
renderTimeline();
renderRaw();
bindToolbar();
renderGraph();
</script>
</body>
</html>
"""
