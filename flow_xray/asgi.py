"""
ASGI middleware: a flow-xray capture for every HTTP request.

    from flow_xray.asgi import TraceMiddleware
    from flow_xray.store import TraceStore

    app.add_middleware(TraceMiddleware, store=TraceStore("traces"))

- The capture stays open until the LAST byte of the response is sent, so a
  streamed response (SSE) records the work done while streaming. (Starlette's
  BaseHTTPMiddleware returns before a streamed body ends.)
- Trace id: the caller's ``X-Request-ID`` when it is well-formed, otherwise a
  new one. Responses carry ``X-Trace-Id`` and, with ``view_url``, a header
  pointing at where the trace can be viewed.
- The root node of every tree is ``http_request(method, path)``, so endpoints
  without @trace still get a trace.
- ``context``: optional ``request -> context manager`` entered around the
  request (e.g. to bind the trace id into your own logging); ``request`` is
  ``{"trace_id", "method", "path"}``.
- ``on_response``: optional ``request -> None`` called when the response is
  complete, with ``status`` and ``duration_ms`` added (access logs, metrics).
"""

from __future__ import annotations

import re
import time
import uuid
from contextlib import nullcontext
from typing import Any, Callable, ContextManager, Iterable

from flow_xray.store import TraceStore
from flow_xray.trace import trace

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


@trace
async def http_request(method: str, path: str, call: Callable) -> None:
    await call()


class TraceMiddleware:
    def __init__(
        self,
        app: Any,
        store: TraceStore,
        *,
        skip_paths: Iterable[str] = ("/healthz", "/readyz", "/metrics", "/favicon.ico"),
        skip_prefixes: Iterable[str] = (),
        request_id_header: str = "x-request-id",
        view_url: str | None = None,
        context: Callable[[dict], ContextManager] | None = None,
        on_response: Callable[[dict], None] | None = None,
    ) -> None:
        self.app = app
        self.store = store
        self.skip_paths = set(skip_paths)
        self.skip_prefixes = tuple(skip_prefixes)
        self.request_id_header = request_id_header.lower().encode()
        self.view_url = view_url  # e.g. "/admin/traces/{trace_id}"
        self.context = context
        self.on_response = on_response

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = ""
        for key, value in scope.get("headers", []):
            if key.lower() == self.request_id_header:
                incoming = value.decode("latin-1")
                break
        trace_id = incoming if _REQUEST_ID.match(incoming) else str(uuid.uuid4())
        method, path = scope["method"], scope["path"]
        request = {"trace_id": trace_id, "method": method, "path": path}
        status = {"code": 500}
        start = time.perf_counter()

        async def send_with_ids(message: dict) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = list(message.get("headers", [])) + [(b"x-trace-id", trace_id.encode())]
                if self.view_url:
                    headers.append((b"x-flow-trace", self.view_url.format(trace_id=trace_id).encode()))
                message["headers"] = headers
            await send(message)

        skip = path in self.skip_paths or (self.skip_prefixes and path.startswith(self.skip_prefixes))
        capture = nullcontext({}) if skip else self.store.capture("http", f"{method} {path}", trace_id)
        with (self.context(request) if self.context else nullcontext()), capture as info:
            try:
                await http_request(method, path, lambda: self.app(scope, receive, send_with_ids))
            finally:
                info["status"] = status["code"]
                if self.on_response is not None:
                    self.on_response({**request, "status": status["code"],
                                      "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
