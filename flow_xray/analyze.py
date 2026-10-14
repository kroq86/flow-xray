"""
Automatic issue scan and summary for a captured trace.

    from flow_xray import trace
    from flow_xray.analyze import analyze, summarize

    result = trace.run(agent, "...")
    issues = analyze(result)          # [{"kind": "node_error", "node": ..., "detail": ...}, ...]
    numbers = summarize(result)       # nodes, llm_calls, tokens, duration_ms, ...

Built-in checks are generic:

- ``node_error``     an exception, reported once at the node that raised it
                     (not again at every ancestor it propagated through);
- ``slow_node``      a leaf node slower than ``slow_ms``;
- ``identical_calls`` the same function called more than once with identical
                     inputs (retry or loop signal; repeated calls with
                     different inputs are normal and not reported);
- ``many_llm_calls`` a root whose subtree made more than ``max_llm_calls``
                     model calls (when set).

Application-specific checks are passed as ``rules``: callables taking a
``TraceNode`` and returning a list of issue dicts.

``http_status``: if the traced work ended in a client error (4xx), the
exceptions inside are the rejection working as designed; they are counted
as ``handled_errors`` in the summary instead of being reported.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable, Iterator

from flow_xray.trace import TraceNode, TraceResult

Rule = Callable[[TraceNode], list]


def _roots(result: TraceResult | Iterable[TraceNode]) -> list[TraceNode]:
    return list(result.roots) if isinstance(result, TraceResult) else list(result)


def walk(node: TraceNode) -> Iterator[TraceNode]:
    yield node
    for child in node.children:
        yield from walk(child)


def is_llm_node(node: TraceNode) -> bool:
    """A node that recorded a model call (model name or token usage)."""
    return bool(node.meta.get("model")) or node.meta.get("total_tokens") is not None


def _input_key(node: TraceNode) -> str:
    try:
        return json.dumps(node.inputs, sort_keys=True, default=str)
    except Exception:
        return repr(node.inputs)


def analyze(
    result: TraceResult | Iterable[TraceNode],
    *,
    slow_ms: float = 5000.0,
    max_llm_calls: int | None = None,
    http_status: int | None = None,
    rules: Iterable[Rule] = (),
) -> list[dict[str, Any]]:
    roots = _roots(result)
    nodes = [n for r in roots for n in walk(r)]
    issues: list[dict[str, Any]] = []
    handled = http_status is not None and 400 <= http_status < 500

    seen_errors: set[str] = set()
    for node in sorted(nodes, key=lambda n: -n.start_ms):  # deepest (latest started) first
        if node.error and node.error not in seen_errors:
            seen_errors.add(node.error)
            if not handled:
                issues.append({"kind": "node_error", "node": node.name, "detail": node.error[:300]})

    for node in nodes:
        if not node.children and node.latency_ms > slow_ms:
            issues.append({"kind": "slow_node", "node": node.name, "ms": round(node.latency_ms)})

    counts: dict[tuple[str, str], int] = {}
    for node in nodes:
        key = (node.name, _input_key(node))
        counts[key] = counts.get(key, 0) + 1
    for (name, _), count in counts.items():
        if count > 1:
            issues.append({"kind": "identical_calls", "node": name, "calls": count})

    if max_llm_calls is not None:
        for root in roots:
            calls = sum(1 for n in walk(root) if is_llm_node(n))
            if calls > max_llm_calls:
                issues.append({"kind": "many_llm_calls", "node": root.name, "calls": calls})

    for rule in rules:
        for node in nodes:
            issues.extend(rule(node) or [])
    return issues


def summarize(result: TraceResult | Iterable[TraceNode], *, http_status: int | None = None) -> dict[str, Any]:
    """Numbers for an index row. ``duration_ms`` is wall clock (first root
    start to last root end), not the sum of nested latencies."""
    roots = _roots(result)
    nodes = [n for r in roots for n in walk(r)]
    llm = [n for n in nodes if is_llm_node(n)]
    errors = sum(1 for n in nodes if n.error)
    out: dict[str, Any] = {
        "nodes": len(nodes),
        "llm_calls": len(llm),
        "tokens": sum(n.meta.get("total_tokens") or 0 for n in llm),
        "cost_usd": round(sum(n.meta.get("estimated_cost_usd") or 0 for n in llm), 8),
        "duration_ms": round(max((r.start_ms + r.latency_ms for r in roots), default=0.0)
                             - min((r.start_ms for r in roots), default=0.0)),
        "errors": errors,
        "handled_errors": errors if http_status is not None and 400 <= http_status < 500 else 0,
    }
    # Optional model timing breakdown, when the tracer recorded it
    # (e.g. trace.meta(load_ms=..., prompt_eval_ms=..., eval_ms=...)).
    for key in ("load_ms", "prompt_eval_ms", "eval_ms"):
        if any(key in n.meta for n in llm):
            out[key] = round(sum(n.meta.get(key) or 0 for n in llm))
    return out
