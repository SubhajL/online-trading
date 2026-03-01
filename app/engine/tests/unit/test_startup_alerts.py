"""Unit tests for startup/warmup alert functionality."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.adapters.alert.alert_formatter import AlertFormatter
from app.engine.adapters.alert.alert_subscriber import AlertSubscriber
from app.engine.adapters.alert.telegram import TelegramAlertAdapter
from app.engine.models import EventType, StartupCompleteEvent


class TestAlertFormatterStartup:
    """Tests for AlertFormatter.format_startup_alert method."""

    @pytest.fixture
    def formatter(self) -> AlertFormatter:
        return AlertFormatter()

    def test_format_backfill_complete_alert(self, formatter: AlertFormatter) -> None:
        """Backfill complete alert includes symbols, timeframes, and counts."""
        startup_data = {
            "phase": "backfill_complete",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "timeframes": ["5m", "15m", "1h"],
            "candle_counts": {"BTCUSDT": 1500, "ETHUSDT": 1500},
            "duration_seconds": 12.5,
        }

        message = formatter.format_startup_alert(startup_data)

        assert "Backfill Complete" in message
        assert "BTCUSDT" in message
        assert "ETHUSDT" in message
        assert "5m" in message
        assert "15m" in message
        assert "1h" in message
        assert "1,500" in message or "1500" in message
        assert "12.5" in message or "12.50" in message

    def test_format_realtime_active_alert(self, formatter: AlertFormatter) -> None:
        """Realtime active alert includes symbols and status."""
        startup_data = {
            "phase": "realtime_active",
            "symbols": ["BTCUSDT"],
            "timeframes": ["15m"],
            "candle_counts": {"BTCUSDT": 1},
            "duration_seconds": 0.0,
        }

        message = formatter.format_startup_alert(startup_data)

        assert "Realtime Active" in message or "Realtime" in message
        assert "BTCUSDT" in message

    def test_format_startup_alert_includes_emoji(self, formatter: AlertFormatter) -> None:
        """Startup alerts include appropriate emoji."""
        startup_data = {
            "phase": "backfill_complete",
            "symbols": ["BTCUSDT"],
            "timeframes": ["15m"],
            "candle_counts": {"BTCUSDT": 100},
            "duration_seconds": 5.0,
        }

        message = formatter.format_startup_alert(startup_data)

        # Should include some kind of status emoji
        assert any(emoji in message for emoji in ["✅", "🚀", "📊", "🟢"])


class TestTelegramAdapterStartupAlert:
    """Tests for TelegramAlertAdapter.send_startup_alert method."""

    @pytest.fixture
    def telegram_adapter(self) -> TelegramAlertAdapter:
        adapter = TelegramAlertAdapter(
            bot_token="test-bot-token",
            chat_id="test-chat-id",
            rate_limit_per_minute=30,
        )
        adapter.deduplicator.redis_client = None
        adapter.startup_deduplicator.redis_client = MagicMock()
        adapter.startup_deduplicator.redis_client.get = MagicMock(return_value=None)
        adapter.startup_deduplicator.redis_client.set = MagicMock(return_value=True)
        adapter.startup_deduplicator.redis_client.delete = MagicMock(return_value=1)
        return adapter

    @pytest.mark.asyncio
    async def test_send_startup_alert_claims_before_sending(
        self,
        telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        calls: list[str] = []

        def try_add(_key: str) -> bool:
            calls.append("try_add")
            return True

        async def send(_message: str) -> bool:
            calls.append("send")
            return True

        telegram_adapter.startup_deduplicator.try_add = try_add  # type: ignore[method-assign]
        telegram_adapter._send_alert = send  # type: ignore[method-assign]

        startup_data = {
            "phase": "backfill_complete",
            "symbols": ["BTCUSDT"],
            "timeframes": ["15m"],
            "candle_counts": {"BTCUSDT": 100},
            "duration_seconds": 5.0,
        }

        ok = await telegram_adapter.send_startup_alert(startup_data)

        assert ok is True
        assert calls == ["try_add", "send"]

    @pytest.mark.asyncio
    async def test_send_startup_alert_skips_send_when_claim_fails(
        self,
        telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        telegram_adapter.startup_deduplicator.try_add = MagicMock(return_value=False)  # type: ignore[method-assign]
        telegram_adapter._send_alert = AsyncMock(return_value=True)  # type: ignore[method-assign]

        startup_data = {
            "phase": "backfill_complete",
            "symbols": ["BTCUSDT"],
            "timeframes": ["15m"],
            "candle_counts": {"BTCUSDT": 100},
            "duration_seconds": 5.0,
        }

        ok = await telegram_adapter.send_startup_alert(startup_data)

        assert ok is False
        telegram_adapter._send_alert.assert_not_called()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_send_startup_alert_clears_key_on_send_failure(
        self,
        telegram_adapter: TelegramAlertAdapter,
    ) -> None:
        telegram_adapter.startup_deduplicator.try_add = MagicMock(return_value=True)  # type: ignore[method-assign]
        telegram_adapter.startup_deduplicator.clear = MagicMock()  # type: ignore[method-assign]
        telegram_adapter._send_alert = AsyncMock(return_value=False)  # type: ignore[method-assign]

        startup_data = {
            "phase": "backfill_complete",
            "symbols": ["BTCUSDT"],
            "timeframes": ["15m"],
            "candle_counts": {"BTCUSDT": 100},
            "duration_seconds": 5.0,
        }

        ok = await telegram_adapter.send_startup_alert(startup_data)

        assert ok is False
        telegram_adapter.startup_deduplicator.clear.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_send_startup_alert_calls_telegram_api(
        self, telegram_adapter: TelegramAlertAdapter
    ) -> None:
        """send_startup_alert sends formatted message to Telegram."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ok": True})

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_context)

        telegram_adapter.session = mock_session

        startup_data = {
            "phase": "backfill_complete",
            "symbols": ["BTCUSDT"],
            "timeframes": ["15m"],
            "candle_counts": {"BTCUSDT": 100},
            "duration_seconds": 5.0,
        }

        success = await telegram_adapter.send_startup_alert(startup_data)

        assert success is True
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert "sendMessage" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_send_startup_alert_handles_api_failure(
        self, telegram_adapter: TelegramAlertAdapter
    ) -> None:
        """send_startup_alert returns False on API failure."""
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Server error")

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_context)

        telegram_adapter.session = mock_session

        startup_data = {
            "phase": "backfill_complete",
            "symbols": ["BTCUSDT"],
            "timeframes": ["15m"],
            "candle_counts": {"BTCUSDT": 100},
            "duration_seconds": 5.0,
        }

        success = await telegram_adapter.send_startup_alert(startup_data)

        assert success is False

    @pytest.mark.asyncio
    async def test_send_startup_alert_no_session(
        self, telegram_adapter: TelegramAlertAdapter
    ) -> None:
        """send_startup_alert returns False if session not initialized."""
        telegram_adapter.session = None

        startup_data = {
            "phase": "backfill_complete",
            "symbols": ["BTCUSDT"],
            "timeframes": ["15m"],
            "candle_counts": {"BTCUSDT": 100},
            "duration_seconds": 5.0,
        }

        success = await telegram_adapter.send_startup_alert(startup_data)

        assert success is False


