from flow_xray import GraphDebugger, TwoStepDebugger, Value, iter_backward_steps


def test_two_step_debugger() -> None:
    x = Value(2.0, label="x")
    y = x * x
    dbg = TwoStepDebugger(y)
    d0 = dbg.step_forward_dot()
    assert "grad:" not in d0
    y.backward()
    d1 = dbg.step_backward_dot()
    assert "grad:" in d1


def test_iter_backward_steps_yields_reverse_topo() -> None:
    a = Value(2.0, label="a")
    b = Value(3.0, label="b")
    y = a * b
    order = list(iter_backward_steps(y))
    assert order[0] is y
    assert set(order) == {a, b, y}


def test_named_snapshots_keys() -> None:
    a = Value(2.0, label="a")
    b = Value(3.0, label="b")
    y = a * b
    dbg = GraphDebugger(y)
    snaps = dbg.named_snapshots(include_step_dots=True)
    assert "forward" in snaps
    assert "after_backward" in snaps
    assert "backward_step_0" in snaps
    assert snaps["forward"] != snaps["after_backward"]
