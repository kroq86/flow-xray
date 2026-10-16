"""Persistence contracts: full trees, byte parity, cancellation, ASGI and faults."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

import pytest

from flow_xray import TraceNode, TraceResult, TraceStore, annotate, trace
from flow_xray.asgi import TraceMiddleware


def result(value="details"):
    leaf = TraceNode("tool", "leaf", {"query": value}, output={"rows": [value]},
                     start_ms=105, latency_ms=3, meta={"tenant": "acme"}, kind="tool", tags={"source": "fixture"})
    root = TraceNode("request", "root", {"question": value}, output={"answer": value},
                     start_ms=100, latency_ms=10, children=[leaf])
    return TraceResult([root], t0=100)


def json_tree(store, row):
    return json.loads((store.root / row["path"]).with_suffix(".json").read_text())


async def event_set(event):
    for _ in range(500):
        if event.is_set():
            return
        await asyncio.sleep(.002)
    raise AssertionError("worker did not reach the synchronization point")


def test_same_result_has_byte_identical_sync_and_async_files(tmp_path, monkeypatch):
    import importlib
    trace_module = importlib.import_module("flow_xray.trace")
    monkeypatch.setitem(trace_module._settings, "max_value_chars", 100_000)
    detailed = result("complete detail " * 2000 + " secret@example.com")
    redact = lambda text: text.replace("secret@example.com", "[REDACTED:email]")
    sync = TraceStore(tmp_path / "sync", redact=redact)
    asynchronous = TraceStore(tmp_path / "async", redact=redact)
    before = detailed.to_json()
    old = sync.save(detailed, kind="http", name="request", trace_id="same-result", tenant="acme")
    new = asyncio.run(asynchronous.asave(detailed, kind="http", name="request", trace_id="same-result", tenant="acme"))
    assert old and new
    for extension in (".json", ".html"):
        old_bytes = (sync.root / old["path"]).with_suffix(extension).read_bytes()
        new_bytes = (asynchronous.root / new["path"]).with_suffix(extension).read_bytes()
        assert old_bytes == new_bytes
        assert b"secret@example.com" not in new_bytes
        assert b"complete detail" in new_bytes
    assert detailed.to_json() == before
    assert new["nodes"] == 2 and new["tenant"] == "acme"
    assert json_tree(asynchronous, new)["nodes"][0]["children"][0]["tags"] == {"source": "fixture"}


def test_nested_capture_and_annotations_share_one_complete_tree(tmp_path):
    store = TraceStore(tmp_path)

    @trace
    async def inner():
        annotate(tenant="acme")
        return {"data": [1, 2, 3]}

    @trace
    async def outer():
        with store.capture("nested", "sync"):
            async with store.acapture("nested", "async"):
                return await inner()

    async def run():
        async with store.acapture("mcp", "search", "nested-async") as info:
            assert await outer() == {"data": [1, 2, 3]}
            info["status"] = 200

    asyncio.run(run())
    rows = store.entries()
    assert len(rows) == 1 and rows[0]["tenant"] == "acme" and rows[0]["nodes"] == 2
    assert "inner" in json_tree(store, rows[0])["nodes"][0]["children"][0]["name"]


def test_no_capture_when_sampled_out_or_empty(tmp_path):
    store = TraceStore(tmp_path, sample=0)

    @trace
    def work():
        return 42

    async def run():
        async with store.acapture("job", "sampled"):
            work()
        await store.asave(TraceResult([]), kind="job", name="empty")
    asyncio.run(run())
    assert not list(tmp_path.iterdir()) and store.save_failures == 0


def test_capture_records_error_before_propagating(tmp_path):
    store = TraceStore(tmp_path)

    @trace
    async def bad():
        raise ValueError("test failure")

    async def run():
        with pytest.raises(ValueError, match="test failure"):
            async with store.acapture("job", "error"):
                await bad()
        assert len(store.entries()) == 1
    asyncio.run(run())
    assert json_tree(store, store.entries()[0])["nodes"][0]["error"] == "ValueError: test failure"


def test_async_capture_joins_an_existing_sync_capture(tmp_path):
    store = TraceStore(tmp_path)

    @trace
    async def work():
        return "joined"

    async def run():
        async with store.acapture("mcp", "nested"):
            await work()

    with store.capture("job", "outer", "sync-outer"):
        asyncio.run(run())
        assert store.entries() == []
    assert len(store.entries()) == 1 and store.entries()[0]["name"] == "outer"


def test_cancel_during_body_closes_nodes_and_saves(tmp_path):
    store = TraceStore(tmp_path)

    async def run():
        entered = asyncio.Event()

        @trace
        async def pending():
            entered.set()
            await asyncio.Event().wait()

        async def request():
            async with store.acapture("job", "cancelled", "cancel-body"):
                await pending()
        task = asyncio.create_task(request())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        row = store.entries()[0]
        node = json_tree(store, row)["nodes"][0]
        assert node["error"].startswith("CancelledError:")
        assert node["latency_ms"] > 0
        from flow_xray.trace import _TraceSession
        assert _TraceSession.current() is None
    asyncio.run(run())


def test_slow_save_does_not_block_loop_or_get_abandoned_on_repeated_cancel(tmp_path):
    entered, release = threading.Event(), threading.Event()
    writer_threads = []

    def slow_redact(text):
        writer_threads.append(threading.current_thread().name)
        entered.set()
        if not release.wait(3):
            raise TimeoutError("test failed to release disk")
        return text

    store = TraceStore(tmp_path, redact=slow_redact)

    async def run():
        task = asyncio.create_task(store.asave(result(), kind="http", name="slow"))
        try:
            await event_set(entered)
            task.cancel()
            for _ in range(5):
                await asyncio.sleep(0)
            assert not task.done()
            task.cancel()
            for _ in range(5):
                await asyncio.sleep(0)
            assert not task.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(store.entries()) == 1
    asyncio.run(run())
    assert writer_threads and all(name.startswith("flow-xray-save") for name in writer_threads)


def test_cancellation_waiting_for_pool_capacity_still_saves(tmp_path):
    both_entered, release = threading.Event(), threading.Event()
    lock = threading.Lock()
    calls = 0

    def slow_redact(text):
        nonlocal calls
        with lock:
            calls += 1
            if calls >= 2:
                both_entered.set()
        if not release.wait(3):
            raise TimeoutError("test failed to release pool")
        return text

    store = TraceStore(tmp_path, redact=slow_redact)

    async def run():
        first = [asyncio.create_task(store.asave(result(str(i)), kind="job", name=str(i))) for i in range(2)]
        third = None
        try:
            await event_set(both_entered)
            third = asyncio.create_task(store.asave(result("third"), kind="job", name="third"))
            await asyncio.sleep(0)
            third.cancel()
            await asyncio.sleep(0)
            assert not third.done()
        finally:
            release.set()
        await asyncio.gather(*first)
        with pytest.raises(asyncio.CancelledError):
            await third
        assert len(store.entries()) == 3 and store.save_failures == 0
    asyncio.run(run())


def test_cancellation_is_preserved_even_if_the_worker_also_fails(tmp_path, monkeypatch, caplog):
    entered, release = threading.Event(), threading.Event()
    store = TraceStore(tmp_path)

    def broken_write(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        raise RuntimeError("unexpected worker failure")
    monkeypatch.setattr(store, "save", broken_write)

    async def run():
        task = asyncio.create_task(store.asave(result(), kind="job", name="cancel-and-fail"))
        try:
            await event_set(entered)
            task.cancel()
            await asyncio.sleep(0)
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert store.save_failures == 1 and "unexpected worker failure" in caplog.text


def test_executor_submission_failure_is_visible(tmp_path, monkeypatch, caplog):
    from flow_xray import _async_save
    store = TraceStore(tmp_path)

    def unavailable(*args, **kwargs):
        raise RuntimeError("executor unavailable")
    monkeypatch.setattr(_async_save._POOL, "submit", unavailable)
    assert asyncio.run(store.asave(result(), kind="job", name="submission")) is None
    assert store.save_failures == 1 and "executor unavailable" in caplog.text


def test_asave_does_not_use_default_executor(tmp_path):
    class ForbiddenExecutor(ThreadPoolExecutor):
        def submit(self, *args, **kwargs):
            raise AssertionError("default executor used for trace persistence")

    async def run():
        asyncio.get_running_loop().set_default_executor(ForbiddenExecutor(max_workers=1))
        assert await TraceStore(tmp_path).asave(result(), kind="job", name="dedicated")
    asyncio.run(run())


@pytest.mark.parametrize("asynchronous", [False, True])
def test_failed_save_is_logged_and_counted_without_raising(tmp_path, caplog, asynchronous):
    root = tmp_path / "not-a-directory"
    root.write_text("blocked")
    store = TraceStore(root)
    if asynchronous:
        row = asyncio.run(store.asave(result(), kind="http", name="failed", trace_id="failure"))
    else:
        row = store.save(result(), kind="http", name="failed", trace_id="failure")
    assert row is None and store.save_failures == 1
    assert "trace_save_failed" in caplog.text
    assert "trace_save_failed_total 1\n" in store.prometheus_metrics()


def test_broken_log_handler_does_not_replace_the_captured_error(tmp_path, monkeypatch):
    import flow_xray.store as store_module
    root = tmp_path / "blocked"
    root.write_text("blocked")
    store = TraceStore(root)

    def bad_log(*args, **kwargs):
        raise RuntimeError("logging is broken")
    monkeypatch.setattr(store_module._LOGGER, "exception", bad_log)

    @trace
    async def bad():
        raise ValueError("original business error")

    async def run():
        with pytest.raises(ValueError, match="original business error"):
            async with store.acapture("job", "failed"):
                await bad()
    asyncio.run(run())
    assert store.save_failures == 1


def test_concurrent_stores_never_overwrite_same_trace_id(tmp_path):
    stores = [TraceStore(tmp_path) for _ in range(4)]

    async def run():
        return await asyncio.gather(*(stores[i % 4].asave(result(str(i)), kind="job", name=str(i),
                                                          trace_id="shared-trace") for i in range(16)))
    rows = asyncio.run(run())
    assert len(rows) == len({r["path"] for r in rows}) == 16
    assert len(stores[0].entries(limit=100)) == 16
    for i, row in enumerate(rows):
        assert json_tree(stores[0], row)["nodes"][0]["inputs"]["question"] == json.dumps(str(i))


def test_asgi_keeps_stream_open_through_last_traced_step(tmp_path):
    store = TraceStore(tmp_path)
    sent = []

    @trace
    async def stream_piece(text):
        return text.upper()

    async def app(scope, receive, send):
        annotate(tenant="acme")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        for number, text in enumerate(("first", "last")):
            await send({"type": "http.response.body", "body": (await stream_piece(text)).encode(),
                        "more_body": number == 0})

    async def send(message):
        sent.append(message)
        assert store.entries() == []  # Save happens after the last body byte.

    async def receive():
        return {"type": "http.request", "body": b""}

    middleware = TraceMiddleware(app, store, view_url="/traces/{trace_id}")
    asyncio.run(middleware({"type": "http", "method": "GET", "path": "/stream",
                            "headers": [(b"x-request-id", b"stream-123456")]}, receive, send))
    assert [m["body"] for m in sent[1:]] == [b"FIRST", b"LAST"]
    assert (b"x-trace-id", b"stream-123456") in sent[0]["headers"]
    row = store.entries()[0]
    assert row["trace_id"] == "stream-123456" and row["tenant"] == "acme" and row["status"] == 200
    children = json_tree(store, row)["nodes"][0]["children"]
    assert len(children) == 2 and children[-1]["output"] == json.dumps("LAST")


def test_asgi_write_failure_preserves_sent_response(tmp_path, caplog):
    root = tmp_path / "blocked"
    root.write_text("not a directory")
    store = TraceStore(root)
    sent = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message):
        sent.append(message)

    asyncio.run(TraceMiddleware(app, store)({"type": "http", "method": "GET", "path": "/ok"}, None, send))
    assert sent[0]["status"] == 200 and sent[-1]["body"] == b"ok"
    assert store.save_failures == 1 and "trace_save_failed" in caplog.text
