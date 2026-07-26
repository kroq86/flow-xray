from pathlib import Path

from flow_xray.static_index import build_index


def _index_source(tmp_path: Path, source: str, name: str = "mod.py"):
    f = tmp_path / name
    f.write_text(source)
    return build_index([f])


def test_flat_function_calls(tmp_path: Path) -> None:
    index = _index_source(
        tmp_path,
        """
def plan():
    return 1

def answer(x):
    return x

def agent():
    result = plan()
    return answer(result)
""",
    )
    assert index.callees("agent") == ["answer", "plan"]
    assert index.callers("plan") == ["agent"]
    assert index.callers("answer") == ["agent"]


def test_method_calls_use_qualname(tmp_path: Path) -> None:
    index = _index_source(
        tmp_path,
        """
class Agent:
    def plan(self):
        return self.choose_tool()

    def choose_tool(self):
        return "search"
""",
    )
    assert "Agent.plan" in index.functions
    assert "Agent.choose_tool" in index.functions
    assert index.callees("Agent.plan") == ["Agent.choose_tool"]
    assert index.callers("Agent.choose_tool") == ["Agent.plan"]


def test_nested_function_qualname_matches_runtime(tmp_path: Path) -> None:
    index = _index_source(
        tmp_path,
        """
def outer():
    def inner():
        return 1
    return inner()
""",
    )
    assert "outer.<locals>.inner" in index.functions
    assert index.callees("outer") == ["outer.<locals>.inner"]


def test_blast_radius_is_transitive(tmp_path: Path) -> None:
    index = _index_source(
        tmp_path,
        """
def a():
    return b()

def b():
    return c()

def c():
    return 1
""",
    )
    assert index.blast_radius("c") == ["a", "b"]
    assert index.blast_radius("b") == ["a"]
    assert index.blast_radius("a") == []


def test_unused_excludes_entry_points_and_called_functions(tmp_path: Path) -> None:
    index = _index_source(
        tmp_path,
        """
def helper():
    return 1

def used():
    return helper()

def main():
    return used()

def orphan():
    return 2
""",
    )
    assert index.unused() == ["orphan"]


def test_attribute_call_on_unknown_object_records_bare_name(tmp_path: Path) -> None:
    index = _index_source(
        tmp_path,
        """
def run(obj):
    return obj.execute()
""",
    )
    assert index.callees("run") == ["execute"]


def test_directory_indexing_walks_py_files_and_skips_excluded_dirs(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def foo():\n    return bar()\n")
    (tmp_path / "b.py").write_text("def bar():\n    return 1\n")
    excluded = tmp_path / "__pycache__"
    excluded.mkdir()
    (excluded / "c.py").write_text("def should_not_appear():\n    return 1\n")

    index = build_index([tmp_path])

    assert "foo" in index.functions
    assert "bar" in index.functions
    assert "should_not_appear" not in index.functions
    assert index.callers("bar") == ["foo"]


def test_syntax_error_file_is_skipped_not_raised(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def foo(:\n")
    index = build_index([tmp_path])
    assert index.functions == {}
