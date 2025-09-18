"""
Unit tests for legacy adapter.
Following T-3: Pure logic unit tests without database dependencies.
Following T-4: Avoiding heavy mocking.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any

# Import from the actual module (will create after tests)
from app.engine.adapters.legacy_adapter import (
    adapt_legacy_order_format,
    adapt_legacy_position_format,
    adapt_position_to_legacy_format,
    adapt_order_to_legacy_format
)
from app.engine.services.order_service import (
    OrderRequest,
    OrderSide,
    OrderType,
    OrderResponse
)
from app.engine.services.position_tracker import (
    Position,
    PositionSide
)


class TestAdaptLegacyOrderFormat:
    """Tests for converting legacy order format to new format."""

    def test_adapt_legacy_order_format_market_buy(self):
        """Converts legacy market buy order."""
        legacy_order = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": "0.001",
            "type": "MARKET",
            "price": None,
            "stopPrice": None
        }

        order = adapt_legacy_order_format(legacy_order)

        assert order.symbol == "BTCUSDT"
        assert order.side == OrderSide.BUY
        assert order.quantity == Decimal("0.001")
        assert order.order_type == OrderType.MARKET
        assert order.price is None
        assert order.stop_price is None

    def test_adapt_legacy_order_format_limit_sell(self):
        """Converts legacy limit sell order."""
        legacy_order = {
            "symbol": "ETHUSDT",
            "side": "SELL",
            "quantity": "0.5",
            "type": "LIMIT",
            "price": "3500.50",
            "stopPrice": None
        }

        order = adapt_legacy_order_format(legacy_order)

        assert order.symbol == "ETHUSDT"
        assert order.side == OrderSide.SELL
        assert order.quantity == Decimal("0.5")
        assert order.order_type == OrderType.LIMIT
        assert order.price == Decimal("3500.50")
        assert order.stop_price is None

    def test_adapt_legacy_order_format_stop_market(self):
        """Converts legacy stop market order."""
        legacy_order = {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "quantity": "0.1",
            "type": "STOP_MARKET",
            "price": None,
            "stopPrice": "49000"
        }

        order = adapt_legacy_order_format(legacy_order)

        assert order.symbol == "BTCUSDT"
        assert order.side == OrderSide.SELL
        assert order.quantity == Decimal("0.1")
        assert order.order_type == OrderType.STOP_MARKET
        assert order.price is None
        assert order.stop_price == Decimal("49000")

    def test_adapt_legacy_order_format_missing_required_fields(self):
        """Raises error for missing required fields."""
        legacy_order = {
            "symbol": "BTCUSDT",
            "side": "BUY"
            # Missing quantity and type
        }

        with pytest.raises(ValueError) as exc_info:
            adapt_legacy_order_format(legacy_order)

        assert "missing required field" in str(exc_info.value).lower()

    def test_adapt_legacy_order_format_invalid_side(self):
        """Raises error for invalid side."""
        legacy_order = {
            "symbol": "BTCUSDT",
            "side": "INVALID",
            "quantity": "0.1",
            "type": "MARKET"
        }

        with pytest.raises(ValueError) as exc_info:
            adapt_legacy_order_format(legacy_order)

        assert "invalid side" in str(exc_info.value).lower()


class TestAdaptLegacyPositionFormat:
    """Tests for converting legacy position format to new format."""

    def test_adapt_legacy_position_format_long(self):
        """Converts legacy long position."""
        legacy_pos = {
            "symbol": "BTCUSDT",
            "side": "LONG",
            "quantity": "0.1",
            "entryPrice": "50000",
            "realizedPnl": "-10.5",
            "commission": "10.5",
            "openTime": "2024-01-15T10:30:00Z"
        }

        position = adapt_legacy_position_format(legacy_pos)

        assert position.symbol == "BTCUSDT"
        assert position.side == PositionSide.LONG
        assert position.quantity == Decimal("0.1")
        assert position.entry_price == Decimal("50000")
        assert position.realized_pnl == Decimal("-10.5")
        assert position.total_commission == Decimal("10.5")
        assert position.open_time.year == 2024
        assert position.open_time.month == 1
        assert position.open_time.day == 15

    def test_adapt_legacy_position_format_short_with_stops(self):
        """Converts legacy short position with stop loss and take profit."""
        legacy_pos = {
            "symbol": "ETHUSDT",
            "side": "SHORT",
            "quantity": "1.5",
            "entryPrice": "3500",
            "realizedPnl": "0",
            "commission": "3.5",
            "openTime": "2024-01-15T10:30:00Z",
            "stopLoss": "3600",
            "takeProfit": "3300"
        }

        position = adapt_legacy_position_format(legacy_pos)

        assert position.symbol == "ETHUSDT"
        assert position.side == PositionSide.SHORT
        assert position.quantity == Decimal("1.5")
        assert position.entry_price == Decimal("3500")
        assert position.stop_loss == Decimal("3600")
        assert position.take_profit == Decimal("3300")

    def test_adapt_legacy_position_format_closed(self):
        """Converts closed position."""
        legacy_pos = {
            "symbol": "BTCUSDT",
            "side": "LONG",
            "quantity": "0",
            "entryPrice": "50000",
            "realizedPnl": "200",
            "commission": "20",
            "openTime": "2024-01-15T10:30:00Z",
            "isClosed": True,
            "closeTime": "2024-01-15T11:30:00Z"
        }

        position = adapt_legacy_position_format(legacy_pos)

        assert position.quantity == Decimal("0")
        assert position.is_closed is True
        assert position.close_time is not None
        assert position.realized_pnl == Decimal("200")

    def test_adapt_legacy_position_format_defaults(self):
        """Uses sensible defaults for missing optional fields."""
        legacy_pos = {
            "symbol": "BTCUSDT",
            "side": "LONG",
            "quantity": "0.1",
            "entryPrice": "50000",
            "openTime": "2024-01-15T10:30:00Z"
        }

        position = adapt_legacy_position_format(legacy_pos)

        assert position.realized_pnl == Decimal("0")
        assert position.total_commission == Decimal("0")
        assert position.stop_loss is None
        assert position.take_profit is None
        assert position.is_closed is False


class TestAdaptToLegacyFormat:
    """Tests for converting new format back to legacy format."""

    def test_adapt_order_to_legacy_format(self):
        """Converts OrderRequest to legacy dictionary format."""
        order = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            price=Decimal("50000.50")
        )

        legacy = adapt_order_to_legacy_format(order)

        assert legacy["symbol"] == "BTCUSDT"
        assert legacy["side"] == "BUY"
        assert legacy["quantity"] == "0.001"
        assert legacy["type"] == "LIMIT"
        assert legacy["price"] == "50000.50"
        assert legacy["stopPrice"] is None

    def test_adapt_position_to_legacy_format(self):
        """Converts Position to legacy dictionary format."""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            realized_pnl=Decimal("100.50"),
            total_commission=Decimal("10.50"),
            open_time=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            stop_loss=Decimal("51000"),
            take_profit=Decimal("48000")
        )

        legacy = adapt_position_to_legacy_format(position)

        assert legacy["symbol"] == "BTCUSDT"
        assert legacy["side"] == "SHORT"
        assert legacy["quantity"] == "0.1"
        assert legacy["entryPrice"] == "50000"
        assert legacy["realizedPnl"] == "100.50"
        assert legacy["commission"] == "10.50"
        assert legacy["stopLoss"] == "51000"
        assert legacy["takeProfit"] == "48000"
        assert legacy["isClosed"] is False
        assert "openTime" in legacy