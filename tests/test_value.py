import math

import pytest

from flow_xray import Value, backward_from, zero_grad


def test_forward_mul_add() -> None:
    a = Value(2.0, label="a")
    b = Value(-3.0, label="b")
    c = Value(10.0, label="c")
    y = (a * b) + c
    assert y.data == pytest.approx(4.0)


def test_backward_tanh_chain() -> None:
    a = Value(2.0, label="a")
    b = Value(-3.0, label="b")
    c = Value(10.0, label="c")
    L = ((a * b) + c).relu().tanh()
    L.backward()
    t = math.tanh(4.0)
    d_tanh = 1.0 - t * t
    assert L.grad == pytest.approx(1.0)
    assert c.grad == pytest.approx(d_tanh)
    assert a.grad == pytest.approx(d_tanh * b.data)


def test_zero_grad_then_backward_idempotent() -> None:
    x = Value(3.0, label="x")
    y = x * x
    y.backward()
    g1 = x.grad
    zero_grad(y)
    y.backward()
    g2 = x.grad
    assert g1 == pytest.approx(6.0)
    assert g2 == pytest.approx(6.0)


def test_backward_accumulates_without_zero() -> None:
    x = Value(2.0)
    y = x * x
    y.backward()
    first = x.grad
    y.backward()
    assert x.grad == pytest.approx(2 * first)


def test_relu_positive_and_zero_input_grad() -> None:
    x = Value(1.0)
    y = x.relu()
    y.backward()
    assert x.grad == pytest.approx(1.0)

    z = Value(0.0)
    u = z.relu()
    u.backward()
    assert z.grad == pytest.approx(0.0)


def test_finite_diff_mul_tanh() -> None:
    h = 1e-5
    x0 = 0.7

    def loss_at(val: float) -> float:
        a = Value(val, label="a")
        b = Value(1.2, label="b")
        L = (a * b).tanh()
        return L.data

    a0 = Value(x0, label="a")
    b0 = Value(1.2, label="b")
    L0 = (a0 * b0).tanh()
    L0.backward()
    g = a0.grad
    g_num = (loss_at(x0 + h) - loss_at(x0 - h)) / (2 * h)
    assert g == pytest.approx(g_num, rel=1e-3, abs=1e-5)


def test_backward_from_custom_seed() -> None:
    x = Value(2.0)
    y = x * x
    backward_from(y, seed=2.0, zero_first=True)
    assert x.grad == pytest.approx(8.0)
