"""
Unit tests for paper bracket order lifecycle.

Tests the OCO behavior and schema-aligned SQL generation without DB access.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.engine.backtest.types import (
    BacktestFill,
    BacktestOrder,
    FillReason,
    OrderSide,
    OrderStatus,
    OrderType,
)
from app.engine.paper.schema import (
    PositionParams,
    build_insert_paper_fill,
    build_insert_paper_order,
    build_upsert_paper_position,
    cancel_oco_siblings_sql,
)


class TestPaperBracketLifecycle:
    """Tests for paper bracket order lifecycle with OCO behavior."""

    @pytest.fixture
    def paper_session_id(self) -> UUID:
        """Create unique paper session ID."""
        return uuid4()

    @pytest.fixture
    def entry_order(self) -> BacktestOrder:
        """Create entry order."""
        return BacktestOrder(
            id=uuid4(),
            client_order_id="paper_entry_1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal("0.01"),
            price=Decimal(50000),
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("0.01"),
            remaining_quantity=Decimal(0),
            reduce_only=False,
            order_time=datetime.now(UTC),
        )

    @pytest.fixture
    def tp_order(self) -> BacktestOrder:
        """Create take-profit order."""
        return BacktestOrder(
            id=uuid4(),
            client_order_id="paper_tp_1",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal(52000),
            status=OrderStatus.NEW,
            filled_quantity=Decimal(0),
            remaining_quantity=Decimal("0.01"),
            reduce_only=True,
            order_time=datetime.now(UTC),
        )

    @pytest.fixture
    def sl_order(self) -> BacktestOrder:
        """Create stop-loss order."""
        return BacktestOrder(
            id=uuid4(),
            client_order_id="paper_sl_1",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            type=OrderType.STOP_MARKET,  # Stop market for SL
            quantity=Decimal("0.01"),
            price=Decimal(49000),
            stop_price=Decimal(49000),
            status=OrderStatus.NEW,
            filled_quantity=Decimal(0),
            remaining_quantity=Decimal("0.01"),
            reduce_only=True,
            order_time=datetime.now(UTC),
        )

    def test_bracket_entry_generates_correct_sql(
        self,
        entry_order: BacktestOrder,
        paper_session_id: UUID,
    ) -> None:
        """Entry order SQL uses schema-aligned columns."""
        sql, params = build_insert_paper_order(entry_order, paper_session_id)

        assert "paper_orders" in sql
        assert "order_time" in sql
        assert "paper_session_id" in sql
        assert paper_session_id in params

    def test_tp_order_has_reduce_only_true(
        self,
        tp_order: BacktestOrder,
        paper_session_id: UUID,
    ) -> None:
        """TP order SQL sets reduce_only=True."""
        _sql, params = build_insert_paper_order(tp_order, paper_session_id)

        assert True in params  # reduce_only=True

    def test_sl_order_has_reduce_only_true(
        self,
        sl_order: BacktestOrder,
        paper_session_id: UUID,
    ) -> None:
        """SL order SQL sets reduce_only=True."""
        _sql, params = build_insert_paper_order(sl_order, paper_session_id)

        assert True in params  # reduce_only=True

    def test_oco_cancel_excludes_filled_order(
        self,
        paper_session_id: UUID,
        tp_order: BacktestOrder,
    ) -> None:
        """OCO cancellation excludes the order that triggered it."""
        sql, params = cancel_oco_siblings_sql(
            paper_session_id,
            tp_order.id,
            symbol="BTCUSDT",
        )

        # Should exclude the filled order ID
        assert tp_order.id in params
        # Should set status to CANCELED
        assert "CANCELED" in params or "CANCELED" in sql


class TestPaperOrdersPersistence:
    """Tests for paper orders persistence with schema columns."""

    def test_orders_use_order_time_column(self) -> None:
        """Paper orders use order_time column per schema (business timestamp)."""
        order = BacktestOrder(
            id=uuid4(),
            client_order_id="test",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_time=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        )
        sql, params = build_insert_paper_order(order, uuid4())

        # order_time is the business timestamp when order was placed
        assert "order_time" in sql
        # Verify the order_time value is in params
        assert order.order_time in params

    def test_orders_use_paper_session_id_not_bracket_order_id(self) -> None:
        """Paper orders use paper_session_id column per schema."""
        order = BacktestOrder(
            id=uuid4(),
            client_order_id="test",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
        )
        sql, _ = build_insert_paper_order(order, uuid4())

        assert "paper_session_id" in sql
        assert "bracket_order_id" not in sql


class TestPaperFillsPersistence:
    """Tests for paper fills persistence with schema columns."""

    @pytest.fixture
    def sample_fill(self) -> BacktestFill:
        """Create sample fill."""
        return BacktestFill(
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
            candle_open_time=datetime.now(UTC),
            candle_high=Decimal(50100),
            candle_low=Decimal(49900),
        )

    def test_fills_use_fill_time_column(self, sample_fill: BacktestFill) -> None:
        """Paper fills use fill_time column per schema."""
        sql, _ = build_insert_paper_fill(sample_fill, position_id=None)

        assert "fill_time" in sql

    def test_fills_use_fill_reason_column(self, sample_fill: BacktestFill) -> None:
        """Paper fills use fill_reason column per schema."""
        sql, _ = build_insert_paper_fill(sample_fill, position_id=None)

        assert "fill_reason" in sql

    def test_fills_include_candle_context(self, sample_fill: BacktestFill) -> None:
        """Paper fills include candle context columns per schema."""
        sql, _ = build_insert_paper_fill(sample_fill, position_id=None)

        assert "candle_open_time" in sql
        assert "candle_high" in sql
        assert "candle_low" in sql


class TestPaperPositionsPersistence:
    """Tests for paper positions persistence with composite key."""

    def test_positions_use_paper_session_id_in_constraint(self) -> None:
        """Paper positions use (symbol, paper_session_id) composite key."""
        params = PositionParams(
            symbol="BTCUSDT",
            paper_session_id=uuid4(),
            side="LONG",
            quantity=Decimal("0.01"),
            entry_price=Decimal(50000),
            mark_price=Decimal(51000),
            unrealized_pnl=Decimal(10),
            realized_pnl=Decimal(0),
            total_fees=Decimal("0.5"),
            total_funding=Decimal(0),
        )
        sql, _ = build_upsert_paper_position(params)

        assert "ON CONFLICT" in sql
        assert "symbol" in sql
        assert "paper_session_id" in sql
