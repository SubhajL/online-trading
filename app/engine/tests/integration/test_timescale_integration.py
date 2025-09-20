"""Integration tests for TimescaleDB DAL functions."""

import asyncio
import os
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import asyncpg
from asyncpg import Connection

from app.engine.adapters.db import timescale
from app.engine.adapters.db.connection_pool import ConnectionPool, DBConfig
from app.engine.adapters.db.migrations import MigrationRunner
from app.engine.models import (
    Candle,
    TimeFrame,
    TechnicalIndicators,
    SupplyDemandZone,
    ZoneType,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_db_config():
    """Test database configuration."""
    return DBConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("TEST_DB_NAME", "test_trading_db"),
        username=os.getenv("DB_USER", "trading_user"),
        password=os.getenv("DB_PASSWORD", "trading_pass"),
        max_connections=5,
        min_connections=1,
    )


@pytest.fixture(scope="session")
async def test_pool(test_db_config):
    """Create test connection pool."""
    await timescale.initialize_pool(test_db_config)
    yield timescale.get_pool()
    await timescale.close_pool()


@pytest.fixture(autouse=True)
async def clean_database(test_pool):
    """Clean database before each test."""
    async with test_pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE candles CASCADE")
        await conn.execute("TRUNCATE TABLE indicators CASCADE")
        await conn.execute("TRUNCATE TABLE zones CASCADE")
        await conn.execute("TRUNCATE TABLE orders CASCADE")
        await conn.execute("TRUNCATE TABLE positions CASCADE")
        await conn.execute("TRUNCATE TABLE decisions CASCADE")
        await conn.execute("TRUNCATE TABLE smc_events CASCADE")


class TestCandleOperations:
    @pytest.mark.asyncio
    async def test_candle_upsert_and_retrieve(self, test_pool):
        """Test inserting and retrieving candles with Decimal precision."""
        # Create test candle
        candle = Candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            open_time=datetime.utcnow(),
            close_time=datetime.utcnow() + timedelta(hours=1),
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

        # Upsert candle
        result = await timescale.upsert_candle(candle)
        assert result is True

        # Retrieve candle
        candles = await timescale.get_candles(
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            start_time=candle.open_time - timedelta(minutes=1),
            end_time=candle.open_time + timedelta(minutes=1),
        )

        assert len(candles) == 1
        retrieved = candles[0]

        # Verify Decimal precision preserved
        assert retrieved["open_price"] == candle.open_price
        assert retrieved["high_price"] == candle.high_price
        assert retrieved["low_price"] == candle.low_price
        assert retrieved["close_price"] == candle.close_price
        assert retrieved["volume"] == candle.volume
        assert retrieved["quote_volume"] == candle.quote_volume
        assert retrieved["taker_buy_base_volume"] == candle.taker_buy_base_volume
        assert retrieved["taker_buy_quote_volume"] == candle.taker_buy_quote_volume

    @pytest.mark.asyncio
    async def test_candle_upsert_idempotent(self, test_pool):
        """Test candle upsert is idempotent."""
        candle = Candle(
            symbol="ETHUSDT",
            timeframe=TimeFrame.M15,
            open_time=datetime.utcnow(),
            close_time=datetime.utcnow() + timedelta(minutes=15),
            open_price=Decimal("3000.50"),
            high_price=Decimal("3050.00"),
            low_price=Decimal("2990.00"),
            close_price=Decimal("3020.75"),
            volume=Decimal("500.0"),
            quote_volume=Decimal("1510000.0"),
            trades=2000,
            taker_buy_base_volume=Decimal("250.0"),
            taker_buy_quote_volume=Decimal("755000.0"),
        )

        # Insert multiple times
        for _ in range(3):
            result = await timescale.upsert_candle(candle)
            assert result is True

        # Should only have one record
        candles = await timescale.get_candles(
            symbol="ETHUSDT",
            timeframe=TimeFrame.M15,
        )
        assert len(candles) == 1

    @pytest.mark.asyncio
    async def test_candle_retrieval_with_filters(self, test_pool):
        """Test candle retrieval with various filters."""
        base_time = datetime.utcnow().replace(microsecond=0)

        # Insert multiple candles
        for i in range(10):
            candle = Candle(
                symbol="BTCUSDT",
                timeframe=TimeFrame.H1,
                open_time=base_time + timedelta(hours=i),
                close_time=base_time + timedelta(hours=i+1),
                open_price=Decimal(f"50000.{i}"),
                high_price=Decimal(f"51000.{i}"),
                low_price=Decimal(f"49000.{i}"),
                close_price=Decimal(f"50500.{i}"),
                volume=Decimal("100.0"),
                quote_volume=Decimal("5000000.0"),
                trades=1000,
                taker_buy_base_volume=Decimal("50.0"),
                taker_buy_quote_volume=Decimal("2500000.0"),
            )
            await timescale.upsert_candle(candle)

        # Test with time range filter
        candles = await timescale.get_candles(
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            start_time=base_time + timedelta(hours=2),
            end_time=base_time + timedelta(hours=7),
            limit=20,
        )

        assert len(candles) == 6  # Hours 2-7 inclusive
        assert candles[0]["open_time"] == base_time + timedelta(hours=2)
        assert candles[-1]["open_time"] == base_time + timedelta(hours=7)


