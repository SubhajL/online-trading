"""Edge-case tests for RedisAdapter chunked clear_cache and normalization."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from app.engine.adapters.redis.redis_adapter import RedisAdapter


class _FakeRedisLarge:
    """Fake Redis client exposing scan_iter and batched delete."""

    def __init__(self, keys: list[str]) -> None:
        self._keys = list(keys)
        self.deleted_calls: list[list[str]] = []

    async def keys(self, pattern: str) -> list[str]:  # noqa: D401
        raise NotImplementedError("keys() should not be used; use scan_iter instead")

    async def delete(self, *keys: str) -> int:  # noqa: D401
        batch = list(keys)
        self.deleted_calls.append(batch)
        return len(batch)

    async def flushdb(self) -> bool:  # noqa: D401
        self.deleted_calls.append(self._keys[:])
        n = len(self._keys)
        self._keys.clear()
        return n > 0

    async def scan_iter(self, match: str, count: int = 1000):  # noqa: D401, ANN001
        # Simple paginator over self._keys matching prefix
        prefix = match.split("*")[0]
        filtered = [k for k in self._keys if k.startswith(prefix)]
        i = 0
        while i < len(filtered):
            chunk = filtered[i : i + count]
            for k in chunk:
                yield k
            i += count


class _FakeRedisStore:
    """In-memory fake redis for mset/mget and get/set round-trip."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    async def mset(self, mapping: dict[str, Any]) -> bool:  # noqa: D401, ANN001
        for k, v in mapping.items():
            self._data[str(k)] = (
                v.encode("utf-8") if isinstance(v, str) else bytes(str(v), "utf-8")
            )
        return True

    async def mget(self, *keys: str) -> list[bytes | None]:  # noqa: D401
        return [self._data.get(k) for k in keys]

    async def set(self, key: str, value: str) -> bool:  # noqa: D401
        self._data[key] = value.encode("utf-8")
        return True

    async def get(self, key: str) -> bytes | None:  # noqa: D401
        return self._data.get(key)


@pytest.mark.asyncio
async def test_clear_cache_large_keyset_chunking(monkeypatch: pytest.MonkeyPatch) -> None:
    # Prepare 2500 keys with prefix cache:
    keys = [f"cache:item:{i}" for i in range(2500)]
    fake = _FakeRedisLarge(keys)

    adapter = RedisAdapter()
    adapter._redis = fake  # type: ignore[assignment]
    adapter._initialized = True  # type: ignore[assignment]

    # Expect chunked deletion (default batch_size expected ~1000 after impl)
    # Call with prefix to avoid flushdb path
    # We will set concrete parameters later once implemented
    try:
        deleted = await adapter.clear_cache(prefix="cache")
    except NotImplementedError:
        # Current implementation uses keys(); force failure to drive SCAN-based impl
        deleted = -1

    assert deleted != -1, "clear_cache should not rely on KEYS; use SCAN in batches"
    assert deleted == 2500
    # Ensure multiple delete calls (chunking), not a single huge delete
    assert len(fake.deleted_calls) >= 3
    # Each intermediate batch should be reasonable (<= 1000)
    assert all(len(batch) <= 1000 for batch in fake.deleted_calls)


@pytest.mark.asyncio
async def test_mset_round_trip_normalization() -> None:
    fake = _FakeRedisStore()
    adapter = RedisAdapter()
    adapter._redis = fake  # type: ignore[assignment]
    adapter._initialized = True  # type: ignore[assignment]

    # Mixed values
    pairs = {
        "a": 1,
        "b": "x",
        "c": Decimal("1.23"),
        "d": {"n": 1},
        "e": ["a", 1],
    }

    ok = await adapter.mset(pairs)
    assert ok is True

    out = await adapter.mget(["a", "b", "c", "d", "e"])
    assert out == [1, "x", "1.23", {"n": 1}, ["a", 1]]
