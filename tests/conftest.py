import pytest


@pytest.fixture(autouse=True)
def reset_value_node_counter() -> None:
    """Deterministic ``node_id`` (v0, v1, …) at the start of each test."""
    from flow_xray.value import Value

    Value._next_seq = 0
    yield
