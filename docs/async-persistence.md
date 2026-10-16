# Awaited trace persistence

Scope: flow-xray 0.5.0 candidate against 0.4.1, commit `906c7c5`. No application
integration, production traffic, LLM calls or remote services are part of the
measurement. This is implementation validation and an engineering trade-off.

The benchmark below covers persistence before the per-node traffic-light UI,
commit `b15c00f`. The newer viewer adds diagnostic fields and therefore is no
longer byte-identical HTML to 0.4.1. Full trace JSON remains unchanged; current
sync/async saves still have byte-identical JSON and HTML in the regression test.
No new performance measurement is claimed for the viewer additions.

## Contract and decision

Keep the synchronous API. Add `acapture()` / `asave()` in the library, and use
`acapture()` in ASGI. Capture still includes the last streamed response byte.
Persistence is awaited after that byte: analyze, redact, render, JSON/HTML writes,
index append and retention all run in a dedicated two-worker pool. A semaphore
admits at most two executor submissions per event loop. Waiting callers retain
their capture; saturation neither detaches nor drops it. Across multiple event
loops the executor still has two workers; each loop has its own admission bound.

The unchanged format and current configured detail limit are invariants. Sampling
remains configurable, with the unchanged default of 100%. The captured result must
not be mutated while its `asave()` is pending. Tracing/snapshotting the individual
calls still costs time on the caller; moving persistence does not remove all GIL
contention or establish non-blocking behavior for arbitrary user callbacks.

Alternatives: leave the old path unchanged (measured loop stall); add an application
wrapper (rejected boundary: persistence belongs to this library); use the default
executor (rejected isolation: other application I/O uses it); detach a writer task
or drop work on a full queue (rejected trace-completeness contract).

## Claims and bounded evidence

- **C0 — representation compatibility, SUPPORTED for the fixed capture.** One real
  `trace.run()` result is saved with the old `save()` implementation and new
  `asave()`. Redacted JSON and standalone HTML must be byte-identical. Separate
  captures cannot be compared byte-for-byte because their ids/timings differ.
- **C1 — reduced event-loop stall, SUPPORTED in the measured workload.** Control:
  old ASGI middleware. Intervention: async ASGI persistence, same app, inputs,
  redactor, interpreter and disk. Three series of eight requests each; 2 ms loop
  ticker; record maximum lag, series duration, file sizes and saved count. Stop
  after these series. Support criterion: baseline max lag above 20 ms and new max
  lag below half the baseline; no missing traces. Otherwise leave the benefit
  inconclusive and stop. The benchmark is synthetic, not a production throughput
  claim, and does not measure an LLM or SQLite workload.
- **C2 — completion and failure behavior, SUPPORTED for executed tests.** Save
  success/error, nested sync/async capture, PII redaction, SSE last step, caller
  cancellation during capture/write/capacity wait, repeated cancellation,
  unexpected worker/submission failure, and concurrent segment reservation are
  checked. A deliberately unavailable default executor confirms pool isolation.
- **C3 — graceful ASGI shutdown, SUPPORTED for the executed Uvicorn test.** Stall
  persistence with a synchronization event; receive the complete HTTP response;
  request server shutdown; observe that the server remains alive until the write
  is released, then check JSON/HTML/index and the complete two-node call tree.

C0 is necessary for adopting the faster path without representation loss. It does
not establish C1, C2 or C3: each has its own observation. Passing these scenarios
does not prove universal trace durability or runtime refinement.

## Observed results

Python 3.12.13, macOS, local temporary directory. Fixture: 20 documents of 664
characters, nested ASGI/tool/model-shaped calls, two PII regex replacements,
`max_value_chars=100000`. Mean files: about 29 KB JSON and 66 KB HTML per request,
smaller than the application's reported real traces. Both versions warm the HTML
export before measurement. No seed is used; the fixture and request count are fixed.

| Metric, three series | 0.4.1 | 0.5.0 candidate |
| --- | --- | --- |
| Maximum event-loop lag per series | 61.131 / 85.060 / 62.386 ms | 6.232 / 2.738 / 5.425 ms |
| Eight-request duration | 62.244 / 86.141 / 63.420 ms | 74.342 / 62.288 / 60.189 ms |
| Captures saved | 24 / 24 | 24 / 24 |

The loop-stall criterion is met. Total completion time did not consistently
improve; no throughput advantage is claimed. Raw observations and the byte-parity
result are in `benchmarks/results/async-persistence-20261016.json`.

The final Python 3.12 suite passed 84 tests; the optional server check was skipped there
because uvicorn is not installed. On Python 3.14, all 85 tests passed, including the
real Uvicorn 0.53.0 / httpx 0.28.1 server check. A built 0.5.0 wheel was installed
into a separate temporary directory and saved JSON/HTML/index successfully.
Server behavior under other versions and operating systems remains unmeasured.

## Failures, cancellation and limits

Save failures preserve the captured application's return value or exception and
return `None`, as before. They now log `trace_save_failed`, increment the per-store
`save_failures` counter, and are exposed by `prometheus_metrics()` as
`trace_save_failed_total`. The application must append this text to its `/metrics`
response; the library does not start an endpoint. A broken logging handler cannot
replace the application outcome; the counter remains observable.

Cancellation drains the save attempt before propagating, including a caller still
waiting for pool capacity. Async traced nodes close with `CancelledError` instead
of remaining unfinished. The event loop must stay alive until capture tasks drain.
Uvicorn's normal graceful shutdown waits for the ASGI tasks. SIGKILL, forced loop
termination, storage failure, and hard shutdown deadlines can lose unsaved work.
A permanently stalled filesystem can prevent drain completion. There is no
durable spool, fsync-based crash guarantee, retry protocol or exactly-once claim.

## Reproduction

From a source checkout with pytest installed:

```sh
python -m pytest -q
python benchmarks/async_persistence.py .
```

Obtain a separate, read-only baseline source tree at `906c7c5`, then run:

```sh
python benchmarks/async_persistence.py /path/to/baseline
python benchmarks/compare_persistence.py . /path/to/baseline
```

To execute the optional network/server test, install uvicorn and httpx in a test
environment and run `python -m pytest tests/test_store_server.py -q`. Core runtime
dependencies remain empty. Filesystem permissions must allow localhost binding.

Next integration boundary: the application owner switches asynchronous MCP/tool
captures to `async with STORE.acapture(...)`, appends the metric, and pins the
released library version. No ticket_harness code is part of this change.

The final suite also checks optional per-kind analysis budgets (typed parent
operations, model-metadata fallback and unchanged tree serialization). These
checks add no performance claim to the recorded persistence benchmark.
