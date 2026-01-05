"""Tests for SignalEmitter publishing BaseEvent objects."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.engine.adapters.alert.signal_emitter import SignalEmitter
from app.engine.models import BaseEvent, EventType, TradingDecisionEvent


class TestSignalEmitterPublishesBaseEvent:
    """Test that SignalEmitter publishes proper BaseEvent objects."""

    @pytest.fixture
    def mock_event_bus(self) -> Mock:
        """Create a mock event bus that captures published events."""
        bus = Mock()
        bus.publish = AsyncMock(return_value=True)
        return bus

    @pytest.fixture
    def mock_bff_client(self) -> Mock:
        """Create a mock BFF client."""
        client = Mock()
        client.post = AsyncMock(
            return_value={"success": True, "signalId": "test", "imageUrl": "/test.png"},
        )
        return client

    @pytest.fixture
    def emitter(self, mock_event_bus: Mock, mock_bff_client: Mock) -> SignalEmitter:
        """Create a SignalEmitter with mocked dependencies."""
        return SignalEmitter(mock_event_bus, mock_bff_client)

    @pytest.mark.asyncio
    async def test_signal_emitter_publishes_base_event_object(
        self,
        emitter: SignalEmitter,
        mock_event_bus: Mock,
    ) -> None:
        """bus.publish receives BaseEvent instance, not a dict."""
        decision_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

        await emitter.emit_signal(
            symbol="BTCUSDT",
            venue="SPOT",
            side="long",
            entry=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0,
            confidence=0.85,
            reasons=["SMC Breaker", "Bullish OB"],
            timeframe="15m",
            decision_time=decision_time,
        )

        mock_event_bus.publish.assert_called_once()
        call_args = mock_event_bus.publish.call_args
        published_event = call_args[0][0]

        assert isinstance(
            published_event,
            BaseEvent,
        ), f"Expected BaseEvent, got {type(published_event)}"

    @pytest.mark.asyncio
    async def test_signal_emitter_uses_trading_decision_event_type(
        self,
        emitter: SignalEmitter,
        mock_event_bus: Mock,
    ) -> None:
        """event.event_type is TRADING_DECISION."""
        decision_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

        await emitter.emit_signal(
            symbol="ETHUSDT",
            venue="USD_M",
            side="short",
            entry=3000.0,
            stop_loss=3100.0,
            take_profit=2800.0,
            confidence=0.72,
            reasons=["Bearish FVG"],
            timeframe="1h",
            decision_time=decision_time,
        )

        published_event = mock_event_bus.publish.call_args[0][0]

        assert published_event.event_type == EventType.TRADING_DECISION

    @pytest.mark.asyncio
    async def test_signal_emitter_includes_decision_in_payload(
        self,
        emitter: SignalEmitter,
        mock_event_bus: Mock,
    ) -> None:
        """decision fields accessible via event.decision or payload."""
        decision_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

        signal_id = await emitter.emit_signal(
            symbol="SOLUSDT",
            venue="SPOT",
            side="long",
            entry=150.0,
            stop_loss=145.0,
            take_profit=160.0,
            confidence=0.90,
            reasons=["Trend Alignment", "OB Retest"],
            timeframe="15m",
            decision_time=decision_time,
        )

        published_event = mock_event_bus.publish.call_args[0][0]

        expected_entry = Decimal("150.0")
        expected_stop = Decimal("145.0")
        expected_take = Decimal("160.0")
        expected_conf = Decimal("0.90")

        assert isinstance(published_event, TradingDecisionEvent)
        decision = published_event.decision
        assert decision.symbol == "SOLUSDT"
        assert decision.entry_price == expected_entry
        assert decision.stop_loss == expected_stop
        assert decision.take_profit == expected_take
        assert decision.confidence == expected_conf
        assert decision.action == "BUY"

        assert signal_id.startswith("sig_")

    @pytest.mark.asyncio
    async def test_signal_emitter_sets_correct_symbol_and_timestamp(
        self,
        emitter: SignalEmitter,
        mock_event_bus: Mock,
    ) -> None:
        """BaseEvent has correct symbol and timestamp fields."""
        decision_time = datetime(2025, 6, 20, 14, 30, 0, tzinfo=UTC)

        await emitter.emit_signal(
            symbol="AVAXUSDT",
            venue="USD_M",
            side="short",
            entry=35.0,
            stop_loss=36.0,
            take_profit=32.0,
            confidence=0.65,
            reasons=["Structure Break"],
            timeframe="4h",
            decision_time=decision_time,
        )

        published_event = mock_event_bus.publish.call_args[0][0]

        assert published_event.symbol == "AVAXUSDT"
        assert published_event.timestamp == decision_time

    @pytest.mark.asyncio
    async def test_signal_emitter_converts_side_to_action(
        self,
        emitter: SignalEmitter,
        mock_event_bus: Mock,
    ) -> None:
        """'long' becomes 'BUY', 'short' becomes 'SELL'."""
        decision_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

        await emitter.emit_signal(
            symbol="BTCUSDT",
            venue="SPOT",
            side="long",
            entry=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0,
            confidence=0.80,
            reasons=["Test"],
            decision_time=decision_time,
        )

        published_event = mock_event_bus.publish.call_args[0][0]

        if isinstance(published_event, TradingDecisionEvent):
            assert published_event.decision.action == "BUY"

        mock_event_bus.publish.reset_mock()

        await emitter.emit_signal(
            symbol="ETHUSDT",
            venue="USD_M",
            side="short",
            entry=3000.0,
            stop_loss=3100.0,
            take_profit=2800.0,
            confidence=0.75,
            reasons=["Test"],
            decision_time=decision_time,
        )

        published_event = mock_event_bus.publish.call_args[0][0]

        if isinstance(published_event, TradingDecisionEvent):
            assert published_event.decision.action == "SELL"

    @pytest.mark.asyncio
    async def test_signal_emitter_populates_metadata_for_audit(
        self,
        emitter: SignalEmitter,
        mock_event_bus: Mock,
    ) -> None:
        """Metadata includes signal_id, venue, timeframe, and optional zone."""
        decision_time = datetime(2025, 7, 1, 9, 0, 0, tzinfo=UTC)
        zone = {
            "zone_type": "FAIR_VALUE_GAP",
            "top_price": Decimal(3190),
            "bottom_price": Decimal(3180),
        }

        signal_id = await emitter.emit_signal(
            symbol="ETHUSDT",
            venue="SPOT",
            side="short",
            entry=3184.36,
            stop_loss=3187.16,
            take_profit=3152.52,
            confidence=0.65,
            reasons=["FVG fill with bearish bias"],
            timeframe="15m",
            decision_time=decision_time,
            zone=zone,
        )

        published_event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(published_event, TradingDecisionEvent)
        assert published_event.metadata["signal_id"] == signal_id
        assert published_event.metadata["venue"] == "SPOT"
        assert published_event.metadata["timeframe"] == "15m"
        assert published_event.metadata["zone"] == zone
