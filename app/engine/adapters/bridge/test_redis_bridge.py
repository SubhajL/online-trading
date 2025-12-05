"""Tests for RedisBridge forwarding events to Redis pub/sub."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from app.engine.adapters.bridge.redis_bridge import RedisBridge
from app.engine.models import BaseEvent, EventType


class TestRedisBridge:
    """Test that RedisBridge correctly forwards events to Redis."""

    @pytest.fixture
    def mock_redis_adapter(self) -> Mock:
        """Create a mock Redis adapter."""
        adapter = Mock()
        adapter.publish = AsyncMock(return_value=1)
        return adapter

    @pytest.fixture
    def mock_event_bus(self) -> Mock:
        """Create a mock event bus."""
        bus = Mock()
        bus.subscribe = AsyncMock(return_value="sub_123")
        bus.unsubscribe = AsyncMock(return_value=True)
        return bus

    @pytest.fixture
    def bridge(self, mock_redis_adapter: Mock, mock_event_bus: Mock) -> RedisBridge:
        """Create a RedisBridge with mocked dependencies."""
        return RedisBridge(mock_redis_adapter, mock_event_bus)

    @pytest.mark.asyncio
    async def test_redis_bridge_subscribes_to_all_events(
        self,
        bridge: RedisBridge,
        mock_event_bus: Mock,
    ) -> None:
        """subscription created with event_types=None for all events."""
        await bridge.start()

        mock_event_bus.subscribe.assert_called_once()
        call_kwargs = mock_event_bus.subscribe.call_args.kwargs
        assert call_kwargs["event_types"] is None
        assert call_kwargs["subscriber_id"] == "redis_bridge"

    @pytest.mark.asyncio
    async def test_redis_bridge_publishes_to_correct_channel(
        self,
        bridge: RedisBridge,
        mock_redis_adapter: Mock,
    ) -> None:
        """channel is engine:{event_type}."""
        event = BaseEvent(
            event_type=EventType.TRADING_DECISION,
            timestamp=datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
            symbol="BTCUSDT",
        )

        await bridge.forward_to_redis(event)

        mock_redis_adapter.publish.assert_called_once()
        channel = mock_redis_adapter.publish.call_args[0][0]
        assert channel == "engine:trading_decision"

    @pytest.mark.asyncio
    async def test_redis_bridge_serializes_event_as_json(
        self,
        bridge: RedisBridge,
        mock_redis_adapter: Mock,
    ) -> None:
        """payload is valid JSON string from model_dump_json."""
        event = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
            symbol="ETHUSDT",
        )

        await bridge.forward_to_redis(event)

        payload = mock_redis_adapter.publish.call_args[0][1]
        assert isinstance(payload, str)
        assert '"symbol":"ETHUSDT"' in payload
        assert '"event_type":"candle_update"' in payload

    @pytest.mark.asyncio
    async def test_redis_bridge_stops_cleanly(
        self,
        bridge: RedisBridge,
        mock_event_bus: Mock,
    ) -> None:
        """unsubscribe called on stop."""
        await bridge.start()
        await bridge.stop()

        mock_event_bus.unsubscribe.assert_called_once_with("sub_123")

    @pytest.mark.asyncio
    async def test_redis_bridge_stop_without_start_is_safe(
        self,
        bridge: RedisBridge,
        mock_event_bus: Mock,
    ) -> None:
        """stop without start should not raise."""
        await bridge.stop()

        mock_event_bus.unsubscribe.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_bridge_start_is_idempotent(
        self,
        bridge: RedisBridge,
        mock_event_bus: Mock,
    ) -> None:
        """Calling start twice unsubscribes first subscription."""
        mock_event_bus.subscribe = AsyncMock(side_effect=["sub_1", "sub_2"])

        await bridge.start()
        await bridge.start()

        expected_call_count = 2
        assert mock_event_bus.subscribe.call_count == expected_call_count
        mock_event_bus.unsubscribe.assert_called_once_with("sub_1")

    @pytest.mark.asyncio
    async def test_redis_bridge_handles_publish_error(
        self,
        bridge: RedisBridge,
        mock_redis_adapter: Mock,
    ) -> None:
        """Redis publish error is logged but does not raise."""
        mock_redis_adapter.publish = AsyncMock(
            side_effect=ConnectionError("Redis down"),
        )
        event = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
            symbol="BTCUSDT",
        )

        await bridge.forward_to_redis(event)

    @pytest.mark.asyncio
    async def test_redis_bridge_stop_handles_unsubscribe_failure(
        self,
        bridge: RedisBridge,
        mock_event_bus: Mock,
    ) -> None:
        """Failed unsubscribe keeps subscription_id."""
        mock_event_bus.unsubscribe = AsyncMock(return_value=False)
        await bridge.start()

        await bridge.stop()

        assert bridge.is_running
