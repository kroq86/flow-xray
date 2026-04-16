"""
Backward-compatibility imports for code that used ``graph_debug``.

Prefer::

    from flow_xray import Value, value_graph_to_dot, TwoStepDebugger, ...
"""

from flow_xray import (
    GraphDebugger,
    TwoStepDebugger,
    Value,
    backward_from,
    graph_to_ir,
    ir_to_json,
    iter_backward_steps,
    topological_order,
    value_graph_to_dot,
    write_dot,
    zero_grad,
)
from flow_xray.export_html import standalone_viewer_html, write_standalone_viewer_html

__all__ = [
    "GraphDebugger",
    "TwoStepDebugger",
    "Value",
    "backward_from",
    "graph_to_ir",
    "ir_to_json",
    "iter_backward_steps",
    "topological_order",
    "value_graph_to_dot",
    "write_dot",
    "zero_grad",
    "standalone_viewer_html",
    "write_standalone_viewer_html",
]


if __name__ == "__main__":
    a = Value(2.0, label="a")
    b = Value(-3.0, label="b")
    c = Value(10.0, label="c")
    L = ((a * b) + c).relu().tanh()
    L.label = "L"
    fwd = value_graph_to_dot(L, show_grad=False)
    L.backward()
    bwd = value_graph_to_dot(L, show_grad=True)
    write_standalone_viewer_html("forward.html", fwd, title="flow-xray forward")
    write_standalone_viewer_html("backward.html", bwd, title="flow-xray backward")
    print("Wrote forward.html and backward.html — open in your browser.")
