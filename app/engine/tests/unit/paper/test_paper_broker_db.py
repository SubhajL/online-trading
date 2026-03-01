"""Unit tests for paper broker database operations.

Tests verify that broker methods call the correct schema-aligned SQL builders
and execute the generated SQL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.engine.backtest.types import (
    BacktestFill,
    BacktestOrder,
    FillReason,
    OrderSide,
    OrderStatus,
    OrderType,
)
from app.engine.paper.broker import PaperBroker, PaperPosition, PlaceBracketRequest

# Accessing broker internals is intentional in these SQL-shape tests.
# ruff: noqa: SLF001

EXPECTED_BRACKET_ORDER_COUNT = 3


@pytest.fixture
def mock_pool() -> tuple[MagicMock, AsyncMock]:
    """Create a mock database pool."""
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None
    return pool, conn


@pytest.fixture
def paper_broker(mock_pool: tuple[MagicMock, AsyncMock]) -> PaperBroker:
    """Create a PaperBroker with mocked database pool."""
    pool, _conn = mock_pool
    broker = PaperBroker(
        database_url="postgresql://test:test@localhost/test",
    )
    broker.db_pool = pool
    return broker


class TestInsertPaperOrder:
    """Tests for _insert_paper_order method."""

    @pytest.mark.asyncio
    async def test_insert_paper_order_uses_paper_session_id(
        self,
        paper_broker: PaperBroker,
        mock_pool: tuple[MagicMock, AsyncMock],
    ) -> None:
        """Order is inserted with provided bracket_id."""
        _pool, conn = mock_pool
        bracket_id = uuid4()
        order = BacktestOrder(
            id=uuid4(),
            client_order_id=f"test_{uuid4().hex[:8]}",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.01"),
            status=OrderStatus.NEW,
            order_time=datetime.now(UTC),
        )

        await paper_broker._insert_paper_order(order, bracket_id)

        # Verify execute was called with SQL containing paper_session_id
        conn.execute.assert_called_once()
        call_args = conn.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]

        assert "paper_session_id" in sql
        assert bracket_id in params

    @pytest.mark.asyncio
    async def test_insert_paper_order_uses_order_time_column(
        self,
        paper_broker: PaperBroker,
        mock_pool: tuple[MagicMock, AsyncMock],
    ) -> None:
        """SQL uses order_time column for order placement time."""
        _pool, conn = mock_pool
        order_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        order = BacktestOrder(
            id=uuid4(),
            client_order_id=f"test_{uuid4().hex[:8]}",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal(50000),
            status=OrderStatus.NEW,
            order_time=order_time,
        )

        await paper_broker._insert_paper_order(order, uuid4())

        call_args = conn.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]

        assert "order_time" in sql
        assert order_time in params

    @pytest.mark.asyncio
    async def test_insert_paper_order_sets_reduce_only_for_exits(
        self,
        paper_broker: PaperBroker,
        mock_pool: tuple[MagicMock, AsyncMock],
    ) -> None:
        """TP/SL orders have reduce_only=True in SQL params."""
        _pool, conn = mock_pool

        # TP order (reduce_only=True)
        tp_order = BacktestOrder(
            id=uuid4(),
            client_order_id=f"test_tp_{uuid4().hex[:8]}",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal(55000),
            status=OrderStatus.NEW,
            reduce_only=True,
            order_time=datetime.now(UTC),
        )

        await paper_broker._insert_paper_order(tp_order, uuid4())

        call_args = conn.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]

        assert "reduce_only" in sql
        assert True in params


class TestInsertPaperFill:
    """Tests for _insert_paper_fill method."""

    @pytest.mark.asyncio
    async def test_insert_paper_fill_uses_fill_reason_and_candle_context(
        self,
        paper_broker: PaperBroker,
        mock_pool: tuple[MagicMock, AsyncMock],
    ) -> None:
        """SQL includes fill_reason and candle context columns."""
        _pool, conn = mock_pool
        candle_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        fill = BacktestFill(
            id=uuid4(),
            order_id=uuid4(),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
            price=Decimal(50000),
            fee=Decimal("0.5"),
            slippage=Decimal("0.1"),
            fill_time=datetime.now(UTC),
            fill_reason=FillReason.MARKET,
            candle_open_time=candle_time,
            candle_high=Decimal(50100),
            candle_low=Decimal(49900),
        )

        await paper_broker._insert_paper_fill(fill)

        call_args = conn.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]

        assert "fill_reason" in sql
        assert "candle_open_time" in sql
        assert "candle_high" in sql
        assert "candle_low" in sql
        assert "market" in params  # FillReason.MARKET lowercase
        assert candle_time in params
        assert Decimal(50100) in params
        assert Decimal(49900) in params


class TestUpsertPaperPosition:
    """Tests for _upsert_paper_position method."""

    @pytest.mark.asyncio
    async def test_upsert_paper_position_uses_composite_key(
        self,
        paper_broker: PaperBroker,
        mock_pool: tuple[MagicMock, AsyncMock],
    ) -> None:
        """Upsert uses (symbol, paper_session_id) as unique constraint."""
        _pool, conn = mock_pool
        position = PaperPosition("BTCUSDT", is_futures=False)
        position.net_quantity = Decimal("0.01")
        position.avg_entry_price = Decimal(50000)
        position.unrealized_pnl = Decimal(10)
        position.total_fees = Decimal("0.5")

        bracket_id = uuid4()
        await paper_broker._upsert_paper_position(position, bracket_id)

        call_args = conn.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]

        assert "ON CONFLICT" in sql
        assert "symbol" in sql
        assert "paper_session_id" in sql
        assert "BTCUSDT" in params
        assert bracket_id in params


class TestCancelOcoSiblings:
    """Tests for _cancel_oco_siblings method."""

    @pytest.mark.asyncio
    async def test_cancel_oco_siblings_sets_status_canceled(
        self,
        paper_broker: PaperBroker,
        mock_pool: tuple[MagicMock, AsyncMock],
    ) -> None:
        """SQL updates siblings to CANCELED status."""
        _pool, conn = mock_pool
        filled_order_id = uuid4()
        bracket_id = uuid4()

        # Add some orders to active_orders
        sl_order = BacktestOrder(
            id=uuid4(),
            client_order_id="test_sl",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            status=OrderStatus.NEW,
            reduce_only=True,
        )
        paper_broker.active_orders["test_sl"] = sl_order
        paper_broker._order_bracket_ids["test_sl"] = bracket_id

        await paper_broker._cancel_oco_siblings(
            filled_order_id,
            bracket_id=bracket_id,
            symbol="BTCUSDT",
        )

        call_args = conn.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1:]

        assert "UPDATE paper_orders" in sql
        assert "CANCELED" in params  # Single L per schema
        assert bracket_id in params
        assert "BTCUSDT" in params
        assert filled_order_id in params


class TestBracketLifecycle:
    """Tests for full bracket order lifecycle."""

    @pytest.mark.asyncio
    async def test_place_bracket_creates_orders_with_correct_reduce_only(
        self,
        paper_broker: PaperBroker,
        mock_pool: tuple[MagicMock, AsyncMock],
    ) -> None:
        """Entry has reduce_only=False, TP/SL have reduce_only=True."""
        _pool, conn = mock_pool

        request = PlaceBracketRequest(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("0.01"),
            take_profit_prices=[Decimal(55000)],
            stop_loss_price=Decimal(48000),
            order_type="LIMIT",
            entry_price=Decimal(50000),
        )

        await paper_broker.place_bracket_order(request)

        # Should have 3 orders: entry, 1 TP, 1 SL
        assert conn.execute.call_count == EXPECTED_BRACKET_ORDER_COUNT

        # Check each order's reduce_only flag
        calls = conn.execute.call_args_list
        call_bracket_ids = []
        reduce_only_values = []
        for call in calls:
            params = call[0][1:]
            # reduce_only is at position 13 (0-indexed) in the params
            # Find the boolean value in params
            for param in params:
                if isinstance(param, bool):
                    reduce_only_values.append(param)
                    break
            call_uuids = {p for p in params if isinstance(p, type(uuid4()))}
            call_bracket_ids.append(call_uuids)

        # First order (entry) should have reduce_only=False
        # Second and third (TP, SL) should have reduce_only=True
        assert reduce_only_values[0] is False
        assert reduce_only_values[1] is True
        assert reduce_only_values[2] is True

        # The same bracket_id (paper_session_id) is used for all three orders.
        common = set.intersection(*call_bracket_ids)
        assert len(common) == 1
