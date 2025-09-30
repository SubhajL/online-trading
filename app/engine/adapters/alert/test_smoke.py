"""
Smoke tests for alert adapters to ensure basic functionality in CI.
These tests verify that modules can be imported and instantiated correctly.
"""
import pytest
from unittest.mock import Mock


def test_alert_modules_importable():
    """Verify all alert modules can be imported."""
    # These imports should not raise any errors
    from app.engine.adapters.alert.telegram import TelegramAlertAdapter
    from app.engine.adapters.alert.line import LineAlertAdapter
    from app.engine.adapters.alert.alert_formatter import AlertFormatter
    from app.engine.adapters.alert.alert_deduplicator import AlertDeduplicator

    # Verify classes exist
    assert TelegramAlertAdapter
    assert LineAlertAdapter
    assert AlertFormatter
    assert AlertDeduplicator


def test_alert_formatter_basic_functionality():
    """Test AlertFormatter can format basic messages."""
    from app.engine.adapters.alert.alert_formatter import AlertFormatter

    formatter = AlertFormatter()

    # Test decision formatting
    decision = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "action": "BUY",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": 52000.0,
        "confidence": 0.85,
        "quantity": 0.001
    }

    message = formatter.format_decision(decision)
    assert "BTCUSDT" in message.upper()
    # Check for either long or short signals
    assert any(word in message.upper() for word in ["LONG", "SHORT", "BUY", "SELL"])
    assert "50000" in message or "50,000" in message  # May be formatted with comma

    # Test order formatting
    order = {
        "symbol": "ETHUSDT",
        "side": "SELL",
        "status": "filled",
        "quantity": 1.5,
        "executed_qty": 1.5,
        "executed_price": 3000.0
    }

    message = formatter.format_order_update(order)
    assert "ETHUSDT" in message
    assert "Sell" in message or "SELL" in message
    assert "Filled" in message.title() or "FILLED" in message.upper()


def test_adapter_initialization():
    """Test that adapters can be initialized with required parameters."""
    from app.engine.adapters.alert.telegram import TelegramAlertAdapter
    from app.engine.adapters.alert.line import LineAlertAdapter

    mock_event_bus = Mock()

    # Test Telegram adapter init
    telegram = TelegramAlertAdapter(
        bot_token="test-token",
        chat_id="test-chat",
        event_bus=mock_event_bus
    )
    assert telegram.bot_token == "test-token"
    assert telegram.chat_id == "test-chat"

    # Test LINE adapter init
    line = LineAlertAdapter(
        access_token="test-token",
        user_id="test-user",
        event_bus=mock_event_bus
    )
    assert line.access_token == "test-token"
    assert line.user_id == "test-user"


def test_position_formatting():
    """Test position formatting functionality."""
    from app.engine.adapters.alert.alert_formatter import AlertFormatter

    formatter = AlertFormatter()

    # Test long position with profit
    position = {
        "symbol": "BTCUSDT",
        "side": "long",
        "entry_price": 50000.0,
        "current_price": 51000.0,
        "quantity": 0.1,
        "pnl": 100.0,
        "pnl_percent": 2.0
    }

    message = formatter.format_position(position)
    assert "BTCUSDT" in message
    assert "LONG" in message.upper() or "Long" in message
    assert "100" in message  # PnL value
    assert "2.0" in message  # Percentage


def test_deduplicator_initialization():
    """Test deduplicator can be initialized."""
    from app.engine.adapters.alert.alert_deduplicator import AlertDeduplicator

    # Should work even without Redis in CI
    dedup = AlertDeduplicator(ttl_seconds=60)
    assert dedup.ttl_seconds == 60