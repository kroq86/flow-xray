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


def test_all_nodes_strict_threshold_and_unique_call_identity():
    from flow_xray.analyze import latency_profile
    leaves = [TraceNode('same', 'at-limit', {}, start_ms=1, latency_ms=50),
              TraceNode('same', 'above', {}, start_ms=2, latency_ms=50.001),
              TraceNode('model', 'model', {}, start_ms=3, latency_ms=51, kind='llm'),
              TraceNode('failure', 'error', {}, start_ms=4, latency_ms=2, error='failed')]
    root = TraceNode('request', 'root', {}, start_ms=0, latency_ms=100, children=leaves)
    tree = TraceResult([root])
    before = tree.to_json()
    issues = analyze(tree, slow_ms=50, slow_all_nodes=True)
    slow = [i for i in issues if i['kind'] == 'slow_node']
    assert {i['node_id'] for i in slow} == {'root', 'above', 'model'}
    assert all(i['threshold_ms'] == 50 and i['severity'] == 'warning' for i in slow)
    profile = latency_profile(tree)
    assert profile['at-limit']['level'] == 'ok'
    assert profile['above']['level'] == 'warning'
    assert profile['model']['level'] == 'warning'  # no implicit LLM exemption
    assert profile['error']['level'] == 'error'
    assert tree.to_json() == before
    assert not [i for i in analyze(tree) if i['kind'] == 'slow_node']


def test_self_wall_time_merges_parallel_children_and_clips_to_parent():
    from flow_xray.analyze import self_time_ms
    children = [TraceNode('a', 'a', {}, start_ms=10, latency_ms=70),
                TraceNode('b', 'b', {}, start_ms=40, latency_ms=50)]
    root = TraceNode('request', 'root', {}, start_ms=0, latency_ms=100, children=children)
    assert self_time_ms(root) == 20  # union [10,90], not sum 70+50
    children += [TraceNode('early', 'early', {}, start_ms=-20, latency_ms=25),
                 TraceNode('late', 'late', {}, start_ms=98, latency_ms=20)]
    assert self_time_ms(root) == 13
    assert self_time_ms(TraceNode('gap', 'gap', {}, latency_ms=61)) == 61


def test_store_uses_same_threshold_for_scan_and_viewer(tmp_path):
    import json, re
    tree = TraceResult([TraceNode('request', 'r', {}, start_ms=10, latency_ms=80,
                                 children=[TraceNode('leaf', 'c', {}, start_ms=20, latency_ms=60)])])
    store = TraceStore(tmp_path, slow_ms=50, slow_all_nodes=True)
    before = tree.to_json()
    row = store.save(tree, kind='http', name='request')
    assert {i['node_id'] for i in row['issues'] if i['kind']=='slow_node'} == {'r', 'c'}
    text = (store.root / row['path']).read_text()
    profile = json.loads(re.search(r'const LATENCY=(.*);', text)[1])
    assert profile['r']['level'] == profile['c']['level'] == 'warning'
    assert profile['r']['self_ms'] == 20
    assert profile['r']['threshold_ms'] == profile['c']['threshold_ms'] == 50
    assert (store.root / row['path']).with_suffix('.json').read_text() == before


def test_dot_traffic_light_uses_unrounded_node_latency():
    node = TraceNode('work', 'r', {}, latency_ms=50.001)
    text = TraceResult([node]).to_dot()
    assert 'fillcolor="#d29922"' in text
    node.latency_ms = 50
    assert 'fillcolor="#238636"' in TraceResult([node]).to_dot()


def test_real_async_wait_is_flagged_without_classifying_it_as_blocking(tmp_path):
    import asyncio
    from flow_xray import trace
    store = TraceStore(tmp_path, slow_ms=50, slow_all_nodes=True)
    async def go():
        entered, release = asyncio.Event(), asyncio.Event()
        progress = []
        @trace
        async def wait_point():
            entered.set()
            await release.wait()
            return 'complete'
        @trace
        async def request():
            return await wait_point()
        async def observer():
            await asyncio.wait_for(entered.wait(), 2)
            progress.append('another task ran while the node waited')
            await asyncio.sleep(.06)
            release.set()
        observing = asyncio.create_task(observer())
        async with store.acapture('job', 'wait'):
            assert await asyncio.wait_for(request(), 2) == 'complete'
        await observing
        assert progress
    asyncio.run(go())
    row, = store.entries()
    slow = [i for i in row['issues'] if i['kind'] == 'slow_node']
    assert len(slow) == 2
    assert all(i['elapsed_ms'] > 50 and i['threshold_ms'] == 50 for i in slow)
    assert all(i['severity'] == 'warning' for i in slow)


def test_rounding_cannot_hide_an_above_threshold_node():
    from flow_xray.analyze import latency_profile
    tree = TraceResult([TraceNode('work', 'r', {}, latency_ms=50.0001)])
    profile = latency_profile(tree)['r']
    assert profile['elapsed_ms'] == 50
    assert profile['above_threshold'] is True
    assert profile['level'] == 'warning'
