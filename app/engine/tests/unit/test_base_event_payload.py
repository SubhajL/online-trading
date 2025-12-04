"""Tests for BaseEvent payload field and topic-to-event-type mapping."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.engine.bus import TOPIC_TO_EVENT_TYPE, publish_event, set_event_bus
from app.engine.models import BaseEvent, EventType, TimeFrame


class TestBaseEventPayload:
    """Tests for BaseEvent payload field."""

    def test_base_event_accepts_payload_field(self) -> None:
        """BaseEvent should accept a payload dict."""
        payload = {"symbol": "BTCUSDT", "price": "50000.00"}
        event = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            payload=payload,
        )
        assert event.payload == payload

    def test_base_event_payload_defaults_to_empty_dict(self) -> None:
        """BaseEvent payload should default to empty dict."""
        event = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
        )
        assert event.payload == {}

    def test_base_event_payload_serializes_to_dict(self) -> None:
        """BaseEvent payload should be included in model_dump."""
        payload = {"venue": "binance", "is_closed": True}
        event = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            payload=payload,
        )
        dumped = event.model_dump()
        assert dumped["payload"] == payload

    def test_base_event_payload_with_nested_data(self) -> None:
        """BaseEvent payload should handle nested structures."""
        payload = {
            "candle": {
                "open": "50000",
                "high": "51000",
                "low": "49000",
                "close": "50500",
            },
            "indicators": ["ema_20", "rsi_14"],
        }
        event = BaseEvent(
            event_type=EventType.FEATURES_CALCULATED,
            timestamp=datetime.now(UTC),
            symbol="ETHUSDT",
            payload=payload,
        )
        assert event.payload["candle"]["high"] == "51000"
        assert "rsi_14" in event.payload["indicators"]


class TestTopicToEventTypeMapping:
    """Tests for TOPIC_TO_EVENT_TYPE mapping."""

    def test_topic_mapping_exists(self) -> None:
        """TOPIC_TO_EVENT_TYPE should be importable from bus module."""
        assert isinstance(TOPIC_TO_EVENT_TYPE, dict)

    def test_candles_topic_maps_to_candle_update(self) -> None:
        """candles.v1 should map to CANDLE_UPDATE."""
        assert TOPIC_TO_EVENT_TYPE["candles.v1"] == EventType.CANDLE_UPDATE

    def test_features_topic_maps_to_features_calculated(self) -> None:
        """features.v1 should map to FEATURES_CALCULATED."""
        assert TOPIC_TO_EVENT_TYPE["features.v1"] == EventType.FEATURES_CALCULATED

    def test_smc_events_topic_maps_to_smc_signal(self) -> None:
        """smc_events.v1 should map to SMC_SIGNAL."""
        assert TOPIC_TO_EVENT_TYPE["smc_events.v1"] == EventType.SMC_SIGNAL

    def test_decision_topic_maps_to_trading_decision(self) -> None:
        """decision.v1 should map to TRADING_DECISION."""
        assert TOPIC_TO_EVENT_TYPE["decision.v1"] == EventType.TRADING_DECISION

    def test_order_update_topic_maps_to_order_placed(self) -> None:
        """order_update.v1 should map to ORDER_PLACED."""
        assert TOPIC_TO_EVENT_TYPE["order_update.v1"] == EventType.ORDER_PLACED

    def test_signals_raw_topic_maps_to_retest_signal(self) -> None:
        """signals_raw.v1 should map to RETEST_SIGNAL."""
        assert TOPIC_TO_EVENT_TYPE["signals_raw.v1"] == EventType.RETEST_SIGNAL


class TestPublishEvent:
    """Tests for publish_event function."""

    @pytest.mark.asyncio
    async def test_publish_event_routes_candles_to_candle_update(self) -> None:
        """publish_event should route candles.v1 to CANDLE_UPDATE."""
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock(return_value=True)
        set_event_bus(mock_bus)

        data = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "timestamp": datetime.now(UTC),
        }
        await publish_event("candles.v1", data)

        mock_bus.publish.assert_called_once()
        event = mock_bus.publish.call_args[0][0]
        assert event.event_type == EventType.CANDLE_UPDATE

    @pytest.mark.asyncio
    async def test_publish_event_routes_decision_to_trading_decision(self) -> None:
        """publish_event should route decision.v1 to TRADING_DECISION."""
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock(return_value=True)
        set_event_bus(mock_bus)

        data = {
            "symbol": "ETHUSDT",
            "timestamp": datetime.now(UTC),
        }
        await publish_event("decision.v1", data)

        mock_bus.publish.assert_called_once()
        event = mock_bus.publish.call_args[0][0]
        assert event.event_type == EventType.TRADING_DECISION

    @pytest.mark.asyncio
    async def test_publish_event_stores_data_in_payload(self) -> None:
        """publish_event should store data dict in payload field."""
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock(return_value=True)
        set_event_bus(mock_bus)

        data = {
            "symbol": "BTCUSDT",
            "venue": "binance",
            "open": "50000",
            "high": "51000",
            "timestamp": datetime.now(UTC),
        }
        await publish_event("candles.v1", data)

        event = mock_bus.publish.call_args[0][0]
        assert event.payload["venue"] == "binance"
        assert event.payload["open"] == "50000"
        assert event.payload["high"] == "51000"

    @pytest.mark.asyncio
    async def test_publish_event_extracts_symbol_from_data(self) -> None:
        """publish_event should extract symbol from data."""
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock(return_value=True)
        set_event_bus(mock_bus)

        data = {
            "symbol": "SOLUSDT",
            "timestamp": datetime.now(UTC),
        }
        await publish_event("features.v1", data)

        event = mock_bus.publish.call_args[0][0]
        assert event.symbol == "SOLUSDT"

    @pytest.mark.asyncio
    async def test_publish_event_extracts_timeframe_from_data(self) -> None:
        """publish_event should extract timeframe from data when present."""
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock(return_value=True)
        set_event_bus(mock_bus)

        data = {
            "symbol": "BTCUSDT",
            "timeframe": "4h",
            "timestamp": datetime.now(UTC),
        }
        await publish_event("candles.v1", data)

        event = mock_bus.publish.call_args[0][0]
        assert event.timeframe == TimeFrame.H4

    @pytest.mark.asyncio
    async def test_publish_event_unknown_topic_defaults_to_candle_update(self) -> None:
        """publish_event with unknown topic should default to CANDLE_UPDATE."""
        mock_bus = AsyncMock()
        mock_bus.publish = AsyncMock(return_value=True)
        set_event_bus(mock_bus)

        data = {
            "symbol": "BTCUSDT",
            "timestamp": datetime.now(UTC),
        }
        await publish_event("unknown.topic", data)

        event = mock_bus.publish.call_args[0][0]
        assert event.event_type == EventType.CANDLE_UPDATE
