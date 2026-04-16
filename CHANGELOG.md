# Changelog

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
