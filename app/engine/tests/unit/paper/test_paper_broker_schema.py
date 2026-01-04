"""
Tests for paper broker schema alignment with db/migrations/020_reports.sql.

These tests ensure the broker correctly maps between Python types and DB schema:
- OrderStatus.CANCELLED → 'CANCELED' (schema uses single L)
- Uses order_time/fill_time not created_at/updated_at
- Uses paper_session_id not bracket_order_id
- FillReason enum values match schema
"""

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
    fill_reason_to_db,
    status_from_db,
    status_to_db,
)


class TestStatusMapping:
    """Tests for order status mapping between Python enums and DB values."""

    def test_status_to_db_maps_cancelled_to_canceled(self) -> None:
        """CANCELLED (double L) maps to CANCELED (single L) for DB."""
        result = status_to_db(OrderStatus.CANCELLED)
        assert result == "CANCELED"

    def test_status_to_db_preserves_other_statuses(self) -> None:
        """Other statuses map to their direct string values."""
        assert status_to_db(OrderStatus.NEW) == "NEW"
        assert status_to_db(OrderStatus.FILLED) == "FILLED"
        assert status_to_db(OrderStatus.PARTIALLY_FILLED) == "PARTIALLY_FILLED"
        assert status_to_db(OrderStatus.REJECTED) == "REJECTED"
        assert status_to_db(OrderStatus.EXPIRED) == "EXPIRED"

    def test_status_from_db_maps_canceled_to_cancelled(self) -> None:
        """CANCELED (single L) from DB maps to CANCELLED (double L) enum."""
        result = status_from_db("CANCELED")
        assert result == OrderStatus.CANCELLED

    def test_status_from_db_preserves_other_statuses(self) -> None:
        """Other DB statuses map to their enum values."""
        assert status_from_db("NEW") == OrderStatus.NEW
        assert status_from_db("FILLED") == OrderStatus.FILLED
        assert status_from_db("PARTIALLY_FILLED") == OrderStatus.PARTIALLY_FILLED


class TestFillReasonMapping:
    """Tests for fill reason enum to DB string mapping."""

    def test_fill_reason_to_db_uses_lowercase(self) -> None:
        """FillReason enum values are lowercase strings matching schema."""
        assert fill_reason_to_db(FillReason.MARKET) == "market"
        assert fill_reason_to_db(FillReason.LIMIT) == "limit"
        assert fill_reason_to_db(FillReason.STOP) == "stop"
        assert fill_reason_to_db(FillReason.LIQUIDATION) == "liquidation"


class TestBuildInsertPaperOrder:
    """Tests for building INSERT SQL for paper_orders table."""

    @pytest.fixture
    def sample_order(self) -> BacktestOrder:
        """Create a sample order for testing."""
        return BacktestOrder(
            id=uuid4(),
            client_order_id="paper_abc123",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            price=Decimal(50000),
            stop_price=None,
            status=OrderStatus.NEW,
            filled_quantity=Decimal(0),
            remaining_quantity=Decimal("0.01"),
            reduce_only=False,
            order_time=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            fill_time=None,
        )

    @pytest.fixture
    def sample_session_id(self) -> UUID:
        """Create a sample paper session ID."""
        return uuid4()

    def test_uses_schema_column_order_time(
        self,
        sample_order: BacktestOrder,
        sample_session_id: UUID,
    ) -> None:
        """SQL uses order_time column for order placement time."""
        sql, params = build_insert_paper_order(sample_order, sample_session_id)
        assert "order_time" in sql
        # order_time should be in params (distinct from created_at audit column)
        assert sample_order.order_time in params

    def test_uses_schema_column_paper_session_id(
        self,
        sample_order: BacktestOrder,
        sample_session_id: UUID,
    ) -> None:
        """SQL uses paper_session_id column, not bracket_order_id."""
        sql, _params = build_insert_paper_order(sample_order, sample_session_id)
        assert "paper_session_id" in sql
        assert "bracket_order_id" not in sql

    def test_uses_schema_column_remaining_quantity(
        self,
        sample_order: BacktestOrder,
        sample_session_id: UUID,
    ) -> None:
        """SQL includes remaining_quantity column."""
        sql, _params = build_insert_paper_order(sample_order, sample_session_id)
        assert "remaining_quantity" in sql

    def test_uses_schema_column_reduce_only(
        self,
        sample_order: BacktestOrder,
        sample_session_id: UUID,
    ) -> None:
        """SQL includes reduce_only column."""
        sql, _params = build_insert_paper_order(sample_order, sample_session_id)
        assert "reduce_only" in sql

    def test_status_maps_cancelled_correctly(self, sample_session_id: UUID) -> None:
        """CANCELLED status is mapped to CANCELED in params."""
        order = BacktestOrder(
            status=OrderStatus.CANCELLED,
            client_order_id="test",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
        )
        _sql, params = build_insert_paper_order(order, sample_session_id)
        # Status should be CANCELED (single L) in params
        assert "CANCELED" in params

    def test_sets_reduce_only_true_for_exit_orders(
        self,
        sample_session_id: UUID,
    ) -> None:
        """Exit orders (reduce_only=True) have correct param."""
        order = BacktestOrder(
            client_order_id="paper_tp_1",
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            reduce_only=True,
        )
        _sql, params = build_insert_paper_order(order, sample_session_id)
        # reduce_only should be True in params
        assert True in params

    def test_returns_correct_param_count(
        self,
        sample_order: BacktestOrder,
        sample_session_id: UUID,
    ) -> None:
        """SQL has correct number of placeholders matching params."""
        sql, params = build_insert_paper_order(sample_order, sample_session_id)
        placeholder_count = sql.count("$")
        assert placeholder_count == len(params)


