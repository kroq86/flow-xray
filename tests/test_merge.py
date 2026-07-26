import importlib.util
import sys
from pathlib import Path

from flow_xray.merge import merge_trace_with_static
from flow_xray.static_index import FuncDef, StaticIndex, build_index
from flow_xray.trace import trace


def _static_index(functions: list[str], calls: list[tuple[str, str]]) -> StaticIndex:
    """Hand-built index — full control over deliberate mismatches with the
    runtime trace, independent of what a real file would produce."""
    index = StaticIndex()
    for i, name in enumerate(functions):
        index.functions[name] = FuncDef(qualname=name, name=name, file="mod.py", lineno=i + 1)
    index.calls = set(calls)
    return index


def test_runtime_edge_confirmed_by_static_is_both() -> None:
    @trace
    def b():
        return 1

    @trace
    def a():
        return b()

    result = trace.run(a)
    a_name, b_name = result.roots[0].name, result.roots[0].children[0].name
    merged = merge_trace_with_static(result, _static_index([a_name, b_name], [(a_name, b_name)]))

    edge = merged.edges[(a_name, b_name)]
    assert edge.runtime is True
    assert edge.static is True
    assert edge.status == "both"
    assert merged.nodes[a_name].status == "executed"
    assert merged.nodes[b_name].status == "executed"


def test_runtime_edge_missing_from_static_is_runtime_only() -> None:
    """E.g. a call the ast pass couldn't see — dynamic dispatch, monkey-patching."""

    @trace
    def b():
        return 1

    @trace
    def a():
        return b()

    result = trace.run(a)
    a_name, b_name = result.roots[0].name, result.roots[0].children[0].name
    merged = merge_trace_with_static(result, _static_index([a_name, b_name], []))

    edge = merged.edges[(a_name, b_name)]
    assert edge.runtime is True
    assert edge.static is False
    assert edge.status == "runtime-only"


def test_static_edge_not_executed_is_static_only() -> None:
    """A statically-possible branch (choose_tool -> call_email) that this run didn't take."""

    @trace
    def choose_tool():
        return call_database()

    @trace
    def call_database():
        return "db"

    result = trace.run(choose_tool)
    tool_name = result.roots[0].name
    db_name = result.roots[0].children[0].name
    email_name = f"{tool_name.rsplit('.', 1)[0]}.call_email"
    static = _static_index(
        [tool_name, db_name, email_name],
        [(tool_name, db_name), (tool_name, email_name)],
    )
    merged = merge_trace_with_static(result, static)

    assert merged.edges[(tool_name, db_name)].status == "both"

    not_taken = merged.edges[(tool_name, email_name)]
    assert not_taken.runtime is False
    assert not_taken.static is True
    assert not_taken.status == "static-only"

    node = merged.nodes[email_name]
    assert node.executed is False
    assert node.static is True
    assert node.status == "reachable-but-not-executed"


def test_executed_function_missing_from_static_index() -> None:
    """The indexer never resolved this def (e.g. built dynamically) — still surfaces as executed."""

    @trace
    def mystery():
        return 1

    result = trace.run(mystery)
    mystery_name = result.roots[0].name
    merged = merge_trace_with_static(result, _static_index([], []))

    node = merged.nodes[mystery_name]
    assert node.executed is True
    assert node.static is False
    assert node.status == "executed"


def test_static_function_never_executed() -> None:
    @trace
    def a():
        return 1

    result = trace.run(a)
    a_name = result.roots[0].name
    merged = merge_trace_with_static(result, _static_index([a_name, "unused_elsewhere"], []))

    node = merged.nodes["unused_elsewhere"]
    assert node.executed is False
    assert node.static is True
    assert node.status == "reachable-but-not-executed"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_traced_qualname_matches_static_index_qualname(tmp_path: Path) -> None:
    """Confirms, against a real file, that TraceNode.name (fn.__qualname__)
    and StaticIndex qualnames actually agree — not assumed, since a
    decorator without functools.wraps or a hand-set label would break it."""
    src = """
from flow_xray.trace import trace


class Agent:
    @trace
    def plan(self):
        return self.choose_tool()

    @trace
    def choose_tool(self):
        return "search"
"""
    path = tmp_path / "agent_mod.py"
    path.write_text(src)
    mod = _load_module(path, "flow_xray_test_agent_mod")

    result = trace.run(mod.Agent().plan)
    executed_names: set[str] = set()

    def walk(node) -> None:
        executed_names.add(node.name)
        for child in node.children:
            walk(child)

    for root in result.roots:
        walk(root)

    assert executed_names == {"Agent.plan", "Agent.choose_tool"}

    index = build_index([path])
    assert executed_names <= set(index.functions)

    merged = merge_trace_with_static(result, index)
    assert merged.nodes["Agent.plan"].status == "executed"
    assert merged.edges[("Agent.plan", "Agent.choose_tool")].status == "both"
