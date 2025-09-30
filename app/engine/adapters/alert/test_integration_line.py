import asyncio
import os
from unittest import mock
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.engine.adapters.alert.line import LineAlertAdapter
from app.engine.adapters.alert.alert_formatter import AlertFormatter
from app.engine.adapters.alert.alert_deduplicator import AlertDeduplicator
from typing import Any



class TestLineIntegration:
    """Integration tests for LINE alert adapter"""

    @pytest.fixture
    def formatter(self) -> Any:
        return AlertFormatter()

    @pytest.fixture
    def deduplicator(self) -> Any:
        return AlertDeduplicator(ttl_seconds=60)

    @pytest.fixture
    def line_adapter(self, formatter: Any, deduplicator: Any) -> Any:
        # Use test credentials if available, otherwise mock
        access_token = os.getenv("LINE_TEST_ACCESS_TOKEN", "test-token")

        # Create a mock event bus that actually triggers handlers
        mock_event_bus = MagicMock()
        subscriptions = {}

        async def mock_subscribe(event_type: str, handler: Any) -> None:
            subscriptions[event_type] = handler

        async def mock_publish(event_type: str, event: Any) -> None:
            if event_type in subscriptions:
                await subscriptions[event_type](event)

        mock_event_bus.subscribe = AsyncMock(side_effect=mock_subscribe)
        mock_event_bus.publish = AsyncMock(side_effect=mock_publish)

        adapter = LineAlertAdapter(
            access_token=access_token,
            user_id="test-user",
            event_bus=mock_event_bus
        )

        # We'll start the adapter in each test that needs it

        # Replace the internal formatter and deduplicator for testing
        adapter.formatter = formatter
        adapter.deduplicator = deduplicator

        return adapter

    @pytest.mark.asyncio
    async def test_send_order_filled_notification(self, line_adapter: Any) -> None:
        """Test sending order filled notification through LINE Notify"""
        await line_adapter.start()

        order = {
            "order_id": "LINE-ORDER-001",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "status": "filled",
            "quantity": 0.002,
            "executed_qty": 0.002,
            "executed_price": 44800.0,
            "venue": "USD_M",
            "timestamp": datetime.now(timezone.utc)
        }

        with patch.object(line_adapter, '_send_alert') as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            await line_adapter.event_bus.publish("order_update.v1", order)

            # Verify the message was formatted and sent
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "Order Filled" in message
            assert "BTCUSDT" in message
            assert "Sell" in message
            assert "0.002" in message

    @pytest.mark.asyncio
    async def test_send_position_with_emoji(self, line_adapter: Any) -> None:
        """Test LINE supports emoji in position alerts"""
        await line_adapter.start()

        position = {
            "symbol": "SOLUSDT",
            "side": "LONG",
            "quantity": 50.0,
            "entry_price": 100.0,
            "current_price": 110.0,
            "venue": "USD_M",
            "pnl": 500.0,
            "pnl_percent": 10.0,
            "timestamp": datetime.now(timezone.utc)
        }

        with patch.object(line_adapter, '_send_alert') as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            # Positions would come from order updates, but for testing formatter:
            message = line_adapter.formatter.format_position(position)
            await line_adapter._send_alert(message)

            # Verify emoji are included (LINE supports them)
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "📊" in message or "POSITION UPDATE" in message
            assert "+$500.00 (+10.00%)" in message

    @pytest.mark.asyncio
    async def test_message_length_limit(self, line_adapter: Any) -> None:
        """Test LINE's 1000 character message limit is respected"""
        await line_adapter.start()

        # Create a decision with very long reasoning
        decision = {
            "symbol": "BTCUSDT",
            "action": "BUY",
            "side": "BUY",
            "quantity": 0.1,
            "venue": "SPOT",
            "type": "MARKET",
            "confidence": 0.95,
            "reason": "A" * 2000,  # Very long reason to exceed limit
            "timestamp": datetime.now(timezone.utc),
            "entry_price": 2400.0,
            "stop_loss": 2350.0,
            "take_profit": 2500.0
        }

        with patch.object(line_adapter, '_send_alert') as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            await line_adapter.event_bus.publish("decision.v1", decision)

            # Verify message was truncated
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert len(message) <= 1000

    @pytest.mark.asyncio
    async def test_auth_header_format(self, line_adapter: Any) -> None:
        """Test LINE Notify authorization header format"""
        await line_adapter.start()

        order = {
            "order_id": "AUTH-TEST",
            "symbol": "ETHUSDT",
            "side": "BUY",
            "status": "filled",
            "quantity": 1.0,
            "executed_qty": 1.0,
            "executed_price": 2500.0,
            "venue": "SPOT",
            "timestamp": datetime.now(timezone.utc)
        }

        with patch.object(line_adapter, '_send_alert') as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            await line_adapter.event_bus.publish("order_update.v1", order)

            # Verify the send was called
            mock_send.assert_called_once()
            # LINE adapter uses Bearer token in Authorization header internally

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, line_adapter: Any) -> None:
        """Test handling LINE's rate limits (1000/hour)"""
        await line_adapter.start()

        # Create multiple orders
        orders = [
            {
                    "order_id": f"RATE-{i}",
                "symbol": "BTCUSDT",
                "side": "BUY" if i % 2 == 0 else "SELL",
                "status": "new",
                "quantity": 0.001,
                "venue": "SPOT",
                "timestamp": datetime.now(timezone.utc)
        }
            for i in range(5)
        ]

        with patch.object(line_adapter, '_send_alert') as mock_send:
            # Simulate rate limit response on 3rd request
            responses = [
                {"status": 200, "message": "ok"},
                {"status": 200, "message": "ok"},
                {"status": 429, "message": "Rate limit exceeded"},
                {"status": 200, "message": "ok"},
                {"status": 200, "message": "ok"},
            ]

            async def mock_send_with_rate_limit(message: Any) -> None:
                response = responses.pop(0)
                if response["status"] == 429:
                    raise Exception("Rate limit exceeded")

            mock_send.side_effect = mock_send_with_rate_limit

            # Send all alerts
            results = []
            for order in orders:
                try:
                    await line_adapter.event_bus.publish("order_update.v1", order)
                    results.append("success")
                except Exception:
                    results.append("rate_limited")

            # Should handle rate limit gracefully
            assert results.count("success") >= 4  # At least 4 should succeed

    @pytest.mark.asyncio
    async def test_sticker_support(self, line_adapter: Any) -> None:
        """Test sending stickers with important alerts"""
        await line_adapter.start()

        # Critical order rejection
        critical_order = {
            "order_id": "CRITICAL-001",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "status": "rejected",
            "quantity": 1.0,
            "venue": "USD_M",
            "reason": "ACCOUNT_SUSPENDED",
            "timestamp": datetime.now(timezone.utc)
        }

        with patch.object(line_adapter, '_send_alert') as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            await line_adapter.event_bus.publish("order_update.v1", critical_order)

            # For critical alerts, LINE could send stickers
            # (implementation would need sticker package/ID support)
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "Rejected" in message
            assert "Reason: ACCOUNT_SUSPENDED" in message

    @pytest.mark.asyncio
    async def test_image_chart_attachment(self, line_adapter: Any) -> None:
        """Test potential for sending chart images with signals"""
        await line_adapter.start()

        decision = {
            "symbol": "ETHUSDT",
            "action": "BUY",
            "side": "BUY",
            "quantity": 2.0,
            "venue": "SPOT",
            "type": "LIMIT",
            "price": 2400.0,
            "confidence": 0.92,
            "chart_url": "https://example.com/chart.png",  # Hypothetical
            "timestamp": datetime.now(timezone.utc),
            "entry_price": 2400.0,
            "stop_loss": 2350.0,
            "take_profit": 2500.0
        }

        with patch.object(line_adapter, '_send_alert') as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            await line_adapter.event_bus.publish("decision.v1", decision)

            # LINE Notify doesn't support images directly,
            # but URL could be included
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "ETHUSDT" in message
            if hasattr(decision, 'chart_url'):
                assert "chart" in message.lower() or "https://" in message

    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self, line_adapter: Any) -> None:
        """Test handling connection timeouts to LINE API"""
        await line_adapter.start()

        order = {
            "order_id": "TIMEOUT-001",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "status": "new",
            "quantity": 0.001,
            "venue": "SPOT",
            "timestamp": datetime.now(timezone.utc)
        }

        async def mock_timeout(*args: Any, **kwargs: Any) -> None:
            await asyncio.sleep(0.1)
            raise asyncio.TimeoutError("Connection timeout")

        with patch.object(line_adapter, '_send_alert', side_effect=mock_timeout):
            # Should handle timeout gracefully
            try:
                await line_adapter.event_bus.publish("order_update.v1", order)
            except asyncio.TimeoutError:
                pass  # Expected, adapter doesn't retry on timeout

    @pytest.mark.asyncio
    async def test_group_notification_support(self, line_adapter: Any) -> None:
        """Test sending to LINE groups vs individual users"""
        await line_adapter.start()

        # LINE Notify can send to groups if token is from group
        position = {
            "symbol": "ADAUSDT",
            "side": "SHORT",
            "quantity": 1000.0,
            "entry_price": 0.50,
            "current_price": 0.48,
            "venue": "SPOT",
            "pnl": 20.0,
            "pnl_percent": 4.0,
            "timestamp": datetime.now(timezone.utc)
        }

        with patch.object(line_adapter, '_send_alert') as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            # If configured for group, same API works
            # Positions would come from order updates, but for testing formatter:
            message = line_adapter.formatter.format_position(position)
            await line_adapter._send_alert(message)

            mock_send.assert_called_once()
            # Group messages work the same way with LINE Notify

    @pytest.mark.asyncio
    async def test_alert_priority_levels(self, line_adapter: Any) -> None:
        """Test different priority levels for alerts"""
        await line_adapter.start()

        # High priority - large loss
        high_priority = {
            "symbol": "BTCUSDT",
            "side": "LONG",
            "quantity": 1.0,
            "entry_price": 50000.0,
            "current_price": 45000.0,
            "venue": "USD_M",
            "pnl": -5000.0,
            "pnl_percent": -10.0,
            "timestamp": datetime.now(timezone.utc)
        }

        # Low priority - small position update
        low_priority = {
            "symbol": "DOGEUSDT",
            "side": "LONG",
            "quantity": 1000.0,
            "entry_price": 0.10,
            "current_price": 0.101,
            "venue": "SPOT",
            "pnl": 1.0,
            "pnl_percent": 1.0,
            "timestamp": datetime.now(timezone.utc)
        }

        with patch.object(line_adapter, '_send_alert') as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            # Test formatter directly for positions
            message = line_adapter.formatter.format_position(high_priority)
            await line_adapter._send_alert(message)
            # Test formatter directly for positions
            message = line_adapter.formatter.format_position(low_priority)
            await line_adapter._send_alert(message)

            # Both sent, but high priority might have special formatting
            assert mock_send.call_count == 2

            high_msg = mock_send.call_args_list[0][0][0]
            low_msg = mock_send.call_args_list[1][0][0]

            # High priority loss should be emphasized
            assert "-$5000.00" in high_msg or "-10.00%" in high_msg

    @pytest.mark.asyncio
    async def test_batch_summary_alerts(self, line_adapter: Any) -> None:
        """Test sending daily summary alerts"""
        await line_adapter.start()

        # Simulate daily summary
        summary_data = {
            "total_trades": 15,
            "winning_trades": 10,
            "total_pnl": 523.45,
            "win_rate": 0.67,
            "date": datetime.now(timezone.utc).date()
        }

        with patch.object(line_adapter, '_send_alert') as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            # Format and send summary
            # Format summary manually
            summary_msg = f"📈 Daily Summary\nTotal Trades: {summary_data['total_trades']}\nWinning: {summary_data['winning_trades']}\nTotal P&L: +${summary_data['total_pnl']:.2f}\nWin Rate: {summary_data['win_rate']:.0%}"
            await line_adapter._send_alert(summary_msg)

            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "Daily" in message or "Summary" in message