import json

from flow_xray import Value, graph_to_ir, ir_to_json


def test_graph_to_ir_schema() -> None:
    a = Value(1.0, label="a")
    b = Value(2.0, label="b")
    y = a * b
    y.backward()
    ir = graph_to_ir(y, include_grad=True)
    assert ir["version"] == 1
    assert ir["root_id"] == y.node_id
    ids = {n["id"] for n in ir["nodes"]}
    assert y.node_id in ids
    for n in ir["nodes"]:
        assert "data" in n and "grad" in n and "parents" in n
    json.loads(ir_to_json(y))
