"""
Scalar Value DAG — core execution layer.

Guarantees (public contract):
  - Forward values are computed eagerly when ops build new Values.
  - ``backward()`` applies reverse-mode AD in reverse topological order.
  - ``node_id`` is stable for the lifetime of the Value object (suitable for DOT/IR).

Does not guarantee:
  - double backward, JIT, GPU, PyTorch/JAX compatibility, or general CAS at ReLU(0)
    (here: grad w.r.t. input at x==0 is 0).
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, Set


class Value:
    """Scalar node in an explicit op graph."""

    __slots__ = ("data", "grad", "_backward", "_prev", "_op", "label", "node_id")

    _next_seq: int = 0

    def __init__(
        self,
        data: float,
        _children: Iterable["Value"] = (),
        _op: str = "",
        label: str = "",
    ) -> None:
        self.data = float(data)
        self.grad = 0.0
        self._backward: Callable[[], None] = lambda: None
        self._prev: Set[Value] = set(_children)
        self._op = _op
        self.label = label
        self.node_id = f"v{Value._next_seq}"
        Value._next_seq += 1

    @property
    def display_name(self) -> str:
        """Human-readable name for export (label if set, else node_id)."""
        return self.label if self.label else self.node_id

    def __repr__(self) -> str:
        return f"Value({self.node_id!r}, data={self.data}, grad={self.grad}, op={self._op!r})"

    def __add__(self, other: object) -> "Value":
        other = other if isinstance(other, Value) else Value(float(other))  # type: ignore[arg-type]
        out = Value(self.data + other.data, (self, other), "+")
        def _backward() -> None:
            self.grad += out.grad
            other.grad += out.grad
        out._backward = _backward
        return out

    def __mul__(self, other: object) -> "Value":
        other = other if isinstance(other, Value) else Value(float(other))  # type: ignore[arg-type]
        out = Value(self.data * other.data, (self, other), "*")
        def _backward() -> None:
            self.grad += other.data * out.grad
            other.grad += self.data * out.grad
        out._backward = _backward
        return out

    def __pow__(self, other: float | int) -> "Value":
        assert isinstance(other, (int, float))
        out = Value(self.data ** other, (self,), f"**{other}")
        def _backward() -> None:
            self.grad += (other * self.data ** (other - 1)) * out.grad
        out._backward = _backward
        return out

    def relu(self) -> "Value":
        out = Value(self.data if self.data > 0 else 0.0, (self,), "ReLU")
        def _backward() -> None:
            # Subgradient at x==0: convention grad 0 (see module docstring).
            self.grad += (1.0 if self.data > 0 else 0.0) * out.grad
        out._backward = _backward
        return out

    def tanh(self) -> "Value":
        t = math.tanh(self.data)
        out = Value(t, (self,), "tanh")
        def _backward() -> None:
            self.grad += (1.0 - t * t) * out.grad
        out._backward = _backward
        return out

    def backward(self) -> None:
        """Reverse-mode AD. Sets ``self.grad`` to 1 then accumulates upstream. Call ``zero_grad`` first for a clean pass."""
        self.grad = 1.0
        for v in reversed(topological_order(self)):
            v._backward()


def topological_order(root: Value) -> list[Value]:
    """Parents before children; root last."""
    topo: list[Value] = []
    seen: Set[Value] = set()

    def visit(v: Value) -> None:
        if v in seen:
            return
        seen.add(v)
        for ch in v._prev:
            visit(ch)
        topo.append(v)

    visit(root)
    return topo


def zero_grad(root: Value) -> None:
    """Set ``grad`` to 0.0 on every node in the subgraph rooted at ``root``."""
    for v in topological_order(root):
        v.grad = 0.0


def backward_from(root: Value, *, seed: float = 1.0, zero_first: bool = True) -> None:
    """
    Run backward with ``root.grad = seed`` after optional ``zero_grad``.

    If ``zero_first`` is False, gradients accumulate (micrograd-style).
    """
    if zero_first:
        zero_grad(root)
    root.grad = float(seed)
    for v in reversed(topological_order(root)):
        v._backward()
