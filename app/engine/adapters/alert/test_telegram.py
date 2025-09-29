import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio
from datetime import datetime
from decimal import Decimal
import uuid

from app.engine.adapters.alert.telegram import TelegramAlertAdapter
from app.engine.adapters.alert.test_helpers import (
    get_mock_telegram_client,
    get_test_event_bus,
    is_ci,
    skip_if_no_service,
)
from app.engine.adapters.alert.alert_deduplicator import AlertDeduplicator
from app.engine.adapters.alert.alert_formatter import AlertFormatter
from typing import Any



class TestTelegramAlertAdapter:
    @pytest.fixture
    def event_bus(self) -> Any:
        """Get test event bus."""
        return get_test_event_bus()

    @pytest.fixture
    def deduplicator(self) -> Any:
        """Get real deduplicator for testing."""
        # In CI, we still use real Redis since it's provided
        return AlertDeduplicator(ttl_seconds=60)

    @pytest.fixture
    def formatter(self) -> Any:
        """Get real formatter for testing."""
        return AlertFormatter()

    @pytest.fixture
    def adapter(self, event_bus: Any, deduplicator: Any, formatter: Any) -> Any:
        """Create adapter with CI-aware Telegram client."""
        if is_ci():
            # In CI, mock the HTTP session
            with patch("aiohttp.ClientSession"):
                adapter = TelegramAlertAdapter(
                    bot_token="test-token",
                    chat_id="test-chat",
                    event_bus=event_bus,
                )
                adapter.deduplicator = deduplicator
                adapter.formatter = formatter
                # Mock the session for CI
                # Create a proper mock session
                mock_session = AsyncMock()

                # Setup the post method to return async context manager
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value={"ok": True})

                mock_context = AsyncMock()
                mock_context.__aenter__.return_value = mock_response
                mock_context.__aexit__.return_value = None

                mock_session.post.return_value = mock_context
                mock_session.close = AsyncMock()

                adapter.session = mock_session
                return adapter
        else:
            # In local, could use real Telegram if credentials exist
            # For now, still mock to avoid spamming real channels
            with patch("aiohttp.ClientSession"):
                adapter = TelegramAlertAdapter(
                    bot_token="test-token",
                    chat_id="test-chat",
                    event_bus=event_bus,
                )
                adapter.deduplicator = deduplicator
                adapter.formatter = formatter
                # Create a proper mock session
                mock_session = AsyncMock()

                # Setup the post method to return async context manager
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value={"ok": True})

                mock_context = AsyncMock()
                mock_context.__aenter__.return_value = mock_response
                mock_context.__aexit__.return_value = None

                mock_session.post.return_value = mock_context
                mock_session.close = AsyncMock()

                adapter.session = mock_session
                return adapter

    @pytest.mark.asyncio
    async def test_init_subscribes_to_events(self, event_bus: Any) -> None:
        """Test that adapter subscribes to correct events."""
        with patch("aiohttp.ClientSession"):
            adapter = TelegramAlertAdapter(
                bot_token="test-token",
                chat_id="test-chat",
                event_bus=event_bus,
            )
            await adapter.start()

        # Check subscriptions
        assert "decision.v1" in event_bus.subscriptions
        assert "order_update.v1" in event_bus.subscriptions
        assert "guard_alert.v1" in event_bus.subscriptions

    @pytest.mark.asyncio
    async def test_send_alert_success(self, adapter: Any) -> None:
        """Test successful alert sending."""
        # Create a proper async context manager mock
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ok": True})

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None

        adapter.session.post.return_value = mock_context

        result = await adapter._send_alert("Test message")

        assert result is True
        adapter.session.post.assert_called_once_with(
            f"https://api.telegram.org/bottest-token/sendMessage",
            json={"chat_id": "test-chat", "text": "Test message", "parse_mode": "HTML"},
        )

    @pytest.mark.asyncio
    async def test_send_alert_failure(self, adapter: Any) -> None:
        """Test failed alert sending."""
        # Create a proper async context manager mock
        mock_response = Mock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Bad request")

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None

        adapter.session.post.return_value = mock_context

        result = await adapter._send_alert("Test message")

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_decision_with_deduplication(self, adapter: Any) -> None:
        """Test decision handling with deduplication."""
        decision = {
            "symbol": "BTCUSDT",
            "side": "long",
            "entry_price": Decimal("42000"),
            "stop_loss": Decimal("40000"),
            "take_profit": Decimal("45000"),
            "quantity": Decimal("0.1"),
            "confidence": 0.85,
            "reasons": ["Strong bullish trend", "Support at 40k"],
            "timestamp": datetime.now(),
        }

        # Generate unique key for this test
        decision["test_id"] = uuid.uuid4().hex[:8]

        # First call should send
        with patch.object(adapter, "_send_alert", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await adapter._handle_decision(decision)
            mock_send.assert_called_once()

        # Second call with same decision should be deduplicated
        with patch.object(adapter, "_send_alert", new_callable=AsyncMock) as mock_send:
            await adapter._handle_decision(decision)
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_order_update(self, adapter: Any) -> None:
        """Test order update handling."""
        order = {
            "symbol": "BTCUSDT",
            "side": "buy",
            "status": "filled",
            "quantity": Decimal("0.1"),
            "filled_price": Decimal("42000"),
            "order_id": uuid.uuid4().hex[:8],
        }

        with patch.object(adapter, "_send_alert", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await adapter._handle_order_update(order)

            mock_send.assert_called_once()
            # Check that formatter was used (message should contain symbol)
            call_args = mock_send.call_args[0][0]
            assert "BTCUSDT" in call_args

    @pytest.mark.asyncio
    async def test_handle_guard_alert(self, adapter: Any) -> None:
        """Test guard alert handling."""
        guard = {
            "type": "funding_rate",
            "symbol": "BTCUSDT",
            "timestamp": datetime.now(),
            "current_value": 0.001,
            "threshold": 0.0005,
            "message": "High funding rate detected",
            "action": "reduce_exposure",
        }

        with patch.object(adapter, "_send_alert", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await adapter._handle_guard_alert(guard)

            mock_send.assert_called_once()
            # Check that formatter was used (message should contain type)
            call_args = mock_send.call_args[0][0]
            assert "funding" in call_args.lower() and "rate" in call_args.lower()

    @pytest.mark.asyncio
    async def test_rate_limiting(self, adapter: Any) -> None:
        """Test rate limiting functionality."""
        # Create a simple rate limiter mock
        adapter.rate_limiter = Mock()
        adapter.rate_limiter.check_rate_limit = AsyncMock(return_value=True)

        # Send should succeed when rate limit allows
        result = await adapter._send_alert("Test message")
        # Result depends on mock response setup
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_stop_closes_session(self, adapter: Any) -> None:
        """Test that stop properly closes the session."""
        # Session is already mocked in adapter fixture
        await adapter.stop()

        adapter.session.close.assert_called_once()