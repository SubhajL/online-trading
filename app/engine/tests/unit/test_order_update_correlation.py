"""Tests for OrderUpdateCorrelationStore Redis write-through persistence.

The store correlates client_order_ids with decision metadata so order-update
alerts survive the allowlist gate. In-memory state is wiped on every engine
restart/reload, so correlations must round-trip through Redis (fail-open when
Redis is unavailable), mirroring the SignalCooldown dual-backend pattern.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.engine.execution.order_update_correlation import (
    ORDER_UPDATE_CORRELATION_PREFIX,
    OrderUpdateCorrelationStore,
)

TTL_SECONDS = 21600
CLIENT_ORDER_ID = "ord-abc123"
METADATA = {"decision_source": "retest_decision_publisher", "signal_id": "sig-1"}


class FakeRedisAdapter:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.set_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []

    async def set(
        self,
        key: str,
        value: Any,
        expire: int | None = None,
        prefix: str = "cache",
    ) -> bool:
        self.set_calls.append({"key": key, "value": value, "expire": expire, "prefix": prefix})
        self.store[f"{prefix}:{key}"] = value
        return True

    async def get(self, key: str, prefix: str = "cache") -> Any | None:
        self.get_calls.append({"key": key, "prefix": prefix})
        return self.store.get(f"{prefix}:{key}")

    async def delete(self, key: str, prefix: str = "cache") -> bool:
        self.delete_calls.append({"key": key, "prefix": prefix})
        return self.store.pop(f"{prefix}:{key}", None) is not None


class RaisingRedisAdapter:
    async def set(self, *args: Any, **kwargs: Any) -> bool:
        raise ConnectionError("redis down")

    async def get(self, *args: Any, **kwargs: Any) -> Any | None:
        raise ConnectionError("redis down")

    async def delete(self, *args: Any, **kwargs: Any) -> bool:
        raise ConnectionError("redis down")


class TestOrderUpdateCorrelationRedisBackend:
    @pytest.mark.asyncio
    async def test_register_writes_through_to_redis_with_ttl(self) -> None:
        redis = FakeRedisAdapter()
        store = OrderUpdateCorrelationStore(ttl_seconds=TTL_SECONDS, redis=redis)

        await store.register(client_order_id=CLIENT_ORDER_ID, metadata=METADATA)

        assert len(redis.set_calls) == 1
        call = redis.set_calls[0]
        assert call["key"] == CLIENT_ORDER_ID
        assert call["expire"] == TTL_SECONDS
        assert call["prefix"] == ORDER_UPDATE_CORRELATION_PREFIX
        assert call["value"]["metadata"] == METADATA
        assert isinstance(call["value"]["created_at"], str)

    @pytest.mark.asyncio
    async def test_get_memory_hit_does_not_read_redis(self) -> None:
        redis = FakeRedisAdapter()
        store = OrderUpdateCorrelationStore(ttl_seconds=TTL_SECONDS, redis=redis)
        await store.register(client_order_id=CLIENT_ORDER_ID, metadata=METADATA)

        correlation = await store.get(client_order_id=CLIENT_ORDER_ID)

        assert correlation is not None
        assert correlation.metadata == METADATA
        assert redis.get_calls == []

    @pytest.mark.asyncio
    async def test_get_after_restart_rehydrates_from_redis(self) -> None:
        redis = FakeRedisAdapter()
        first = OrderUpdateCorrelationStore(ttl_seconds=TTL_SECONDS, redis=redis)
        await first.register(client_order_id=CLIENT_ORDER_ID, metadata=METADATA)

        # Fresh store instance with empty memory simulates an engine restart.
        second = OrderUpdateCorrelationStore(ttl_seconds=TTL_SECONDS, redis=redis)
        correlation = await second.get(client_order_id=CLIENT_ORDER_ID)

        assert correlation is not None
        assert correlation.client_order_id == CLIENT_ORDER_ID
        assert correlation.metadata == METADATA

        # Rehydration caches in memory: the second read must not hit Redis.
        redis.get_calls.clear()
        again = await second.get(client_order_id=CLIENT_ORDER_ID)
        assert again is not None
        assert redis.get_calls == []

    @pytest.mark.asyncio
    async def test_redis_errors_fail_open(self) -> None:
        store = OrderUpdateCorrelationStore(ttl_seconds=TTL_SECONDS, redis=RaisingRedisAdapter())

        await store.register(client_order_id=CLIENT_ORDER_ID, metadata=METADATA)
        correlation = await store.get(client_order_id=CLIENT_ORDER_ID)

        assert correlation is not None  # in-memory path still works
        assert correlation.metadata == METADATA

        missing = await store.get(client_order_id="never-registered")
        assert missing is None

    @pytest.mark.asyncio
    async def test_delete_removes_from_memory_and_redis(self) -> None:
        redis = FakeRedisAdapter()
        store = OrderUpdateCorrelationStore(ttl_seconds=TTL_SECONDS, redis=redis)
        await store.register(client_order_id=CLIENT_ORDER_ID, metadata=METADATA)

        await store.delete(client_order_id=CLIENT_ORDER_ID)

        assert await store.get(client_order_id=CLIENT_ORDER_ID) is None
        assert len(redis.delete_calls) == 1
        assert redis.delete_calls[0]["prefix"] == ORDER_UPDATE_CORRELATION_PREFIX
