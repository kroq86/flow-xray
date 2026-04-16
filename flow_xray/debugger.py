"""
Stepping / snapshot debugger — delivery hooks on top of core + export.

Stepping model
--------------

1. **Two-phase (global)** — ``TwoStepDebugger``:
   - Phase A: export DOT with ``data`` only (``show_grad=False``).
   - Phase B: after ``backward()`` (or ``backward_from``), export DOT with ``grad`` on each node.

2. **Per-node backward** — ``iter_backward_steps`` / ``GraphDebugger.backward_trace``:
   - Start from ``zero_grad``, set ``root.grad = 1``, walk reverse topological order,
     calling ``_backward()`` on **one** node at a time. After each call, partial gradients
     are filled only along edges that have already been processed; later steps add more.
   - This is for *inspection* of the backward schedule, not a separate math semantics.

3. **Named snapshots** — ``GraphDebugger.named_snapshots`` returns strings (DOT) keyed by
   ``forward``, ``after_backward``, and ``backward_step_{k}`` (k = 0..n-1 in reverse topo).

**Rewind:** not supported; re-build the expression or keep a copy if you need replay.

Double backward is not supported as a product guarantee; use ``zero_grad`` + single ``backward``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from flow_xray.export_dot import value_graph_to_dot
from flow_xray.ir import graph_to_ir
from flow_xray.value import Value, topological_order, zero_grad


class TwoStepDebugger:
    """
    Two global phases: forward DOT (data only), backward DOT (data + grad).

    Usage::

        dbg = TwoStepDebugger(y)
        dot1 = dbg.step_forward_dot()
        y.backward()
        dot2 = dbg.step_backward_dot()
    """

    __slots__ = ("_root",)

    def __init__(self, root: Value) -> None:
        self._root = root

    def step_forward_dot(self) -> str:
        return value_graph_to_dot(self._root, show_grad=False)

    def step_backward_dot(self) -> str:
        return value_graph_to_dot(self._root, show_grad=True)


def iter_backward_steps(root: Value, *, seed: float = 1.0) -> Iterator[Value]:
    """
    Yield each ``Value`` in reverse topological order as its ``_backward`` is applied.

    Mutates ``root`` subgraph gradients. Starts from a clean slate (zeros then seed).
    """
    zero_grad(root)
    root.grad = float(seed)
    for v in reversed(topological_order(root)):
        v._backward()
        yield v


class GraphDebugger:
    """
    Captures DOT (+ optional IR) for forward, each backward micro-step, and final state.
    """

    __slots__ = ("root",)

    def __init__(self, root: Value) -> None:
        self.root = root

    def dot_forward(self) -> str:
        return value_graph_to_dot(self.root, show_grad=False)

    def dot_backward(self) -> str:
        return value_graph_to_dot(self.root, show_grad=True)

    def ir_forward(self) -> dict[str, Any]:
        return graph_to_ir(self.root, include_grad=False)

    def ir_backward(self) -> dict[str, Any]:
        return graph_to_ir(self.root, include_grad=True)

    def named_snapshots(
        self,
        *,
        seed: float = 1.0,
        include_step_dots: bool = True,
    ) -> dict[str, str]:
        """
        Return DOT strings. Keys: ``forward``, optional ``backward_step_0``..``n-1``,
        ``after_backward``.

        Runs backward on ``self.root`` (mutating grads). Caller should not rely on pre-backward
        grad state after this returns.
        """
        out: dict[str, str] = {"forward": self.dot_forward()}
        zero_grad(self.root)
        self.root.grad = float(seed)
        rev = list(reversed(topological_order(self.root)))
        if include_step_dots:
            for k, v in enumerate(rev):
                v._backward()
                out[f"backward_step_{k}"] = value_graph_to_dot(self.root, show_grad=True)
        else:
            for v in rev:
                v._backward()
        out["after_backward"] = value_graph_to_dot(self.root, show_grad=True)
        return out
