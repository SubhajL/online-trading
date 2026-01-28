"""Real integration tests for the alert system.

Tests the complete alert pipeline with actual Telegram API calls.
Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from app.engine.adapters.alert.telegram import TelegramAlertAdapter

# Check if Telegram credentials are available
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
HAS_TELEGRAM_CREDENTIALS = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

SKIP_REASON = "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required for integration tests"


@pytest.mark.integration
@pytest.mark.skipif(not HAS_TELEGRAM_CREDENTIALS, reason=SKIP_REASON)
class TestAlertSystemRealIntegration:
    """Real integration tests for the complete alert system."""

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
    async def test_complete_trading_flow(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Test a complete trading flow: signal → order → fill → guard."""
        # 1. Trading decision signal
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
                "🧪 Complete Flow Test",
                "SMC Bullish BOS",
                "15m OB Retest",
            ],
        }
        await telegram_adapter._handle_decision(decision)

        # Small delay between messages
        await asyncio.sleep(0.5)

        # 2. Order filled confirmation
        order_filled = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "status": "filled",
            "quantity": Decimal("0.01"),
            "filled_price": Decimal("50005.00"),
        }
        await telegram_adapter._handle_order_update(order_filled)

        await asyncio.sleep(0.5)

        # 3. Guard alert (position monitoring)
        guard = {
            "type": "position_size",
            "symbol": "BTCUSDT",
            "current_value": 0.02,
            "threshold": 0.03,
            "action": "monitor",
        }
        await telegram_adapter._handle_guard_alert(guard)

    @pytest.mark.asyncio
    async def test_multiple_symbols_flow(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Test alerts for multiple trading pairs."""
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

        for i, symbol in enumerate(symbols):
            decision = {
                "symbol": symbol,
                "side": "long" if i % 2 == 0 else "short",
                "timestamp": datetime.now(UTC).isoformat(),
                "entry_price": Decimal("1000.00") * (i + 1),
                "stop_loss": Decimal("950.00") * (i + 1),
                "take_profit": Decimal("1050.00") * (i + 1),
                "quantity": Decimal("0.1"),
                "confidence": 0.75 + (i * 0.05),
                "reasons": [f"🧪 Multi-symbol test {i + 1}/3"],
            }
            await telegram_adapter._handle_decision(decision)
            await asyncio.sleep(0.3)

    @pytest.mark.asyncio
    async def test_error_scenarios(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Test error/rejection alert scenarios."""
        # Order rejected
        rejected = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "status": "rejected",
            "quantity": Decimal("1.0"),
            "reason": "🧪 Error Test - Insufficient margin",
        }
        await telegram_adapter._handle_order_update(rejected)

        await asyncio.sleep(0.3)

        # Critical guard alert
        critical_guard = {
            "type": "drawdown",
            "symbol": "PORTFOLIO",
            "current_value": 0.08,
            "threshold": 0.05,
            "action": "trading_disabled",
        }
        await telegram_adapter._handle_guard_alert(critical_guard)

    @pytest.mark.asyncio
    async def test_high_frequency_alerts(
        self, telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        """Test system handles rapid alerts without rate limit issues."""
        # Set higher rate limit for this test
        telegram_adapter.rate_limit_per_minute = 10

        success_count = 0
        for i in range(5):
            success = await telegram_adapter._send_alert(
                f"🧪 High frequency test {i + 1}/5",
            )
            if success:
                success_count += 1

        # All 5 should succeed (under rate limit of 10)
        assert success_count == 5, f"Expected 5 messages, got {success_count}"

    @pytest.mark.asyncio
    async def test_session_recovery(self) -> None:
        """Test adapter can recover from session issues."""
        adapter = TelegramAlertAdapter(
            bot_token=TELEGRAM_BOT_TOKEN,
            chat_id=TELEGRAM_CHAT_ID,
        )

        # Start, send, stop, restart, send again
        await adapter.start()
        success1 = await adapter._send_alert("🧪 Recovery test - before restart")
        assert success1 is True

        await adapter.stop()
        await adapter.start()

        success2 = await adapter._send_alert("🧪 Recovery test - after restart")
        assert success2 is True

        await adapter.stop()
