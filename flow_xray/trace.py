"""
Execution tracing — capture function-call DAGs with I/O, latency, and errors.

Usage::

    from flow_xray import trace

    @trace
    def call_llm(prompt):
        return openai.chat(...)

    @trace
    def agent(query):
        plan = call_llm(f"plan: {query}")
        return call_llm(f"answer: {plan}")

    result = trace.run(agent, "weather in Tokyo?")
    result.to_html("trace.html")       # open in browser — done

Or via CLI::

    flow-xray run agent.py --html trace.html
"""

from __future__ import annotations

import functools
import inspect
import json
import re
import time
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable


_UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
_ISO_TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b")
_USER_PATH_RE = re.compile(r"/Users/[^/\s]+(?:/[^\s\"']+)+")
_TMP_PATH_RE = re.compile(r"/tmp(?:/[^\s\"']+)+")


def _normalize_preview_text(text: str) -> str:
    text = _UUID_RE.sub("<uuid>", text)
    text = _ISO_TS_RE.sub("<timestamp>", text)
    text = _USER_PATH_RE.sub(lambda m: f"<path:{m.group(0).rsplit('/', 1)[-1]}>", text)
    text = _TMP_PATH_RE.sub(lambda m: f"<tmp:{m.group(0).rsplit('/', 1)[-1]}>", text)
    return text


def _safe_repr(obj: Any, max_len: int = 800) -> str:
    try:
        s = json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        s = repr(obj)
    s = _normalize_preview_text(s)
    if len(s) > max_len:
        s = s[: max_len - 1] + "\u2026"
    return s


def _bind_args(fn: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
    try:
        sig = inspect.signature(fn)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except Exception:
        return {"args": list(args), "kwargs": kwargs}


def _mask_value(obj: Any, redacted_keys: set[str]) -> Any:
    if isinstance(obj, Mapping):
        return {
            k: ("[redacted]" if isinstance(k, str) and k in redacted_keys else _mask_value(v, redacted_keys))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_mask_value(v, redacted_keys) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_mask_value(v, redacted_keys) for v in obj)
    return obj


def _redact_inputs(inputs: dict[str, Any], redacted_keys: set[str]) -> dict[str, Any]:
    if not redacted_keys:
        return inputs
    return {
        key: ("[redacted]" if key in redacted_keys else _mask_value(value, redacted_keys))
        for key, value in inputs.items()
    }


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class TraceNode:
    name: str
    node_id: str
    inputs: dict[str, Any]
    output: Any = None
    error: str | None = None
    start_ms: float = 0.0
    latency_ms: float = 0.0
    children: list[TraceNode] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    kind: str | None = None
    tags: dict[str, Any] = field(default_factory=dict)
    _stack_token: object | None = field(default=None, repr=False)

    def to_dict(self, t0: float = 0.0) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.node_id,
            "name": self.name,
            "inputs": {k: _safe_repr(v) for k, v in self.inputs.items()},
            "output": _safe_repr(self.output),
            "error": self.error,
            "start_ms": round(self.start_ms - t0, 2),
            "latency_ms": round(self.latency_ms, 2),
            "children": [c.to_dict(t0) for c in self.children],
        }
        if self.meta:
            d["meta"] = self.meta
        if self.kind is not None:
            d["kind"] = self.kind
        if self.tags:
            d["tags"] = self.tags
        return d


# Approximate cost per 1M tokens (input/output) for common models.
_COST_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o3-mini": (1.10, 4.40),
}


def _extract_llm_meta(output: Any) -> dict[str, Any]:
    """Auto-extract token usage, model, and estimated cost from OpenAI-style response objects."""
    meta: dict[str, Any] = {}
    usage = getattr(output, "usage", None)
    if usage is None:
        return meta
    prompt_tok = getattr(usage, "prompt_tokens", None)
    if prompt_tok is None:
        prompt_tok = getattr(usage, "input_tokens", None)
    completion_tok = getattr(usage, "completion_tokens", None)
    if completion_tok is None:
        completion_tok = getattr(usage, "output_tokens", None)
    total_tok = getattr(usage, "total_tokens", None)
    if prompt_tok is not None:
        meta["prompt_tokens"] = prompt_tok
    if completion_tok is not None:
        meta["completion_tokens"] = completion_tok
    if total_tok is not None:
        meta["total_tokens"] = total_tok
    elif prompt_tok is not None and completion_tok is not None:
        meta["total_tokens"] = prompt_tok + completion_tok
    model = getattr(output, "model", None)
    if model:
        meta["model"] = model
    _maybe_add_cost(meta)
    return meta


