"""
Unit tests for AlertSubscriber.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine.adapters.alert.alert_subscriber import AlertSubscriber
from app.engine.models import (
    ErrorEvent,
    EventType,
    Order,
    OrderFilledEvent,
    OrderSide,
    OrderType,
    TimeFrame,
    TradingDecision,
    TradingDecisionEvent,
)


class _FakeBus:
    """Fake event bus for testing."""

    def __init__(self) -> None:
        self.subscriptions: list[dict[str, object]] = []
        self.unsubscribed: list[str] = []

    async def subscribe(
        self,
        subscriber_id: str,
        handler: object,
        event_types: list[EventType] | None = None,
        priority: int = 0,
    ) -> str:
        sub_id = f"sub-{len(self.subscriptions)}"
        self.subscriptions.append(
            {
                "subscriber_id": subscriber_id,
                "handler": handler,
                "event_types": event_types,
                "priority": priority,
                "sub_id": sub_id,
            },
        )
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        self.unsubscribed.append(subscription_id)
        return True


def _make_trading_decision_event(*, timestamp: datetime) -> TradingDecisionEvent:
    decision = TradingDecision(
        symbol="BTCUSDT",
        timestamp=timestamp,
        action="BUY",
        entry_price=Decimal(50000),
        stop_loss=Decimal(49000),
        take_profit=Decimal(52000),
        quantity=Decimal("0.01"),
        confidence=Decimal("0.85"),
        reasoning="SMC Break; Trend Alignment",
    )
    return TradingDecisionEvent(
        timestamp=timestamp,
        symbol="BTCUSDT",
        timeframe=TimeFrame.H1,
        metadata={"signal_id": "sig_123"},
        decision=decision,
    )


def _make_order_filled_event(*, timestamp: datetime) -> OrderFilledEvent:
    order = Order(
        client_order_id="order-123",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        created_at=timestamp,
    )
    return OrderFilledEvent(
        timestamp=timestamp,
        symbol="BTCUSDT",
        order=order,
        fill_price=Decimal("50123.45"),
        fill_quantity=Decimal("0.01"),
        fill_timestamp=timestamp,
    )


def _make_error_event(*, timestamp: datetime) -> ErrorEvent:
    return ErrorEvent(
        timestamp=timestamp,
        symbol="BTCUSDT",
        component="ingest",
        error_type="ConnectionError",
        error_message="WebSocket disconnected",
    )


class TestAlertSubscriberRegister:
    @pytest.mark.asyncio
    async def test_registers_with_subscriber_id(self) -> None:
        bus = _FakeBus()
        subscriber = AlertSubscriber()

        await subscriber.register(bus)

        assert len(bus.subscriptions) == 1
        assert bus.subscriptions[0]["subscriber_id"] == "alert-subscriber"

    @pytest.mark.asyncio
    async def test_registers_with_correct_event_types(self) -> None:
        bus = _FakeBus()
        subscriber = AlertSubscriber()

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert event_types is not None
        assert EventType.TRADING_DECISION in event_types
        assert EventType.ORDER_FILLED in event_types
        assert EventType.ERROR in event_types

    @pytest.mark.asyncio
    async def test_registers_with_low_priority(self) -> None:
        bus = _FakeBus()
        subscriber = AlertSubscriber()

        await subscriber.register(bus)

        assert bus.subscriptions[0]["priority"] == 10


class TestAlertSubscriberUnregister:
    @pytest.mark.asyncio
    async def test_unregisters_from_bus(self) -> None:
        bus = _FakeBus()
        subscriber = AlertSubscriber()
        await subscriber.register(bus)

        await subscriber.unregister()

        assert "sub-0" in bus.unsubscribed


class TestAlertSubscriberHandleEvent:
    @pytest.mark.asyncio
    async def test_routes_trading_decision_to_telegram(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._handle_decision = AsyncMock()

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)

        await subscriber._handle_event(_make_trading_decision_event(timestamp=ts))

        mock_telegram._handle_decision.assert_called_once()
        payload = mock_telegram._handle_decision.call_args[0][0]
        assert payload["symbol"] == "BTCUSDT"
        assert payload["side"] == "long"
        assert payload["entry_price"] == Decimal(50000)
        assert payload["stop_loss"] == Decimal(49000)
        assert payload["take_profit"] == Decimal(52000)
        assert payload["quantity"] == Decimal("0.01")
        assert payload["signal_id"] == "sig_123"
        assert payload["timeframe"] == "1h"
        assert payload["venue"] is None
        assert payload["reasons"] == ["SMC Break", "Trend Alignment"]

    @pytest.mark.asyncio
    async def test_routes_zone_metadata_to_telegram_payload(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._handle_decision = AsyncMock()

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)

        decision = TradingDecision(
            symbol="ETHUSDT",
            timestamp=ts,
            action="SELL",
            entry_price=Decimal("3184.36"),
            stop_loss=Decimal("3187.16"),
            take_profit=Decimal("3152.52"),
            quantity=Decimal("0.01"),
            confidence=Decimal("0.65"),
            reasoning="FVG fill with bearish bias",
        )
        event = TradingDecisionEvent(
            timestamp=ts,
            symbol="ETHUSDT",
            timeframe=TimeFrame.M15,
            decision=decision,
            metadata={
                "signal_id": "sig_456",
                "timeframe": "15m",
                "zone": {
                    "zone_type": "FAIR_VALUE_GAP",
                    "top_price": Decimal(3190),
                    "bottom_price": Decimal(3180),
                },
            },
        )

        await subscriber._handle_event(event)

        payload = mock_telegram._handle_decision.call_args[0][0]
        assert payload["zone"] == {
            "zone_type": "FAIR_VALUE_GAP",
            "top_price": Decimal(3190),
            "bottom_price": Decimal(3180),
        }

    @pytest.mark.asyncio
    async def test_routes_order_filled_to_telegram(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._handle_order_update = AsyncMock()

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)

        await subscriber._handle_event(_make_order_filled_event(timestamp=ts))

        mock_telegram._handle_order_update.assert_called_once()
        payload = mock_telegram._handle_order_update.call_args[0][0]
        assert payload["symbol"] == "BTCUSDT"
        assert payload["status"] == "filled"
        assert payload["side"] == "buy"
        assert payload["filled_price"] == Decimal("50123.45")

    @pytest.mark.asyncio
    async def test_routes_error_to_telegram(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._send_alert = AsyncMock(return_value=True)

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)

        await subscriber._handle_event(_make_error_event(timestamp=ts))

        mock_telegram._send_alert.assert_called_once()
        message = mock_telegram._send_alert.call_args[0][0]
        assert "Engine error" in message
        assert "ingest" in message

    @pytest.mark.asyncio
    async def test_handles_no_telegram_adapter(self) -> None:
        subscriber = AlertSubscriber(telegram_adapter=None)
        ts = datetime.now(UTC)
        await subscriber._handle_event(_make_trading_decision_event(timestamp=ts))

    @pytest.mark.asyncio
    async def test_handles_telegram_error_gracefully(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._handle_decision = AsyncMock(
            side_effect=Exception("Network error"),
        )

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)
        await subscriber._handle_event(_make_trading_decision_event(timestamp=ts))


class TestAlertSubscriberStop:
    @pytest.mark.asyncio
    async def test_stop_calls_unregister(self) -> None:
        bus = _FakeBus()
        subscriber = AlertSubscriber()
        await subscriber.register(bus)

        await subscriber.stop()

        assert "sub-0" in bus.unsubscribed


class TestAlertSubscriberEventTypesParameter:
    """Tests for configurable event_types parameter."""

    @pytest.mark.asyncio
    async def test_default_event_types_when_none(self) -> None:
        """When event_types=None, uses default list of all three types."""
        bus = _FakeBus()
        subscriber = AlertSubscriber(event_types=None)

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert event_types is not None
        assert len(event_types) == 3
        assert EventType.TRADING_DECISION in event_types
        assert EventType.ORDER_FILLED in event_types
        assert EventType.ERROR in event_types

    @pytest.mark.asyncio
    async def test_custom_event_types_override(self) -> None:
        """When event_types provided, uses only those types."""
        bus = _FakeBus()
        custom_types = [EventType.TRADING_DECISION]
        subscriber = AlertSubscriber(event_types=custom_types)

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert event_types == [EventType.TRADING_DECISION]

    @pytest.mark.asyncio
    async def test_decision_only_subscriber_ignores_order_filled(self) -> None:
        """Subscriber with only TRADING_DECISION doesn't receive ORDER_FILLED."""
        bus = _FakeBus()
        subscriber = AlertSubscriber(event_types=[EventType.TRADING_DECISION])

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert EventType.ORDER_FILLED not in event_types
        assert EventType.ERROR not in event_types

    @pytest.mark.asyncio
    async def test_multiple_custom_event_types(self) -> None:
        """Can specify multiple custom event types."""
        bus = _FakeBus()
        custom_types = [EventType.TRADING_DECISION, EventType.ERROR]
        subscriber = AlertSubscriber(event_types=custom_types)

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert len(event_types) == 2
        assert EventType.TRADING_DECISION in event_types
        assert EventType.ERROR in event_types
        assert EventType.ORDER_FILLED not in event_types
