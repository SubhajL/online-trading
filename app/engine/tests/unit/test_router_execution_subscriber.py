"""Unit tests for RouterExecutionSubscriber."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    RouterExecutionSubscriber,
    _sanitize_value_for_json,
)
from app.engine.models import EventType, TimeFrame, TradingDecision, TradingDecisionEvent

# =============================================================================
# Tests for _sanitize_value_for_json (P0 #2)
# =============================================================================


class TestSanitizeValueForJson:
    """Tests for JSON serialization sanitization."""

    def test_converts_decimal_to_string(self) -> None:
        """Decimal values are converted to string representation."""
        result = _sanitize_value_for_json(Decimal("123.456"))
        assert result == "123.456"
        assert isinstance(result, str)

    def test_converts_datetime_to_iso_string(self) -> None:
        """Datetime values are converted to ISO 8601 strings."""
        dt = datetime(2025, 1, 6, 12, 30, 45, tzinfo=UTC)
        result = _sanitize_value_for_json(dt)
        assert result == "2025-01-06T12:30:45+00:00"
        assert isinstance(result, str)

    def test_converts_naive_datetime_to_utc_iso(self) -> None:
        """Naive datetime is assumed UTC and converted."""
        dt = datetime(2025, 1, 6, 12, 30, 45)  # noqa: DTZ001 - testing naive datetime handling
        result = _sanitize_value_for_json(dt)
        assert "+00:00" in result or "Z" in result

    def test_preserves_none_values(self) -> None:
        """None values remain None."""
        assert _sanitize_value_for_json(None) is None

    def test_preserves_string_values(self) -> None:
        """String values pass through unchanged."""
        assert _sanitize_value_for_json("hello") == "hello"

    def test_preserves_int_values(self) -> None:
        """Integer values pass through unchanged."""
        assert _sanitize_value_for_json(42) == 42

    def test_preserves_bool_values(self) -> None:
        """Boolean values pass through unchanged."""
        true_val = True
        false_val = False
        assert _sanitize_value_for_json(true_val) is True
        assert _sanitize_value_for_json(false_val) is False

    def test_handles_nested_dict_with_decimals(self) -> None:
        """Nested dicts with Decimal values are sanitized recursively."""
        input_data = {
            "zone_id": "zone_1",
            "top_price": Decimal("3190.50"),
            "bottom_price": Decimal("3180.25"),
            "nested": {"inner_decimal": Decimal("100.00")},
        }
        result = _sanitize_value_for_json(input_data)
        assert result["top_price"] == "3190.50"
        assert result["bottom_price"] == "3180.25"
        assert result["nested"]["inner_decimal"] == "100.00"
        assert result["zone_id"] == "zone_1"

    def test_handles_list_of_decimals(self) -> None:
        """Lists containing Decimals are sanitized."""
        input_data = [Decimal("1.1"), Decimal("2.2"), Decimal("3.3")]
        result = _sanitize_value_for_json(input_data)
        assert result == ["1.1", "2.2", "3.3"]

    def test_handles_mixed_list(self) -> None:
        """Lists with mixed types are sanitized correctly."""
        input_data = [Decimal("1.5"), "text", 42, None]
        result = _sanitize_value_for_json(input_data)
        assert result == ["1.5", "text", 42, None]


# =============================================================================
# Test Fixtures
# =============================================================================


class _FakeBus:
    def __init__(self) -> None:
        self.handler: object | None = None
        self.event_types: list[EventType] | None = None
        self.unsubscribed: list[str] = []
        self.published_events: list[object] = []

    async def subscribe(
        self,
        subscriber_id: str,
        handler: object,
        event_types: list[EventType] | None = None,
        priority: int = 0,
    ) -> str:
        _ = subscriber_id
        _ = priority
        self.handler = handler
        self.event_types = event_types
        return "sub-1"

    async def unsubscribe(self, subscription_id: str) -> bool:
        self.unsubscribed.append(subscription_id)
        return True

    async def publish(self, event: object, priority: int = 0) -> bool:
        _ = priority
        self.published_events.append(event)
        return True


def _make_valid_decision_event() -> TradingDecisionEvent:
    """Create a valid trading decision event for testing."""
    now = datetime.now(UTC)
    decision = TradingDecision(
        symbol="BTCUSDT",
        timestamp=now,
        action="BUY",
        entry_price=Decimal("50000.00"),
        stop_loss=Decimal("49500.00"),
        take_profit=Decimal("51000.00"),
        quantity=Decimal("0.001"),
        confidence=Decimal("0.75"),
        reasoning="Test decision",
    )
    return TradingDecisionEvent(
        symbol="BTCUSDT",
        timestamp=now,
        timeframe=TimeFrame.M15,
        decision=decision,
        metadata={"signal_id": "sig_test123"},
    )


# =============================================================================
# Tests for Error Handling (P0 #1)
# =============================================================================


class TestExecutionSubscriberErrorHandling:
    """Tests for error handling in RouterExecutionSubscriber."""

    @pytest.mark.asyncio
    async def test_emits_error_event_on_router_exception(self) -> None:
        """Router exceptions are caught and an ErrorEvent is emitted."""
        from app.engine.models import ErrorEvent

        bus = _FakeBus()
        router_client = AsyncMock()
        router_client.place_bracket_order.side_effect = Exception("Connection refused")

        subscriber = RouterExecutionSubscriber(
            bus=bus,
            router_client=router_client,
            execution_mode=ExecutionMode.FUTURES_TESTNET,
        )
        await subscriber.start()

        event = _make_valid_decision_event()
        assert callable(bus.handler)
        await bus.handler(event)

        # Verify error event was published
        assert len(bus.published_events) == 1
        error_event = bus.published_events[0]
        assert isinstance(error_event, ErrorEvent)
        assert error_event.error_type == "router_exception"
        assert "Connection refused" in error_event.error_message
        assert error_event.component == "router_execution_subscriber"
        assert error_event.symbol == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_emits_error_event_on_unsuccessful_response(self) -> None:
        """Router returns success=False triggers ErrorEvent."""
        from app.engine.models import ErrorEvent

        bus = _FakeBus()
        router_client = AsyncMock()
        router_client.place_bracket_order.return_value = {
            "success": False,
            "error": "Insufficient balance",
        }

        subscriber = RouterExecutionSubscriber(
            bus=bus,
            router_client=router_client,
            execution_mode=ExecutionMode.FUTURES_TESTNET,
        )
        await subscriber.start()

        event = _make_valid_decision_event()
        assert callable(bus.handler)
        await bus.handler(event)

        # Verify error event was published
        assert len(bus.published_events) == 1
        error_event = bus.published_events[0]
        assert isinstance(error_event, ErrorEvent)
        assert error_event.error_type == "router_error"
        assert "Insufficient balance" in error_event.error_message

    @pytest.mark.asyncio
    async def test_no_error_event_on_successful_response(self) -> None:
        """Successful router response does not emit error event."""
        bus = _FakeBus()
        router_client = AsyncMock()
        router_client.place_bracket_order.return_value = {
            "success": True,
            "order_id": "order_123",
        }

        subscriber = RouterExecutionSubscriber(
            bus=bus,
            router_client=router_client,
            execution_mode=ExecutionMode.FUTURES_TESTNET,
        )
        await subscriber.start()

        event = _make_valid_decision_event()
        assert callable(bus.handler)
        await bus.handler(event)

        # No error event should be published
        assert len(bus.published_events) == 0

    @pytest.mark.asyncio
    async def test_handler_completes_after_error(self) -> None:
        """Handler completes without raising even after router error."""
        bus = _FakeBus()
        router_client = AsyncMock()
        router_client.place_bracket_order.side_effect = Exception("Network error")

        subscriber = RouterExecutionSubscriber(
            bus=bus,
            router_client=router_client,
            execution_mode=ExecutionMode.FUTURES_TESTNET,
        )
        await subscriber.start()

        event = _make_valid_decision_event()
        assert callable(bus.handler)

        # Should not raise
        await bus.handler(event)

        # Subscriber should still be functional
        assert subscriber._subscription_id == "sub-1"


# =============================================================================
# Tests for RouterExecutionSubscriber Core Functionality
# =============================================================================


@pytest.mark.asyncio
async def test_execution_subscriber_calls_router_place_bracket_with_provenance() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = {"success": True}

    subscriber = RouterExecutionSubscriber(
        bus=bus,
        router_client=router_client,
        execution_mode=ExecutionMode.FUTURES_TESTNET,
    )

    await subscriber.start()
    assert bus.event_types == [EventType.TRADING_DECISION]

    now = datetime.now(UTC)
    decision = TradingDecision(
        symbol="ETHUSDT",
        timestamp=now,
        action="SELL",
        entry_price=Decimal("3184.36"),
        stop_loss=Decimal("3187.16"),
        take_profit=Decimal("3152.52"),
        quantity=Decimal("0.01"),
        confidence=Decimal("0.65"),
        reasoning="FVG fill with bearish bias",
    )
    event = TradingDecisionEvent(
        symbol="ETHUSDT",
        timestamp=now,
        timeframe=TimeFrame.M15,
        decision=decision,
        metadata={
            "signal_id": "sig_abc123",
            "timeframe": "15m",
            "zone": {
                "zone_id": "zone_1",
                "zone_type": "FAIR_VALUE_GAP",
                "top_price": Decimal(3190),
                "bottom_price": Decimal(3180),
            },
        },
    )

    assert callable(bus.handler)
    await bus.handler(event)  # type: ignore[misc]

    router_client.place_bracket_order.assert_awaited_once()
    payload = router_client.place_bracket_order.call_args.args[0]

    assert payload["symbol"] == "ETHUSDT"
    assert payload["side"] == "SELL"
    assert payload["is_futures"] is True
    assert payload["metadata"]["signal_id"] == "sig_abc123"
    assert payload["metadata"]["timeframe"] == "15m"
    assert payload["metadata"]["zone"]["zone_type"] == "FAIR_VALUE_GAP"


@pytest.mark.asyncio
async def test_execution_subscriber_ignores_decisions_missing_levels() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()

    subscriber = RouterExecutionSubscriber(
        bus=bus,
        router_client=router_client,
        execution_mode=ExecutionMode.FUTURES_TESTNET,
    )
    await subscriber.start()

    now = datetime.now(UTC)
    decision = TradingDecision(
        symbol="BTCUSDT",
        timestamp=now,
        action="BUY",
        entry_price=None,
        stop_loss=None,
        take_profit=None,
        quantity=Decimal("0.01"),
        confidence=Decimal("0.8"),
        reasoning="missing levels",
    )
    event = TradingDecisionEvent(
        symbol="BTCUSDT",
        timestamp=now,
        timeframe=TimeFrame.M5,
        decision=decision,
    )

    assert callable(bus.handler)
    await bus.handler(event)  # type: ignore[misc]

    router_client.place_bracket_order.assert_not_awaited()
