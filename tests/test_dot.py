from flow_xray import Value, value_graph_to_dot


def test_dot_uses_node_id_not_python_id() -> None:
    a = Value(1.0, label="a")
    b = Value(2.0, label="b")
    y = a * b
    dot = value_graph_to_dot(y, show_grad=False)
    assert "v0" in dot and "v1" in dot and "v2" in dot
    assert f"n{id(y)}" not in dot


def test_dot_deterministic_across_runs_reset_by_fixture() -> None:
    a = Value(1.0, label="a")
    b = Value(2.0, label="b")
    y = a * b
    d1 = value_graph_to_dot(y, show_grad=False)
    assert '\n  v0 [' in d1
    assert "v0 ->" in d1
