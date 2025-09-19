"""Unit tests for updated timescale.py with ConnectionPool and Decimal precision."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

import pytest
from asyncpg import Connection

from app.engine.adapters.db import timescale
from app.engine.adapters.db.connection_pool import ConnectionPool, DBConfig
from app.engine.types import (
    Candle,
    TimeFrame,
    TechnicalIndicators,
    SupplyDemandZone,
    ZoneType,
)


@pytest.fixture
def db_config():
    """Database configuration for testing."""
    return DBConfig(
        host="localhost",
        port=5432,
        database="test_db",
        username="test_user",
        password="test_password",
    )


@pytest.fixture
def mock_connection():
    """Mock database connection."""
    conn = AsyncMock(spec=Connection)
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock()
    conn.fetchval = AsyncMock()
    return conn


@pytest.fixture
def mock_pool(mock_connection):
    """Mock connection pool."""
    pool = MagicMock(spec=ConnectionPool)

    @asynccontextmanager
    async def mock_acquire():
        yield mock_connection

    pool.acquire = mock_acquire
    return pool


@pytest.fixture
def sample_candle():
    """Sample candle for testing."""
    return Candle(
        symbol="BTCUSDT",
        timeframe=TimeFrame.H1,
        open_time=datetime.utcnow(),
        close_time=datetime.utcnow() + timedelta(hours=1),
        open_price=Decimal("50000.00"),
        high_price=Decimal("51000.00"),
        low_price=Decimal("49000.00"),
        close_price=Decimal("50500.00"),
        volume=Decimal("100.5"),
        quote_volume=Decimal("5050000.00"),
        trades=1000,
        taker_buy_base_volume=Decimal("50.25"),
        taker_buy_quote_volume=Decimal("2525000.00"),
    )


class TestPoolManagement:
    @pytest.mark.asyncio
    async def test_initialize_pool(self, db_config):
        """Test pool initialization."""
        with patch(
            "app.engine.adapters.db.timescale.ConnectionPool"
        ) as mock_pool_class:
            mock_pool = MagicMock()
            mock_pool.initialize = AsyncMock()
            mock_pool_class.return_value = mock_pool

            await timescale.initialize_pool(db_config)

            mock_pool_class.assert_called_once_with(db_config)
            mock_pool.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_pool(self):
        """Test pool closure."""
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()

        # Set the global pool
        timescale._pool = mock_pool

        await timescale.close_pool()

        mock_pool.close.assert_called_once()
        assert timescale._pool is None

    def test_get_pool_not_initialized(self):
        """Test getting pool when not initialized."""
        timescale._pool = None

        with pytest.raises(RuntimeError, match="Database pool not initialized"):
            timescale.get_pool()

    def test_get_pool_initialized(self, mock_pool):
        """Test getting pool when initialized."""
        timescale._pool = mock_pool

        pool = timescale.get_pool()

        assert pool == mock_pool


class TestCandleOperations:
    @pytest.mark.asyncio
    async def test_upsert_candle_success(
        self, mock_pool, mock_connection, sample_candle
    ):
        """Test successful candle upsert."""
        timescale._pool = mock_pool

        result = await timescale.upsert_candle(sample_candle)

        assert result is True
        mock_connection.execute.assert_called_once()

        # Verify SQL and parameters
        call_args = mock_connection.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]

        assert "INSERT INTO candles" in sql
        assert "ON CONFLICT" in sql
        assert params[0] == "binance"  # venue
        assert params[1] == sample_candle.symbol
        assert params[2] == sample_candle.timeframe.value
        assert params[4] == sample_candle.close_time
        assert params[5] == sample_candle.open_price  # Should be Decimal

    @pytest.mark.asyncio
    async def test_upsert_candle_error(self, mock_pool, mock_connection, sample_candle):
        """Test candle upsert with error."""
        timescale._pool = mock_pool
        mock_connection.execute.side_effect = Exception("Database error")

        result = await timescale.upsert_candle(sample_candle)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_candles_decimal_precision(self, mock_pool, mock_connection):
        """Test get_candles preserves Decimal precision."""
        timescale._pool = mock_pool

        # Mock database response
        mock_connection.fetch.return_value = [
            {
                "venue": "binance",
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "open_time": datetime.utcnow(),
                "close_time": datetime.utcnow() + timedelta(hours=1),
                "open_price": Decimal("50000.12345678"),
                "high_price": Decimal("51000.87654321"),
                "low_price": Decimal("49000.11111111"),
                "close_price": Decimal("50500.99999999"),
                "volume": Decimal("100.12345678"),
                "quote_volume": Decimal("5050000.12345678"),
                "trades": 1000,
                "taker_buy_base_volume": Decimal("50.12345678"),
                "taker_buy_quote_volume": Decimal("2525000.12345678"),
            }
        ]

        candles = await timescale.get_candles(symbol="BTCUSDT", timeframe=TimeFrame.H1)

        assert len(candles) == 1
        candle = candles[0]

        # Verify all Decimal fields preserved
        assert isinstance(candle["open_price"], Decimal)
        assert isinstance(candle["high_price"], Decimal)
        assert isinstance(candle["low_price"], Decimal)
        assert isinstance(candle["close_price"], Decimal)
        assert isinstance(candle["volume"], Decimal)
        assert isinstance(candle["quote_volume"], Decimal)
        assert isinstance(candle["taker_buy_base_volume"], Decimal)
        assert isinstance(candle["taker_buy_quote_volume"], Decimal)

        # Verify precision maintained
        assert candle["open_price"] == Decimal("50000.12345678")
        assert candle["high_price"] == Decimal("51000.87654321")

    @pytest.mark.asyncio
    async def test_get_candles_with_filters(self, mock_pool, mock_connection):
        """Test get_candles with time filters."""
        timescale._pool = mock_pool
        mock_connection.fetch.return_value = []

        start_time = datetime.utcnow() - timedelta(days=1)
        end_time = datetime.utcnow()

        await timescale.get_candles(
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            start_time=start_time,
            end_time=end_time,
            limit=500,
        )

        # Verify SQL construction
        call_args = mock_connection.fetch.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]

        assert "AND open_time >=" in sql
        assert "AND open_time <=" in sql
        assert "LIMIT" in sql
        assert params[3] == start_time
        assert params[4] == end_time
        assert params[5] == 500


class TestOrderOperations:
    @pytest.mark.asyncio
    async def test_upsert_order_decimal_conversion(self, mock_pool, mock_connection):
        """Test order upsert converts to Decimal properly."""
        timescale._pool = mock_pool

        order_data = {
            "order_id": "12345",
            "client_order_id": "client_12345",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "quantity": "0.01",  # String input
            "price": 50000.5,  # Float input
            "filled_quantity": 0.005,  # Float input
            "average_fill_price": "50100.25",  # String input
            "commission": "0.00001",  # String input
        }

        result = await timescale.upsert_order(order_data)

        assert result is True

        # Verify Decimal conversion
        call_args = mock_connection.execute.call_args
        params = call_args[0][1:]

        assert params[6] == Decimal("0.01")  # quantity
        assert params[7] == Decimal("50000.5")  # price
        assert params[10] == Decimal("0.005")  # filled_quantity
        assert params[11] == Decimal("50100.25")  # average_fill_price
        assert params[15] == Decimal("0.00001")  # commission

    @pytest.mark.asyncio
    async def test_upsert_order_optional_fields(self, mock_pool, mock_connection):
        """Test order upsert with minimal required fields."""
        timescale._pool = mock_pool

        order_data = {
            "client_order_id": "client_12345",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "quantity": "0.01",
        }

        result = await timescale.upsert_order(order_data)

        assert result is True

        # Verify optional fields are None or defaults
        call_args = mock_connection.execute.call_args
        params = call_args[0][1:]

        assert params[0] is None  # order_id
        assert params[7] is None  # price
        assert params[8] is None  # stop_price
        assert params[9] == "NEW"  # status default
        assert params[10] == Decimal("0")  # filled_quantity default
        assert params[11] is None  # average_fill_price
        assert params[15] == Decimal("0")  # commission default


class TestPositionOperations:
    @pytest.mark.asyncio
    async def test_get_active_positions_decimal_preservation(
        self, mock_pool, mock_connection
    ):
        """Test positions query preserves Decimal types."""
        timescale._pool = mock_pool

        mock_connection.fetch.return_value = [
            {
                "position_id": "pos_123",
                "venue": "binance",
                "symbol": "BTCUSDT",
                "side": "LONG",
                "size": Decimal("0.1"),
                "entry_price": Decimal("50000.50"),
                "current_price": Decimal("51000.75"),
                "unrealized_pnl": Decimal("100.025"),
                "realized_pnl": Decimal("0.0"),
                "margin_used": Decimal("1000.10"),
                "leverage": Decimal("5.0"),
                "opened_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "stop_loss": Decimal("49000.00"),
                "take_profit": Decimal("52000.00"),
                "decision_id": "dec_456",
            }
        ]

        positions = await timescale.get_active_positions()

        assert len(positions) == 1
        position = positions[0]

        # Verify all Decimal fields preserved
        decimal_fields = [
            "size",
            "entry_price",
            "current_price",
            "unrealized_pnl",
            "realized_pnl",
            "margin_used",
            "leverage",
            "stop_loss",
            "take_profit",
        ]

        for field in decimal_fields:
            assert isinstance(position[field], Decimal)

        # Verify precision
        assert position["entry_price"] == Decimal("50000.50")
        assert position["unrealized_pnl"] == Decimal("100.025")

    @pytest.mark.asyncio
    async def test_get_active_positions_with_symbol_filter(
        self, mock_pool, mock_connection
    ):
        """Test positions query with symbol filter."""
        timescale._pool = mock_pool
        mock_connection.fetch.return_value = []

        await timescale.get_active_positions(symbol="ETHUSDT")

        # Verify SQL includes symbol filter
        call_args = mock_connection.fetch.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]

        assert "AND symbol = $2" in sql
        assert params[1] == "ETHUSDT"


# Cleanup global state after tests
@pytest.fixture(autouse=True)
def cleanup_global_pool():
    """Clean up global pool after each test."""
    yield
    timescale._pool = None
