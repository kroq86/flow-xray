# Changelog

## 0.5.0 (2026-10-16)

- Optional `slow_all_nodes=True` checks every node against `slow_ms`, including
  parents. Findings identify the exact call and its elapsed/self wall time.
- HTML and DOT show per-node latency traffic lights; direct exports default
  to 50 ms. Stored HTML follows the store thresholds. All exceeding nodes
  are listed with navigation, and overlapping child time is merged before
  computing self time. Full trace JSON stays unchanged.
- Embedded trace strings cannot terminate the viewer script or recursively
  expand template placeholders. Viewer path time no longer sums nested spans.

- Optional `slow_ms_by_kind` budgets in the analyzer and store, including typed parent operations.

- `TraceStore.acapture()` and `asave()` await complete persistence in a dedicated
  two-thread pool. ASGI uses `acapture()` after the last response byte, including
  SSE. The synchronous API, JSON/HTML representation, detail limits, annotations,
  sampling and retention remain compatible. Busy writers apply backpressure;
  there is no detached queue with a drop policy.
- Cancelled callers await their admitted write attempt before cancellation is
  propagated. Async traced nodes now record `CancelledError` and close their
  timing/stack correctly. Normal shutdown must drain request/capture tasks;
  forced termination and storage failure remain explicit limits.
- Failed saves log `trace_save_failed` and increment `TraceStore.save_failures`.
  `prometheus_metrics()` exposes the counter for an application's `/metrics`.
  Trace failures preserve the captured application's result/error.
- Segment file names are reserved exclusively across store instances/processes,
  preventing concurrent writers with the same trace id from overwriting a segment.

## 0.4.1

- `TraceStore` retention now also removes expired rows from `index.jsonl`. Before,
  day folders were deleted but their rows stayed: the index grew forever with rows
  pointing at deleted files, and every `entries()` read scanned all of them.
- Index writers lock a separate `index.lock`, so compaction (an atomic replace of
  the index) cannot lose rows appended by other processes at the same time
  (4 concurrent writers x 100 captures during compaction: 400/400 rows).

## 0.4.0

**Trace every real run, not just a script** — persistent capture for services.
- `flow_xray.TraceStore(dir)` — keeps every captured call tree on disk:
  `<day>/<trace_id>.<kind>.<n>.json|html` plus `index.jsonl` with a summary row
  (nodes, LLM calls, tokens, cost, wall-clock duration, issues). Several captures
  of one trace id (a request and the job it triggered) are separate segments.
  Retention, sampling and a `redact` hook (str -> str) for PII; index appends take a
  file lock so several processes can share a directory.
- `store.capture(kind, name, trace_id)` — context manager that records the block
  (joins an already open capture instead of nesting); `flow_xray.annotate(**fields)`
  adds summary fields (tenant, user, status) from anywhere inside it.
- `flow_xray.asgi.TraceMiddleware` — a capture per HTTP request, kept open until the
  last byte (works for streamed / SSE responses, unlike BaseHTTPMiddleware); trace id
  from `X-Request-ID`, `X-Trace-Id` / `X-Flow-Trace` response headers, `context` and
  `on_response` hooks.
- `flow_xray.analyze(result)` — issue scan: `node_error` (once, where raised),
  `slow_node`, `identical_calls` (same function + same inputs: retry/loop signal),
  `many_llm_calls`; app-specific checks via `rules=[...]`; errors inside a handled 4xx
  are counted, not reported. `flow_xray.summarize(result)`.
- `flow-xray report <dir> [--issues]` — CLI summary of a store.
- `trace.configure(max_value_chars=...)` (or `FLOW_XRAY_MAX_VALUE_CHARS`) — recorded
  values were always cut at 800 chars, dropping most of an agent's prompt.

**Fixes**
- Inputs are recorded as they were at call time. They used to be kept by reference
  and serialized at export, so a list the caller kept appending to (an agent's
  `messages`) showed its final contents on every call — all model calls of a run
  looked identical.
- `trace.meta(prompt_tokens=..., completion_tokens=...)` now sets `total_tokens`;
  the summary showed 0 tokens for manually recorded usage.
- Viewer "Total" is the wall-clock span of the trace; it was the sum of all node
  latencies, counting nested time once per ancestor. Subtree latency (and the critical
  path built on it) no longer double-counts children.
- "Repeated Calls" warns only for calls with identical inputs; the same function with
  different inputs (an agent calling its model each turn) is listed without a warning.
- `flow_xray.__version__` comes from the package metadata (it was stuck at 0.3.1).

## 0.3.6

**Static context — possible vs actual execution**
- `flow_xray.static_index.build_index(paths)` — indexes Python source via `ast` (no execution) into a call graph keyed by `__qualname__`, with `callers`, `callees`, `blast_radius`, and `unused` queries (same query shape as callers/callees/blast-radius tools for other languages, rebuilt for Python).
- `flow_xray.merge.merge_trace_with_static(trace_result, static_index)` — combines a runtime trace with a static call graph by name; classifies every edge as `both` / `runtime-only` / `static-only` and every node as `executed` / `reachable-but-not-executed`.
- `TraceResult.to_html(..., static_index=...)` — the graph view gains a **"Show static context"** toggle: statically-reachable-but-not-executed functions render as dashed ghost nodes, edges the static pass couldn't confirm (dynamic dispatch, decorators) are marked runtime-only, and clicking any node shows its static callers/callees/blast-radius alongside the usual runtime detail panel.
- New example: `examples/static_context_demo.py` — a small tool-router agent demonstrating the difference: a database call that fails, an untaken `call_search`/`fallback` branch shown as ghost context, and a dynamically-dispatched call honestly marked runtime-only.

## 0.3.5

- Added `await trace.arun(...)` for native async trace sessions without nesting `asyncio.run(...)` inside an existing event loop.
- Updated async docs to use `trace.arun(...)` as the default async entrypoint.

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
