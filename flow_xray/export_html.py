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
header{padding:10px 20px;background:#161b22;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:18px;flex-shrink:0}
header h1{font-size:15px;font-weight:600}
.st{font-size:13px;color:#8b949e}.st b{color:#c9d1d9}.st b.err{color:#f85149}
.ctl{margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.ctl input{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;border-radius:6px;padding:6px 8px;font-size:12px;min-width:170px}
.ctl button{background:#21262d;border:1px solid #30363d;color:#c9d1d9;border-radius:6px;padding:6px 10px;font-size:12px;cursor:pointer}
.ctl button:hover{background:#30363d}
#main{display:flex;flex:1;overflow:hidden}
#graph{flex:1;overflow:auto;display:flex;align-items:center;justify-content:center;padding:20px}
#graph svg{max-width:100%;height:auto;cursor:grab}
#det{width:370px;background:#161b22;border-left:1px solid #30363d;overflow-y:auto;padding:16px;font-size:13px;flex-shrink:0}
.dt{font-size:14px;font-weight:600;margin-bottom:10px;color:#f0f6fc}
.ds{margin-bottom:14px}
.dl{font-size:10px;text-transform:uppercase;color:#8b949e;margin-bottom:3px;letter-spacing:.5px}
.dv{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:8px 10px;font-family:'SF Mono','Fira Code',monospace;font-size:12px;white-space:pre-wrap;word-break:break-all;max-height:220px;overflow-y:auto;color:#c9d1d9}
.ok{color:#3fb950}.er{color:#f85149}.warn{color:#d29922}
#graph .node{cursor:pointer}
#graph .node:hover polygon{stroke:#58a6ff!important;stroke-width:2}
#graph .selected polygon{stroke:#58a6ff!important;stroke-width:2.5}
#graph .match polygon{stroke:#d29922!important;stroke-width:2.5}
#graph .edge path{stroke:#30363d!important}
#graph .edge polygon{fill:#30363d!important;stroke:#30363d!important}
#graph text{fill:#fff!important}
#hint{color:#484f58;text-align:center;padding:40px 20px;line-height:1.6}
#fb{white-space:pre-wrap;font-size:12px;color:#8b949e;padding:20px;display:none}
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
  <input id="search" type="search" placeholder="Search nodes">
  <button id="zoomout" type="button">-</button>
  <button id="zoomin" type="button">+</button>
  <button id="zoomreset" type="button">Reset</button>
  <button id="copydet" type="button">Copy details</button>
 </div>
</header>
<div id="main">
 <div id="graph"><div id="hint">Rendering graph…</div></div>
 <div id="det"><div id="hint">Click a node to inspect</div></div>
</div>
<pre id="fb"></pre>
<script type="module">
const TRACE=__TRACE_JSON__;
function flat(roots,pid){let r=[];(roots||[]).forEach(n=>{r.push({...n,pid});r=r.concat(flat(n.children,n.id))});return r}
const nodes=flat(TRACE.nodes,null);
const byId=Object.fromEntries(nodes.map(n=>[n.id,n]));
document.getElementById("sn").textContent=nodes.length;
const errs=nodes.filter(n=>n.error).length;
document.getElementById("se").textContent=errs;
const total=nodes.reduce((s,n)=>s+n.latency_ms,0);
document.getElementById("stm").textContent=total.toFixed(1)+"ms";
let sumTok=0,sumCost=0;
nodes.forEach(n=>{if(n.meta){if(n.meta.total_tokens)sumTok+=n.meta.total_tokens;if(n.meta.estimated_cost_usd)sumCost+=n.meta.estimated_cost_usd}});
if(sumTok){document.getElementById("stok").style.display="";document.getElementById("stokv").textContent=sumTok}
if(sumCost){document.getElementById("scost").style.display="";document.getElementById("scostv").textContent="$"+sumCost.toFixed(6)}

function mkDot(){
  let d='digraph G {\n  rankdir="TB";\n  bgcolor="transparent";\n';
  d+='  node [shape=box,style="rounded,filled",fontname="Helvetica",fontsize=11,margin="0.3,0.15"];\n';
  d+='  edge [color="#30363d",arrowsize=0.7];\n';
  for(const n of nodes){
    const c=n.error?"#da3633":n.latency_ms>1000?"#9e6a03":"#238636";
    const ms=n.latency_ms<1?n.latency_ms.toFixed(2):n.latency_ms<100?n.latency_ms.toFixed(1):Math.round(n.latency_ms);
    let lb=n.name+"\\n"+ms+"ms";
    if(n.meta&&n.meta.total_tokens)lb+="\\n"+n.meta.total_tokens+" tok";
    d+=`  ${n.id} [label="${lb}",fillcolor="${c}",fontcolor="white",tooltip="${n.id}"];\n`;
  }
  for(const n of nodes){if(n.pid)d+=`  ${n.pid} -> ${n.id};\n`}
  d+='}';return d;
}

const det=document.getElementById("det");
const searchInput=document.getElementById("search");
const copyButton=document.getElementById("copydet");
let selectedNode=null;
let zoomLevel=1;
function showDet(n){
  selectedNode=n||null;
  if(!n){det.innerHTML='<div id="hint">Click a node to inspect</div>';return}
  const st=n.error?`<span class="er">ERROR</span>`:`<span class="ok">OK</span>`;
  const ms=n.latency_ms.toFixed(2);
  let h=`<div class="dt">${esc(n.name)}</div>`;
  h+=`<div class="ds"><div class="dl">Status</div><div class="dv">${st}</div></div>`;
  h+=`<div class="ds"><div class="dl">Latency</div><div class="dv">${ms} ms</div></div>`;
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
    const extra=Object.entries(m).filter(([k])=>!["model","prompt_tokens","completion_tokens","total_tokens","estimated_cost_usd"].includes(k));
    if(extra.length){h+=`<div class="ds"><div class="dl">Meta</div>`;extra.forEach(([k,v])=>{h+=`<div class="dv"><b>${esc(k)}</b>: ${esc(JSON.stringify(v))}</div>`});h+=`</div>`}
  }
  det.innerHTML=h;
}
function esc(s){const d=document.createElement('div');d.textContent=String(s);return d.innerHTML}
function detailText(n){
  if(!n)return "No node selected";
  const parts=[`name: ${n.name}`, `latency_ms: ${n.latency_ms.toFixed(2)}`, `status: ${n.error ? "ERROR" : "OK"}`];
  if(n.error)parts.push(`error: ${n.error}`);
  parts.push(`inputs: ${JSON.stringify(n.inputs || {}, null, 2)}`);
  if(n.output!=null)parts.push(`output: ${String(n.output)}`);
  if(n.meta)parts.push(`meta: ${JSON.stringify(n.meta, null, 2)}`);
  return parts.join("\n\n");
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
function updateZoom(){
  const svg=document.querySelector('#graph svg');
  if(!svg)return;
  svg.style.transform=`scale(${zoomLevel})`;
  svg.style.transformOrigin='center center';
}
function bindToolbar(){
  document.getElementById("zoomin").addEventListener("click",()=>{zoomLevel=Math.min(zoomLevel+0.15,3);updateZoom()});
  document.getElementById("zoomout").addEventListener("click",()=>{zoomLevel=Math.max(zoomLevel-0.15,0.4);updateZoom()});
  document.getElementById("zoomreset").addEventListener("click",()=>{zoomLevel=1;updateZoom()});
  copyButton.addEventListener("click",copyDetails);
  searchInput.addEventListener("input",()=>{
    const q=searchInput.value.trim().toLowerCase();
    document.querySelectorAll('#graph .node').forEach(el=>{
      const text=(el.textContent || '').toLowerCase();
      el.classList.toggle('match', !!q && text.includes(q));
    });
  });
}

async function render(){
  const dot=mkDot();
  const gc=document.getElementById("graph");
  try{
    const {Graphviz}=await import("https://cdn.jsdelivr.net/npm/@hpcc-js/wasm-graphviz@1.6.1/+esm");
    const gv=await Graphviz.load();
    const svg=gv.dot(dot);
    gc.innerHTML=svg;
    gc.querySelectorAll('.node').forEach(el=>{
      const title=el.querySelector('title');
      if(!title)return;
      const nid=title.textContent.trim();
      el.addEventListener('click',()=>{
        gc.querySelectorAll('.selected').forEach(s=>s.classList.remove('selected'));
        el.classList.add('selected');
        showDet(byId[nid]);
      });
    });
    bindToolbar();
    updateZoom();
  }catch(e){
    console.error(e);
    gc.innerHTML='<div id="hint" style="color:#f85149">WASM render failed, likely due to offline or blocked CDN access. DOT is shown below so the trace is still inspectable.</div>';
    const fb=document.getElementById("fb");fb.style.display="block";fb.textContent=dot;
    bindToolbar();
  }
}
render();
</script>
</body>
</html>
"""
