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
- ``slow_node``      a node slower than ``slow_ms`` (leaves by default, all
                     nodes with ``slow_all_nodes=True``; kinds can override);
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
from typing import Any, Callable, Iterable, Iterator, Mapping

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


def self_time_ms(node: TraceNode) -> float:
    """Wall time outside recorded child intervals, not CPU or blocking time.

    Clip to the parent and merge overlapping async children before subtracting:
    summing their durations would subtract concurrent time more than once.
    Uninstrumented work, waits and scheduler delays remain indistinguishable.
    """
    start, end = node.start_ms, node.start_ms + max(0.0, node.latency_ms)
    intervals = sorted((max(start, c.start_ms), min(end, c.start_ms + max(0.0, c.latency_ms)))
                       for c in node.children)
    covered, cursor = 0.0, start
    for left, right in intervals:
        left = max(left, cursor)
        if right > left:
            covered += right - left
            cursor = right
    return max(0.0, node.latency_ms - covered)


def latency_profile(result: TraceResult | Iterable[TraceNode], *, slow_ms: float = 50.0,
                    slow_ms_by_kind: Mapping[str, float] | None = None) -> dict[str, dict[str, Any]]:
    """Per-node traffic lights; separate derived data, leaving the tree intact."""
    budgets = slow_ms_by_kind or {}
    profile = {}
    for root in _roots(result):
        for node in walk(root):
            kind = node.kind or ("llm" if is_llm_node(node) else None)
            threshold = budgets.get(kind, slow_ms)
            profile[node.node_id] = {
                "elapsed_ms": round(node.latency_ms, 3), "self_ms": round(self_time_ms(node), 3),
                "threshold_ms": threshold, "above_threshold": node.latency_ms > threshold,
                "level": "error" if node.error else "warning" if node.latency_ms > threshold else "ok",
            }
    return profile


def analyze(
    result: TraceResult | Iterable[TraceNode],
    *,
    slow_ms: float = 5000.0,
    slow_ms_by_kind: Mapping[str, float] | None = None,
    slow_all_nodes: bool = False,
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

    # Explicit kind budgets also cover parent nodes: a retrieval operation
    # includes its embedding child. Unconfigured nodes keep the leaf-only
    # legacy check. Model metadata supplies "llm" when no kind was recorded.
    budgets = slow_ms_by_kind or {}
    for node in nodes:
        kind = node.kind or ("llm" if is_llm_node(node) else None)
        configured = kind in budgets
        threshold = budgets[kind] if configured else slow_ms
        if (slow_all_nodes or configured or not node.children) and node.latency_ms > threshold:
            issue = {"kind": "slow_node", "node": node.name, "ms": round(node.latency_ms)}
            if configured:
                issue.update(node_kind=kind, threshold_ms=threshold)
            if slow_all_nodes:
                issue.update(node_id=node.node_id, threshold_ms=threshold,
                             elapsed_ms=round(node.latency_ms, 3), self_ms=round(self_time_ms(node), 3),
                             severity="warning")
            issues.append(issue)

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
