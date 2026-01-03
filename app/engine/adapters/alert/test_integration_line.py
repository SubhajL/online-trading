import asyncio
from datetime import UTC, datetime
import os
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.engine.adapters.alert.alert_deduplicator import AlertDeduplicator
from app.engine.adapters.alert.alert_formatter import AlertFormatter
from app.engine.adapters.alert.line import LineAlertAdapter
from app.engine.models import Position, TradingDecisionEvent
from app.engine.paper.broker import OrderUpdate


@pytest.mark.skip(
    reason="Outdated: uses deprecated LineAlertAdapter API (formatter/deduplicator args, send_alert method). "
    "LINE integration not yet implemented with new API."
)
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

        adapter = LineAlertAdapter(
            access_token=access_token,
            formatter=formatter,
            deduplicator=deduplicator,
        )
        return adapter

    @pytest.mark.asyncio
    async def test_send_order_filled_notification(self, line_adapter: Any) -> None:
        """Test sending order filled notification through LINE Notify"""
        order = OrderUpdate(
            order_id="LINE-ORDER-001",
            symbol="BTCUSDT",
            side="SELL",
            status="FILLED",
            executed_qty=0.002,
            executed_price=44800.0,
            venue="USD_M",
            timestamp=datetime.now(UTC),
        )

        with patch.object(line_adapter, "_send_line_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            await line_adapter.send_alert(order)

            # Verify the message was formatted and sent
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "ORDER FILLED" in message
            assert "BTCUSDT" in message
            assert "SELL" in message
            assert "0.002" in message

    @pytest.mark.asyncio
    async def test_send_position_with_emoji(self, line_adapter: Any) -> None:
        """Test LINE supports emoji in position alerts"""
        position = Position(
            symbol="SOLUSDT",
            side="LONG",
            quantity=50.0,
            entry_price=100.0,
            current_price=110.0,
            venue="USD_M",
            pnl=500.0,
            pnl_percent=10.0,
            timestamp=datetime.now(UTC),
        )

        with patch.object(line_adapter, "_send_line_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            await line_adapter.send_alert(position)

            # Verify emoji are included (LINE supports them)
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "📊" in message or "POSITION UPDATE" in message
            assert "+$500.00 (+10.00%)" in message

    @pytest.mark.asyncio
    async def test_message_length_limit(self, line_adapter: Any) -> None:
        """Test LINE's 1000 character message limit is respected"""
        # Create a decision with very long reasoning
        decision = TradingDecisionEvent(
            symbol="BTCUSDT",
            action="BUY",
            quantity=0.1,
            venue="SPOT",
            type="MARKET",
            confidence=0.95,
            reason="A" * 2000,  # Very long reason to exceed limit
            timestamp=datetime.now(UTC),
        )

        with patch.object(line_adapter, "_send_line_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            await line_adapter.send_alert(decision)

            # Verify message was truncated
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert len(message) <= 1000

    @pytest.mark.asyncio
    async def test_auth_header_format(self, line_adapter: Any) -> None:
        """Test LINE Notify authorization header format"""
        order = OrderUpdate(
            order_id="AUTH-TEST",
            symbol="ETHUSDT",
            side="BUY",
            status="NEW",
            quantity=1.0,
            venue="SPOT",
            timestamp=datetime.now(UTC),
        )

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.json = AsyncMock(
                return_value={"status": 200, "message": "ok"}
            )
            mock_response.status = 200
            mock_post.return_value.__aenter__.return_value = mock_response

            await line_adapter.send_alert(order)

            # Verify authorization header
            mock_post.assert_called_once()
            headers = mock_post.call_args[1]["headers"]
            assert "Authorization" in headers
            assert headers["Authorization"].startswith("Bearer ")

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, line_adapter: Any) -> None:
        """Test handling LINE's rate limits (1000/hour)"""
        # Create multiple orders
        orders = [
            OrderUpdate(
                order_id=f"RATE-{i}",
                symbol="BTCUSDT",
                side="BUY" if i % 2 == 0 else "SELL",
                status="NEW",
                quantity=0.001,
                venue="SPOT",
                timestamp=datetime.now(UTC),
            )
            for i in range(5)
        ]

        with patch.object(line_adapter, "_send_line_message") as mock_send:
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
                    await line_adapter.send_alert(order)
                    results.append("success")
                except Exception:
                    results.append("rate_limited")

            # Should handle rate limit gracefully
            assert results.count("success") >= 4  # At least 4 should succeed

    @pytest.mark.asyncio
    async def test_sticker_support(self, line_adapter: Any) -> None:
        """Test sending stickers with important alerts"""
        # Critical order rejection
        critical_order = OrderUpdate(
            order_id="CRITICAL-001",
            symbol="BTCUSDT",
            side="BUY",
            status="REJECTED",
            quantity=1.0,
            venue="USD_M",
            error="ACCOUNT_SUSPENDED",
            timestamp=datetime.now(UTC),
        )

        with patch.object(line_adapter, "_send_line_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            await line_adapter.send_alert(critical_order)

            # For critical alerts, LINE could send stickers
            # (implementation would need sticker package/ID support)
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "REJECTED" in message
            assert "ACCOUNT_SUSPENDED" in message

    @pytest.mark.asyncio
    async def test_image_chart_attachment(self, line_adapter: Any) -> None:
        """Test potential for sending chart images with signals"""
        decision = TradingDecisionEvent(
            symbol="ETHUSDT",
            action="BUY",
            quantity=2.0,
            venue="SPOT",
            type="LIMIT",
            price=2400.0,
            confidence=0.92,
            chart_url="https://example.com/chart.png",  # Hypothetical
            timestamp=datetime.now(UTC),
        )

        with patch.object(line_adapter, "_send_line_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            await line_adapter.send_alert(decision)

            # LINE Notify doesn't support images directly,
            # but URL could be included
            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "ETHUSDT" in message
            if hasattr(decision, "chart_url"):
                assert "chart" in message.lower() or "https://" in message

    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self, line_adapter: Any) -> None:
        """Test handling connection timeouts to LINE API"""
        order = OrderUpdate(
            order_id="TIMEOUT-001",
            symbol="BTCUSDT",
            side="BUY",
            status="NEW",
            quantity=0.001,
            venue="SPOT",
            timestamp=datetime.now(UTC),
        )

        async def mock_timeout(*args: Any, **kwargs: Any) -> None:
            await asyncio.sleep(0.1)
            raise TimeoutError("Connection timeout")

        with patch.object(line_adapter, "_send_line_message", side_effect=mock_timeout):
            with patch.object(line_adapter, "timeout_seconds", 0.05):
                # Should handle timeout gracefully
                try:
                    await line_adapter.send_alert(order)
                except TimeoutError:
                    pass  # Expected

    @pytest.mark.asyncio
    async def test_group_notification_support(self, line_adapter: Any) -> None:
        """Test sending to LINE groups vs individual users"""
        # LINE Notify can send to groups if token is from group
        position = Position(
            symbol="ADAUSDT",
            side="SHORT",
            quantity=1000.0,
            entry_price=0.50,
            current_price=0.48,
            venue="SPOT",
            pnl=20.0,
            pnl_percent=4.0,
            timestamp=datetime.now(UTC),
        )

        with patch.object(line_adapter, "_send_line_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            # If configured for group, same API works
            await line_adapter.send_alert(position)

            mock_send.assert_called_once()
            # Group messages work the same way with LINE Notify

    @pytest.mark.asyncio
    async def test_alert_priority_levels(self, line_adapter: Any) -> None:
        """Test different priority levels for alerts"""
        # High priority - large loss
        high_priority = Position(
            symbol="BTCUSDT",
            side="LONG",
            quantity=1.0,
            entry_price=50000.0,
            current_price=45000.0,
            venue="USD_M",
            pnl=-5000.0,
            pnl_percent=-10.0,
            timestamp=datetime.now(UTC),
        )

        # Low priority - small position update
        low_priority = Position(
            symbol="DOGEUSDT",
            side="LONG",
            quantity=1000.0,
            entry_price=0.10,
            current_price=0.101,
            venue="SPOT",
            pnl=1.0,
            pnl_percent=1.0,
            timestamp=datetime.now(UTC),
        )

        with patch.object(line_adapter, "_send_line_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            await line_adapter.send_alert(high_priority)
            await line_adapter.send_alert(low_priority)

            # Both sent, but high priority might have special formatting
            assert mock_send.call_count == 2

            high_msg = mock_send.call_args_list[0][0][0]
            low_msg = mock_send.call_args_list[1][0][0]

            # High priority loss should be emphasized
            assert "-$5000.00" in high_msg or "-10.00%" in high_msg

    @pytest.mark.asyncio
    async def test_batch_summary_alerts(self, line_adapter: Any) -> None:
        """Test sending daily summary alerts"""
        # Simulate daily summary
        summary_data = {
            "total_trades": 15,
            "winning_trades": 10,
            "total_pnl": 523.45,
            "win_rate": 0.67,
            "date": datetime.now(UTC).date(),
        }

        with patch.object(line_adapter, "_send_line_message") as mock_send:
            loop = asyncio.get_event_loop()
            mock_send.return_value = loop.create_future()
            mock_send.return_value.set_result({"status": 200, "message": "ok"})

            # Format and send summary
            summary_msg = line_adapter.formatter.format_daily_summary(summary_data)
            await line_adapter._send_line_message(summary_msg)

            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "Daily" in message or "Summary" in message
