from flow_xray.export_html import standalone_viewer_html, trace_to_standalone_html
from flow_xray import trace


def test_standalone_html_inlines_dot_no_fetch_path() -> None:
    dot = 'digraph G { a -> b; }'
    html = standalone_viewer_html(dot, title="t")
    assert "digraph G" in html
    assert "fetch(" not in html
    assert "const dot = " in html or '"digraph G' in html


def test_trace_html_uses_flattened_total_latency() -> None:
    @trace
    def child() -> int:
        return 1

    @trace
    def parent() -> int:
        return child()

    result = trace.run(parent)
    viewer_html = trace_to_standalone_html(result)
    assert "const total=nodes.reduce((s,n)=>s+n.latency_ms,0);" in viewer_html
    assert "offline or blocked CDN access" in viewer_html
    assert 'id="search"' in viewer_html
    assert 'id="copydet"' in viewer_html
    assert 'id="mode-overview"' in viewer_html
    assert 'id="mode-timeline"' in viewer_html
    assert 'id="mode-raw"' in viewer_html
    assert 'id="rawfilter"' in viewer_html
    assert 'id="rawtrace"' in viewer_html
    assert "renderOverview()" in viewer_html
    assert "renderTimeline()" in viewer_html
    assert "renderRaw()" in viewer_html
    assert "Raw Node JSON" in viewer_html
    assert "bindToolbar()" in viewer_html
    assert "navigator.clipboard.writeText" in viewer_html
