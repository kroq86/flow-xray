"""Awaited trace writes on a dedicated, bounded worker pool.

There is no detached writer queue: each caller awaits its own write. The
semaphore keeps submissions to the executor bounded on each event loop.
Python joins executor threads at normal interpreter exit; servers should
first drain their request/capture tasks before stopping the event loop.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import threading
from typing import Any, Callable
import weakref

_WORKERS = 2
_POOL = ThreadPoolExecutor(max_workers=_WORKERS, thread_name_prefix="flow-xray-save")
_LOCK = threading.Lock()
# Weak values avoid retaining a closed loop through Semaphore._loop.
_LIMITS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _limit() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    with _LOCK:
        reference = _LIMITS.get(loop)
        limit = reference() if reference else None
        if limit is None:
            limit = asyncio.Semaphore(_WORKERS)
            _LIMITS[loop] = weakref.ref(limit)
        return limit


async def run_save(function: Callable[[], Any], on_error: Callable[[], None]) -> Any:
    """Finish an admitted save even if its caller is cancelled, then re-raise.

    Shield the capacity wait as well as the disk write. This also handles a
    second cancellation while the first cancellation is being drained.
    """
    async def execute() -> Any:
        try:
            async with _limit():
                return await asyncio.get_running_loop().run_in_executor(_POOL, copy_context().run, function)
        except Exception:
            # Count unexpected worker/submission errors before cancellation
            # is propagated to the caller, preserving both outcomes.
            on_error()
            return None

    operation = asyncio.create_task(execute())
    cancellation: asyncio.CancelledError | None = None
    while True:
        try:
            result = await asyncio.shield(operation)
            break
        except asyncio.CancelledError as exc:
            if operation.cancelled():
                raise  # Event-loop shutdown cancelled the write task itself.
            cancellation = exc
    if cancellation is not None:
        raise cancellation
    return result
