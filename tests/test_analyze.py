from flow_xray import TraceNode, TraceResult, TraceStore
from flow_xray.analyze import analyze


def test_kind_budget_includes_parent_and_preserves_fallback():
    child = TraceNode("embedding", "e", {}, latency_ms=90, kind="embedding")
    parent = TraceNode("search", "s", {}, latency_ms=150, kind="retrieval", children=[child])
    ordinary = TraceNode("other", "o", {}, latency_ms=5100)
    tree = TraceResult([parent, ordinary])
    assert [i["node"] for i in analyze(tree)] == ["other"]
    issues = analyze(tree, slow_ms_by_kind={"retrieval": 100, "embedding": 1000})
    assert [i["node"] for i in issues] == ["search", "other"]
    assert issues[0]["threshold_ms"] == 100
    assert issues[0]["node_kind"] == "retrieval"


def test_model_metadata_and_explicit_kind_precedence():
    node = TraceNode("m", "model", {}, latency_ms=3000, meta={"model": "fixture"})
    assert not analyze([node], slow_ms_by_kind={"llm": 5000})
    assert analyze([node], slow_ms_by_kind={"llm": 2000})[0]["node_kind"] == "llm"
    node.kind = "embedding"
    assert not analyze([node], slow_ms_by_kind={"llm": 2000, "embedding": 4000})


def test_store_applies_kind_budget_without_changing_tree(tmp_path):
    tree = TraceResult([TraceNode("r", "search", {"full": "input"}, latency_ms=51, kind="retrieval")])
    original = tree.to_json()
    store = TraceStore(tmp_path, slow_ms_by_kind={"retrieval": 50})
    row = store.save(tree, kind="http", name="request")
    assert row["issues"][0]["node_kind"] == "retrieval"
    assert tree.to_json() == original