class TestAlertSubscriberStartup:
    """Tests for AlertSubscriber handling of STARTUP_COMPLETE events."""

    @pytest.fixture
    def mock_telegram_adapter(self) -> MagicMock:
        adapter = MagicMock()
        adapter.send_startup_alert = AsyncMock(return_value=True)
        return adapter

    @pytest.mark.asyncio
    async def test_alert_subscriber_handles_startup_complete_event(
        self, mock_telegram_adapter: MagicMock
    ) -> None:
        """AlertSubscriber routes STARTUP_COMPLETE events to telegram."""
        subscriber = AlertSubscriber(
            telegram_adapter=mock_telegram_adapter,
            execution_enabled=False,
        )

        event = StartupCompleteEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            phase="backfill_complete",
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=["15m", "1h"],
            candle_counts={"BTCUSDT": 100, "ETHUSDT": 100},
            duration_seconds=5.5,
        )

        await subscriber._handle_event(event)

        mock_telegram_adapter.send_startup_alert.assert_called_once()
        call_args = mock_telegram_adapter.send_startup_alert.call_args[0][0]
        assert call_args["phase"] == "backfill_complete"
        assert "BTCUSDT" in call_args["symbols"]
        assert call_args["duration_seconds"] == 5.5

    @pytest.mark.asyncio
    async def test_startup_complete_in_execution_enabled_event_types(self) -> None:
        """STARTUP_COMPLETE is in both execution enabled and disabled event types."""
        from app.engine.adapters.alert.alert_subscriber import (
            EXECUTION_DISABLED_EVENT_TYPES,
            EXECUTION_ENABLED_EVENT_TYPES,
        )

        assert EventType.STARTUP_COMPLETE in EXECUTION_ENABLED_EVENT_TYPES
        assert EventType.STARTUP_COMPLETE in EXECUTION_DISABLED_EVENT_TYPES

    @pytest.mark.asyncio
    async def test_no_telegram_adapter_skips_startup_event(self) -> None:
        """AlertSubscriber with no telegram adapter skips startup events."""
        subscriber = AlertSubscriber(
            telegram_adapter=None,
            execution_enabled=False,
        )

        event = StartupCompleteEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            phase="backfill_complete",
            symbols=["BTCUSDT"],
            timeframes=["15m"],
            candle_counts={"BTCUSDT": 100},
            duration_seconds=1.0,
        )

        # Should not raise
        await subscriber._handle_event(event)
