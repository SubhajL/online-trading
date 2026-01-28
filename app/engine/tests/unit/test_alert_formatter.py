"""Unit tests for AlertFormatter."""

from decimal import Decimal

from app.engine.adapters.alert.alert_formatter import AlertFormatter


def test_format_decision_includes_timeframe_and_signal_id_when_present() -> None:
    formatter = AlertFormatter()

    message = formatter.format_decision(
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "entry_price": Decimal(50000),
            "stop_loss": Decimal(49000),
            "take_profit": Decimal(52000),
            "quantity": Decimal("0.01"),
            "confidence": 0.85,
            "reasons": ["Reason A"],
            "timeframe": "15m",
            "signal_id": "sig_abc123",
        },
    )

    assert "TF: 15m" in message
    assert "Signal: sig_abc123" in message


def test_format_decision_omits_timeframe_and_signal_id_when_missing() -> None:
    formatter = AlertFormatter()

    message = formatter.format_decision(
        {
            "symbol": "BTCUSDT",
            "side": "short",
            "entry_price": Decimal(50000),
            "stop_loss": Decimal(51000),
            "take_profit": Decimal(48000),
            "quantity": Decimal("0.01"),
            "confidence": 0.75,
            "reasons": ["Reason A"],
        },
    )

    assert "TF:" not in message
    assert "Signal:" not in message


def test_format_decision_includes_zone_when_present() -> None:
    formatter = AlertFormatter()

    message = formatter.format_decision(
        {
            "symbol": "ETHUSDT",
            "side": "short",
            "entry_price": Decimal("3184.36"),
            "stop_loss": Decimal("3187.16"),
            "take_profit": Decimal("3152.52"),
            "quantity": Decimal("0.01"),
            "confidence": 0.65,
            "reasons": ["FVG fill with bearish bias"],
            "zone": {
                "zone_type": "FAIR_VALUE_GAP",
                "top_price": Decimal(3190),
                "bottom_price": Decimal(3180),
            },
        },
    )

    assert "Zone: FAIR_VALUE_GAP" in message
    assert "$3,180.00" in message
    assert "$3,190.00" in message


# =============================================================================
# Tests for is_order_placed labeling (Gap 4 fix)
# =============================================================================


def test_format_decision_shows_order_placed_label() -> None:
    """When is_order_placed=True, header shows ORDER PLACED."""
    formatter = AlertFormatter()

    message = formatter.format_decision(
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "entry_price": Decimal(50000),
            "stop_loss": Decimal(49000),
            "take_profit": Decimal(52000),
            "quantity": Decimal("0.01"),
            "confidence": 0.85,
            "reasons": ["Reason A"],
            "is_order_placed": True,
        },
    )

    assert "✅" in message
    assert "ORDER PLACED" in message


def test_format_decision_shows_signal_label_when_not_placed() -> None:
    """When is_order_placed=False, header shows SIGNAL."""
    formatter = AlertFormatter()

    message = formatter.format_decision(
        {
            "symbol": "ETHUSDT",
            "side": "short",
            "entry_price": Decimal(3000),
            "stop_loss": Decimal(3050),
            "take_profit": Decimal(2900),
            "quantity": Decimal("0.01"),
            "confidence": 0.75,
            "reasons": ["Reason A"],
            "is_order_placed": False,
        },
    )

    assert "📊" in message or "📉" in message
    assert "SIGNAL" in message
    assert "ORDER PLACED" not in message


def test_format_decision_defaults_to_signal_label() -> None:
    """When is_order_placed not provided, defaults to SIGNAL label."""
    formatter = AlertFormatter()

    message = formatter.format_decision(
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "entry_price": Decimal(50000),
            "stop_loss": Decimal(49000),
            "take_profit": Decimal(52000),
            "quantity": Decimal("0.01"),
            "confidence": 0.80,
            "reasons": [],
        },
    )

    # Default should be signal (no order placed)
    assert "ORDER PLACED" not in message
