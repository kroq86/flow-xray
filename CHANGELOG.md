# Changelog

## 0.3.3

**Viewer UX**
- Gantt tab: horizontal bar chart of all nodes sorted by wall-clock start time — shows real async overlap at a glance. Bars colored by kind/error/latency; clickable rows select node in inspector.
- Clickable stat cards in Overview: click Errors → jump to first error node in Timeline; click LLM Calls → first LLM node; click Nodes → root in Graph; click Tokens → Gantt.
- Repeated Calls rows now clickable: click a function name → sets search filter and switches to Timeline showing all instances.
- Expand/collapse for long values in Node Inspector: inputs, outputs, and raw JSON truncate at 250 chars with a Show more toggle.

**Tracing API**
- `@trace(kind="llm"|"tool"|"agent")` — first-class node typing. Kind is serialized in trace data, used for graph coloring (llm=blue, tool=purple, agent=teal) and shown in Node Inspector.
- `trace.tag("label", key=value)` — attach arbitrary string labels or key-value tags to the current node. Tags appear as badges in Node Inspector.
- `TraceResult.diff(other)` — compare two trace runs; returns standalone dark-theme HTML showing changed/removed/added nodes with old vs new output side by side.
- `start_ms` is now included in serialized node data (relative to trace session start), enabling the Gantt view and future timeline analysis.

## 0.3.2

- Overhauled the Overview tab into a single unified analysis surface — no separate tab needed.
- Added **Critical Path** panel: traces the heaviest-latency chain from root to leaf with clickable nodes.
- Added **Latency Waterfall**: top-10 nodes by own latency with percentage-of-total bars, replaces the old "Slowest Nodes" list.
- Added **Depth Distribution**: bar chart of node counts per call depth, reveals flat vs deeply nested agent structure.
- Added **Repeated Calls**: detects functions called more than once, flags likely retry loops.
- Added **Error Analysis**: lists every errored node with parent context and truncated error message, each row clickable to Node Inspector.
- Clicking a waterfall row or critical-path node selects it across Graph, Timeline, and Node Inspector (cross-tab sync).

## 0.3.1

- Refreshed the package README and PyPI long description with a clearer local-first value proposition.
- Added stronger audience fit, main use case, CLI onboarding, safety/sharing guidance, and comparison/docs links.

## 0.3.0

- Async tracing now uses task-local context, so concurrent coroutine branches keep the correct DAG shape.
- `TraceResult` exposes the captured exception object, and `trace.run(..., raise_exceptions=True)` can re-raise after capture.
- Added trace privacy controls: `@trace(redact={...})` masks matching input keys and nested dict fields, and `capture_output=False` stores a redacted output in HTML while preserving the Python return value.
- Improved token/cost extraction to preserve zero token counts correctly.
- Upgraded the standalone HTML trace viewer into a multi-mode debug surface with `Overview`, `Graph`, `Timeline`, and `Raw` views.
- Added derived summary cards, raw trace filtering, copy-raw/copy-details actions, stronger node inspector output, graph search, fit/reset zoom controls, and synchronized selection between graph and timeline.
- Viewer payload previews now normalize noisy values such as UUIDs, timestamps, user paths, and temp paths for cleaner, safer summaries.
- CLI polish: clearer zero-node messaging for `flow-xray run`, better `dot export` error handling, and cleaned up legacy naming drift.
- README and examples were refreshed, including faster onboarding, trace safety guidance, and the `OPENAI_MODEL` fix in `examples/real_agent.py`.

## 0.2.0

- Renamed project: `gtype` → `flow-xray` (PyPI: `pip install flow-xray`, import: `flow_xray`).
- `@trace` decorator + `trace.run()` for capturing execution DAGs.
- Token/cost tracking: auto-extraction from OpenAI responses + `trace.meta()` manual API.
- Self-contained HTML trace viewer (dark theme, Graphviz WASM, click-to-inspect, tokens/cost in header and nodes).
- CLI: `flow-xray run script.py --html trace.html`.

## 0.1.0

- Initial packaged module: `Value`, `backward`, `zero_grad`, `backward_from`.
- Graphviz DOT export with stable per-node `node_id` (not `id(self)`).
- `TwoStepDebugger`, `GraphDebugger` with named per-step DOT snapshots.
- JSON IR (`graph_to_ir`, `ir_to_json`).
- CLI: `flow-xray dot demo|export`, `flow-xray-viewer` local server + WASM viewer page with DOT fallback.
