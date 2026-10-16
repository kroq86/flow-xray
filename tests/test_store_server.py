"""Optional real-server check; requires uvicorn and httpx (no runtime dependency)."""
import asyncio
import socket
import threading

import pytest

uvicorn = pytest.importorskip("uvicorn")
httpx = pytest.importorskip("httpx")

from flow_xray import TraceStore, trace
from flow_xray.asgi import TraceMiddleware


def test_uvicorn_sends_response_then_drains_trace_before_graceful_exit(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def slow_redact(text):
        entered.set()
        if not release.wait(5):
            raise TimeoutError("test did not release disk")
        return text

    store = TraceStore(tmp_path, redact=slow_redact)

    @trace
    async def core():
        return {"answer": "complete result", "steps": ["lookup", "calculate"]}

    async def app(scope, receive, send):
        await core()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"complete result"})

    async def run():
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(TraceMiddleware(app, store), lifespan="off", log_config=None,
                                               access_log=False, timeout_graceful_shutdown=3))
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            for _ in range(500):
                if server.started:
                    break
                if serving.done():
                    await serving
                await asyncio.sleep(.002)
            assert server.started
            async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
                response = await client.get(f"http://127.0.0.1:{port}/result")
            assert response.status_code == 200 and response.text == "complete result"
            for _ in range(500):
                if entered.is_set():
                    break
                await asyncio.sleep(.002)
            assert entered.is_set() and store.entries() == []
            server.should_exit = True
            await asyncio.sleep(.25)
            assert not serving.done(), "server exited before its trace save finished"
            release.set()
            await asyncio.wait_for(serving, 3)
            rows = store.entries()
            assert len(rows) == 1 and rows[0]["nodes"] == 2 and store.save_failures == 0
            assert "complete result" in store.html(rows[0])
        finally:
            release.set()
            server.should_exit = True
            await asyncio.wait_for(serving, 4)
            listener.close()
    asyncio.run(run())
