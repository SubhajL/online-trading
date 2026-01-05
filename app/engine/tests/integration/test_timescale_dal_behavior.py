"""Integration tests for module-level Timescale DAL (no mocks)."""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.engine.adapters.db import timescale
from app.engine.adapters.db.connection_pool import DBConfig
from app.engine.models import Candle, TimeFrame, TechnicalIndicators, SupplyDemandZone, ZoneType


@pytest.fixture(scope="session")
def test_db_config() -> DBConfig:
    """Database configuration for integration tests (from env)."""
    import os
    return DBConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("TEST_DB_NAME", "test_trading_db"),
        username=os.getenv("DB_USER", "trading_user"),
        password=os.getenv("DB_PASSWORD", "trading_pass"),
        pool_size=5,
    )


@pytest_asyncio.fixture(scope="function")
async def pool(test_db_config: DBConfig):
    """Initialize module-level pool for timescale DAL."""
    await timescale.initialize_pool(test_db_config)
    yield timescale.get_pool()
    await timescale.close_pool()


@pytest_asyncio.fixture(autouse=True)
async def clean_db(pool):
    async with pool.acquire() as conn:
        for table in [
            "candles",
            "indicators",
            "zones",
            "orders",
            "positions",
            "decisions",
            "smc_events",
        ]:
            await conn.execute(f"TRUNCATE TABLE {table} CASCADE")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_candle_and_retrieve(pool) -> None:
    candle = Candle(
        venue="spot",
        symbol="BTCUSDT",
        timeframe=TimeFrame.H1,
        open_time=datetime.utcnow().replace(microsecond=0),
        close_time=datetime.utcnow().replace(microsecond=0) + timedelta(hours=1),
        open_price=Decimal("50000.12345678"),
        high_price=Decimal("51000.87654321"),
        low_price=Decimal("49000.11111111"),
        close_price=Decimal("50500.99999999"),
        volume=Decimal("100.12345678"),
        quote_volume=Decimal("5050000.12345678"),
        trades=1000,
        taker_buy_base_volume=Decimal("50.12345678"),
        taker_buy_quote_volume=Decimal("2525000.12345678"),
    )

    assert await timescale.upsert_candle(candle) is True

    # Verify presence and values via DAL range retrieval
    got = await timescale.get_candles(
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        start_time=candle.open_time - timedelta(minutes=1),
        end_time=candle.open_time + timedelta(minutes=1),
        limit=5,
    )
    assert len(got) == 1
    row = got[0]
    assert row["open_price"] == candle.open_price
    assert row["close_price"] == candle.close_price

    # Range retrieval
    got = await timescale.get_candles(
        symbol="BTCUSDT",
        timeframe=TimeFrame.H1,
        start_time=candle.open_time - timedelta(minutes=1),
        end_time=candle.open_time + timedelta(minutes=1),
    )
    assert len(got) == 1
    assert got[0]["open_price"] == candle.open_price


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_candles_with_filters(pool) -> None:
    base = datetime.utcnow().replace(microsecond=0)
    for i in range(6):
        c = Candle(
            venue="spot",
            symbol="ETHUSDT",
            timeframe=TimeFrame.M15,
            open_time=base + timedelta(minutes=15 * i),
            close_time=base + timedelta(minutes=15 * (i + 1)),
            open_price=Decimal(f"3000.{i}"),
            high_price=Decimal(f"3010.{i}"),
            low_price=Decimal(f"2990.{i}"),
            close_price=Decimal(f"3005.{i}"),
            volume=Decimal("50.0"),
            quote_volume=Decimal("150000.0"),
            trades=500,
            taker_buy_base_volume=Decimal("25.0"),
            taker_buy_quote_volume=Decimal("75000.0"),
        )
        assert await timescale.upsert_candle(c) is True

    got = await timescale.get_candles(
        symbol="ETHUSDT",
        timeframe=TimeFrame.M15,
        start_time=base + timedelta(minutes=15),
        end_time=base + timedelta(minutes=60),
        limit=10,
    )
    # Expect 4 rows: i = 1..4
    assert len(got) == 4
    # Ensure chronological order and symbol match
    assert got[0]["symbol"] == "ETHUSDT"
    assert all(got[i]["open_time"] < got[i + 1]["open_time"] for i in range(len(got) - 1))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_indicator(pool) -> None:
    ind = TechnicalIndicators(
        symbol="BTCUSDT",
        timeframe=TimeFrame.H1,
        timestamp=datetime.utcnow().replace(microsecond=0),
        ema_9=Decimal("50100.12"),
        ema_21=Decimal("50050.34"),
        ema_50=Decimal("50000.56"),
        ema_200=Decimal("49800.78"),
        rsi_14=Decimal("65.43"),
        macd_line=Decimal("150.12"),
        macd_signal=Decimal("145.34"),
        macd_histogram=Decimal("4.78"),
        atr_14=Decimal("500.25"),
        bb_upper=Decimal("51000.00"),
        bb_middle=Decimal("50000.00"),
        bb_lower=Decimal("49000.00"),
        bb_width=Decimal("2000.00"),
        bb_percent=Decimal("0.75"),
    )
    assert await timescale.upsert_indicator(ind) is True

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM indicators
            WHERE venue = 'binance' AND symbol = $1 AND timeframe = $2
            ORDER BY timestamp DESC LIMIT 1
            """,
            ind.symbol,
            ind.timeframe.value,
        )
        assert row is not None
        assert row["rsi_14"] == ind.rsi_14


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_zone(pool) -> None:
    zone = SupplyDemandZone(
        zone_id=str(uuid4()),
        symbol="BTCUSDT",
        timeframe=TimeFrame.H4,
        zone_type=ZoneType.DEMAND,
        top_price=Decimal("51000.00"),
        bottom_price=Decimal("50000.00"),
        created_at=datetime.utcnow().replace(microsecond=0),
        strength=5,
        volume_profile=Decimal("1000000.00"),
        touches=0,
        is_active=True,
        tested_at=None,
    )
    assert await timescale.upsert_zone(zone) is True

    # Update touches
    zone.touches = 1
    assert await timescale.upsert_zone(zone) is True

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM zones WHERE zone_id = $1", zone.zone_id)
        assert row is not None
        assert row["touches"] == 1
