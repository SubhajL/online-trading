import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio
from datetime import datetime
from decimal import Decimal

from app.engine.adapters.alert.telegram import TelegramAlertAdapter
from typing import Any



class TestTelegramAlertAdapter:
    @pytest.fixture
    def mock_event_bus(self) -> Any:
        bus = Mock()
        bus.subscribe = AsyncMock()
        return bus

    @pytest.fixture
    def mock_deduplicator(self) -> Any:
        dedup = Mock()
        dedup.is_duplicate = Mock(return_value=False)
        dedup.add = Mock()
        return dedup

    @pytest.fixture
    def mock_formatter(self) -> Any:
        formatter = Mock()
        formatter.format_decision = Mock(return_value="Formatted decision")
        formatter.format_order_update = Mock(return_value="Formatted order")
        formatter.format_guard_alert = Mock(return_value="Formatted guard")
        return formatter

    @pytest.fixture
    def adapter(self, mock_event_bus: Any, mock_deduplicator: Any, mock_formatter: Any) -> Any:
        with patch("telegram.aiohttp.ClientSession"):
            adapter = TelegramAlertAdapter(
                bot_token="test_token",
                chat_id="test_chat",
                event_bus=mock_event_bus,
            )
            adapter.deduplicator = mock_deduplicator
            adapter.formatter = mock_formatter
            return adapter

    @pytest.mark.asyncio
    async def test_init_subscribes_to_events(self, mock_event_bus: Any) -> None:
        with patch("telegram.aiohttp.ClientSession"):
            adapter = TelegramAlertAdapter(
                bot_token="test_token",
                chat_id="test_chat",
                event_bus=mock_event_bus,
            )
            await adapter.start()

        assert mock_event_bus.subscribe.call_count == 3
        calls = mock_event_bus.subscribe.call_args_list
        assert calls[0][0][0] == "decision.v1"
        assert calls[1][0][0] == "order_update.v1"
        assert calls[2][0][0] == "guard_alert.v1"

    @pytest.mark.asyncio
    async def test_send_alert_success(self, adapter: Any) -> None:
        with patch.object(adapter.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"ok": True})
            mock_post.return_value.__aenter__.return_value = mock_response

            result = await adapter._send_alert("Test message")

            assert result is True
            mock_post.assert_called_once_with(
                f"https://api.telegram.org/bottest_token/sendMessage",
                json={"chat_id": "test_chat", "text": "Test message", "parse_mode": "HTML"},
            )

    @pytest.mark.asyncio
    async def test_send_alert_failure(self, adapter: Any) -> None:
        with patch.object(adapter.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.status = 400
            mock_response.text = AsyncMock(return_value="Bad request")
            mock_post.return_value.__aenter__.return_value = mock_response

            result = await adapter._send_alert("Test message")

            assert result is False

    @pytest.mark.asyncio
    async def test_handle_decision_with_deduplication(self, adapter: Any, mock_deduplicator: Any) -> None:
        decision = {
            "symbol": "BTCUSDT",
            "side": "long",
            "entry_price": Decimal("42000"),
            "timestamp": datetime.now(),
        }

        # Test duplicate
        mock_deduplicator.is_duplicate.return_value = True
        with patch.object(adapter, "_send_alert") as mock_send:
            await adapter._handle_decision(decision)
            mock_send.assert_not_called()

        # Test non-duplicate
        mock_deduplicator.is_duplicate.return_value = False
        with patch.object(adapter, "_send_alert") as mock_send:
            await adapter._handle_decision(decision)
            mock_send.assert_called_once()
            mock_deduplicator.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_order_update(self, adapter: Any, mock_formatter: Any) -> None:
        order = {"symbol": "BTCUSDT", "status": "filled"}

        with patch.object(adapter, "_send_alert") as mock_send:
            await adapter._handle_order_update(order)

            mock_formatter.format_order_update.assert_called_once_with(order)
            mock_send.assert_called_once_with("Formatted order")

    @pytest.mark.asyncio
    async def test_handle_guard_alert(self, adapter: Any, mock_formatter: Any) -> None:
        guard = {"type": "funding_rate", "symbol": "BTCUSDT"}

        with patch.object(adapter, "_send_alert") as mock_send:
            await adapter._handle_guard_alert(guard)

            mock_formatter.format_guard_alert.assert_called_once_with(guard)
            mock_send.assert_called_once_with("Formatted guard")

    @pytest.mark.asyncio
    async def test_rate_limiting(self, adapter: Any) -> None:
        adapter.rate_limiter = Mock()
        adapter.rate_limiter.check_rate_limit = AsyncMock(side_effect=[True, False, True])

        with patch.object(adapter, "_send_alert") as mock_send:
            # First call passes rate limit
            await adapter._send_alert("Message 1")
            assert mock_send.call_count == 0  # Rate limiter is checked in _send_alert

    @pytest.mark.asyncio
    async def test_stop_closes_session(self, adapter: Any) -> None:
        adapter.session = Mock()
        adapter.session.close = AsyncMock()

        await adapter.stop()

        adapter.session.close.assert_called_once()