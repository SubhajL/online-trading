"""
Unit test to verify TimescaleDBAdapter uses batch executemany for candles.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter
from app.engine.models import Candle, TimeFrame


class _FakeConn:
    def __init__(self):
        self.executemany_called = False
        self.executemany_sql = None
        self.executemany_records = None

    async def execute(self, *args, **kwargs):  # noqa: D401, ANN001
        return None

    async def fetch(self, *args, **kwargs):  # noqa: D401, ANN001
        return []

    async def fetchrow(self, *args, **kwargs):  # noqa: D401, ANN001
        return None

    async def executemany(self, sql, records):  # noqa: D401, ANN001
        self.executemany_called = True
        self.executemany_sql = sql
        self.executemany_records = list(records)

    # Provide default copy_records_to_table that is not implemented
    async def copy_records_to_table(self, *args, **kwargs):  # noqa: D401, ANN001
        raise NotImplementedError


class _FakePoolCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):  # noqa: D401
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):  # noqa: D401, ANN001
        return False


@pytest.mark.asyncio
async def test_insert_candles_batch_calls_executemany(monkeypatch) -> None:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )

    fake_conn = _FakeConn()

    # Patch write connection to return our fake connection context manager
    adapter.get_write_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment]

    t0 = datetime.now(UTC)
    candles = [
        Candle(
            venue="spot",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            open_time=t0 + timedelta(minutes=i * 15),
            close_time=t0 + timedelta(minutes=(i + 1) * 15),
            open_price=Decimal("100"),
            high_price=Decimal("101"),
            low_price=Decimal("99"),
            close_price=Decimal("100.5"),
            volume=Decimal("10"),
            quote_volume=Decimal("1000"),
            trades=5,
            taker_buy_base_volume=Decimal("6"),
            taker_buy_quote_volume=Decimal("600"),
        )
        for i in range(3)
    ]

    inserted = await adapter.insert_candles_batch(candles)
    assert inserted == 3
    assert fake_conn.executemany_called is True
    assert fake_conn.executemany_sql is not None and "INSERT INTO candles" in fake_conn.executemany_sql
    assert len(fake_conn.executemany_records) == 3


class _FakeConnCopy(_FakeConn):
    def __init__(self):
        super().__init__()
        self.copy_called = False
        self.copy_args = None

    async def copy_records_to_table(self, table, *, records, columns):  # noqa: D401, ANN001
        self.copy_called = True
        self.copy_args = {"table": table, "columns": list(columns), "records": list(records)}
        return len(list(records))


class _FakePoolCtxCopy(_FakePoolCtx):
    async def __aenter__(self):  # noqa: D401
        return self._conn


@pytest.mark.asyncio
async def test_insert_candles_batch_uses_copy_for_large_batches(monkeypatch) -> None:
    # Force low threshold to trigger COPY path
    monkeypatch.setenv("TIMESCALE_COPY_THRESHOLD", "1")

    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )

    fake_conn = _FakeConnCopy()
    # Patch write connection to return our fake connection context manager
    adapter.get_write_connection = lambda: _FakePoolCtxCopy(fake_conn)  # type: ignore[assignment]

    t0 = datetime.now(UTC)
    candles = [
        Candle(
            venue="spot",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M1,
            open_time=t0,
            close_time=t0 + timedelta(minutes=1),
            open_price=Decimal("100"),
            high_price=Decimal("101"),
            low_price=Decimal("99"),
            close_price=Decimal("100.5"),
            volume=Decimal("10"),
            quote_volume=Decimal("1000"),
            trades=5,
            taker_buy_base_volume=Decimal("6"),
            taker_buy_quote_volume=Decimal("600"),
        )
        for _ in range(2)
    ]

    inserted = await adapter.insert_candles_batch(candles)
    assert inserted == 2
    assert fake_conn.copy_called is True
    assert fake_conn.executemany_called is False
    args = fake_conn.copy_args
    assert args is not None and args["table"] == "candles"
    assert set(args["columns"]) == {
        "venue",
        "symbol",
        "timeframe",
        "open_time",
        "close_time",
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "quote_volume",
        "trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    }
