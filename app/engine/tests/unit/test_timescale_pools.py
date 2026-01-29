"""Tests for read/write pool initialization and usage in TimescaleDBAdapter."""

import asyncio
import types

import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter


class _AcquireCtx:
    def __init__(self, pool):
        self.pool = pool
        async def _exec(*args, **kwargs):  # noqa: D401, ANN001
            return "OK"
        async def _fetch(*args, **kwargs):  # noqa: D401, ANN001
            return []
        async def _fetchval(*args, **kwargs):  # noqa: D401, ANN001
            return True
        async def _fetchrow(*args, **kwargs):  # noqa: D401, ANN001
            return None
        self._conn = types.SimpleNamespace(
            execute=_exec,
            fetch=_fetch,
            fetchval=_fetchval,
            fetchrow=_fetchrow,
        )

    async def __aenter__(self):  # noqa: D401
        self.pool.acquired = True
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):  # noqa: D401, ANN001
        return False


class _Pool:
    def __init__(self):
        self.acquired = False

    def acquire(self):  # noqa: D401
        return _AcquireCtx(self)

    async def close(self):  # noqa: D401
        return None


class _Ctx:
    def __init__(self, pool):
        self.pool = pool
        self.conn = types.SimpleNamespace()

    async def __aenter__(self):  # noqa: D401
        self.pool.acquired = True
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):  # noqa: D401, ANN001
        return False


@pytest.mark.asyncio
async def test_timescale_adapter_initializes_two_pools_with_tuned_settings(monkeypatch) -> None:
    calls = []

    async def _fake_create_pool(**kwargs):  # noqa: D401, ANN001
        calls.append(kwargs)
        return _Pool()

    monkeypatch.setattr("asyncpg.create_pool", lambda **kwargs: _fake_create_pool(**kwargs))

    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
        pool_size=5,
    )

    await adapter.initialize()

    assert len(calls) == 2  # read and write pools
    t0 = calls[0]["command_timeout"]
    t1 = calls[1]["command_timeout"]
    fast = min(t0, t1)
    slow = max(t0, t1)
    assert fast < slow
    assert calls[0].get("statement_cache_size", 1000) == 1000
    assert calls[1].get("statement_cache_size", 1000) == 1000


@pytest.mark.asyncio
async def test_get_candles_uses_read_pool(monkeypatch) -> None:
    read_pool = _Pool()
    write_pool = _Pool()
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )
    adapter._read_pool = read_pool
    adapter._write_pool = write_pool

    # Patch read connection context manager to yield a fake conn with fetch that returns []
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_read_conn():  # noqa: D401
        read_pool.acquired = True
        conn = types.SimpleNamespace()
        async def _fetch(*args, **kwargs):  # noqa: D401, ANN001
            return []
        async def _fetchrow(*args, **kwargs):  # noqa: D401, ANN001
            return None
        conn.fetch = _fetch
        conn.fetchrow = _fetchrow
        yield conn

    adapter.get_read_connection = _fake_read_conn  # type: ignore[method-assign]

    # Call get_candles; should use read pool and not touch write pool
    from app.engine.models import TimeFrame
    out = await adapter.get_candles(symbol="BTCUSDT", timeframe=TimeFrame.M1, start_time=None, end_time=None, limit=1)
    assert isinstance(out, list)
    assert read_pool.acquired is True
    assert write_pool.acquired is False
    assert read_pool.acquired is True
    assert write_pool.acquired is False
