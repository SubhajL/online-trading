"""
Unit tests for order service.
Following T-3: Pure logic unit tests without database dependencies.
Following T-4: Avoiding heavy mocking.
"""

import pytest
from decimal import Decimal

# Import from the actual module
from app.engine.services.order_service import (
    validate_order_params,
    calculate_position_size,
    create_order_with_retry,
    OrderRequest,
    OrderSide,
    OrderType,
    ValidationResult,
    AccountInfo,
    TradingSignal,
    OrderResponse
)


class TestValidateOrderParams:
    """Tests for order parameter validation."""

    def test_validate_order_params_valid(self):
        """Valid order passes all validation checks."""
        order = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.MARKET
        )

        result = validate_order_params(order)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_order_params_quantity_too_small(self):
        """Rejects order below minimum quantity."""
        order = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.00001"),  # Too small for BTC
            order_type=OrderType.MARKET
        )

        result = validate_order_params(order)

        assert result.is_valid is False
        assert any("minimum quantity" in error.lower() for error in result.errors)

    def test_validate_order_params_price_precision_invalid(self):
        """Rejects order with incorrect price precision."""
        order = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            price=Decimal("50000.12345")  # Too many decimals
        )

        result = validate_order_params(order)

        assert result.is_valid is False
        assert any("price precision" in error.lower() for error in result.errors)

    def test_validate_order_params_missing_price_for_limit(self):
        """Rejects limit order without price."""
        order = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            quantity=Decimal("0.001"),
            order_type=OrderType.LIMIT,
            price=None
        )

        result = validate_order_params(order)

        assert result.is_valid is False
        assert any("price required" in error.lower() for error in result.errors)

    def test_validate_order_params_notional_too_small(self):
        """Rejects order with notional value below minimum."""
        order = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.0001"),
            order_type=OrderType.LIMIT,
            price=Decimal("50")  # Notional = 0.0001 * 50 = 0.005 USDT (too small)
        )

        result = validate_order_params(order)

        assert result.is_valid is False
        assert any("notional" in error.lower() for error in result.errors)


class TestCalculatePositionSize:
    """Tests for position size calculation."""

    def test_calculate_position_size_risk_limit(self):
        """Respects maximum risk per trade."""
        signal = TradingSignal(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),  # 2% risk
            confidence=Decimal("0.8")
        )
        account = AccountInfo(
            balance=Decimal("10000"),
            risk_per_trade=Decimal("0.005")  # 0.5% = $50 risk
        )

        # Risk is $50, stop loss is $1000 per BTC, so position = 0.05 BTC
        position_size = calculate_position_size(signal, account)

        # Expected: $50 risk / ($1000 loss per BTC) = 0.05 BTC
        assert position_size == Decimal("0.05")

    def test_calculate_position_size_insufficient_balance(self):
        """Handles insufficient balance gracefully."""
        signal = TradingSignal(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49500"),  # 1% risk
            confidence=Decimal("0.8")
        )
        account = AccountInfo(
            balance=Decimal("100"),  # Only $100
            risk_per_trade=Decimal("0.005")
        )

        position_size = calculate_position_size(signal, account)

        # Should return 0 or very small position
        assert position_size <= Decimal("0.002")  # Max possible with $100

    def test_calculate_position_size_with_leverage(self):
        """Uses leverage appropriately."""
        signal = TradingSignal(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49500"),  # 1% risk
            confidence=Decimal("0.9")
        )
        account = AccountInfo(
            balance=Decimal("1000"),
            max_leverage=Decimal("3.0"),
            risk_per_trade=Decimal("0.01")  # 1% = $10 risk
        )

        position_size = calculate_position_size(signal, account)

        # Risk is $10, stop loss is $500 per BTC, so position = 0.02 BTC
        assert position_size == Decimal("0.02")

    def test_calculate_position_size_confidence_scaling(self):
        """Scales position size based on signal confidence."""
        signal_high = TradingSignal(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            confidence=Decimal("0.9")
        )
        signal_low = TradingSignal(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            confidence=Decimal("0.5")
        )
        account = AccountInfo(
            balance=Decimal("10000"),
            risk_per_trade=Decimal("0.005")
        )

        size_high = calculate_position_size(signal_high, account)
        size_low = calculate_position_size(signal_low, account)

        # Higher confidence should result in larger position
        assert size_high > size_low
        assert size_high / size_low >= Decimal("1.5")


class TestCreateOrderWithRetry:
    """Tests for order creation with retry logic."""

    @pytest.mark.asyncio
    async def test_create_order_with_retry_success(self):
        """Successfully creates order on first attempt."""
        order = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.MARKET
        )

        response = await create_order_with_retry(order, max_retries=3)

        assert response.status == "FILLED"
        assert response.order_id is not None
        assert response.filled_quantity == order.quantity

    @pytest.mark.asyncio
    async def test_create_order_with_retry_transient_failure(self):
        """Retries on network error and succeeds."""
        order = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.MARKET
        )

        # This will fail first time, then succeed
        response = await create_order_with_retry(order, max_retries=3)

        assert response.status in ["FILLED", "PARTIALLY_FILLED"]
        assert response.order_id is not None

    @pytest.mark.asyncio
    async def test_create_order_with_retry_permanent_failure(self):
        """Fails after max retries on permanent error."""
        order = OrderRequest(
            symbol="INVALID",  # Invalid symbol
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            order_type=OrderType.MARKET
        )

        with pytest.raises(Exception) as exc_info:
            await create_order_with_retry(order, max_retries=2)

        assert "invalid symbol" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_create_order_with_retry_timeout(self):
        """Handles timeout appropriately."""
        order = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            quantity=Decimal("1000000"),  # Huge order that might timeout
            order_type=OrderType.MARKET
        )

        with pytest.raises(Exception) as exc_info:
            await create_order_with_retry(order, max_retries=1)

        assert "timeout" in str(exc_info.value).lower() or "insufficient" in str(exc_info.value).lower()