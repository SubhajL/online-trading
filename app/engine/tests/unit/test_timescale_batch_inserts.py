"""
Unit test to verify TimescaleDBAdapter uses batch executemany for candles.
"""

import asyncio
from datetime import datetime, timedelta
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

    # Patch get_connection to return our fake connection context manager
    async def _fake_get_connection():  # noqa: D401
        return _FakePoolCtx(fake_conn)

    # monkeypatch the asynccontextmanager method by returning the context directly
    adapter.get_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment]

    t0 = datetime.utcnow()
    candles = [
        Candle(
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
