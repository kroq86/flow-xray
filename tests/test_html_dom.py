"""Optional DOM checks: renderer layout is stubbed, viewer logic is executed."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from flow_xray import TraceNode, TraceResult


def test_latency_traffic_lights_and_hotspot_navigation(tmp_path):
    if not os.getenv('FLOW_XRAY_JSDOM') or not shutil.which('node'):
        pytest.skip('set FLOW_XRAY_JSDOM to an installed jsdom package')
    nodes = [TraceNode('fast', 'fast', {}, start_ms=10, latency_ms=49.99),
             TraceNode('same', 'at', {}, start_ms=20, latency_ms=50),
             TraceNode('same', 'above', {}, start_ms=30, latency_ms=50.001),
             TraceNode('model wait', 'gap', {}, start_ms=80, latency_ms=60, kind='llm'),
             TraceNode('failure', 'error', {}, start_ms=5, latency_ms=2, error='fixture error')]
    tree = TraceResult([TraceNode('request', 'root', {'input': '__LATENCY_JSON__ </script>'},
                                 start_ms=0, latency_ms=140, children=nodes)], t0=0)
    path=tmp_path/'traffic.html'
    tree.to_html(str(path), slow_ms=50)
    result=subprocess.run(['node',str(Path(__file__).with_name('check_latency_viewer.cjs')),str(path)],
                          capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
