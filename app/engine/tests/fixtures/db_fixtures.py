"""Database fixtures for testing."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional

import asyncpg
from asyncpg import Pool

from app.engine.adapters.db.connection_pool import ConnectionPool


@dataclass
class TestData:
    """Container for test data loaded into database."""

    candles: List[Dict[str, Any]] = field(default_factory=list)
    indicators: List[Dict[str, Any]] = field(default_factory=list)
    orders: List[Dict[str, Any]] = field(default_factory=list)
    zones: List[Dict[str, Any]] = field(default_factory=list)
    positions: List[Dict[str, Any]] = field(default_factory=list)


def create_test_candle(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    open_time: Optional[datetime] = None,
    open_price: Decimal = Decimal("50000"),
    volume: Decimal = Decimal("100"),
    venue: str = "binance",
) -> Dict[str, Any]:
    """Create a test candle with realistic data."""
    if open_time is None:
        open_time = datetime.utcnow() - timedelta(hours=1)

    close_time = open_time + timedelta(hours=1)

    # Generate realistic OHLC values
    volatility = Decimal("0.01")  # 1% volatility
    high_price = open_price * (Decimal("1") + volatility)
    low_price = open_price * (Decimal("1") - volatility)
    close_price = open_price + (high_price - low_price) * Decimal("0.3")

    return {
        "venue": venue,
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time": open_time,
        "close_time": close_time,
        "open_price": open_price,
        "high_price": high_price,
        "low_price": low_price,
        "close_price": close_price,
        "volume": volume,
        "quote_volume": volume * open_price,
        "trades": 1000,
        "taker_buy_base_volume": volume * Decimal("0.5"),
        "taker_buy_quote_volume": volume * open_price * Decimal("0.5"),
    }


def create_test_order(
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    order_type: str = "LIMIT",
    quantity: Decimal = Decimal("0.01"),
    price: Optional[Decimal] = None,
    status: str = "NEW",
    venue: str = "binance",
) -> Dict[str, Any]:
    """Create a test order with valid data."""
    order_id = str(uuid.uuid4())
    client_order_id = f"test_{uuid.uuid4().hex[:16]}"

    return {
        "order_id": order_id,
        "client_order_id": client_order_id,
        "venue": venue,
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "quantity": quantity,
        "price": price,
        "status": status,
        "filled_quantity": Decimal("0"),
        "average_fill_price": None,
        "created_at": datetime.utcnow(),
        "decision_id": str(uuid.uuid4()),
    }


def create_test_zone(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    zone_type: str = "SUPPLY",
    top_price: Decimal = Decimal("51000"),
    bottom_price: Decimal = Decimal("50000"),
    venue: str = "binance",
) -> Dict[str, Any]:
    """Create a test supply/demand zone."""
    zone_id = str(uuid.uuid4())

    return {
        "zone_id": zone_id,
        "venue": venue,
        "symbol": symbol,
        "timeframe": timeframe,
        "zone_type": zone_type,
        "top_price": top_price,
        "bottom_price": bottom_price,
        "created_at": datetime.utcnow(),
        "strength": "STRONG",
        "volume_profile": Decimal("1000"),
        "touches": 0,
        "is_active": True,
        "tested_at": None,
    }


class DBFixtures:
    """Database fixture management for tests."""

    def __init__(self, pool: Pool):
        self.pool = pool
        self.test_db_name = "trading_test"

    async def setup_test_db(self) -> None:
        """Create test database and schema."""
        async with self.pool.acquire() as conn:
            # Check if test database exists
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", self.test_db_name
            )

            if not exists:
                # Create test database
                await conn.execute(f"CREATE DATABASE {self.test_db_name}")

            # Run migrations (simplified for testing)
            await self._run_migrations(conn)

    async def teardown_test_db(self) -> None:
        """Drop test database."""
        async with self.pool.acquire() as conn:
            # Terminate connections to test database
            await conn.execute(
                f"""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = '{self.test_db_name}'
                AND pid <> pg_backend_pid()
            """
            )

            # Drop test database
            await conn.execute(f"DROP DATABASE IF EXISTS {self.test_db_name}")

    async def clear_tables(self) -> None:
        """Clear all tables maintaining referential integrity."""
        async with self.pool.acquire() as conn:
            # Order matters due to foreign key constraints
            tables = [
                "positions",
                "orders",
                "zones",
                "smc_events",
                "indicators",
                "candles",
            ]

            for table in tables:
                await conn.execute(f"TRUNCATE TABLE {table} CASCADE")

    async def load_test_data(self) -> TestData:
        """Load sample test data into database."""
        test_data = TestData()

        async with self.pool.acquire() as conn:
            # Load test candles
            for i in range(100):
                candle = create_test_candle(
                    open_time=datetime.utcnow() - timedelta(hours=100 - i),
                    open_price=Decimal("50000") + Decimal(i * 100),
                )
                test_data.candles.append(candle)

                await conn.execute(
                    """
                    INSERT INTO candles (
                        venue, symbol, timeframe, open_time, close_time,
                        open_price, high_price, low_price, close_price,
                        volume, quote_volume, trades,
                        taker_buy_base_volume, taker_buy_quote_volume
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """,
                    *candle.values(),
                )

            # Load test orders
            for i in range(10):
                order = create_test_order(
                    side="BUY" if i % 2 == 0 else "SELL",
                    quantity=Decimal("0.01") * (i + 1),
                    price=Decimal("50000") + Decimal(i * 100),
                )
                test_data.orders.append(order)

                await conn.execute(
                    """
                    INSERT INTO orders (
                        order_id, client_order_id, venue, symbol, side, type,
                        quantity, price, status, filled_quantity,
                        average_fill_price, created_at, decision_id
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                    *order.values(),
                )

            # Load test zones
            for i in range(5):
                zone = create_test_zone(
                    zone_type="SUPPLY" if i % 2 == 0 else "DEMAND",
                    top_price=Decimal("51000") + Decimal(i * 1000),
                    bottom_price=Decimal("50000") + Decimal(i * 1000),
                )
                test_data.zones.append(zone)

                await conn.execute(
                    """
                    INSERT INTO zones (
                        zone_id, venue, symbol, timeframe, zone_type,
                        top_price, bottom_price, created_at,
                        strength, volume_profile, touches, is_active, tested_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                    *zone.values(),
                )

        return test_data

    async def _run_migrations(self, conn: asyncpg.Connection) -> None:
        """Run database migrations for test database."""
        # Simplified migration for testing
        # In production, this would read from migration files

        # Enable TimescaleDB
        await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

        # Create tables (simplified schema)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candles (
                venue TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time TIMESTAMPTZ NOT NULL,
                close_time TIMESTAMPTZ NOT NULL,
                open_price NUMERIC(18,8) NOT NULL,
                high_price NUMERIC(18,8) NOT NULL,
                low_price NUMERIC(18,8) NOT NULL,
                close_price NUMERIC(18,8) NOT NULL,
                volume NUMERIC(18,8) NOT NULL,
                quote_volume NUMERIC(18,8) NOT NULL,
                trades INTEGER NOT NULL,
                taker_buy_base_volume NUMERIC(18,8) NOT NULL,
                taker_buy_quote_volume NUMERIC(18,8) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (venue, symbol, timeframe, open_time)
            )
        """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                client_order_id TEXT NOT NULL,
                venue TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                type TEXT NOT NULL,
                quantity NUMERIC(18,8) NOT NULL,
                price NUMERIC(18,8),
                status TEXT NOT NULL,
                filled_quantity NUMERIC(18,8) DEFAULT 0,
                average_fill_price NUMERIC(18,8),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                decision_id TEXT,
                UNIQUE(venue, client_order_id)
            )
        """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS zones (
                zone_id TEXT PRIMARY KEY,
                venue TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                zone_type TEXT NOT NULL,
                top_price NUMERIC(18,8) NOT NULL,
                bottom_price NUMERIC(18,8) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                strength TEXT NOT NULL,
                volume_profile NUMERIC(18,8),
                touches INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                tested_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Add other tables as needed...


# Pytest fixture
import pytest


@pytest.fixture
async def db_session():
    """Pytest fixture providing database session with test data."""
    # This would use the real connection pool in integration tests
    # For unit tests, it's mocked
    pass
