"""Keyed executor for per-(symbol,timeframe) serialization.

Used to guarantee in-order, non-concurrent processing for stateful handlers
while still allowing parallelism across independent keys.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Generic, TypeVar, cast

_T = TypeVar("_T")


@dataclass
class _KeyWorker:
    queue: asyncio.Queue[tuple[Callable[[], Awaitable[Any]], asyncio.Future[Any]]]
    task: asyncio.Task[None]
    last_used_at: datetime


class KeyedExecutor:
    """Execute submitted coroutines sequentially per key (FIFO)."""

    def __init__(
        self,
        *,
        idle_ttl: timedelta = timedelta(minutes=10),
        max_queue_size_per_key: int = 10_000,
    ) -> None:
        if max_queue_size_per_key <= 0:
            raise ValueError("max_queue_size_per_key must be positive")
        self._idle_ttl = idle_ttl
        self._max_queue_size_per_key = max_queue_size_per_key
        self._workers: dict[str, _KeyWorker] = {}
        self._lock = asyncio.Lock()

    async def run(self, key: str, fn: Callable[[], Awaitable[_T]]) -> _T:
        """Run `fn` under the key's serialized executor."""
        if not key:
            raise ValueError("key must be non-empty")

        worker = await self._get_or_create_worker(key)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()

        try:
            worker.queue.put_nowait((fn, fut))
        except asyncio.QueueFull as exc:  # pragma: no cover
            raise RuntimeError(f"Key queue full for {key}") from exc

        worker.last_used_at = datetime.now(UTC)
        return cast(_T, await fut)

    async def _get_or_create_worker(self, key: str) -> _KeyWorker:
        async with self._lock:
            existing = self._workers.get(key)
            if existing is not None and not existing.task.done():
                return existing

            queue: asyncio.Queue[tuple[Callable[[], Awaitable[Any]], asyncio.Future[Any]]] = (
                asyncio.Queue(maxsize=self._max_queue_size_per_key)
            )

            task = asyncio.create_task(self._worker_loop(key, queue))
            worker = _KeyWorker(
                queue=queue,
                task=task,
                last_used_at=datetime.now(UTC),
            )
            self._workers[key] = worker
            return worker

    async def _worker_loop(
        self,
        key: str,
        queue: asyncio.Queue[tuple[Callable[[], Awaitable[Any]], asyncio.Future[Any]]],
    ) -> None:
        while True:
            try:
                fn, fut = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                await self._maybe_cleanup_idle_worker(key)
                continue

            try:
                result = await fn()
                if not fut.done():
                    fut.set_result(result)
            except Exception as exc:
                if not fut.done():
                    fut.set_exception(exc)
            finally:
                queue.task_done()

    async def _maybe_cleanup_idle_worker(self, key: str) -> None:
        async with self._lock:
            worker = self._workers.get(key)
            if worker is None:
                return
            if not worker.queue.empty():
                return
            idle_for = datetime.now(UTC) - worker.last_used_at
            if idle_for < self._idle_ttl:
                return

            worker.task.cancel()
            self._workers.pop(key, None)
