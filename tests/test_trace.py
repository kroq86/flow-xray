import json
import asyncio

from flow_xray import TraceResult, trace


def test_trace_captures_flat_calls() -> None:
    @trace
    def step_a(x: int) -> int:
        return x + 1

    @trace
    def step_b(x: int) -> int:
        return x * 2

    @trace
    def pipeline(x: int) -> int:
        a = step_a(x)
        return step_b(a)

    result = trace.run(pipeline, 5)
    assert result.return_value == 12
    assert len(result.roots) == 1
    root = result.roots[0]
    assert root.name == "test_trace_captures_flat_calls.<locals>.pipeline"
    assert len(root.children) == 2
    assert root.children[0].name.endswith("step_a")
    assert root.children[1].name.endswith("step_b")


def test_trace_captures_nested_calls() -> None:
    @trace
    def inner() -> str:
        return "hi"

    @trace
    def outer() -> str:
        return inner()

    result = trace.run(outer)
    root = result.roots[0]
    assert len(root.children) == 1
    child = root.children[0]
    assert child.name.endswith("inner")
    assert child.output == "hi"


def test_trace_captures_error() -> None:
    @trace
    def bad() -> None:
        raise ValueError("boom")

    @trace
    def run() -> None:
        try:
            bad()
        except ValueError:
            pass

    result = trace.run(run)
    assert result.roots[0].children[0].error == "ValueError: boom"


def test_trace_latency_positive() -> None:
    import time

    @trace
    def slow() -> None:
        time.sleep(0.01)

    result = trace.run(slow)
    assert result.roots[0].latency_ms > 5


def test_trace_result_to_dict() -> None:
    @trace
    def fn(a: int) -> int:
        return a

    result = trace.run(fn, 42)
    d = result.to_dict()
    assert "nodes" in d
    assert d["nodes"][0]["name"].endswith("fn")


def test_trace_result_to_json_roundtrip() -> None:
    @trace
    def fn() -> str:
        return "ok"

    result = trace.run(fn)
    parsed = json.loads(result.to_json())
    assert parsed["nodes"][0]["output"] == '"ok"'


def test_trace_result_to_html(tmp_path) -> None:
    @trace
    def fn() -> str:
        return "ok"

    result = trace.run(fn)
    p = tmp_path / "t.html"
    result.to_html(str(p))
    html = p.read_text(encoding="utf-8")
    assert "digraph G" not in html or "__TRACE_JSON__" not in html
    assert "flow-xray trace" in html


def test_trace_no_session_passthrough() -> None:
    @trace
    def fn(x: int) -> int:
        return x + 1

    assert fn(10) == 11


def test_trace_run_exception_still_captures() -> None:
    @trace
    def crash() -> None:
        raise RuntimeError("oops")

    result = trace.run(crash)
    assert result.return_value is None
    assert len(result.roots) == 1
    assert result.roots[0].error is not None


def test_trace_run_exposes_exception_object() -> None:
    @trace
    def crash() -> None:
        raise RuntimeError("oops")

    result = trace.run(crash)
    assert isinstance(result.error, RuntimeError)
    assert str(result.error) == "oops"


def test_trace_run_can_reraise_exceptions() -> None:
    @trace
    def crash() -> None:
        raise RuntimeError("oops")

    try:
        trace.run(crash, raise_exceptions=True)
    except RuntimeError as exc:
        assert str(exc) == "oops"
    else:
        raise AssertionError("expected RuntimeError")


def test_trace_async_nested_calls() -> None:
    @trace
    async def child(x: int) -> int:
        await asyncio.sleep(0)
        return x + 1

    @trace
    async def parent(x: int) -> int:
        return await child(x)

    result = trace.run(lambda: asyncio.run(parent(4)))
    root = result.roots[0]
    assert root.name.endswith("<locals>.parent")
    assert len(root.children) == 1
    assert root.children[0].name.endswith("<locals>.child")
    assert root.children[0].output == 5


