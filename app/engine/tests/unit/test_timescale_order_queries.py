from __future__ import annotations

import pytest

from app.engine.adapters.db.timescale_adapter import DuplicateGuardLookupError, TimescaleDBAdapter


class _FakeConn:
    def __init__(self) -> None:
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_error: Exception | None = None
        self.fetch_error: Exception | None = None

    async def fetchrow(self, sql: str, *args: object):  # noqa: D401, ANN001
        self.fetchrow_calls.append((sql, args))
        if self.fetchrow_error is not None:
            raise self.fetchrow_error
        return None

    async def fetch(self, sql: str, *args: object):  # noqa: D401, ANN001
        self.fetch_calls.append((sql, args))
        if self.fetch_error is not None:
            raise self.fetch_error
        return []


class _FakePoolCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:  # noqa: D401
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: D401, ANN001
        return False


def _make_adapter(fake_conn: _FakeConn) -> TimescaleDBAdapter:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )
    adapter.get_read_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment, return-value]
    return adapter


@pytest.mark.asyncio
async def test_get_order_by_client_order_id_filters_client_order_id_and_venue() -> None:
    fake_conn = _FakeConn()
    adapter = _make_adapter(fake_conn)

    await adapter.get_order_by_client_order_id(client_order_id="cid-1", venue="SPOT")

    assert fake_conn.fetchrow_calls
    sql, args = fake_conn.fetchrow_calls[0]
    assert "FROM orders" in sql
    assert "client_order_id = $1" in sql
    assert "venue = $2" in sql
    assert "signal_id" in sql
    assert "timeframe" in sql
    assert "zone" in sql
    assert args == ("cid-1", "SPOT")


@pytest.mark.asyncio
async def test_get_active_order_for_setup_filters_zone_identity_and_active_status() -> None:
    fake_conn = _FakeConn()
    adapter = _make_adapter(fake_conn)

    await adapter.get_active_order_for_setup(
        venue="SPOT",
        symbol="BTCUSDT",
        side="BUY",
        timeframe="15m",
        zone_id="zone-1",
    )

    assert fake_conn.fetchrow_calls
    sql, args = fake_conn.fetchrow_calls[0]
    assert "FROM orders" in sql
    assert "status IN ('NEW', 'PARTIALLY_FILLED')" in sql
    assert "timeframe = $4" in sql
    assert "zone->>'zone_id' = $5" in sql
    assert args == ("SPOT", "BTCUSDT", "BUY", "15m", "zone-1")


@pytest.mark.asyncio
async def test_get_active_position_for_setup_joins_orders_for_setup_identity() -> None:
    fake_conn = _FakeConn()
    adapter = _make_adapter(fake_conn)

    await adapter.get_active_position_for_setup(
        venue="USD_M",
        symbol="BTCUSDT",
        side="BUY",
        timeframe="15m",
        zone_id="zone-1",
    )

    assert fake_conn.fetchrow_calls
    sql, args = fake_conn.fetchrow_calls[0]
    assert "FROM positions p" in sql
    assert "JOIN orders o ON o.order_id = p.entry_order_id" in sql
    assert "p.is_active = TRUE" in sql
    assert "p.size > 0" in sql
    assert "p.side = $3" in sql
    assert "o.timeframe = $4" in sql
    assert "o.zone->>'zone_id' = $5" in sql
    assert args == ("USD_M", "BTCUSDT", "BUY", "15m", "zone-1")


@pytest.mark.asyncio
async def test_get_active_order_for_setup_raises_when_query_fails() -> None:
    fake_conn = _FakeConn()
    fake_conn.fetchrow_error = RuntimeError("read failed")
    adapter = _make_adapter(fake_conn)

    with pytest.raises(DuplicateGuardLookupError):
        await adapter.get_active_order_for_setup(
            venue="SPOT",
            symbol="BTCUSDT",
            side="BUY",
            timeframe="15m",
            zone_id="zone-1",
        )


@pytest.mark.asyncio
async def test_get_active_position_for_setup_raises_when_query_fails() -> None:
    fake_conn = _FakeConn()
    fake_conn.fetchrow_error = RuntimeError("read failed")
    adapter = _make_adapter(fake_conn)

    with pytest.raises(DuplicateGuardLookupError):
        await adapter.get_active_position_for_setup(
            venue="USD_M",
            symbol="BTCUSDT",
            side="BUY",
            timeframe="15m",
            zone_id="zone-1",
        )


@pytest.mark.asyncio
async def test_get_active_positions_selects_side_and_entry_order_id() -> None:
    fake_conn = _FakeConn()
    adapter = _make_adapter(fake_conn)

    await adapter.get_active_positions("SPOT")

    assert fake_conn.fetch_calls
    sql, args = fake_conn.fetch_calls[0]
    assert "FROM positions" in sql
    assert "SELECT symbol, side, size, current_price" in sql
    assert "COALESCE(entry_order_id::text, '') AS entry_order_id" in sql
    assert args == ("SPOT",)
