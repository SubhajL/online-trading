"""
Unit tests for TimescaleDBAdapter benchmark query helpers.
"""

from datetime import UTC, datetime

import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter


class _FakeConn:
    def __init__(self) -> None:
        self.fetch_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, sql: str, *args: object):  # noqa: D401, ANN001
        self.fetch_calls.append((sql, args))
        return []


class _FakePoolCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:  # noqa: D401
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: D401, ANN001
        return False


@pytest.mark.asyncio
async def test_get_external_telegram_signals_filters_source_and_time() -> None:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )
    fake_conn = _FakeConn()
    adapter.get_read_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment]

    start = datetime(2025, 12, 26, 0, 0, tzinfo=UTC)
    end = datetime(2025, 12, 26, 23, 59, tzinfo=UTC)
    await adapter.get_external_telegram_signals(source="captain", start_time=start, end_time=end, limit=50)

    assert fake_conn.fetch_calls
    sql, args = fake_conn.fetch_calls[0]
    assert "FROM external_telegram_signals" in sql
    assert "source = $1" in sql
    assert args[0] == "captain"
    assert args[1] == start
    assert args[2] == end


@pytest.mark.asyncio
async def test_get_trading_decisions_in_window_filters_symbol_and_time() -> None:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )
    fake_conn = _FakeConn()
    adapter.get_read_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment]

    start = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
    end = datetime(2025, 12, 26, 9, 0, tzinfo=UTC)
    await adapter.get_trading_decisions_in_window(symbol="BTCUSDT", start_time=start, end_time=end)

    sql, args = fake_conn.fetch_calls[0]
    assert "FROM trading_decisions" in sql
    assert "symbol = $1" in sql
    assert args[0] == "BTCUSDT"


@pytest.mark.asyncio
async def test_get_smc_signals_in_window_filters_symbol_timeframe_time() -> None:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )
    fake_conn = _FakeConn()
    adapter.get_read_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment]

    start = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
    end = datetime(2025, 12, 26, 9, 0, tzinfo=UTC)
    await adapter.get_smc_signals_in_window(symbol="EURUSD", timeframe="1h", start_time=start, end_time=end)

    sql, args = fake_conn.fetch_calls[0]
    assert "FROM smc_signals" in sql
    assert "symbol = $1" in sql
    assert "timeframe = $2" in sql
    assert args[0] == "EURUSD"
    assert args[1] == "1h"


@pytest.mark.asyncio
async def test_get_external_telegram_signal_validations_filters_source_and_time() -> None:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )
    fake_conn = _FakeConn()
    adapter.get_read_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment]

    start = datetime(2025, 12, 26, 0, 0, tzinfo=UTC)
    end = datetime(2025, 12, 26, 23, 59, tzinfo=UTC)
    await adapter.get_external_telegram_signal_validations(
        source="captain",
        start_time=start,
        end_time=end,
        limit=50,
    )

    assert fake_conn.fetch_calls
    sql, args = fake_conn.fetch_calls[0]
    assert "FROM external_telegram_signal_validations" in sql
    assert args[0] == "captain"
