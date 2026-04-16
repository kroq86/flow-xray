"""DOT export adapter — inspection layer; does not mutate the graph."""

from __future__ import annotations

from flow_xray.value import Value, topological_order


def _dot_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def value_graph_to_dot(root: Value, *, show_grad: bool = False) -> str:
    """
    Emit Graphviz DOT for the DAG rooted at ``root``.

    Node DOT ids use ``Value.node_id`` (stable for object lifetime).
    """
    nodes = topological_order(root)
    lines = [
        "digraph G {",
        '  rankdir="BT";',
        "  node [shape=box, fontname=Helvetica];",
        "  edge [fontname=Helvetica, fontsize=10];",
    ]
    for v in nodes:
        nid = v.node_id
        title = _dot_escape(v.display_name)
        parts = [title]
        if v._op:
            parts.append(f"op: {_dot_escape(v._op)}")
        parts.append(f"data: {v.data:g}")
        if show_grad:
            parts.append(f"grad: {v.grad:g}")
        label = "\\n".join(parts)
        lines.append(f'  {nid} [label="{label}"];')

    for v in nodes:
        child_id = v.node_id
        for p in v._prev:
            pid = p.node_id
            op_lbl = _dot_escape(v._op or "")
            lines.append(f'  {pid} -> {child_id} [label="{op_lbl}"];')

    lines.append("}")
    return "\n".join(lines)


def write_dot(path: str, dot: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(dot)
