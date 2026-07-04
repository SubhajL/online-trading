from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.engine.adapters.redis.redis_adapter import RedisAdapter

logger = logging.getLogger(__name__)

ORDER_UPDATE_CORRELATION_PREFIX = "order_update_correlation"


@dataclass(frozen=True)
class OrderUpdateCorrelation:
    client_order_id: str
    metadata: dict[str, Any]
    created_at: datetime


class OrderUpdateCorrelationStore:
    """Correlates client order ids with decision metadata for alert routing.

    In-memory state is wiped on every engine restart/reload, which silently
    drops order-update alerts (the allowlist gate needs decision_source from
    this store). When ``redis`` is provided, correlations write through to
    Redis with the same TTL and are rehydrated on memory misses; Redis errors
    fail open to the in-memory behavior, mirroring SignalCooldown.
    """

    def __init__(self, *, ttl_seconds: int, redis: RedisAdapter | None = None) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._ttl_seconds = ttl_seconds
        self._redis = redis
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

        if self._redis is not None:
            try:
                await self._redis.set(
                    client_order_id,
                    {
                        "client_order_id": client_order_id,
                        "metadata": metadata,
                        "created_at": now.isoformat(),
                    },
                    expire=self._ttl_seconds,
                    prefix=ORDER_UPDATE_CORRELATION_PREFIX,
                )
            except Exception:
                logger.warning(
                    "Redis write-through failed for order correlation %s; "
                    "correlation will not survive restart",
                    client_order_id,
                )

    async def get(self, *, client_order_id: str) -> OrderUpdateCorrelation | None:
        if not client_order_id:
            return None
        now = datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        async with self._lock:
            self._prune_locked(now)
            cached = self._by_client_order_id.get(client_order_id)
        if cached is not None:
            return cached

        if self._redis is None:
            return None
        return await self._rehydrate_from_redis(client_order_id, now)

    async def delete(self, *, client_order_id: str) -> None:
        if not client_order_id:
            return
        async with self._lock:
            self._by_client_order_id.pop(client_order_id, None)
        if self._redis is not None:
            try:
                await self._redis.delete(
                    client_order_id,
                    prefix=ORDER_UPDATE_CORRELATION_PREFIX,
                )
            except Exception:
                logger.warning(
                    "Redis delete failed for order correlation %s",
                    client_order_id,
                )

    async def _rehydrate_from_redis(
        self,
        client_order_id: str,
        now: datetime,
    ) -> OrderUpdateCorrelation | None:
        assert self._redis is not None
        try:
            raw = await self._redis.get(
                client_order_id,
                prefix=ORDER_UPDATE_CORRELATION_PREFIX,
            )
        except Exception:
            logger.warning(
                "Redis read failed for order correlation %s",
                client_order_id,
            )
            return None

        if not isinstance(raw, dict):
            return None

        metadata = raw.get("metadata")
        if not isinstance(metadata, dict):
            return None

        created_at = now
        raw_created_at = raw.get("created_at")
        if isinstance(raw_created_at, str):
            try:
                created_at = datetime.fromisoformat(raw_created_at)
            except ValueError:
                created_at = now
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)

        correlation = OrderUpdateCorrelation(
            client_order_id=client_order_id,
            metadata=metadata,
            created_at=created_at,
        )
        async with self._lock:
            self._by_client_order_id[client_order_id] = correlation
        return correlation

    def _prune_locked(self, now: datetime) -> None:
        cutoff = now - self._ttl
        expired = [k for k, v in self._by_client_order_id.items() if v.created_at < cutoff]
        for k in expired:
            self._by_client_order_id.pop(k, None)
