"""
CRITICAL: Order validation tests to ensure orders are properly formatted for exchange.

These tests verify that our orders will pass exchange validation:
1. Prices are rounded to tick size
2. Quantities are rounded to step size
3. Minimum notional values are met
4. Values are within min/max bounds
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, MagicMock

from app.engine.decision.order_formatter import OrderFormatter, ExchangeInfo


class TestOrderFormatter:
    """Test order formatting for exchange compatibility."""

    @pytest.fixture
    def btc_exchange_info(self):
        """Bitcoin exchange info matching router tests."""
        return ExchangeInfo(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            price_tick_size=Decimal("0.01"),
            price_min=Decimal("0.01"),
            price_max=Decimal("1000000"),
            qty_step_size=Decimal("0.00001"),
            qty_min=Decimal("0.0001"),
            qty_max=Decimal("9000"),
            min_notional=Decimal("10"),
        )

    @pytest.fixture
    def eth_exchange_info(self):
        """Ethereum exchange info."""
        return ExchangeInfo(
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            price_tick_size=Decimal("0.01"),
            price_min=Decimal("0.01"),
            price_max=Decimal("100000"),
            qty_step_size=Decimal("0.001"),
            qty_min=Decimal("0.001"),
            qty_max=Decimal("10000"),
            min_notional=Decimal("10"),
        )

    @pytest.fixture
    def formatter(self, btc_exchange_info, eth_exchange_info):
        """Create formatter with exchange info."""
        exchange_info = {
            "BTCUSDT": btc_exchange_info,
            "ETHUSDT": eth_exchange_info,
        }
        return OrderFormatter(exchange_info)

    def test_round_price_to_tick_size(self, formatter):
        """Test price rounding to tick size."""
        test_cases = [
            # (symbol, raw_price, expected)
            ("BTCUSDT", Decimal("50000.12345"), Decimal("50000.12")),
            ("BTCUSDT", Decimal("50000.999"), Decimal("50000.99")),
            ("BTCUSDT", Decimal("50000.00"), Decimal("50000.00")),
            ("ETHUSDT", Decimal("3456.789"), Decimal("3456.78")),
        ]

        for symbol, raw_price, expected in test_cases:
            rounded = formatter.round_price(symbol, raw_price)
            assert rounded == expected, f"{symbol}: {raw_price} -> {rounded} != {expected}"

    def test_round_quantity_to_step_size(self, formatter):
        """Test quantity rounding to step size."""
        test_cases = [
            # (symbol, raw_qty, expected)
            ("BTCUSDT", Decimal("0.123456789"), Decimal("0.12345")),  # Step: 0.00001
            ("BTCUSDT", Decimal("1.000009"), Decimal("1.00000")),
            ("ETHUSDT", Decimal("1.23456"), Decimal("1.234")),  # Step: 0.001
            ("ETHUSDT", Decimal("10.9999"), Decimal("10.999")),
        ]

        for symbol, raw_qty, expected in test_cases:
            rounded = formatter.round_quantity(symbol, raw_qty)
            assert rounded == expected, f"{symbol}: {raw_qty} -> {rounded} != {expected}"

    def test_validate_min_notional(self, formatter):
        """Test minimum notional value validation."""
        # BTC at $50k, min notional $10
        test_cases = [
            # (symbol, price, quantity, should_pass)
            ("BTCUSDT", Decimal("50000"), Decimal("0.0001"), False),  # $5 < $10
            ("BTCUSDT", Decimal("50000"), Decimal("0.0002"), True),   # $10 = $10
            ("BTCUSDT", Decimal("50000"), Decimal("0.001"), True),    # $50 > $10
            ("ETHUSDT", Decimal("3000"), Decimal("0.003"), False),    # $9 < $10
            ("ETHUSDT", Decimal("3000"), Decimal("0.004"), True),     # $12 > $10
        ]

        for symbol, price, quantity, should_pass in test_cases:
            is_valid, reason = formatter.validate_notional(symbol, price, quantity)
            assert is_valid == should_pass, f"{symbol} @ {price} x {quantity}: {reason}"

    def test_validate_price_bounds(self, formatter):
        """Test price is within min/max bounds."""
        test_cases = [
            # (symbol, price, should_pass)
            ("BTCUSDT", Decimal("0.001"), False),      # Below min
            ("BTCUSDT", Decimal("0.01"), True),        # At min
            ("BTCUSDT", Decimal("50000"), True),       # Normal
            ("BTCUSDT", Decimal("1000000"), True),     # At max
            ("BTCUSDT", Decimal("1000001"), False),    # Above max
        ]

        for symbol, price, should_pass in test_cases:
            is_valid, reason = formatter.validate_price(symbol, price)
            assert is_valid == should_pass, f"{symbol} @ {price}: {reason}"

    def test_validate_quantity_bounds(self, formatter):
        """Test quantity is within min/max bounds."""
        test_cases = [
            # (symbol, quantity, should_pass)
            ("BTCUSDT", Decimal("0.00001"), False),    # Below min
            ("BTCUSDT", Decimal("0.0001"), True),      # At min
            ("BTCUSDT", Decimal("1"), True),           # Normal
            ("BTCUSDT", Decimal("9000"), True),        # At max
            ("BTCUSDT", Decimal("9001"), False),       # Above max
        ]

        for symbol, quantity, should_pass in test_cases:
            is_valid, reason = formatter.validate_quantity(symbol, quantity)
            assert is_valid == should_pass, f"{symbol} x {quantity}: {reason}"

    def test_format_complete_order(self, formatter):
        """Test complete order formatting."""
        # Raw order from decision engine
        raw_order = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "price": Decimal("50123.456789"),
            "quantity": Decimal("0.123456789"),
            "stop_loss": Decimal("49000.111"),
            "take_profit": Decimal("52000.999"),
        }

        formatted = formatter.format_order(raw_order)

        # Check all values are properly rounded
        assert formatted["price"] == Decimal("50123.45")  # Rounded down to tick
        assert formatted["quantity"] == Decimal("0.12345")  # Rounded down to step
        assert formatted["stop_loss"] == Decimal("49000.11")
        assert formatted["take_profit"] == Decimal("52000.99")

        # Validate the formatted order
        is_valid, errors = formatter.validate_order(formatted)
        assert is_valid, f"Order validation failed: {errors}"

    def test_futures_order_formatting(self, formatter):
        """Test futures-specific order formatting."""
        # Futures order with leverage
        futures_order = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "MARKET",
            "quantity": Decimal("0.05"),
            "leverage": Decimal("3"),
            "reduce_only": False,
        }

        formatted = formatter.format_futures_order(futures_order)

        # Check futures-specific fields
        assert formatted["quantity"] == Decimal("0.05")
        assert formatted["leverage"] == Decimal("3")
        assert "reduce_only" in formatted

    def test_adjust_quantity_for_min_notional(self, formatter):
        """Test quantity adjustment to meet min notional."""
        # If price is $50k and min notional is $10, min qty is 0.0002
        symbol = "BTCUSDT"
        price = Decimal("50000")

        # Too small quantity
        small_qty = Decimal("0.0001")
        adjusted_qty = formatter.adjust_quantity_for_notional(symbol, price, small_qty)

        # Should be increased to meet min notional
        notional = adjusted_qty * price
        assert notional >= Decimal("10"), f"Adjusted notional {notional} < $10"

        # Should be rounded to step size
        assert adjusted_qty % Decimal("0.00001") == 0

    def test_unknown_symbol_handling(self, formatter):
        """Test handling of unknown symbols."""
        unknown_symbol = "UNKNOWN"

        # Should raise or return None for unknown symbols
        with pytest.raises(ValueError, match="Unknown symbol"):
            formatter.round_price(unknown_symbol, Decimal("100"))

    def test_extreme_precision_handling(self, formatter):
        """Test handling of extreme decimal precision."""
        # Python Decimal can have arbitrary precision
        high_precision_price = Decimal("50000.123456789012345678901234567890")

        rounded = formatter.round_price("BTCUSDT", high_precision_price)

        # Should round to exactly tick size precision
        assert rounded == Decimal("50000.12")
        assert str(rounded) == "50000.12"  # String representation is clean


class TestOrderFormatterIntegration:
    """Integration tests with decision engine output."""

    def test_format_decision_engine_output(self):
        """Test formatting real decision engine output."""
        from app.engine.models import TradingDecision
        from datetime import datetime

        # Create mock exchange info
        exchange_info = {
            "BTCUSDT": ExchangeInfo(
                symbol="BTCUSDT",
                base_asset="BTC",
                quote_asset="USDT",
                price_tick_size=Decimal("0.01"),
                price_min=Decimal("0.01"),
                price_max=Decimal("1000000"),
                qty_step_size=Decimal("0.00001"),
                qty_min=Decimal("0.0001"),
                qty_max=Decimal("9000"),
                min_notional=Decimal("10"),
            )
        }

        formatter = OrderFormatter(exchange_info)

        # Decision from engine
        decision = TradingDecision(
            venue="SPOT",
            symbol="BTCUSDT",
            action="BUY",
            entry_price=Decimal("50234.5678"),
            quantity=Decimal("0.00456789"),  # From position sizer
            stop_loss=Decimal("49123.4567"),
            take_profit=Decimal("51345.6789"),
            confidence=Decimal("0.85"),
            reasoning="Strong bullish signal",
            timestamp=datetime.now(),
        )

        # Format for exchange
        order_dict = {
            "symbol": decision.symbol,
            "side": decision.action,
            "type": "LIMIT",
            "price": decision.entry_price,
            "quantity": decision.quantity,
            "stop_loss": decision.stop_loss,
            "take_profit": decision.take_profit,
        }

        formatted = formatter.format_order(order_dict)

        # Verify all exchange requirements are met
        is_valid, errors = formatter.validate_order(formatted)
        assert is_valid, f"Order failed validation: {errors}"

        # Check specific values
        assert formatted["price"] == Decimal("50234.56")
        assert formatted["quantity"] == Decimal("0.00456")  # Rounded down

        # Verify notional value
        notional = formatted["price"] * formatted["quantity"]
        assert notional >= Decimal("10"), f"Notional {notional} below minimum"

    def test_position_sizer_compatibility(self):
        """Test that position sizer output is compatible with exchange."""
        from app.engine.decision.position_sizer import PositionSizer, PositionSizeConfig

        # Position sizer config
        config = PositionSizeConfig(
            fixed_risk_pct=Decimal("0.005"),
            max_position_pct=Decimal("0.02"),
            min_position_size=Decimal("0.0001"),
        )
        sizer = PositionSizer(config)

        # Calculate position
        account = Decimal("10000")
        entry = Decimal("50000")
        stop = Decimal("49000")

        position_size = sizer.calculate_position_size(
            account_balance=account,
            entry_price=entry,
            stop_loss=stop,
            confidence=Decimal("1.0"),
        )

        # Create formatter
        exchange_info = {
            "BTCUSDT": ExchangeInfo(
                symbol="BTCUSDT",
                base_asset="BTC",
                quote_asset="USDT",
                price_tick_size=Decimal("0.01"),
                price_min=Decimal("0.01"),
                price_max=Decimal("1000000"),
                qty_step_size=Decimal("0.00001"),
                qty_min=Decimal("0.0001"),
                qty_max=Decimal("9000"),
                min_notional=Decimal("10"),
            )
        }
        formatter = OrderFormatter(exchange_info)

        # Format the position size
        rounded_qty = formatter.round_quantity("BTCUSDT", position_size)

        # Verify it meets exchange requirements
        is_valid, reason = formatter.validate_quantity("BTCUSDT", rounded_qty)
        assert is_valid, f"Position size {rounded_qty} invalid: {reason}"

        # Check notional
        notional = rounded_qty * entry
        assert notional >= Decimal("10"), f"Position too small: ${notional}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
