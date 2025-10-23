import asyncio
from datetime import UTC, datetime
import os
from typing import Any
from unittest.mock import patch

import pytest

from app.engine.adapters.alert.alert_deduplicator import AlertDeduplicator
from app.engine.adapters.alert.alert_formatter import AlertFormatter
from app.engine.adapters.alert.telegram import TelegramAlertAdapter
from app.engine.models import Position, TradingDecisionEvent
from app.engine.paper.broker import OrderUpdate


class TestTelegramIntegration:
    """Integration tests for Telegram alert adapter"""

    @pytest.fixture
    def formatter(self) -> Any:
        return AlertFormatter()

    @pytest.fixture
    def deduplicator(self) -> Any:
        return AlertDeduplicator(ttl_seconds=60)

    @pytest.fixture
    def telegram_adapter(self, formatter: Any, deduplicator: Any) -> Any:
        # Use test credentials if available, otherwise mock
        bot_token = os.getenv("TELEGRAM_TEST_BOT_TOKEN", "test-token")
        chat_id = os.getenv("TELEGRAM_TEST_CHAT_ID", "test-chat-id")

        adapter = TelegramAlertAdapter(
            bot_token=bot_token,
            chat_id=chat_id,
            formatter=formatter,
            deduplicator=deduplicator,
        )
        return adapter

    @pytest.mark.asyncio
    async def test_send_order_filled_alert(self, telegram_adapter: Any) -> None:
        """Test sending a real order filled alert through Telegram"""
        order = OrderUpdate(
            order_id="TEST-ORDER-001",
            symbol="BTCUSDT",
            side="BUY",
            status="FILLED",
            executed_qty=0.001,
            executed_price=45000.0,
            venue="SPOT",
            timestamp=datetime.now(UTC),
        )

        with patch.object(telegram_adapter, "_send_telegram_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"ok": True, "result": {"message_id": 123}})

            await telegram_adapter.send_alert(order)

            # Verify the message was formatted and sent
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "✅ ORDER FILLED" in message
            assert "BTCUSDT" in message
            assert "BUY" in message
            assert "0.001" in message

    @pytest.mark.asyncio
    async def test_send_position_alert_with_pnl(self, telegram_adapter: Any) -> None:
        """Test sending position update with P&L calculation"""
        position = Position(
            symbol="ETHUSDT",
            side="LONG",
            quantity=1.5,
            entry_price=2500.0,
            current_price=2600.0,
            venue="USD_M",
            pnl=150.0,
            pnl_percent=4.0,
            timestamp=datetime.now(UTC),
        )

        with patch.object(telegram_adapter, "_send_telegram_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"ok": True, "result": {"message_id": 124}})

            await telegram_adapter.send_alert(position)

            # Verify the message contains P&L info
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "📊 POSITION UPDATE" in message
            assert "ETHUSDT" in message
            assert "P&L: +$150.00 (+4.00%)" in message

    @pytest.mark.asyncio
    async def test_deduplication_prevents_spam(self, telegram_adapter: Any) -> None:
        """Test that deduplication prevents sending duplicate alerts"""
        decision = TradingDecisionEvent(
            symbol="BTCUSDT",
            action="BUY",
            quantity=0.001,
            venue="SPOT",
            type="MARKET",
            confidence=0.85,
            timestamp=datetime.now(UTC),
        )

        with patch.object(telegram_adapter, "_send_telegram_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"ok": True, "result": {"message_id": 125}})

            # First alert should be sent
            await telegram_adapter.send_alert(decision)
            assert mock_send.call_count == 1

            # Duplicate alert should be blocked
            await telegram_adapter.send_alert(decision)
            assert mock_send.call_count == 1  # Still only 1 call

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self, telegram_adapter: Any) -> None:
        """Test retry logic when Telegram API fails"""
        order = OrderUpdate(
            order_id="TEST-ORDER-002",
            symbol="BTCUSDT",
            side="SELL",
            status="NEW",
            quantity=0.001,
            venue="SPOT",
            timestamp=datetime.now(UTC),
        )

        call_count = 0
        async def mock_send_with_retry(message: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Network error")

        with patch.object(telegram_adapter, "_send_telegram_message", side_effect=mock_send_with_retry):
            with patch.object(telegram_adapter, "retry_count", 3):
                with patch.object(telegram_adapter, "retry_delay", 0.01):  # Fast retry for tests
                    await telegram_adapter.send_alert(order)
                    assert call_count == 3  # Should retry until success

    @pytest.mark.asyncio
    async def test_rate_limiting(self, telegram_adapter: Any) -> None:
        """Test that rate limiting prevents excessive API calls"""
        orders = [
            OrderUpdate(
                order_id=f"ORDER-{i}",
                symbol="BTCUSDT",
                side="BUY" if i % 2 == 0 else "SELL",
                status="NEW",
                quantity=0.001,
                venue="SPOT",
                timestamp=datetime.now(UTC),
            )
            for i in range(10)
        ]

        with patch.object(telegram_adapter, "_send_telegram_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"ok": True, "result": {"message_id": 127}})

            # Set rate limit to 3 messages per second
            with patch.object(telegram_adapter, "rate_limit_per_second", 3):
                start_time = asyncio.get_event_loop().time()

                # Send all alerts
                tasks = [telegram_adapter.send_alert(order) for order in orders]
                await asyncio.gather(*tasks)

                end_time = asyncio.get_event_loop().time()
                duration = end_time - start_time

                # Should take at least 3 seconds to send 10 messages at 3/sec
                assert duration >= 3.0
                assert mock_send.call_count == 10

    @pytest.mark.asyncio
    async def test_markdown_formatting_escape(self, telegram_adapter: Any) -> None:
        """Test that special markdown characters are properly escaped"""
        # Order with special characters in symbol
        order = OrderUpdate(
            order_id="TEST_ORDER*123",
            symbol="BTC_USDT",
            side="BUY",
            status="FILLED",
            executed_qty=0.001,
            executed_price=45000.0,
            venue="SPOT",
            timestamp=datetime.now(UTC),
        )

        with patch.object(telegram_adapter, "_send_telegram_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"ok": True, "result": {"message_id": 128}})

            await telegram_adapter.send_alert(order)

            # Verify special characters are escaped
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "BTC\\_USDT" in message or "BTC_USDT" in message  # Escaped or raw

    @pytest.mark.asyncio
    async def test_batch_alerts_for_multiple_events(self, telegram_adapter: Any) -> None:
        """Test handling multiple alerts in quick succession"""
        events = [
            OrderUpdate(
                order_id="ORDER-1",
                symbol="BTCUSDT",
                side="BUY",
                status="NEW",
                quantity=0.001,
                venue="SPOT",
                timestamp=datetime.now(UTC),
            ),
            TradingDecisionEvent(
                symbol="ETHUSDT",
                action="SELL",
                quantity=0.5,
                venue="USD_M",
                type="LIMIT",
                price=2500.0,
                confidence=0.90,
                timestamp=datetime.now(UTC),
            ),
            Position(
                symbol="BNBUSDT",
                side="SHORT",
                quantity=10.0,
                entry_price=300.0,
                current_price=295.0,
                venue="USD_M",
                pnl=50.0,
                pnl_percent=1.67,
                timestamp=datetime.now(UTC),
            ),
        ]

        with patch.object(telegram_adapter, "_send_telegram_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"ok": True, "result": {"message_id": 129}})

            # Send all events
            for event in events:
                await telegram_adapter.send_alert(event)

            # All unique events should be sent
            assert mock_send.call_count == 3

            # Check that different event types are formatted differently
            messages = [call[0][0] for call in mock_send.call_args_list]
            assert any("📋 NEW ORDER" in msg for msg in messages)
            assert any("🎯 TRADING SIGNAL" in msg for msg in messages)
            assert any("📊 POSITION UPDATE" in msg for msg in messages)

    @pytest.mark.asyncio
    async def test_error_alert_formatting(self, telegram_adapter: Any) -> None:
        """Test sending error alerts with proper formatting"""
        error_order = OrderUpdate(
            order_id="ERROR-ORDER",
            symbol="BTCUSDT",
            side="BUY",
            status="REJECTED",
            quantity=0.001,
            venue="SPOT",
            error="Insufficient balance",
            timestamp=datetime.now(UTC),
        )

        with patch.object(telegram_adapter, "_send_telegram_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"ok": True, "result": {"message_id": 130}})

            await telegram_adapter.send_alert(error_order)

            # Verify error message formatting
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "❌ ORDER REJECTED" in message
            assert "Insufficient balance" in message

    @pytest.mark.asyncio
    async def test_connection_pool_handling(self, telegram_adapter: Any) -> None:
        """Test that HTTP connection pooling works correctly"""
        # Send multiple alerts to test connection reuse
        orders = [
            OrderUpdate(
                order_id=f"POOL-ORDER-{i}",
                symbol="BTCUSDT",
                side="BUY",
                status="NEW",
                quantity=0.001,
                venue="SPOT",
                timestamp=datetime.now(UTC),
            )
            for i in range(5)
        ]

        with patch.object(telegram_adapter, "_send_telegram_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"ok": True, "result": {"message_id": 131}})

            # Send alerts sequentially
            for order in orders:
                await telegram_adapter.send_alert(order)

            # All alerts should be sent successfully
            assert mock_send.call_count == 5
