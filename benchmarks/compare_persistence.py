"""Compare old save() and new asave() using one real captured TraceResult.

python benchmarks/compare_persistence.py NEW_SOURCE BASELINE_SOURCE
Both source trees are local; no target application or network is used.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from flow_xray import TraceStore, trace

trace.configure(max_value_chars=100_000)
spec = importlib.util.spec_from_file_location("legacy_store", Path(sys.argv[2]) / "flow_xray/store.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)

@trace(kind="tool")
def query(prompt):
    trace.meta(model="fixture", total_tokens=23)
    return {"rows": [prompt]}

@trace
def pipeline(prompt):
    return {"answer": query(prompt)}

captured = trace.run(pipeline, "same captured prompt and tool data " * 1000 + " pii@example.com")
redact = lambda value: value.replace("pii@example.com", "[REDACTED:email]")
with tempfile.TemporaryDirectory() as tmp:
    old = legacy.TraceStore(Path(tmp) / "old", redact=redact)
    new = TraceStore(Path(tmp) / "new", redact=redact)
    before = old.save(captured, kind="http", name="fixed", trace_id="legacy-byte-parity", tenant="acme")
    after = asyncio.run(new.asave(captured, kind="http", name="fixed", trace_id="legacy-byte-parity", tenant="acme"))
    files = {}
    for extension in (".json", ".html"):
        old_bytes = (old.root / before["path"]).with_suffix(extension).read_bytes()
        new_bytes = (new.root / after["path"]).with_suffix(extension).read_bytes()
        assert old_bytes == new_bytes
        files[extension] = {"bytes": len(new_bytes), "equal": True}
    print(json.dumps({"same_captured_TraceResult": True, "files": files}, indent=2))
