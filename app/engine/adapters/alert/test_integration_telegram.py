"""Real integration tests for Telegram alert adapter.

These tests actually send messages to Telegram - no mocks!
Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.
"""

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from app.engine.adapters.alert.telegram import TelegramAlertAdapter

# Check if Telegram credentials are available
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HAS_TELEGRAM_CREDENTIALS = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# Skip reason for missing credentials
SKIP_REASON = "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required for integration tests"


@pytest.mark.integration
@pytest.mark.skipif(not HAS_TELEGRAM_CREDENTIALS, reason=SKIP_REASON)
class TestTelegramRealIntegration:
    """Real integration tests that send actual messages to Telegram."""

    @pytest_asyncio.fixture
    async def telegram_adapter(self) -> AsyncGenerator[TelegramAlertAdapter, None]:
        """Create and start a real TelegramAlertAdapter."""
        adapter = TelegramAlertAdapter(
            bot_token=TELEGRAM_BOT_TOKEN,
            chat_id=TELEGRAM_CHAT_ID,
            rate_limit_per_minute=30,
        )
        await adapter.start()
        yield adapter
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_decision_alert_long(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Send a real LONG decision alert to Telegram."""
        decision_event = {
            "symbol": "BTCUSDT",
            "side": "long",
            "timestamp": datetime.now(UTC).isoformat(),
            "entry_price": Decimal("50000.00"),
            "stop_loss": Decimal("49000.00"),
            "take_profit": Decimal("52000.00"),
            "quantity": Decimal("0.01"),
            "confidence": 0.85,
            "reasons": ["🧪 Integration Test", "SMC Breakout", "Trend Aligned"],
        }

        # This actually sends to Telegram!
        await telegram_adapter._handle_decision(decision_event)

        # If no exception, message was sent successfully
        # Check your Telegram chat to verify!

    @pytest.mark.asyncio
    async def test_send_decision_alert_short(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Send a real SHORT decision alert to Telegram."""
        decision_event = {
            "symbol": "ETHUSDT",
            "side": "short",
            "timestamp": datetime.now(UTC).isoformat(),
            "entry_price": Decimal("3000.00"),
            "stop_loss": Decimal("3100.00"),
            "take_profit": Decimal("2800.00"),
            "quantity": Decimal("0.5"),
            "confidence": 0.72,
            "reasons": ["🧪 Integration Test", "Resistance Hit", "Bearish Divergence"],
        }

        await telegram_adapter._handle_decision(decision_event)

    @pytest.mark.asyncio
    async def test_send_order_filled_alert(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Send a real order filled alert to Telegram."""
        order_event = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "status": "filled",
            "quantity": Decimal("0.01"),
            "filled_price": Decimal("50123.45"),
        }

        await telegram_adapter._handle_order_update(order_event)

    @pytest.mark.asyncio
    async def test_send_order_cancelled_alert(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Send a real order cancelled alert to Telegram."""
        order_event = {
            "symbol": "ETHUSDT",
            "side": "SELL",
            "status": "cancelled",
            "quantity": Decimal("0.5"),
            "reason": "🧪 Integration Test - User cancelled",
        }

        await telegram_adapter._handle_order_update(order_event)

    @pytest.mark.asyncio
    async def test_send_order_rejected_alert(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Send a real order rejected alert to Telegram."""
        order_event = {
            "symbol": "BNBUSDT",
            "side": "BUY",
            "status": "rejected",
            "quantity": Decimal("10"),
            "reason": "🧪 Integration Test - Insufficient balance",
        }

        await telegram_adapter._handle_order_update(order_event)

    @pytest.mark.asyncio
    async def test_send_guard_alert_funding_rate(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Send a real funding rate guard alert to Telegram."""
        guard_event = {
            "type": "funding_rate",
            "symbol": "BTCUSDT",
            "current_value": 0.015,
            "threshold": 0.01,
            "action": "trading_disabled",
        }

        await telegram_adapter._handle_guard_alert(guard_event)

    @pytest.mark.asyncio
    async def test_send_guard_alert_drawdown(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Send a real drawdown guard alert to Telegram."""
        guard_event = {
            "type": "drawdown",
            "symbol": "PORTFOLIO",
            "current_value": 0.06,
            "threshold": 0.05,
            "action": "reduce_size",
        }

        await telegram_adapter._handle_guard_alert(guard_event)

    @pytest.mark.asyncio
    async def test_send_raw_text_alert(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Send a raw text message to Telegram."""
        message = (
            "🧪 <b>Integration Test Alert</b>\n\n"
            f"Timestamp: {datetime.now(UTC).isoformat()}\n"
            "Status: Pipeline validation successful\n\n"
            "This message confirms the Telegram alert pipeline is working."
        )

        success = await telegram_adapter._send_alert(message)
        assert success is True, "Failed to send raw text alert"

    @pytest.mark.asyncio
    async def test_rate_limiting_works(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Test that rate limiting actually works with real API."""
        # Set a low rate limit
        telegram_adapter.rate_limit_per_minute = 3

        # Send messages up to the limit
        for i in range(3):
            success = await telegram_adapter._send_alert(
                f"🧪 Rate limit test message {i + 1}/3",
            )
            assert success is True, f"Message {i + 1} should have been sent"

        # Next message should be rate limited (not sent)
        success = await telegram_adapter._send_alert(
            "🧪 This message should be rate limited",
        )
        assert success is False, "Message should have been rate limited"

    @pytest.mark.asyncio
    async def test_deduplication_works(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Test that deduplication prevents duplicate alerts."""
        # Use a fixed timestamp so the dedup key is the same
        fixed_timestamp = "2025-01-01T00:00:00Z"

        decision_event = {
            "symbol": "BTCUSDT",
            "side": "long",
            "timestamp": fixed_timestamp,
            "entry_price": Decimal("50000.00"),
            "stop_loss": Decimal("49000.00"),
            "take_profit": Decimal("52000.00"),
            "quantity": Decimal("0.01"),
            "confidence": 0.85,
            "reasons": ["🧪 Dedup Test - First message"],
        }

        # First call - should send
        await telegram_adapter._handle_decision(decision_event)

        # Second call with same key - should be deduplicated (no error, just skipped)
        decision_event["reasons"] = ["🧪 Dedup Test - Should NOT appear"]
        await telegram_adapter._handle_decision(decision_event)

        # If you only see one message in Telegram, deduplication worked!

    @pytest.mark.asyncio
    async def test_adapter_lifecycle(self) -> None:
        """Test adapter start/stop lifecycle with real session."""
        adapter = TelegramAlertAdapter(
            bot_token=TELEGRAM_BOT_TOKEN,
            chat_id=TELEGRAM_CHAT_ID,
        )

        # Initially no session
        assert adapter.session is None

        # Start creates real aiohttp session
        await adapter.start()
        assert adapter.session is not None

        # Can send a message
        success = await adapter._send_alert("🧪 Lifecycle test - adapter started")
        assert success is True

        # Stop closes session
        await adapter.stop()
        assert adapter.session is None

    @pytest.mark.asyncio
    async def test_full_trading_flow_simulation(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Simulate a complete trading flow with real alerts."""
        # 1. Trading decision
        decision = {
            "symbol": "BTCUSDT",
            "side": "long",
            "timestamp": datetime.now(UTC).isoformat(),
            "entry_price": Decimal("50000.00"),
            "stop_loss": Decimal("49500.00"),
            "take_profit": Decimal("51000.00"),
            "quantity": Decimal("0.01"),
            "confidence": 0.88,
            "reasons": [
                "🧪 Full Flow Test",
                "SMC Bullish BOS",
                "15m OB Retest",
                "Trend Aligned",
            ],
        }
        await telegram_adapter._handle_decision(decision)

        # 2. Order filled
        order_filled = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "status": "filled",
            "quantity": Decimal("0.01"),
            "filled_price": Decimal("50005.00"),
        }
        await telegram_adapter._handle_order_update(order_filled)

        # 3. Guard alert (funding rate warning)
        guard = {
            "type": "funding_rate",
            "symbol": "BTCUSDT",
            "current_value": 0.008,
            "threshold": 0.01,
            "action": "monitor",
        }
        await telegram_adapter._handle_guard_alert(guard)

        # All messages sent - check Telegram to verify the flow!
