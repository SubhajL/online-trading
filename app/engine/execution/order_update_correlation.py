from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class OrderUpdateCorrelation:
    client_order_id: str
    metadata: dict[str, Any]
    created_at: datetime


class OrderUpdateCorrelationStore:
    def __init__(self, *, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()
        self._by_client_order_id: dict[str, OrderUpdateCorrelation] = {}

    async def register(self, *, client_order_id: str, metadata: dict[str, Any]) -> None:
        if not client_order_id:
            raise ValueError("client_order_id is required")
        now = datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        async with self._lock:
            self._prune_locked(now)
            self._by_client_order_id[client_order_id] = OrderUpdateCorrelation(
                client_order_id=client_order_id,
                metadata=metadata,
                created_at=now,
            )

    async def get(self, *, client_order_id: str) -> OrderUpdateCorrelation | None:
        if not client_order_id:
            return None
        now = datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        async with self._lock:
            self._prune_locked(now)
            return self._by_client_order_id.get(client_order_id)

    async def delete(self, *, client_order_id: str) -> None:
        if not client_order_id:
            return
        async with self._lock:
            self._by_client_order_id.pop(client_order_id, None)

    def _prune_locked(self, now: datetime) -> None:
        cutoff = now - self._ttl
        expired = [k for k, v in self._by_client_order_id.items() if v.created_at < cutoff]
        for k in expired:
            self._by_client_order_id.pop(k, None)
