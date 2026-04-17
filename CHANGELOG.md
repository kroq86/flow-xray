# Changelog

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
