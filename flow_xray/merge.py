"""
Merge one runtime trace with a static call graph — possible vs actual execution.

``trace.py`` records what happened in one run; ``static_index.py`` records
what the source says could happen. This module is the join between the two:
same-named nodes/edges collapse into one entry, tagged with which side(s)
saw them.

Node/edge identity is the runtime ``TraceNode.name`` — which is the traced
function's ``fn.__qualname__`` (see ``trace.py``'s ``@trace`` wrapper) —
matched against ``StaticIndex`` qualnames, which are built to follow the same
convention on purpose. That match is verified directly by
``tests/test_merge.py::test_traced_qualname_matches_static_index_qualname``
against a real decorated file, not assumed: a decorator that rewraps without
``functools.wraps``, or a hand-set ``trace(kind=...)`` label, would break it,
and this module has no way to detect that case — it would just look like an
ordinary runtime-only node.

A mismatch anywhere — an edge only one side saw, a node the static indexer
never resolved — is not an error to paper over. It's the signal this module
exists to surface: static-only edges are branches the code allows but this
run didn't take; runtime-only edges are calls the static pass couldn't see
(dynamic dispatch, decorators, monkey-patching).
"""

from __future__ import annotations

from dataclasses import dataclass

from flow_xray.static_index import StaticIndex
from flow_xray.trace import TraceNode, TraceResult

MODULE_CALLER = "<module>"


@dataclass(frozen=True)
class MergedNode:
    name: str
    executed: bool
    static: bool

    @property
    def status(self) -> str:
        """"executed" if it ran; otherwise "reachable-but-not-executed" —
        every node here came from either the trace or the static index, so
        the ``not executed`` case implies ``static`` is True."""
        return "executed" if self.executed else "reachable-but-not-executed"


@dataclass(frozen=True)
class MergedEdge:
    caller: str
    callee: str
    runtime: bool
    static: bool

    @property
    def status(self) -> str:
        if self.runtime and self.static:
            return "both"
        return "runtime-only" if self.runtime else "static-only"


@dataclass(frozen=True)
class MergedGraph:
    nodes: dict[str, MergedNode]
    edges: dict[tuple[str, str], MergedEdge]


def _runtime_names_and_edges(roots: list[TraceNode]) -> tuple[set[str], set[tuple[str, str]]]:
    names: set[str] = set()
    edges: set[tuple[str, str]] = set()

    def walk(node: TraceNode, caller: str) -> None:
        names.add(node.name)
        edges.add((caller, node.name))
        for child in node.children:
            walk(child, node.name)

    for root in roots:
        walk(root, MODULE_CALLER)
    return names, edges


def merge_trace_with_static(trace_result: TraceResult, static_index: StaticIndex) -> MergedGraph:
    """Combine one runtime trace with a static call graph by name."""
    executed_names, runtime_edges = _runtime_names_and_edges(trace_result.roots)
    static_names = set(static_index.functions)
    static_edges = static_index.calls

    nodes = {
        name: MergedNode(name=name, executed=name in executed_names, static=name in static_names)
        for name in executed_names | static_names
    }
    edges = {
        pair: MergedEdge(
            caller=pair[0], callee=pair[1],
            runtime=pair in runtime_edges, static=pair in static_edges,
        )
        for pair in runtime_edges | static_edges
    }
    return MergedGraph(nodes=nodes, edges=edges)
