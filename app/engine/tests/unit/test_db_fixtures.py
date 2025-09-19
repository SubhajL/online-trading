"""Unit tests for database fixtures."""

import asyncio
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

import pytest
import asyncpg

from app.engine.tests.fixtures.db_fixtures import (
    DBFixtures,
    TestData,
    create_test_candle,
    create_test_order,
    create_test_zone,
)


@pytest.fixture
def mock_pool():
    """Mock connection pool for testing."""
    pool = MagicMock()
    conn = AsyncMock()

    # Create async context manager for acquire
    @asynccontextmanager
    async def mock_acquire():
        yield conn

    pool.acquire = mock_acquire
    pool.release = AsyncMock()
    pool.close = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetchval = AsyncMock()
    return pool, conn


class TestDBFixtures:
    @pytest.mark.asyncio
    async def test_setup_test_db(self, mock_pool):
        """Test database setup creates schema correctly."""
        pool, conn = mock_pool

        # Mock checking for existing database
        conn.fetchval.return_value = None

        fixtures = DBFixtures(pool)
        await fixtures.setup_test_db()

        # Should execute CREATE DATABASE and migrations
        assert conn.execute.call_count >= 2

    @pytest.mark.asyncio
    async def test_teardown_test_db(self, mock_pool):
        """Test database teardown drops database."""
        pool, conn = mock_pool

        fixtures = DBFixtures(pool)
        await fixtures.teardown_test_db()

        # Should terminate connections and drop the test database
        assert conn.execute.call_count == 2

        # Check that we terminated connections first
        terminate_call = conn.execute.call_args_list[0][0][0]
        assert "pg_terminate_backend" in terminate_call

        # Check that we dropped the database second
        drop_call = conn.execute.call_args_list[1][0][0]
        assert "DROP DATABASE" in drop_call

    @pytest.mark.asyncio
    async def test_load_test_data(self, mock_pool):
        """Test loading sample data into database."""
        pool, conn = mock_pool

        fixtures = DBFixtures(pool)
        test_data = await fixtures.load_test_data()

        # Should insert candles, orders, zones
        assert conn.execute.call_count >= 3
        assert len(test_data.candles) > 0
        assert len(test_data.orders) > 0
        assert len(test_data.zones) > 0

    @pytest.mark.asyncio
    async def test_clear_tables(self, mock_pool):
        """Test clearing all tables maintains referential integrity."""
        pool, conn = mock_pool

        fixtures = DBFixtures(pool)
        await fixtures.clear_tables()

        # Should truncate tables in correct order
        calls = [call[0][0] for call in conn.execute.call_args_list]

        # Orders before candles (due to potential FK)
        orders_idx = next(i for i, call in enumerate(calls) if "orders" in call)
        candles_idx = next(i for i, call in enumerate(calls) if "candles" in call)
        assert orders_idx < candles_idx


class TestDataFactories:
    def test_create_test_candle(self):
        """Test candle factory creates valid candle."""
        candle = create_test_candle(
            symbol="BTCUSDT", open_price=Decimal("50000"), volume=Decimal("100")
        )

        assert candle["symbol"] == "BTCUSDT"
        assert candle["open_price"] == Decimal("50000")
        assert candle["volume"] == Decimal("100")
        assert candle["high_price"] >= candle["open_price"]
        assert candle["low_price"] <= candle["open_price"]
        assert isinstance(candle["open_time"], datetime)
        assert isinstance(candle["close_time"], datetime)
        assert candle["close_time"] > candle["open_time"]

    def test_create_test_order(self):
        """Test order factory creates valid order."""
        order = create_test_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
        )

        assert order["symbol"] == "BTCUSDT"
        assert order["side"] == "BUY"
        assert order["quantity"] == Decimal("0.01")
        assert order["price"] == Decimal("50000")
        assert "client_order_id" in order
        assert order["status"] == "NEW"
        assert order["type"] == "LIMIT"

    def test_create_test_zone(self):
        """Test zone factory creates valid supply/demand zone."""
        zone = create_test_zone(
            symbol="BTCUSDT",
            zone_type="SUPPLY",
            top_price=Decimal("51000"),
            bottom_price=Decimal("50000"),
        )

        assert zone["symbol"] == "BTCUSDT"
        assert zone["zone_type"] == "SUPPLY"
        assert zone["top_price"] == Decimal("51000")
        assert zone["bottom_price"] == Decimal("50000")
        assert zone["top_price"] > zone["bottom_price"]
        assert "zone_id" in zone
        assert zone["is_active"] is True
        assert zone["strength"] in ["STRONG", "MEDIUM", "WEAK"]


@pytest.fixture
async def db_session(mock_pool):
    """Pytest fixture for database session."""
    pool, conn = mock_pool
    fixtures = DBFixtures(pool)

    await fixtures.setup_test_db()
    await fixtures.load_test_data()

    yield fixtures

    await fixtures.teardown_test_db()


class TestFixtureIntegration:
    @pytest.mark.asyncio
    async def test_fixture_isolation(self, mock_pool):
        """Test that each test gets clean database state."""
        pool, conn = mock_pool

        # Create two fixture instances
        fixtures1 = DBFixtures(pool)
        fixtures2 = DBFixtures(pool)

        # Load data in first fixture
        data1 = await fixtures1.load_test_data()

        # Clear and load in second fixture
        await fixtures2.clear_tables()
        data2 = await fixtures2.load_test_data()

        # Data should be independent
        assert data1.candles[0] != data2.candles[0]

    @pytest.mark.asyncio
    async def test_fixture_performance(self, mock_pool):
        """Test setup/teardown completes in reasonable time."""
        pool, conn = mock_pool
        fixtures = DBFixtures(pool)

        start = asyncio.get_event_loop().time()
        await fixtures.setup_test_db()
        await fixtures.load_test_data()
        await fixtures.teardown_test_db()
        end = asyncio.get_event_loop().time()

        # Should complete in under 1 second for unit tests
        assert (end - start) < 1.0