class TestIndicatorOperations:
    @pytest.mark.asyncio
    async def test_indicator_upsert_and_retrieve(self, test_pool):
        """Test technical indicators with Decimal precision."""
        indicator = TechnicalIndicators(
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            timestamp=datetime.utcnow(),
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

        # Upsert indicator
        result = await timescale.upsert_indicator(indicator)
        assert result is True

        # Verify insertion
        async with test_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM indicators
                WHERE venue = 'binance' AND symbol = $1 AND timeframe = $2
                ORDER BY timestamp DESC LIMIT 1
                """,
                indicator.symbol,
                indicator.timeframe.value,
            )

            assert row is not None
            assert row["ema_9"] == indicator.ema_9
            assert row["ema_21"] == indicator.ema_21
            assert row["rsi_14"] == indicator.rsi_14
            assert row["macd_line"] == indicator.macd_line
            assert row["atr_14"] == indicator.atr_14


class TestZoneOperations:
    @pytest.mark.asyncio
    async def test_zone_upsert_and_update(self, test_pool):
        """Test supply/demand zone operations."""
        zone = SupplyDemandZone(
            zone_id=str(uuid4()),
            symbol="BTCUSDT",
            timeframe=TimeFrame.H4,
            zone_type=ZoneType.DEMAND,
            top_price=Decimal("51000.00"),
            bottom_price=Decimal("50000.00"),
            created_at=datetime.utcnow(),
            strength=Decimal("0.85"),
            volume_profile=Decimal("1000000.00"),
            touches=0,
            is_active=True,
            tested_at=None,
        )

        # Insert zone
        result = await timescale.upsert_zone(zone)
        assert result is True

        # Update zone (simulate retest)
        zone.touches = 1
        zone.tested_at = datetime.utcnow()
        result = await timescale.upsert_zone(zone)
        assert result is True

        # Verify update
        async with test_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM zones WHERE zone_id = $1",
                zone.zone_id,
            )

            assert row is not None
            assert row["touches"] == 1
            assert row["tested_at"] is not None
            assert row["top_price"] == zone.top_price
            assert row["bottom_price"] == zone.bottom_price
            assert row["strength"] == zone.strength


class TestOrderOperations:
    @pytest.mark.asyncio
    async def test_order_lifecycle(self, test_pool):
        """Test order creation and updates."""
        # Create initial order
        order_data = {
            "order_id": str(uuid4()),
            "client_order_id": f"test_order_{uuid4()}",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "quantity": "0.01",
            "price": "50000.00",
            "status": "NEW",
            "decision_id": str(uuid4()),
        }

        result = await timescale.upsert_order(order_data)
        assert result is True

        # Update order as filled
        order_data.update({
            "status": "FILLED",
            "filled_quantity": "0.01",
            "average_fill_price": "50100.25",
            "commission": "0.00001",
            "commission_asset": "BTC",
        })

        result = await timescale.upsert_order(order_data)
        assert result is True

        # Verify final state
        async with test_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM orders WHERE client_order_id = $1",
                order_data["client_order_id"],
            )

            assert row is not None
            assert row["status"] == "FILLED"
            assert row["filled_quantity"] == Decimal("0.01")
            assert row["average_fill_price"] == Decimal("50100.25")
            assert row["commission"] == Decimal("0.00001")

    @pytest.mark.asyncio
    async def test_order_decimal_conversion(self, test_pool):
        """Test order handles various numeric input types."""
        order_data = {
            "client_order_id": f"test_decimal_{uuid4()}",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "type": "MARKET",
            "quantity": 0.5,  # Float input
            "filled_quantity": "0.5",  # String input
            "average_fill_price": Decimal("3000.50"),  # Decimal input
            "commission": 0.0005,  # Float input
        }

        result = await timescale.upsert_order(order_data)
        assert result is True

        # Verify all converted to Decimal
        async with test_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM orders WHERE client_order_id = $1",
                order_data["client_order_id"],
            )

            assert isinstance(row["quantity"], Decimal)
            assert isinstance(row["filled_quantity"], Decimal)
            assert isinstance(row["average_fill_price"], Decimal)
            assert isinstance(row["commission"], Decimal)


class TestPositionOperations:
    @pytest.mark.asyncio
    async def test_get_active_positions(self, test_pool):
        """Test retrieving active positions with filters."""
        # Insert test positions directly
        async with test_pool.acquire() as conn:
            # Insert decision first (for foreign key)
            decision_id = str(uuid4())
            await conn.execute(
                """
                INSERT INTO decisions (decision_id, timestamp, symbol)
                VALUES ($1, $2, $3)
                """,
                decision_id,
                datetime.utcnow(),
                "BTCUSDT",
            )

            # Insert positions
            for i, symbol in enumerate(["BTCUSDT", "ETHUSDT", "BTCUSDT"]):
                position_id = str(uuid4())
                await conn.execute(
                    """
                    INSERT INTO positions (
                        position_id, venue, symbol, side, size,
                        entry_price, current_price, unrealized_pnl,
                        realized_pnl, margin_used, leverage,
                        is_active, decision_id
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    """,
                    position_id,
                    "binance",
                    symbol,
                    "LONG",
                    Decimal(f"0.{i+1}"),
                    Decimal(f"{50000 + i*1000}.00"),
                    Decimal(f"{51000 + i*1000}.00"),
                    Decimal(f"{100 + i*10}.00"),
                    Decimal("0.00"),
                    Decimal(f"{1000 + i*100}.00"),
                    Decimal("5.0"),
                    i < 2,  # First two are active
                    decision_id if symbol == "BTCUSDT" else None,
                )

        # Get all active positions
        positions = await timescale.get_active_positions()
        assert len(positions) == 2

        # Get filtered positions
        btc_positions = await timescale.get_active_positions(symbol="BTCUSDT")
        assert len(btc_positions) == 1
        assert btc_positions[0]["symbol"] == "BTCUSDT"

        # Verify Decimal precision
        position = btc_positions[0]
        assert isinstance(position["size"], Decimal)
        assert isinstance(position["entry_price"], Decimal)
        assert isinstance(position["unrealized_pnl"], Decimal)
        assert isinstance(position["margin_used"], Decimal)
        assert isinstance(position["leverage"], Decimal)


class TestTransactionHandling:
    @pytest.mark.asyncio
    async def test_transaction_rollback(self, test_pool):
        """Test transaction rollback on error."""
        async with test_pool.acquire() as conn:
            try:
                async with conn.transaction():
                    # Insert valid candle
                    await conn.execute(
                        """
                        INSERT INTO candles (
                            venue, symbol, timeframe, open_time, close_time,
                            open_price, high_price, low_price, close_price,
                            volume, quote_volume, trades,
                            taker_buy_base_volume, taker_buy_quote_volume
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                        """,
                        "binance", "BTCUSDT", "1h",
                        datetime.utcnow(), datetime.utcnow() + timedelta(hours=1),
                        Decimal("50000"), Decimal("51000"), Decimal("49000"), Decimal("50500"),
                        Decimal("100"), Decimal("5000000"), 1000,
                        Decimal("50"), Decimal("2500000"),
                    )

                    # Force error with constraint violation
                    await conn.execute(
                        "INSERT INTO candles (venue, symbol) VALUES ($1, $2)",
                        "binance", "INVALID"
                    )
            except Exception:
                pass

        # Verify rollback - no candles should exist
        candles = await timescale.get_candles("BTCUSDT", TimeFrame.H1)
        assert len(candles) == 0


class TestConnectionPoolResilience:
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, test_pool):
        """Test pool handles concurrent operations."""
        async def insert_candle(i):
            candle = Candle(
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                open_time=datetime.utcnow() + timedelta(minutes=i*5),
                close_time=datetime.utcnow() + timedelta(minutes=(i+1)*5),
                open_price=Decimal(f"50000.{i}"),
                high_price=Decimal(f"50100.{i}"),
                low_price=Decimal(f"49900.{i}"),
                close_price=Decimal(f"50050.{i}"),
                volume=Decimal("10.0"),
                quote_volume=Decimal("500000.0"),
                trades=100,
                taker_buy_base_volume=Decimal("5.0"),
                taker_buy_quote_volume=Decimal("250000.0"),
            )
            return await timescale.upsert_candle(candle)

        # Run multiple concurrent inserts
        results = await asyncio.gather(
            *[insert_candle(i) for i in range(10)]
        )

        assert all(results)

        # Verify all inserted
        candles = await timescale.get_candles("BTCUSDT", TimeFrame.M5)
        assert len(candles) == 10


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_graceful_error_handling(self, test_pool):
        """Test DAL functions handle errors gracefully."""
        # Test with invalid data
        invalid_candle = Candle(
            symbol="X" * 50,  # Too long
            timeframe=TimeFrame.H1,
            open_time=datetime.utcnow(),
            close_time=datetime.utcnow() + timedelta(hours=1),
            open_price=Decimal("-1000"),  # Invalid negative price
            high_price=Decimal("0"),
            low_price=Decimal("0"),
            close_price=Decimal("0"),
            volume=Decimal("-100"),  # Invalid negative volume
            quote_volume=Decimal("0"),
            trades=-1,  # Invalid negative trades
            taker_buy_base_volume=Decimal("0"),
            taker_buy_quote_volume=Decimal("0"),
        )

        # Should return False instead of raising
        result = await timescale.upsert_candle(invalid_candle)
        assert result is False

        # Verify no partial data inserted
        candles = await timescale.get_candles("X" * 50, TimeFrame.H1)
        assert len(candles) == 0