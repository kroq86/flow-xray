from flow_xray.export_html import standalone_viewer_html


def test_standalone_html_inlines_dot_no_fetch_path() -> None:
    dot = 'digraph G { a -> b; }'
    html = standalone_viewer_html(dot, title="t")
    assert "digraph G" in html
    assert "fetch(" not in html
    assert "const dot = " in html or '"digraph G' in html
