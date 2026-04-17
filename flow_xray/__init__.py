"""
flow-xray — execution graph debugger.

Primary API: ``trace`` (decorator + runner for capturing execution DAGs).

Also includes scalar Value autodiff core + inspection exports.
"""

from flow_xray.trace import TraceNode, TraceResult, trace

from flow_xray.debugger import GraphDebugger, TwoStepDebugger, iter_backward_steps
from flow_xray.export_dot import value_graph_to_dot, write_dot
from flow_xray.export_html import standalone_viewer_html, write_standalone_viewer_html
from flow_xray.ir import graph_to_ir, ir_to_json
from flow_xray.value import Value, backward_from, topological_order, zero_grad

__all__ = [
    # execution tracing (primary)
    "trace",
    "TraceNode",
    "TraceResult",
    # scalar autodiff
    "Value",
    "backward_from",
    "topological_order",
    "zero_grad",
    "value_graph_to_dot",
    "write_dot",
    "standalone_viewer_html",
    "write_standalone_viewer_html",
    "TwoStepDebugger",
    "GraphDebugger",
    "iter_backward_steps",
    "graph_to_ir",
    "ir_to_json",
]

__version__ = "0.3.0"