def test_trace_async_gather_keeps_sibling_structure() -> None:
    @trace
    async def child(label: str, delay: float) -> str:
        await asyncio.sleep(delay)
        return label

    @trace
    async def parent() -> list[str]:
        return await asyncio.gather(
            child("a", 0.01),
            child("b", 0.0),
        )

    result = trace.run(lambda: asyncio.run(parent()))
    root = result.roots[0]
    assert len(root.children) == 2
    assert all(child.name.endswith("<locals>.child") for child in root.children)
    assert [child.output for child in root.children] == ["a", "b"]
    assert all(not child.children for child in root.children)


# ---------------------------------------------------------------------------
# Token / cost meta
# ---------------------------------------------------------------------------


class _FakeUsage:
    def __init__(self, prompt: int, completion: int, total: int):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total


class _FakeResponse:
    def __init__(self, model: str, prompt: int, completion: int):
        self.model = model
        self.usage = _FakeUsage(prompt, completion, prompt + completion)


def test_trace_auto_extracts_openai_meta() -> None:
    @trace
    def llm_call():
        return _FakeResponse("gpt-4o-mini", prompt=100, completion=50)

    result = trace.run(llm_call)
    meta = result.roots[0].meta
    assert meta["prompt_tokens"] == 100
    assert meta["completion_tokens"] == 50
    assert meta["total_tokens"] == 150
    assert meta["model"] == "gpt-4o-mini"
    assert meta["estimated_cost_usd"] > 0


def test_trace_meta_manual() -> None:
    @trace
    def step():
        trace.meta(custom_key="hello", tokens=42)
        return "done"

    result = trace.run(step)
    meta = result.roots[0].meta
    assert meta["custom_key"] == "hello"
    assert meta["tokens"] == 42


def test_trace_meta_in_dict_output() -> None:
    @trace
    def llm():
        return _FakeResponse("gpt-4o", prompt=200, completion=100)

    result = trace.run(llm)
    d = result.to_dict()
    node = d["nodes"][0]
    assert "meta" in node
    assert node["meta"]["total_tokens"] == 300


def test_trace_meta_cost_known_model() -> None:
    @trace
    def call():
        return _FakeResponse("gpt-4o", prompt=1_000_000, completion=1_000_000)

    result = trace.run(call)
    meta = result.roots[0].meta
    assert meta["estimated_cost_usd"] == 12.50


def test_trace_meta_no_meta_when_plain_return() -> None:
    @trace
    def plain():
        return 42

    result = trace.run(plain)
    assert result.roots[0].meta == {}
    d = result.to_dict()
    assert "meta" not in d["nodes"][0]


def test_trace_meta_no_crash_on_error() -> None:
    @trace
    def fail():
        raise ValueError("boom")

    result = trace.run(fail)
    assert result.roots[0].meta == {}


def test_trace_meta_manual_computes_cost() -> None:
    @trace
    def step():
        trace.meta(model="gpt-4o", prompt_tokens=1000, completion_tokens=500)
        return "ok"

    result = trace.run(step)
    meta = result.roots[0].meta
    assert meta["estimated_cost_usd"] == round((1000 * 2.50 + 500 * 10.00) / 1_000_000, 6)


class _ZeroTokenUsage:
    def __init__(self):
        self.prompt_tokens = 0
        self.completion_tokens = 5
        self.total_tokens = 5


class _ZeroPromptResponse:
    def __init__(self):
        self.model = "gpt-4o-mini"
        self.usage = _ZeroTokenUsage()


def test_trace_meta_keeps_zero_token_values() -> None:
    @trace
    def llm():
        return _ZeroPromptResponse()

    result = trace.run(llm)
    meta = result.roots[0].meta
    assert meta["prompt_tokens"] == 0
    assert meta["completion_tokens"] == 5
    assert meta["total_tokens"] == 5