def _maybe_add_cost(meta: dict[str, Any]) -> None:
    """Compute estimated_cost_usd if model + token counts are present."""
    model = meta.get("model")
    pt = meta.get("prompt_tokens")
    ct = meta.get("completion_tokens")
    if not (model and pt is not None and ct is not None):
        return
    base = model.split("-202")[0]
    costs = _COST_PER_1M.get(base)
    if costs:
        meta["estimated_cost_usd"] = round((pt * costs[0] + ct * costs[1]) / 1_000_000, 6)


def _count_all(roots: list[TraceNode]) -> tuple[int, int]:
    """Return (total_nodes, error_count)."""
    total = errors = 0
    def walk(n: TraceNode) -> None:
        nonlocal total, errors
        total += 1
        if n.error:
            errors += 1
        for c in n.children:
            walk(c)
    for r in roots:
        walk(r)
    return total, errors


class TraceResult:
    """Holds a captured DAG and provides export helpers."""

    __slots__ = ("roots", "return_value", "error", "_t0")

    def __init__(
        self,
        roots: list[TraceNode],
        return_value: Any = None,
        error: BaseException | None = None,
        t0: float = 0.0,
    ) -> None:
        self.roots = roots
        self.return_value = return_value
        self.error = error
        self._t0 = t0

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [r.to_dict(self._t0) for r in self.roots]}

    def diff(self, other: "TraceResult") -> str:
        """Compare self (old) with other (new). Returns standalone diff HTML."""
        from flow_xray.export_html import diff_to_html
        return diff_to_html(self, other)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_html(self, path: str, *, title: str = "flow-xray trace") -> None:
        from flow_xray.export_html import trace_to_standalone_html
        from pathlib import Path
        Path(path).write_text(
            trace_to_standalone_html(self, title=title), encoding="utf-8",
        )

    def to_dot(self) -> str:
        flat = _flatten(self.roots)
        lines = [
            "digraph G {",
            '  rankdir="TB";',
            '  bgcolor="transparent";',
            '  node [shape=box, style="rounded,filled", fontname=Helvetica, fontsize=11, margin="0.3,0.15"];',
            '  edge [color="#30363d", arrowsize=0.7];',
        ]
        for n, pid in flat:
            color = "#da3633" if n["error"] else ("#9e6a03" if n["latency_ms"] > 1000 else "#238636")
            meta = n.get("meta", {})
            tok_part = f'\\n{meta["total_tokens"]} tok' if meta.get("total_tokens") else ""
            label = f'{n["name"]}\\n{n["latency_ms"]}ms{tok_part}'
            lines.append(f'  {n["id"]} [label="{label}", fillcolor="{color}", fontcolor="white"];')
        for n, pid in flat:
            if pid:
                lines.append(f"  {pid} -> {n['id']};")
        lines.append("}")
        return "\n".join(lines)


def _flatten(roots: list[dict], parent_id: str | None = None) -> list[tuple[dict, str | None]]:
    """Flatten trace dicts into (node_dict, parent_id) pairs."""
    result: list[tuple[dict, str | None]] = []
    def walk(n: dict | TraceNode, pid: str | None) -> None:
        d = n if isinstance(n, dict) else n.to_dict()
        result.append((d, pid))
        for c in d.get("children", []):
            walk(c, d["id"])
    for r in roots:
        walk(r, parent_id)
    return result


# ---------------------------------------------------------------------------
# Session (task-local call-stack tracker with shared roots per trace session)
# ---------------------------------------------------------------------------

class _TraceSession:
    _current_session: ContextVar[_TraceSession | None] = ContextVar("flow_xray_current_session", default=None)
    _current_stack: ContextVar[tuple[TraceNode, ...]] = ContextVar("flow_xray_current_stack", default=())
    _id_counter = 0
    _id_lock = Lock()

    def __init__(self) -> None:
        self.roots: list[TraceNode] = []
        self._session_start_ms: float = time.perf_counter() * 1000

    @classmethod
    def _next_id(cls) -> str:
        with cls._id_lock:
            cls._id_counter += 1
            return f"t{cls._id_counter}"

    def enter_node(self, name: str, inputs: dict, kind: str | None = None) -> TraceNode:
        stack = self._current_stack.get()
        node = TraceNode(
            name=name,
            node_id=self._next_id(),
            inputs=inputs,
            start_ms=time.perf_counter() * 1000,
            kind=kind,
        )
        if stack:
            stack[-1].children.append(node)
        else:
            self.roots.append(node)
        node._stack_token = self._current_stack.set(stack + (node,))
        return node

    def exit_node(self, node: TraceNode, output: Any, error: str | None) -> None:
        node.output = output
        node.error = error
        node.latency_ms = time.perf_counter() * 1000 - node.start_ms
        if output is not None and not error:
            node.meta.update(_extract_llm_meta(output))
        if node._stack_token is not None:
            self._current_stack.reset(node._stack_token)
            node._stack_token = None

    @classmethod
    def current(cls) -> _TraceSession | None:
        return cls._current_session.get()

    def __enter__(self) -> _TraceSession:
        self._session_token = self._current_session.set(self)
        self._stack_token = self._current_stack.set(())
        return self

    def __exit__(self, *exc: object) -> bool:
        self._current_stack.reset(self._stack_token)
        self._current_session.reset(self._session_token)
        return False


