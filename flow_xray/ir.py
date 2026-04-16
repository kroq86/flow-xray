"""JSON-serializable graph IR — stable ids, no Python object identity in payload."""

from __future__ import annotations

import json
from typing import Any

from flow_xray.value import Value, topological_order


def graph_to_ir(root: Value, *, include_grad: bool = True) -> dict[str, Any]:
    """
    Build a normalized dict suitable for viewers, CLI, and regression tests.

    Schema version 1:
      version, root_id, nodes[{id, op, label, data, grad?, parents: [id,...]}]
    """
    nodes = topological_order(root)
    payload: dict[str, Any] = {
        "version": 1,
        "root_id": root.node_id,
        "nodes": [],
    }
    for v in nodes:
        entry: dict[str, Any] = {
            "id": v.node_id,
            "op": v._op,
            "label": v.label,
            "data": v.data,
            "parents": [p.node_id for p in v._prev],
        }
        if include_grad:
            entry["grad"] = v.grad
        payload["nodes"].append(entry)
    return payload


def ir_to_json(root: Value, *, include_grad: bool = True, indent: int | None = 2) -> str:
    return json.dumps(graph_to_ir(root, include_grad=include_grad), indent=indent)
