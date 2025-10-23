from datetime import datetime
from decimal import Decimal

from app.engine.adapters.alert.alert_formatter import AlertFormatter


class TestAlertFormatter:
    def setup_method(self) -> None:
        self.formatter = AlertFormatter()

    def test_format_decision_alert_long_position(self) -> None:
        decision = {
            "symbol": "BTCUSDT",
            "side": "long",
            "entry_price": Decimal("42000.50"),
            "stop_loss": Decimal("41000.00"),
            "take_profit": Decimal("44000.00"),
            "quantity": Decimal("0.025"),
            "confidence": 0.85,
            "reasons": ["Bullish structure break", "Strong demand zone"],
            "timestamp": datetime(2024, 1, 1, 10, 30, 0),
        }

        result = self.formatter.format_decision(decision)

        assert "🟢 LONG: BTCUSDT" in result
        assert "Entry: $42,000.50" in result
        assert "SL: $41,000.00 (-2.38%)" in result
        assert "TP: $44,000.00 (+4.76%)" in result
        assert "Size: 0.025 BTC" in result
        assert "Confidence: 85%" in result
        assert "• Bullish structure break" in result
        assert "• Strong demand zone" in result

    def test_format_decision_alert_short_position(self) -> None:
        decision = {
            "symbol": "ETHUSDT",
            "side": "short",
            "entry_price": Decimal("2500.00"),
            "stop_loss": Decimal("2600.00"),
            "take_profit": Decimal("2300.00"),
            "quantity": Decimal("1.5"),
            "confidence": 0.75,
            "reasons": ["Bearish divergence"],
            "timestamp": datetime(2024, 1, 1, 11, 0, 0),
        }

        result = self.formatter.format_decision(decision)

        assert "🔴 SHORT: ETHUSDT" in result
        assert "Entry: $2,500.00" in result
        assert "SL: $2,600.00 (+4.00%)" in result
        assert "TP: $2,300.00 (-8.00%)" in result
        assert "Size: 1.5 ETH" in result

    def test_format_order_update_filled(self) -> None:
        order_update = {
            "symbol": "BTCUSDT",
            "side": "buy",
            "status": "filled",
            "filled_price": Decimal("42100.00"),
            "quantity": Decimal("0.025"),
            "order_id": "123456",
        }

        result = self.formatter.format_order_update(order_update)

        assert "✅ Order Filled" in result
        assert "BTCUSDT" in result
        assert "Buy 0.025 @ $42,100.00" in result

    def test_format_order_update_cancelled(self) -> None:
        order_update = {
            "symbol": "ETHUSDT",
            "side": "sell",
            "status": "cancelled",
            "quantity": Decimal("1.5"),
            "order_id": "789012",
            "reason": "Insufficient balance",
        }

        result = self.formatter.format_order_update(order_update)

        assert "❌ Order Cancelled" in result
        assert "ETHUSDT" in result
        assert "Sell 1.5" in result
        assert "Reason: Insufficient balance" in result

    def test_format_alert_guard_triggered(self) -> None:
        guard_alert = {
            "type": "funding_rate",
            "symbol": "BTCUSDT",
            "current_value": 0.015,
            "threshold": 0.01,
            "action": "trading_disabled",
        }

        result = self.formatter.format_guard_alert(guard_alert)

        assert "⚠️ Guard Triggered" in result
        assert "BTCUSDT" in result
        assert "Funding Rate: 1.50%" in result
        assert "Threshold: 1.00%" in result
        assert "Action: Trading disabled" in result

    def test_format_with_empty_reasons(self) -> None:
        decision = {
            "symbol": "BTCUSDT",
            "side": "long",
            "entry_price": Decimal(42000),
            "stop_loss": Decimal(41000),
            "take_profit": Decimal(44000),
            "quantity": Decimal("0.025"),
            "confidence": 0.85,
            "reasons": [],
            "timestamp": datetime.now(),
        }

        result = self.formatter.format_decision(decision)

        assert "Reasons:" not in result

    def test_calculate_percentage_change(self) -> None:
        assert self.formatter._calculate_pct_change(100, 110) == 10.0
        assert self.formatter._calculate_pct_change(100, 90) == -10.0
        assert self.formatter._calculate_pct_change(100, 100) == 0.0

    def test_format_currency_with_different_scales(self) -> None:
        assert self.formatter._format_currency(42000) == "$42,000.00"
        assert self.formatter._format_currency(0.00012345) == "$0.000123"
        assert self.formatter._format_currency(1234567.89) == "$1,234,567.89"