class TestBuildInsertPaperFill:
    """Tests for building INSERT SQL for paper_fills table."""

    @pytest.fixture
    def sample_fill(self) -> BacktestFill:
        """Create a sample fill for testing."""
        return BacktestFill(
            id=uuid4(),
            order_id=uuid4(),
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
            price=Decimal(50000),
            fee=Decimal("0.5"),
            slippage=Decimal("0.1"),
            fill_time=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            fill_reason=FillReason.MARKET,
            candle_open_time=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            candle_high=Decimal(50100),
            candle_low=Decimal(49900),
        )

    def test_uses_schema_column_fill_time(self, sample_fill: BacktestFill) -> None:
        """SQL uses fill_time column, not timestamp."""
        sql, _params = build_insert_paper_fill(sample_fill, position_id=None)
        assert "fill_time" in sql
        assert "timestamp" not in sql.split("VALUES")[0]

    def test_uses_schema_column_fill_reason(self, sample_fill: BacktestFill) -> None:
        """SQL uses fill_reason column, not reason."""
        sql, _params = build_insert_paper_fill(sample_fill, position_id=None)
        assert "fill_reason" in sql

    def test_includes_candle_context_columns(self, sample_fill: BacktestFill) -> None:
        """SQL includes candle context columns."""
        sql, _params = build_insert_paper_fill(sample_fill, position_id=None)
        assert "candle_open_time" in sql
        assert "candle_high" in sql
        assert "candle_low" in sql

    def test_fill_reason_uses_lowercase_enum_value(
        self,
        sample_fill: BacktestFill,
    ) -> None:
        """Fill reason param uses lowercase string value."""
        _sql, params = build_insert_paper_fill(sample_fill, position_id=None)
        # FillReason.MARKET should become "market"
        assert "market" in params

    def test_includes_position_id_when_provided(
        self,
        sample_fill: BacktestFill,
    ) -> None:
        """SQL includes position_id when provided."""
        position_id = uuid4()
        sql, params = build_insert_paper_fill(sample_fill, position_id=position_id)
        assert "position_id" in sql
        assert position_id in params


class TestBuildUpsertPaperPosition:
    """Tests for building UPSERT SQL for paper_positions table."""

    @pytest.fixture
    def sample_position_params(self) -> PositionParams:
        """Create sample position parameters."""
        return PositionParams(
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

    def test_uses_composite_key_for_conflict(
        self,
        sample_position_params: PositionParams,
    ) -> None:
        """Upsert uses (symbol, paper_session_id) as unique constraint."""
        sql, _ = build_upsert_paper_position(sample_position_params)
        assert "ON CONFLICT" in sql
        assert "symbol" in sql
        assert "paper_session_id" in sql

    def test_uses_schema_column_paper_session_id(
        self,
        sample_position_params: PositionParams,
    ) -> None:
        """SQL uses paper_session_id column."""
        sql, _ = build_upsert_paper_position(sample_position_params)
        assert "paper_session_id" in sql

    def test_uses_schema_position_columns(
        self,
        sample_position_params: PositionParams,
    ) -> None:
        """SQL uses schema-aligned column names."""
        sql, _ = build_upsert_paper_position(sample_position_params)
        assert "quantity" in sql
        assert "entry_price" in sql
        assert "mark_price" in sql
        assert "unrealized_pnl" in sql
        assert "realized_pnl" in sql


class TestCancelOcoSiblings:
    """Tests for OCO sibling cancellation SQL generation."""

    def test_generates_update_sql_for_same_session(self) -> None:
        """SQL updates orders in same paper_session_id."""
        paper_session_id = uuid4()
        filled_order_id = uuid4()
        sql, _ = cancel_oco_siblings_sql(
            paper_session_id,
            filled_order_id,
            symbol="BTCUSDT",
        )
        assert "UPDATE paper_orders" in sql
        assert "paper_session_id" in sql

    def test_excludes_filled_order_from_cancellation(self) -> None:
        """SQL excludes the order that was just filled."""
        paper_session_id = uuid4()
        filled_order_id = uuid4()
        sql, _ = cancel_oco_siblings_sql(
            paper_session_id,
            filled_order_id,
            symbol="BTCUSDT",
        )
        assert "!=" in sql or "<>" in sql or "NOT" in sql

    def test_sets_status_to_canceled(self) -> None:
        """SQL sets status to CANCELED (single L)."""
        paper_session_id = uuid4()
        filled_order_id = uuid4()
        sql, params = cancel_oco_siblings_sql(
            paper_session_id,
            filled_order_id,
            symbol="BTCUSDT",
        )
        assert "CANCELED" in params or "CANCELED" in sql

    def test_only_cancels_active_orders(self) -> None:
        """SQL only affects orders with active status (NEW)."""
        paper_session_id = uuid4()
        filled_order_id = uuid4()
        sql, params = cancel_oco_siblings_sql(
            paper_session_id,
            filled_order_id,
            symbol="BTCUSDT",
        )
        assert "NEW" in sql or "NEW" in params
