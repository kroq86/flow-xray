"""
Persistent trace store: capture real runs (requests, jobs, tool calls),
keep every call tree on disk, scan each for issues, list and report them.

    from flow_xray.store import TraceStore

    store = TraceStore("traces", retention_days=7)

    with store.capture("job", "nightly-reindex", trace_id="run-42"):
        reindex()                       # @trace-decorated calls inside are recorded

    store.entries(issues_only=True)     # newest first, with summary + issues
    store.segments("run-42")            # every capture of one trace id

Layout::

    traces/<YYYY-MM-DD>/<trace_id>.<kind>.<n>.json   call tree (TraceResult.to_dict)
    traces/<YYYY-MM-DD>/<trace_id>.<kind>.<n>.html   viewer
    traces/index.jsonl                               one summary row per capture

One trace id can have several captures (segments): e.g. an HTTP request and
the background job it triggered, or an agent run and the remote tool calls
it made — each is its own segment, none overwrites another.

``redact``: a ``str -> str`` callable applied to the JSON and HTML before
they are written (traces hold full inputs and outputs: prompts, documents).
Index appends take an exclusive file lock where the platform has one
(fcntl), so several processes can share one store directory.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping

from flow_xray.analyze import Rule, analyze, summarize
from flow_xray.trace import TraceResult, _TraceSession
from flow_xray._async_save import run_save

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

_SAFE = re.compile(r"[^A-Za-z0-9._-]")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_fields: ContextVar[dict | None] = ContextVar("flow_xray_capture_fields", default=None)
_LOGGER = logging.getLogger(__name__)


def annotate(**fields: Any) -> None:
    """Add summary fields (e.g. tenant, user, status) to the capture that is
    open in the current context; a no-op outside one."""
    current = _fields.get()
    if current is not None:
        current.update(fields)


class TraceStore:
    def __init__(
        self,
        root: str | Path,
        *,
        retention_days: int | None = 7,
        redact: Callable[[str], str] | None = None,
        sample: float = 1.0,
        slow_ms: float = 5000.0,
        slow_ms_by_kind: Mapping[str, float] | None = None,
        slow_all_nodes: bool = False,
        max_llm_calls: int | None = None,
        rules: Iterable[Rule] = (),
    ) -> None:
        self.root = Path(root)
        self.retention_days = retention_days
        self.redact = redact
        self.sample = sample
        self.slow_ms = slow_ms
        self.slow_ms_by_kind = dict(slow_ms_by_kind or {})
        self.slow_all_nodes = slow_all_nodes
        self.max_llm_calls = max_llm_calls
        self.rules = list(rules)
        self._lock = threading.Lock()
        self._save_failures = 0

    # -- capture ------------------------------------------------------------

    @contextmanager
    def capture(self, kind: str, name: str, trace_id: str | None = None, **fields: Any) -> Iterator[dict]:
        """Record the calls made inside the block and save them on exit.

        Joins an already open capture instead of nesting a new one (an HTTP
        request that runs a traced job records one tree, not two). Yields the
        summary-field dict; ``status`` (int, HTTP-like) set in it is used to
        tell handled 4xx rejections from real errors."""
        info: dict[str, Any] = dict(fields)
        if _TraceSession.current() is not None or random.random() >= self.sample:
            yield info
            return
        session = _TraceSession()
        token = _fields.set(info)
        error: BaseException | None = None
        with session:
            try:
                yield info
            except BaseException as exc:
                error = exc
                raise
            finally:
                _fields.reset(token)
                if session.roots:
                    self.save(TraceResult(session.roots, error=error, t0=session._session_start_ms),
                              kind=kind, name=name, trace_id=trace_id, **info)

    @asynccontextmanager
    async def acapture(self, kind: str, name: str, trace_id: str | None = None, **fields: Any):
        """Capture through the final awaited operation, then await persistence.

        Matches capture() sampling, nesting, annotations and error capture.
        All save work runs in the trace-only pool. Cancellation is propagated
        only after the save attempt finishes; SIGKILL cannot be drained.
        """
        info: dict[str, Any] = dict(fields)
        if _TraceSession.current() is not None or random.random() >= self.sample:
            yield info
            return
        session = _TraceSession()
        token = _fields.set(info)
        error: BaseException | None = None
        with session:
            try:
                yield info
            except BaseException as exc:
                error = exc
                raise
            finally:
                _fields.reset(token)
                if session.roots:
                    await self.asave(TraceResult(session.roots, error=error, t0=session._session_start_ms),
                                     kind=kind, name=name, trace_id=trace_id, **info)

    async def asave(self, result: TraceResult, *, kind: str, name: str, trace_id: str | None = None,
                    **fields: Any) -> dict[str, Any] | None:
        """Await save() in a dedicated pool, preserving its format and result.

        The caller must not mutate result until this await completes. Returns
        None on failure, with a logged error and an incremented failure counter.
        No tree is dropped because the executor is busy: callers await capacity.
        """
        if not result.roots:
            return None
        return await run_save(partial(self.save, result, kind=kind, name=name, trace_id=trace_id, **fields),
                              partial(self._save_failed, trace_id, kind, name))

    def _save_failed(self, trace_id: str | None, kind: str, name: str) -> None:
        with self._lock:
            self._save_failures += 1
        try:
            _LOGGER.exception("trace_save_failed", extra={"trace_id": trace_id, "trace_kind": kind,
                                                         "trace_name": name})
        except Exception:
            # A broken logging handler must not replace the application's
            # outcome. The failure counter remains available to /metrics.
            pass

    @property
    def save_failures(self) -> int:
        """Failed save attempts, including synchronous and asynchronous writes."""
        with self._lock:
            return self._save_failures

    def prometheus_metrics(self) -> str:
        """Append to the application's /metrics response; no server dependency."""
        return ("# HELP trace_save_failed_total Trace persistence attempts that failed\n"
                "# TYPE trace_save_failed_total counter\n"
                f"trace_save_failed_total {self.save_failures}\n")

    # -- write --------------------------------------------------------------

    def save(self, result: TraceResult, *, kind: str, name: str, trace_id: str | None = None,
             **fields: Any) -> dict[str, Any] | None:
        """Write one capture and its index row; returns the row. Never raises:
        a tracing failure must not break the work it traces."""
        if not result.roots:
            return None
        try:
            trace_id = trace_id or f"{int(time.time() * 1000)}-{random.randrange(16**6):06x}"
            status = fields.get("status") if isinstance(fields.get("status"), int) else None
            issues = analyze(result, slow_ms=self.slow_ms, slow_ms_by_kind=self.slow_ms_by_kind,
                             slow_all_nodes=self.slow_all_nodes,
                             max_llm_calls=self.max_llm_calls,
                             http_status=status, rules=self.rules)
            now = datetime.now(timezone.utc)
            day = self.root / now.strftime("%Y-%m-%d")
            day.mkdir(parents=True, exist_ok=True)
            safe_id = _SAFE.sub("_", trace_id)
            safe_kind = _SAFE.sub("_", kind)
            with self._lock:
                n = 0
                while True:
                    json_path = day / f"{safe_id}.{safe_kind}.{n}.json"
                    try:
                        # Reserve atomically across stores/processes too.
                        with json_path.open("x", encoding="utf-8"):
                            pass
                        break
                    except FileExistsError:
                        n += 1
                html_path = day / f"{safe_id}.{safe_kind}.{n}.html"
            json_text = result.to_json()
            json_path.write_text(self.redact(json_text) if self.redact else json_text, encoding="utf-8")
            result.to_html(str(html_path), title=f"{kind} {name} — {trace_id}",
                           slow_ms=self.slow_ms, slow_ms_by_kind=self.slow_ms_by_kind)
            if self.redact:
                html_path.write_text(self.redact(html_path.read_text(encoding="utf-8")), encoding="utf-8")
            row = {"ts": now.isoformat(), "trace_id": trace_id, "kind": kind, "name": name,
                   "path": str(html_path.relative_to(self.root)), "issues": issues,
                   **summarize(result, http_status=status), **fields}
            self._append(row)
            self._expire(now)
            return row
        except Exception:
            self._save_failed(trace_id, kind, name)
            return None

    @contextmanager
    def _index_locked(self) -> Iterator[None]:
        """Exclusive lock for index writers, on a separate lock file: the
        index itself is replaced when expired rows are compacted away, and a
        lock (or an open handle) on the replaced file would protect nothing."""
        with self._lock, open(self.root / "index.lock", "a") as lock:
            if fcntl is not None:
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def _append(self, row: dict[str, Any]) -> None:
        line = json.dumps(row, default=str, ensure_ascii=False) + "\n"
        with self._index_locked(), open(self.root / "index.jsonl", "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()

    def _expire(self, now: datetime) -> None:
        """Delete day folders older than the retention period, and their rows
        from the index -- otherwise index.jsonl grows forever with rows
        pointing at deleted files, and every read scans all of them."""
        if not self.retention_days:
            return
        cutoff = (now - timedelta(days=self.retention_days)).strftime("%Y-%m-%d")
        expired = [d for d in self.root.iterdir() if d.is_dir() and _DAY.fullmatch(d.name) and d.name < cutoff]
        for d in expired:
            shutil.rmtree(d, ignore_errors=True)
        index = self.root / "index.jsonl"
        if not index.is_file():
            return
        with open(index, encoding="utf-8") as f:
            first = f.readline()
        try:
            oldest = json.loads(first)["ts"][:10]
        except (ValueError, KeyError, TypeError):
            oldest = ""
        if not expired and oldest >= cutoff:
            return  # nothing to compact: rows are appended in time order
        with self._index_locked():
            kept = []
            for line in index.read_text(encoding="utf-8").splitlines():
                try:
                    if json.loads(line)["ts"][:10] >= cutoff:
                        kept.append(line + "\n")
                except (ValueError, KeyError, TypeError):
                    continue  # a torn line from a crash mid-write
            tmp = index.with_name("index.jsonl.tmp")
            tmp.write_text("".join(kept), encoding="utf-8")
            os.replace(tmp, index)

    # -- read ---------------------------------------------------------------

    def entries(self, limit: int = 50, *, issues_only: bool = False,
                where: Callable[[dict], bool] | None = None) -> list[dict[str, Any]]:
        """Index rows, newest first."""
        index = self.root / "index.jsonl"
        if not index.is_file():
            return []
        rows = []
        for line in index.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue  # a torn line from a crash mid-write
        rows = [r for r in rows if (not issues_only or r.get("issues")) and (where is None or where(r))]
        return rows[::-1][:limit]

    def segments(self, trace_id: str) -> list[dict[str, Any]]:
        """Every capture of one trace id, oldest first."""
        return [r for r in self.entries(limit=10**9) if r.get("trace_id") == trace_id][::-1]

    def html(self, row: dict[str, Any]) -> str:
        return (self.root / row["path"]).read_text(encoding="utf-8")

    def report(self, limit: int = 20, *, issues_only: bool = False) -> str:
        rows = self.entries(limit=limit, issues_only=issues_only)
        lines = []
        totals: dict[str, int] = {}
        for r in rows:
            kinds = sorted({i["kind"] for i in r.get("issues", [])})
            for k in (i["kind"] for i in r.get("issues", [])):
                totals[k] = totals.get(k, 0) + 1
            lines.append(f"{r['ts'][:19]} {r['kind']:<8} {str(r['name'])[:32]:<32} {r.get('duration_ms', 0):>7}ms "
                         f"llm={r.get('llm_calls', 0):<3} tok={r.get('tokens', 0):<7} "
                         f"issues=[{', '.join(kinds) or '-'}]  {r['path']}")
        with_issues = sum(1 for r in rows if r.get("issues"))
        lines.append(f"\n{len(rows)} traces, {with_issues} with issues: {totals}")
        return "\n".join(lines)