# ---------------------------------------------------------------------------
# Public API object
# ---------------------------------------------------------------------------

class _Trace:
    """
    Decorator + runner.

    ``@trace`` — mark functions for capture.
    ``trace.run(fn, ...)`` — execute with capture, return ``TraceResult``.
    ``trace.capture()`` — context manager for manual session.
    """

    def __call__(
        self,
        fn: Callable | None = None,
        *,
        redact: list[str] | tuple[str, ...] | set[str] | None = None,
        capture_output: bool = True,
        kind: str | None = None,
    ) -> Callable:
        if fn is None:
            return lambda actual_fn: self(
                actual_fn,
                redact=redact,
                capture_output=capture_output,
                kind=kind,
            )
        redacted_keys = {str(item) for item in (redact or ())}

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                session = _TraceSession.current()
                if session is None:
                    return await fn(*args, **kwargs)
                inputs = _redact_inputs(_bind_args(fn, args, kwargs), redacted_keys)
                node = session.enter_node(fn.__qualname__, inputs, kind=kind)
                try:
                    result = await fn(*args, **kwargs)
                    session.exit_node(node, result if capture_output else "[redacted]", None)
                    return result
                except Exception as e:
                    session.exit_node(node, None, f"{type(e).__name__}: {e}")
                    raise
            async_wrapper._traced = True  # type: ignore[attr-defined]
            return async_wrapper
        else:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                session = _TraceSession.current()
                if session is None:
                    return fn(*args, **kwargs)
                inputs = _redact_inputs(_bind_args(fn, args, kwargs), redacted_keys)
                node = session.enter_node(fn.__qualname__, inputs, kind=kind)
                try:
                    result = fn(*args, **kwargs)
                    session.exit_node(node, result if capture_output else "[redacted]", None)
                    return result
                except Exception as e:
                    session.exit_node(node, None, f"{type(e).__name__}: {e}")
                    raise
            wrapper._traced = True  # type: ignore[attr-defined]
            return wrapper

    def run(
        self,
        fn: Callable,
        *args: Any,
        raise_exceptions: bool = False,
        **kwargs: Any,
    ) -> TraceResult:
        """Execute *fn* inside a fresh trace session, return ``TraceResult``."""
        session = _TraceSession()
        rv: Any = None
        err: BaseException | None = None
        with session:
            try:
                rv = fn(*args, **kwargs)
            except Exception as exc:
                err = exc
        if err is not None and raise_exceptions:
            raise err
        return TraceResult(session.roots, return_value=rv, error=err, t0=session._session_start_ms)

    def capture(self) -> _TraceSession:
        """Return a context-manager session for manual use."""
        return _TraceSession()

    @staticmethod
    def tag(*labels: str, **kwargs: Any) -> None:
        """Attach tags to the current trace node. Visible as badges in the viewer."""
        session = _TraceSession.current()
        stack = _TraceSession._current_stack.get()
        if session is None or not stack:
            return
        t = stack[-1].tags
        for label in labels:
            t[label] = True
        t.update(kwargs)

    @staticmethod
    def meta(**kwargs: Any) -> None:
        """Attach arbitrary metadata to the current trace node.

        Use inside a ``@trace``-decorated function to record token counts,
        cost, model name, or any custom key-value pairs::

            @trace
            def call_llm(prompt):
                resp = openai.chat.completions.create(...)
                trace.meta(prompt_tokens=resp.usage.prompt_tokens,
                           completion_tokens=resp.usage.completion_tokens)
                return resp.choices[0].message.content

        When ``model``, ``prompt_tokens``, and ``completion_tokens`` are all
        present, ``estimated_cost_usd`` is computed automatically.
        """
        session = _TraceSession.current()
        stack = _TraceSession._current_stack.get()
        if session is None or not stack:
            return
        m = stack[-1].meta
        m.update(kwargs)
        _maybe_add_cost(m)


trace = _Trace()
