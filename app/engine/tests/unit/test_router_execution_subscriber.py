"""Unit tests for RouterExecutionSubscriber."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio

from app.engine.adapters.router_client.http_client import (
    BracketClientOrderIDs,
    BracketPlacementResult,
    RouterTransportError,
)
from app.engine.execution.order_update_correlation import OrderUpdateCorrelationStore
import app.engine.execution.router_execution_subscriber as router_module
from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    RouterExecutionSubscriber,
    _sanitize_value_for_json,
)
from app.engine.models import (
    ErrorEvent,
    EventType,
    Order,
    OrderPlacedEvent,
    OrderSide,
    OrderStatus,
    OrderType,
    RiskParameters,
    TimeFrame,
    TradingDecision,
    TradingDecisionEvent,
)

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


_created_subscribers: list[RouterExecutionSubscriber] = []


@pytest_asyncio.fixture(autouse=True)
async def _stop_created_subscribers() -> AsyncIterator[None]:
    first = len(_created_subscribers)
    yield
    for subscriber in reversed(_created_subscribers[first:]):
        await subscriber.stop()
    del _created_subscribers[first:]


def _track_subscriber(subscriber: RouterExecutionSubscriber) -> RouterExecutionSubscriber:
    _created_subscribers.append(subscriber)
    return subscriber


class _FakeBus:
    def __init__(self) -> None:
        self.handler: object | None = None
        self.event_types: list[EventType] | None = None
        self.subscribe_calls: list[str] = []
        self.unsubscribed: list[str] = []
        self.published_events: list[object] = []
        self.publish_and_wait_result = True

    async def subscribe(
        self,
        subscriber_id: str,
        handler: object,
        event_types: list[EventType] | None = None,
        priority: int = 0,
    ) -> str:
        _ = priority
        self.subscribe_calls.append(subscriber_id)
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

    async def publish_and_wait(self, event: object, priority: int = 0) -> bool:
        _ = priority
        self.published_events.append(event)
        return self.publish_and_wait_result


class _FakeDBAdapter:
    def __init__(self) -> None:
        self.upserted_orders: list[dict[str, object]] = []
        self.active_positions: list[dict[str, object]] = []
        self.active_setup_order: dict[str, object] | None = None
        self.active_setup_position: dict[str, object] | None = None
        self.active_positions_error: Exception | None = None
        self.active_positions_errors: list[Exception | None] = []
        self.active_setup_order_error: Exception | None = None
        self.active_setup_position_error: Exception | None = None
        self.execution_intents: list[dict[str, object]] = []
        self.execution_intent_transitions: list[tuple[str, str]] = []
        self.prepare_execution_intent_result = True
        self.transition_execution_intent_result = True
        self.transition_failure_state: str | None = None
        self.commit_execution_ack_result = True
        self.commit_execution_ack_results: list[bool] = []
        self.commit_execution_ack_calls: list[dict[str, object]] = []
        self.execution_intent_lookup_result: dict[str, object] | None = None
        self.execution_intent_lookup_calls: list[dict[str, object]] = []
        self.execution_success_delivery_states: dict[str, str] = {}
        self.execution_success_delivery_payloads: dict[str, dict[str, object]] = {}
        self.execution_success_delivery_claims: list[dict[str, object]] = []
        self.execution_success_delivery_completions: list[dict[str, object]] = []
        self.execution_success_delivery_failures: list[dict[str, object]] = []
        self.execution_intent_recovery_claims: list[dict[str, object]] = []
        self.execution_intent_recovery_claim_calls = 0
        self.has_foreign_incomplete_execution_intent = False
        self.incomplete_execution_intent_venue_checks: list[str] = []

    async def upsert_order(self, _order: dict[str, object]) -> bool:
        self.upserted_orders.append(_order)
        return True

    async def prepare_execution_intent(self, intent: dict[str, object]) -> bool:
        self.execution_intents.append(intent)
        return self.prepare_execution_intent_result

    async def get_execution_intent_for_request(
        self,
        idempotency_key: str,
        *,
        venue: str,
        request_payload: dict[str, object],
    ) -> dict[str, object] | None:
        self.execution_intent_lookup_calls.append(
            {
                "idempotency_key": idempotency_key,
                "venue": venue,
                "request_payload": request_payload,
            }
        )
        return self.execution_intent_lookup_result

    async def commit_execution_ack(
        self,
        idempotency_key: str,
        *,
        venue: str,
        response_payload: dict[str, object],
        order_rows: list[dict[str, object]],
        deliveries: list[dict[str, object]],
    ) -> bool:
        self.commit_execution_ack_calls.append(
            {
                "idempotency_key": idempotency_key,
                "venue": venue,
                "response_payload": response_payload,
                "order_rows": order_rows,
                "deliveries": deliveries,
            }
        )
        commit_result = (
            self.commit_execution_ack_results.pop(0)
            if self.commit_execution_ack_results
            else self.commit_execution_ack_result
        )
        if not commit_result:
            return False
        self.upserted_orders.extend(order_rows)
        self.execution_intent_transitions.append((idempotency_key, "ACKNOWLEDGED"))
        for delivery in deliveries:
            delivery_kind = str(delivery["delivery_kind"])
            delivery_payload = delivery["delivery_payload"]
            assert isinstance(delivery_payload, dict)
            self.execution_success_delivery_states[delivery_kind] = "PENDING"
            self.execution_success_delivery_payloads[delivery_kind] = delivery_payload
        return True

    async def claim_execution_success_delivery(
        self,
        idempotency_key: str,
        *,
        venue: str,
    ) -> dict[str, object] | None:
        for delivery_kind in ("SNAPSHOT", "ORDER_PLACED"):
            if self.execution_success_delivery_states.get(delivery_kind) != "PENDING":
                continue
            if (
                delivery_kind == "ORDER_PLACED"
                and self.execution_success_delivery_states.get("SNAPSHOT") != "DELIVERED"
                and "SNAPSHOT" in self.execution_success_delivery_states
            ):
                return None
            lease_token = f"lease-{len(self.execution_success_delivery_claims) + 1}"
            self.execution_success_delivery_states[delivery_kind] = "DELIVERING"
            claim = {
                "idempotency_key": idempotency_key,
                "venue": venue,
                "delivery_kind": delivery_kind,
                "lease_token": lease_token,
                "delivery_payload": self.execution_success_delivery_payloads[delivery_kind],
            }
            self.execution_success_delivery_claims.append(claim)
            return claim
        return None

    async def complete_execution_success_delivery(
        self,
        idempotency_key: str,
        *,
        venue: str,
        delivery_kind: str,
        lease_token: str,
    ) -> None:
        self.execution_success_delivery_completions.append(
            {
                "idempotency_key": idempotency_key,
                "venue": venue,
                "delivery_kind": delivery_kind,
                "lease_token": lease_token,
            }
        )
        self.execution_success_delivery_states[delivery_kind] = "DELIVERED"

    async def fail_execution_success_delivery(
        self,
        idempotency_key: str,
        *,
        venue: str,
        delivery_kind: str,
        lease_token: str,
        error_message: str,
    ) -> None:
        self.execution_success_delivery_failures.append(
            {
                "idempotency_key": idempotency_key,
                "venue": venue,
                "delivery_kind": delivery_kind,
                "lease_token": lease_token,
                "error_message": error_message,
            }
        )
        self.execution_success_delivery_states[delivery_kind] = "PENDING"

    async def has_pending_execution_success_delivery(
        self,
        idempotency_key: str,
        *,
        venue: str,
    ) -> bool:
        _ = idempotency_key, venue
        return any(
            state != "DELIVERED" for state in self.execution_success_delivery_states.values()
        )

    async def claim_next_execution_intent_recovery(
        self,
        *,
        venue: str,
    ) -> dict[str, object] | None:
        self.execution_intent_recovery_claim_calls += 1
        for index, claim in enumerate(self.execution_intent_recovery_claims):
            if claim["venue"] == venue:
                return self.execution_intent_recovery_claims.pop(index)
        return None

    async def has_incomplete_execution_intent_outside_venue(
        self,
        active_venue: str,
    ) -> bool:
        self.incomplete_execution_intent_venue_checks.append(active_venue)
        return self.has_foreign_incomplete_execution_intent

    async def transition_execution_intent(
        self,
        idempotency_key: str,
        state: str,
        **_kwargs: object,
    ) -> bool:
        self.execution_intent_transitions.append((idempotency_key, state))
        if state == self.transition_failure_state:
            return False
        return self.transition_execution_intent_result

    async def get_latest_equity_sample(self):
        return Decimal(10_000), datetime.now(UTC)

    async def get_equity_sample_at_or_after(self, _ts: datetime):
        return Decimal(10_000)

    async def get_peak_equity_since(self, _ts: datetime):
        return Decimal(10_000)

    async def get_active_positions(self, _venue: str):
        if self.active_positions_errors:
            next_error = self.active_positions_errors.pop(0)
            if next_error is not None:
                raise next_error
        if self.active_positions_error is not None:
            raise self.active_positions_error
        return list(self.active_positions)

    async def get_active_order_for_setup(
        self,
        *,
        venue: str,
        symbol: str,
        side: str,
        timeframe: str,
        zone_id: str,
    ) -> dict[str, object] | None:
        _ = venue, symbol, side, timeframe, zone_id
        if self.active_setup_order_error is not None:
            raise self.active_setup_order_error
        return self.active_setup_order

    async def get_active_position_for_setup(
        self,
        *,
        venue: str,
        symbol: str,
        side: str,
        timeframe: str,
        zone_id: str,
    ) -> dict[str, object] | None:
        _ = venue, symbol, side, timeframe, zone_id
        if self.active_setup_position_error is not None:
            raise self.active_setup_position_error
        return self.active_setup_position


class _BlockingDuplicateGuardDBAdapter(_FakeDBAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()
        self.setup_position_started = asyncio.Event()
        self.active_positions_started = asyncio.Event()
        self.setup_order_started = asyncio.Event()

    async def get_active_positions(self, _venue: str):
        self.active_positions_started.set()
        await self.release.wait()
        return await super().get_active_positions(_venue)

    async def get_active_order_for_setup(
        self,
        *,
        venue: str,
        symbol: str,
        side: str,
        timeframe: str,
        zone_id: str,
    ) -> dict[str, object] | None:
        self.setup_order_started.set()
        await self.release.wait()
        return await super().get_active_order_for_setup(
            venue=venue,
            symbol=symbol,
            side=side,
            timeframe=timeframe,
            zone_id=zone_id,
        )

    async def get_active_position_for_setup(
        self,
        *,
        venue: str,
        symbol: str,
        side: str,
        timeframe: str,
        zone_id: str,
    ) -> dict[str, object] | None:
        self.setup_position_started.set()
        await self.release.wait()
        return await super().get_active_position_for_setup(
            venue=venue,
            symbol=symbol,
            side=side,
            timeframe=timeframe,
            zone_id=zone_id,
        )


class _RestartDeliveryDBAdapter(_FakeDBAdapter):
    def __init__(self, pending: dict[str, object]) -> None:
        super().__init__()
        self.pending = pending
        self.list_pending_calls = 0

    async def claim_next_execution_success_delivery(
        self,
        *,
        venue: str,
    ) -> dict[str, object] | None:
        self.list_pending_calls += 1
        if venue != self.pending["venue"]:
            return None
        if not await self.has_pending_execution_success_delivery(
            str(self.pending["idempotency_key"]),
            venue=venue,
        ):
            return None
        claim = await self.claim_execution_success_delivery(
            str(self.pending["idempotency_key"]),
            venue=venue,
        )
        if claim is None:
            return None
        return {**claim, "idempotency_key": self.pending["idempotency_key"]}


class _MultiVenueRestartDBAdapter(_FakeDBAdapter):
    def __init__(self, claims: list[dict[str, object]]) -> None:
        super().__init__()
        self.claims = list(claims)
        self.completed_venues: list[str] = []

    async def claim_next_execution_success_delivery(
        self,
        *,
        venue: str,
    ) -> dict[str, object] | None:
        for index, claim in enumerate(self.claims):
            if claim["venue"] == venue:
                return self.claims.pop(index)
        return None

    async def complete_execution_success_delivery(
        self,
        idempotency_key: str,
        *,
        venue: str,
        delivery_kind: str,
        lease_token: str,
    ) -> None:
        _ = idempotency_key, delivery_kind, lease_token
        self.completed_venues.append(venue)


class _BlockingUpsertDBAdapter(_FakeDBAdapter):
    def __init__(self, expected_calls: int) -> None:
        super().__init__()
        self.expected_calls = expected_calls
        self.release = asyncio.Event()
        self.all_started = asyncio.Event()
        self.in_flight = 0
        self.max_in_flight = 0

    async def upsert_order(self, order: dict[str, object]) -> bool:
        self.upserted_orders.append(order)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        if len(self.upserted_orders) == self.expected_calls:
            self.all_started.set()
        await self.release.wait()
        self.in_flight -= 1
        return True


def _default_risk() -> RiskParameters:
    return RiskParameters(
        max_position_size=Decimal("999999"),
        max_daily_loss=Decimal("1"),
        max_drawdown=Decimal("1"),
        risk_per_trade=Decimal("0.01"),
        max_correlation=Decimal("1"),
        max_open_positions=100,
        max_total_exposure_leverage=Decimal("100"),
        max_symbol_exposure_pct=Decimal("1"),
        max_position_notional_pct=Decimal("1"),
        risk_data_max_age_seconds=86400,
        drawdown_lookback_days=30,
    )


def _venue_for_mode(mode: ExecutionMode) -> str:
    if mode in {ExecutionMode.FUTURES_MAINNET, ExecutionMode.FUTURES_TESTNET}:
        return "USD_M"
    return "SPOT"


def _make_subscriber(
    *,
    bus: _FakeBus,
    router_client: AsyncMock,
    execution_mode: ExecutionMode = ExecutionMode.FUTURES_TESTNET,
    **kwargs: Any,
) -> RouterExecutionSubscriber:
    correlation_store = kwargs.pop(
        "order_update_correlation_store",
        OrderUpdateCorrelationStore(ttl_seconds=3600),
    )
    db_adapter = kwargs.pop("db_adapter", _FakeDBAdapter())
    return _track_subscriber(
        RouterExecutionSubscriber(
            bus=bus,
            router_client=router_client,
            db_adapter=db_adapter,  # type: ignore[arg-type]
            risk=_default_risk(),
            venue=_venue_for_mode(execution_mode),
            execution_mode=execution_mode,
            order_update_correlation_store=correlation_store,
            **kwargs,
        )
    )


def _make_valid_decision_event() -> TradingDecisionEvent:
    """Create a valid trading decision event for testing."""
    now = datetime.now(UTC)
    decision = TradingDecision(
        venue="SPOT",
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
        metadata={
            "signal_id": "sig_test123",
            "decision_source": "retest_decision_publisher",
        },
    )


def _bff_post_paths(client: AsyncMock) -> list[str]:
    return [call.args[0] for call in client.post.await_args_list]


def _placement_result(
    *,
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    quantity: Decimal = Decimal("0.001"),
    id_token: str = "adeb4758accdcc17",
    bracket_order_id: str = "bracket-1",
) -> BracketPlacementResult:
    return BracketPlacementResult(
        bracket_order_id=bracket_order_id,
        client_order_ids=BracketClientOrderIDs(
            main=f"{id_token}_entry",
            take_profits=(f"{id_token}_tp1",),
            stop_loss=f"{id_token}_sl",
        ),
        symbol=symbol,
        side=side,
        quantity=quantity,
        created_at=datetime(2026, 8, 13, tzinfo=UTC),
        partial_failure=False,
        errors=(),
        legs_pending_trigger=True,
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

        subscriber = _make_subscriber(bus=bus, router_client=router_client, router_max_attempts=1)
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
    async def test_emits_protocol_error_on_untyped_response(self) -> None:
        """Legacy response dictionaries cannot advance placement success."""
        from app.engine.models import ErrorEvent

        bus = _FakeBus()
        router_client = AsyncMock()
        router_client.place_bracket_order.return_value = {
            "success": False,
            "error": "Insufficient balance",
        }

        subscriber = _make_subscriber(bus=bus, router_client=router_client, router_max_attempts=1)
        await subscriber.start()

        event = _make_valid_decision_event()
        assert callable(bus.handler)
        await bus.handler(event)

        # Verify error event was published
        assert len(bus.published_events) == 1
        error_event = bus.published_events[0]
        assert isinstance(error_event, ErrorEvent)
        assert error_event.error_type == "router_protocol_error"
        assert error_event.error_message == "Router client returned an untyped placement response"

    @pytest.mark.asyncio
    async def test_no_error_event_on_successful_response(self) -> None:
        """Successful router response does not emit error event."""
        bus = _FakeBus()
        router_client = AsyncMock()
        router_client.place_bracket_order.return_value = _placement_result()
        bff_client = AsyncMock()
        bff_client.post.return_value = {"ok": True}

        subscriber = _make_subscriber(
            bus=bus,
            router_client=router_client,
            bff_client=bff_client,
        )
        await subscriber.start()

        event = _make_valid_decision_event()
        assert callable(bus.handler)
        await bus.handler(event)

        # Only OrderPlacedEvent should be published (no ErrorEvent)
        assert len(bus.published_events) == 1
        from app.engine.models import OrderPlacedEvent

        assert isinstance(bus.published_events[0], OrderPlacedEvent)

    @pytest.mark.asyncio
    async def test_blocks_execution_when_ingest_health_is_unhealthy(self) -> None:
        from app.engine.models import ErrorEvent

        bus = _FakeBus()
        router_client = AsyncMock()
        router_client.place_bracket_order.return_value = {"success": True}
        execution_readiness_check = AsyncMock(
            return_value=(
                False,
                "Execution blocked: websocket_disconnected",
                {"blocking_issue_types": ["websocket_disconnected"]},
            ),
        )

        subscriber = _make_subscriber(
            bus=bus,
            router_client=router_client,
            execution_readiness_check=execution_readiness_check,
        )
        await subscriber.start()

        event = _make_valid_decision_event()
        assert callable(bus.handler)
        await bus.handler(event)

        router_client.place_bracket_order.assert_not_awaited()
        assert len(bus.published_events) == 1
        error_event = bus.published_events[0]
        assert isinstance(error_event, ErrorEvent)
        assert error_event.error_type == "execution_blocked_unhealthy_ingest"

    @pytest.mark.asyncio
    async def test_handler_completes_after_error(self) -> None:
        """Handler completes without raising even after router error."""
        bus = _FakeBus()
        router_client = AsyncMock()
        router_client.place_bracket_order.side_effect = Exception("Network error")

        subscriber = _make_subscriber(bus=bus, router_client=router_client, router_max_attempts=1)
        await subscriber.start()

        event = _make_valid_decision_event()
        assert callable(bus.handler)

        # Should not raise
        await bus.handler(event)

        # Subscriber should still be functional
        assert subscriber._subscription_id == "sub-1"


@pytest.mark.asyncio
async def test_execution_retries_on_transient_exception_then_succeeds(monkeypatch: Any) -> None:
    from app.engine.models import OrderPlacedEvent
    from app.engine.resilience.backoff import BackoffConfig

    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.side_effect = [
        RouterTransportError("timeout"),
        RouterTransportError("connection reset"),
        _placement_result(),
    ]
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}

    sleep = AsyncMock()
    monkeypatch.setattr(router_module.asyncio, "sleep", sleep)

    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        bff_client=bff_client,
        router_max_attempts=3,
        router_backoff_config=BackoffConfig(
            base_delay_s=0.001,
            max_delay_s=0.001,
            multiplier=2.0,
            jitter_pct=0.0,
        ),
    )
    await subscriber.start()

    event = _make_valid_decision_event()
    assert callable(bus.handler)
    await bus.handler(event)

    assert router_client.place_bracket_order.call_count == 3
    assert sleep.call_count == 2
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], OrderPlacedEvent)


@pytest.mark.asyncio
async def test_router_failure_has_no_success_side_effects() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = {
        "error": "invalid bracket request",
        "status": 400,
    }
    db_adapter = _FakeDBAdapter()
    cooldown = AsyncMock()
    cooldown.try_acquire_async.return_value = True
    bff_client = AsyncMock()
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        cooldown=cooldown,
        bff_client=bff_client,
        router_max_attempts=1,
    )
    await subscriber.start()
    event = _make_valid_decision_event()
    event.metadata["zone"] = {
        "zone_id": "zone_1",
        "zone_type": "FAIR_VALUE_GAP",
    }

    assert callable(bus.handler)
    await bus.handler(event)

    assert db_adapter.upserted_orders == []
    bff_client.post.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "router_protocol_error"
    cooldown.release_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_execution_intent_failure_never_calls_router() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    db_adapter = _FakeDBAdapter()
    db_adapter.prepare_execution_intent_result = False
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        router_max_attempts=1,
    )
    await subscriber.start()

    assert callable(bus.handler)
    await bus.handler(_make_valid_decision_event())

    router_client.place_bracket_order.assert_not_awaited()
    assert db_adapter.execution_intents[0]["state"] == "PREPARED"
    assert any(
        isinstance(event, ErrorEvent) and event.error_type == "execution_intent_unavailable"
        for event in bus.published_events
    )


@pytest.mark.asyncio
async def test_ack_commit_failure_has_no_success_effects_and_retains_ambiguous_replay(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = _placement_result()
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}
    db_adapter = _FakeDBAdapter()
    db_adapter.commit_execution_ack_result = False
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}
    cooldown = AsyncMock()
    cooldown.try_acquire_async.return_value = True
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        bff_client=bff_client,
        cooldown=cooldown,
        router_max_attempts=1,
    )
    await subscriber.start()
    caplog.set_level("INFO", logger=router_module.__name__)

    assert callable(bus.handler)
    await bus.handler(_make_valid_decision_event())

    router_client.place_bracket_order.assert_awaited_once()
    assert len(db_adapter.commit_execution_ack_calls) == 1
    assert db_adapter.upserted_orders == []
    bff_client.post.assert_not_awaited()
    assert not any(isinstance(event, OrderPlacedEvent) for event in bus.published_events)
    assert ("sig_test123", "AMBIGUOUS") in db_adapter.execution_intent_transitions
    assert any(
        isinstance(event, ErrorEvent) and event.error_type == "execution_intent_unavailable"
        for event in bus.published_events
    )
    assert not any("Order placed successfully" in record.getMessage() for record in caplog.records)
    cooldown.release_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_key_replay_after_ack_commit_failure_recovers_success_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = _placement_result()
    db_adapter = _FakeDBAdapter()
    db_adapter.commit_execution_ack_results = [False, True]
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        bff_client=bff_client,
        router_max_attempts=1,
    )
    await subscriber.start()
    caplog.set_level("INFO", logger=router_module.__name__)
    event = _make_valid_decision_event()

    assert callable(bus.handler)
    await bus.handler(event)

    stored_payload = db_adapter.execution_intents[0]["request_payload"]
    assert isinstance(stored_payload, dict)
    db_adapter.execution_intent_lookup_result = {
        "state": "AMBIGUOUS",
        "request_payload": stored_payload,
        "response_payload": None,
    }
    db_adapter.active_setup_order = {"client_order_id": "existing-projection"}

    await bus.handler(event)

    assert len(db_adapter.execution_intent_lookup_calls) == 2
    assert router_client.place_bracket_order.await_count == 2
    assert (
        router_client.place_bracket_order.await_args_list[0]
        == (router_client.place_bracket_order.await_args_list[1])
    )
    assert len(db_adapter.commit_execution_ack_calls) == 2
    assert _bff_post_paths(bff_client) == [
        "/api/signals/alert",
        "/api/internal/trading/order-update",
    ]
    assert sum(isinstance(published, OrderPlacedEvent) for published in bus.published_events) == 1
    assert sum("Order placed successfully" in record.getMessage() for record in caplog.records) == 1
    assert ("sig_test123", "AMBIGUOUS") in db_adapter.execution_intent_transitions
    assert ("sig_test123", "ACKNOWLEDGED") in db_adapter.execution_intent_transitions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blocking_gate",
    ["max_position", "risk_unavailable", "readiness_unavailable"],
)
async def test_restart_worker_recovers_submitting_intent_without_decision_republish(
    blocking_gate: str,
) -> None:
    first_bus = _FakeBus()
    first_router = AsyncMock()
    first_router.place_bracket_order.side_effect = RouterTransportError("connection reset")
    first_db = _FakeDBAdapter()
    first_subscriber = _make_subscriber(
        bus=first_bus,
        router_client=first_router,
        db_adapter=first_db,
        router_max_attempts=1,
        execution_intent_recovery_poll_interval_seconds=0.01,
    )
    await first_subscriber.start()
    assert callable(first_bus.handler)
    await first_bus.handler(_make_valid_decision_event())
    await first_subscriber.stop()

    stored_payload = first_db.execution_intents[0]["request_payload"]
    assert isinstance(stored_payload, dict)
    recovery_db = _FakeDBAdapter()
    recovery_db.execution_intent_lookup_result = {
        "state": "SUBMITTING",
        "request_payload": stored_payload,
        "response_payload": None,
    }
    recovery_db.execution_intent_recovery_claims = [
        {
            "venue": "USD_M",
            "idempotency_key": "sig_test123",
            "state": "SUBMITTING",
            "request_payload": stored_payload,
        }
    ]
    recovery_bus = _FakeBus()
    recovery_router = AsyncMock()
    recovery_router.place_bracket_order.return_value = _placement_result()
    recovery_kwargs: dict[str, object] = {}
    if blocking_gate == "max_position":
        recovery_kwargs["max_position_size"] = Decimal("0.0001")
    elif blocking_gate == "risk_unavailable":
        recovery_db.active_positions_error = RuntimeError("risk database unavailable")
    else:
        recovery_kwargs["execution_readiness_check"] = AsyncMock(
            return_value=(False, "ingest unavailable", {})
        )
    recovery_subscriber = _make_subscriber(
        bus=recovery_bus,
        router_client=recovery_router,
        db_adapter=recovery_db,
        router_max_attempts=1,
        execution_intent_recovery_poll_interval_seconds=0.01,
        **recovery_kwargs,
    )

    await recovery_subscriber.start()
    try:
        for _ in range(100):
            if recovery_router.place_bracket_order.await_count:
                break
            await asyncio.sleep(0.01)
        assert recovery_router.place_bracket_order.await_count == 1
        assert len(recovery_db.commit_execution_ack_calls) == 1
        assert recovery_db.commit_execution_ack_calls[0]["idempotency_key"] == "sig_test123"
        assert ("sig_test123", "ACKNOWLEDGED") in recovery_db.execution_intent_transitions
        assert recovery_db.execution_intent_recovery_claim_calls > 0
    finally:
        await recovery_subscriber.stop()


@pytest.mark.asyncio
async def test_transport_exhaustion_marks_execution_intent_ambiguous() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.side_effect = RouterTransportError("connection reset")
    db_adapter = _FakeDBAdapter()
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        router_max_attempts=1,
    )
    await subscriber.start()

    assert callable(bus.handler)
    await bus.handler(_make_valid_decision_event())

    assert ("sig_test123", "AMBIGUOUS") in db_adapter.execution_intent_transitions
    assert not any(isinstance(event, OrderPlacedEvent) for event in bus.published_events)


@pytest.mark.asyncio
async def test_order_event_failure_leaves_acknowledged_delivery_pending(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = _FakeBus()
    bus.publish_and_wait_result = False
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = _placement_result()
    db_adapter = _FakeDBAdapter()
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        router_max_attempts=1,
    )
    await subscriber.start()
    caplog.set_level("INFO", logger=router_module.__name__)

    assert callable(bus.handler)
    await bus.handler(_make_valid_decision_event())

    assert ("sig_test123", "ACKNOWLEDGED") in db_adapter.execution_intent_transitions
    assert ("sig_test123", "AMBIGUOUS") not in db_adapter.execution_intent_transitions
    assert db_adapter.execution_success_delivery_states == {"ORDER_PLACED": "PENDING"}
    assert len(db_adapter.execution_success_delivery_failures) == 1
    assert any(
        isinstance(event, ErrorEvent) and event.error_type == "success_delivery_pending"
        for event in bus.published_events
    )
    assert not any("Order placed successfully" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_snapshot_failure_leaves_acknowledged_delivery_pending(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = _placement_result()
    db_adapter = _FakeDBAdapter()
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": False}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        bff_client=bff_client,
        router_max_attempts=1,
    )
    await subscriber.start()
    caplog.set_level("INFO", logger=router_module.__name__)

    assert callable(bus.handler)
    await bus.handler(_make_valid_decision_event())

    assert ("sig_test123", "ACKNOWLEDGED") in db_adapter.execution_intent_transitions
    assert ("sig_test123", "AMBIGUOUS") not in db_adapter.execution_intent_transitions
    assert db_adapter.execution_success_delivery_states == {
        "ORDER_PLACED": "PENDING",
        "SNAPSHOT": "PENDING",
    }
    assert len(db_adapter.execution_success_delivery_failures) == 1
    assert not any(isinstance(event, OrderPlacedEvent) for event in bus.published_events)
    assert any(
        isinstance(event, ErrorEvent) and event.error_type == "success_delivery_pending"
        for event in bus.published_events
    )
    assert not any("Order placed successfully" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_snapshot_delivery_payload_matches_bff_contract_and_scopes_identity() -> None:
    bus = _FakeBus()
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=AsyncMock(),
        bff_client=bff_client,
    )
    event = _make_valid_decision_event()

    assert await subscriber._notify_snapshot(event, "sig_test123")

    bff_client.post.assert_awaited_once()
    endpoint, payload = bff_client.post.await_args.args
    assert endpoint == "/api/signals/alert"
    assert payload == {
        "signalId": payload["signalId"],
        "symbol": "BTCUSDT",
        "venue": "USD_M",
        "side": "BUY",
        "entry": 50000.0,
        "stopLoss": 49500.0,
        "takeProfit": 51000.0,
        "confidence": 0.75,
        "reasons": ["Test decision"],
        "timeframe": "15m",
        "signalTime": event.decision.timestamp.isoformat(),
    }
    assert isinstance(payload["signalId"], str) and payload["signalId"]
    assert payload["signalId"] != "sig_test123"
    assert "idempotencyKey" not in payload


@pytest.mark.asyncio
async def test_snapshot_delivery_has_canonical_fallbacks_without_signal_or_timeframe() -> None:
    bus = _FakeBus()
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=AsyncMock(),
        bff_client=bff_client,
    )
    event = _make_valid_decision_event()
    event.metadata.pop("signal_id")
    event.timeframe = None
    idempotency_key = str(event.decision.decision_id)

    assert await subscriber._notify_snapshot(event, idempotency_key)

    payload = bff_client.post.await_args.args[1]
    assert payload["signalId"]
    assert payload["timeframe"] == "unknown"
    assert payload["confidence"] == 0.75


@pytest.mark.asyncio
async def test_order_placed_and_snapshot_identities_are_distinct_across_venues() -> None:
    event = _make_valid_decision_event()
    response = _placement_result().to_dict()
    buses = [_FakeBus(), _FakeBus()]
    bff_clients = [AsyncMock(), AsyncMock()]
    for client in bff_clients:
        client.post.return_value = {"ok": True}
    subscribers = [
        _make_subscriber(
            bus=buses[0],
            router_client=AsyncMock(),
            execution_mode=ExecutionMode.SPOT_TESTNET,
            bff_client=bff_clients[0],
        ),
        _make_subscriber(
            bus=buses[1],
            router_client=AsyncMock(),
            execution_mode=ExecutionMode.FUTURES_TESTNET,
            bff_client=bff_clients[1],
        ),
    ]

    for subscriber in subscribers:
        await subscriber._notify_snapshot(event, "sig_test123")
        await subscriber._emit_order_placed(
            event,
            response,
            "client-entry",
            "sig_test123",
        )

    spot_event = buses[0].published_events[0]
    futures_event = buses[1].published_events[0]
    assert isinstance(spot_event, OrderPlacedEvent)
    assert isinstance(futures_event, OrderPlacedEvent)
    assert spot_event.event_id != futures_event.event_id
    assert spot_event.metadata["signal_id"] != futures_event.metadata["signal_id"]
    assert (
        bff_clients[0].post.await_args.args[1]["signalId"]
        != bff_clients[1].post.await_args.args[1]["signalId"]
    )


@pytest.mark.asyncio
async def test_start_drains_persisted_success_deliveries_without_decision_replay() -> None:
    decision_event = _make_valid_decision_event()
    delivery_signal_id = "exec_restart_delivery"
    order_event = OrderPlacedEvent(
        event_id=uuid4(),
        timestamp=decision_event.timestamp,
        symbol=decision_event.symbol,
        timeframe=decision_event.timeframe,
        metadata={
            **decision_event.metadata,
            "source_signal_id": decision_event.metadata["signal_id"],
            "signal_id": delivery_signal_id,
        },
        order=Order(
            client_order_id="restart-entry",
            symbol=decision_event.symbol,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
            status=OrderStatus.NEW,
            created_at=decision_event.timestamp,
        ),
        decision=decision_event.decision,
        router_response=_placement_result().to_dict(),
    )
    pending = {
        "venue": "USD_M",
        "idempotency_key": "restart-key",
    }
    db_adapter = _RestartDeliveryDBAdapter(pending)
    db_adapter.execution_success_delivery_states = {
        "SNAPSHOT": "PENDING",
        "ORDER_PLACED": "PENDING",
    }
    db_adapter.execution_success_delivery_payloads = {
        "SNAPSHOT": {
            "signalId": delivery_signal_id,
            "symbol": "BTCUSDT",
            "venue": "USD_M",
            "side": "BUY",
            "entry": 50000.0,
            "stopLoss": 49500.0,
            "takeProfit": 51000.0,
            "confidence": 0.75,
            "reasons": ["Test decision"],
            "timeframe": "15m",
            "signalTime": decision_event.decision.timestamp.isoformat(),
        },
        "ORDER_PLACED": order_event.model_dump(mode="json"),
    }
    bus = _FakeBus()
    router_client = AsyncMock()
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        bff_client=bff_client,
        success_delivery_poll_interval_seconds=0.01,
    )

    await subscriber.start()
    try:
        async with asyncio.timeout(1):
            while db_adapter.execution_success_delivery_states != {
                "SNAPSHOT": "DELIVERED",
                "ORDER_PLACED": "DELIVERED",
            }:
                await asyncio.sleep(0.01)
    finally:
        await subscriber.stop()

    router_client.place_bracket_order.assert_not_awaited()
    assert _bff_post_paths(bff_client) == [
        "/api/signals/alert",
        "/api/internal/trading/order-update",
    ]
    assert bff_client.post.await_args_list[0].args == (
        "/api/signals/alert",
        db_adapter.execution_success_delivery_payloads["SNAPSHOT"],
    )
    assert sum(isinstance(item, OrderPlacedEvent) for item in bus.published_events) == 1
    assert db_adapter.list_pending_calls > 0


@pytest.mark.asyncio
async def test_start_fails_closed_for_incomplete_intent_on_inactive_venue() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.health_check.return_value = {"execution_env": "testnet"}
    db_adapter = _FakeDBAdapter()
    db_adapter.has_foreign_incomplete_execution_intent = True
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        execution_mode=ExecutionMode.FUTURES_TESTNET,
        db_adapter=db_adapter,
    )

    with pytest.raises(RuntimeError, match="inactive venue"):
        await subscriber.start()

    assert db_adapter.incomplete_execution_intent_venue_checks == ["USD_M"]
    assert bus.subscribe_calls == []
    assert subscriber._execution_intent_recovery_task is None
    assert subscriber._success_delivery_tasks == {}
    assert subscriber._started is False
    router_client.place_bracket_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_mode_drains_both_venues_without_enabling_placement() -> None:
    decision_event = _make_valid_decision_event()
    claims: list[dict[str, object]] = []
    for venue in ("SPOT", "USD_M"):
        order_event = OrderPlacedEvent(
            event_id=uuid4(),
            timestamp=decision_event.timestamp,
            symbol=decision_event.symbol,
            timeframe=decision_event.timeframe,
            metadata={**decision_event.metadata, "venue": venue},
            order=Order(
                client_order_id=f"{venue.lower()}-entry",
                symbol=decision_event.symbol,
                side=OrderSide.BUY,
                type=OrderType.LIMIT,
                quantity=Decimal("0.001"),
                price=Decimal("50000"),
                status=OrderStatus.NEW,
                created_at=decision_event.timestamp,
            ),
            decision=decision_event.decision,
            router_response=_placement_result().to_dict(),
        )
        claims.append(
            {
                "venue": venue,
                "idempotency_key": f"{venue.lower()}-restart-key",
                "delivery_kind": "ORDER_PLACED",
                "lease_token": f"{venue.lower()}-lease",
                "delivery_payload": order_event.model_dump(mode="json"),
            },
        )

    db_adapter = _MultiVenueRestartDBAdapter(claims)
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.health_check = AsyncMock()
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        execution_mode=ExecutionMode.DISABLED,
        db_adapter=db_adapter,
        bff_client=bff_client,
        success_delivery_venues=("SPOT", "USD_M"),
        success_delivery_poll_interval_seconds=0.01,
    )

    await subscriber.start()
    try:
        async with asyncio.timeout(1):
            while len(db_adapter.completed_venues) < 2:
                await asyncio.sleep(0.01)
    finally:
        await subscriber.stop()

    assert sorted(db_adapter.completed_venues) == ["SPOT", "USD_M"]
    assert bus.handler is None
    router_client.health_check.assert_not_awaited()
    router_client.place_bracket_order.assert_not_awaited()
    assert sum(isinstance(item, OrderPlacedEvent) for item in bus.published_events) == 2
    assert _bff_post_paths(bff_client) == [
        "/api/internal/trading/order-update",
        "/api/internal/trading/order-update",
    ]


@pytest.mark.asyncio
async def test_start_is_idempotent_and_stop_cancels_every_recovery_worker() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.health_check.return_value = {"execution_env": "testnet"}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        success_delivery_venues=("SPOT", "USD_M"),
        success_delivery_poll_interval_seconds=1,
    )
    before = set(asyncio.all_tasks())

    try:
        await subscriber.start()
        first_tasks = dict(subscriber._success_delivery_tasks)
        await subscriber.start()

        assert bus.subscribe_calls == ["router-execution"]
        assert subscriber._success_delivery_tasks == first_tasks
    finally:
        await subscriber.stop()
        leaked = [
            task
            for task in asyncio.all_tasks() - before
            if task.get_name().startswith("router-execution-success-delivery-") and not task.done()
        ]
        for task in leaked:
            task.cancel()
        await asyncio.gather(*leaked, return_exceptions=True)

    assert not [
        task
        for task in asyncio.all_tasks() - before
        if task.get_name().startswith("router-execution-success-delivery-") and not task.done()
    ]


@pytest.mark.asyncio
async def test_concurrent_start_calls_create_one_subscription_and_worker_set() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    health_calls = 0

    async def blocked_health_check() -> dict[str, str]:
        nonlocal health_calls
        health_calls += 1
        entered.set()
        await release.wait()
        return {"execution_env": "testnet"}

    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.health_check.side_effect = blocked_health_check
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        success_delivery_venues=("SPOT", "USD_M"),
        success_delivery_poll_interval_seconds=1,
    )

    first = asyncio.create_task(subscriber.start())
    await entered.wait()
    second = asyncio.create_task(subscriber.start())
    await asyncio.sleep(0)
    release.set()
    try:
        await asyncio.gather(first, second)

        assert health_calls == 1
        assert bus.subscribe_calls == ["router-execution"]
        assert set(subscriber._success_delivery_tasks) == {"SPOT", "USD_M"}
    finally:
        await subscriber.stop()


@pytest.mark.asyncio
async def test_stop_waits_for_concurrent_start_and_leaves_no_owned_workers() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked_health_check() -> dict[str, str]:
        entered.set()
        await release.wait()
        return {"execution_env": "testnet"}

    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.health_check.side_effect = blocked_health_check
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        success_delivery_venues=("SPOT", "USD_M"),
        success_delivery_poll_interval_seconds=1,
    )

    start_task = asyncio.create_task(subscriber.start())
    await entered.wait()
    stop_task = asyncio.create_task(subscriber.stop())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(start_task, stop_task)
    try:
        assert subscriber._started is False
        assert subscriber._subscription_id is None
        assert subscriber._success_delivery_tasks == {}
        assert bus.unsubscribed == ["sub-1"]
    finally:
        await subscriber.stop()


@pytest.mark.asyncio
async def test_order_placed_delivery_requires_durable_bff_acceptance() -> None:
    event = _make_valid_decision_event()
    bus = _FakeBus()
    db_adapter = _FakeDBAdapter()
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": False}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=AsyncMock(),
        db_adapter=db_adapter,
        bff_client=bff_client,
    )
    order_event = subscriber._build_order_placed_event(
        event,
        _placement_result().to_dict(),
        _placement_result().client_order_ids.main,
        "durable-bff-key",
    )

    delivered = await subscriber._process_success_delivery_claim(
        {
            "venue": "USD_M",
            "idempotency_key": "durable-bff-key",
            "delivery_kind": "ORDER_PLACED",
            "lease_token": "lease-durable-bff",
            "delivery_payload": order_event.model_dump(mode="json"),
        },
        event=event,
    )

    assert delivered is False
    assert bff_client.post.await_args.args[0] == "/api/internal/trading/order-update"
    posted = bff_client.post.await_args.args[1]
    assert {
        "client_order_id": posted["client_order_id"],
        "order_id": posted["order_id"],
        "status": posted["status"],
        "venue": posted["venue"],
    } == {
        "client_order_id": order_event.order.client_order_id,
        "order_id": "",
        "status": "new",
        "venue": "USD_M",
    }
    assert not any(isinstance(published, OrderPlacedEvent) for published in bus.published_events)
    assert db_adapter.execution_success_delivery_completions == []
    assert db_adapter.execution_success_delivery_failures == [
        {
            "idempotency_key": "durable-bff-key",
            "venue": "USD_M",
            "delivery_kind": "ORDER_PLACED",
            "lease_token": "lease-durable-bff",
            "error_message": "order placement delivery was not durably acknowledged",
        }
    ]


@pytest.mark.asyncio
async def test_pending_order_event_replay_does_not_repeat_snapshot(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = _FakeBus()
    bus.publish_and_wait_result = False
    router_client = AsyncMock()
    placement = _placement_result()
    router_client.place_bracket_order.return_value = placement
    db_adapter = _FakeDBAdapter()
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        bff_client=bff_client,
        router_max_attempts=1,
    )
    await subscriber.start()
    caplog.set_level("INFO", logger=router_module.__name__)
    event = _make_valid_decision_event()

    assert callable(bus.handler)
    await bus.handler(event)

    stored_payload = db_adapter.execution_intents[0]["request_payload"]
    assert isinstance(stored_payload, dict)
    db_adapter.execution_intent_lookup_result = {
        "state": "ACKNOWLEDGED",
        "request_payload": stored_payload,
        "response_payload": placement.to_dict(),
    }
    bus.publish_and_wait_result = True

    await bus.handler(event)

    router_client.place_bracket_order.assert_awaited_once()
    assert len(db_adapter.commit_execution_ack_calls) == 1
    assert _bff_post_paths(bff_client) == [
        "/api/signals/alert",
        "/api/internal/trading/order-update",
        "/api/internal/trading/order-update",
    ]
    assert db_adapter.execution_success_delivery_states == {
        "ORDER_PLACED": "DELIVERED",
        "SNAPSHOT": "DELIVERED",
    }
    assert [
        completion["delivery_kind"]
        for completion in db_adapter.execution_success_delivery_completions
    ] == ["SNAPSHOT", "ORDER_PLACED"]
    assert sum("Order placed successfully" in record.getMessage() for record in caplog.records) == 1


@pytest.mark.asyncio
async def test_delivered_execution_replay_is_noop(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    placement = _placement_result()
    router_client.place_bracket_order.return_value = placement
    db_adapter = _FakeDBAdapter()
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        bff_client=bff_client,
        router_max_attempts=1,
    )
    await subscriber.start()
    caplog.set_level("INFO", logger=router_module.__name__)
    event = _make_valid_decision_event()

    assert callable(bus.handler)
    await bus.handler(event)

    stored_payload = db_adapter.execution_intents[0]["request_payload"]
    assert isinstance(stored_payload, dict)
    db_adapter.execution_intent_lookup_result = {
        "state": "ACKNOWLEDGED",
        "request_payload": stored_payload,
        "response_payload": placement.to_dict(),
    }
    await bus.handler(event)

    router_client.place_bracket_order.assert_awaited_once()
    assert len(db_adapter.commit_execution_ack_calls) == 1
    assert _bff_post_paths(bff_client) == [
        "/api/signals/alert",
        "/api/internal/trading/order-update",
    ]
    assert db_adapter.execution_success_delivery_states == {
        "ORDER_PLACED": "DELIVERED",
        "SNAPSHOT": "DELIVERED",
    }
    assert [
        completion["delivery_kind"]
        for completion in db_adapter.execution_success_delivery_completions
    ] == ["SNAPSHOT", "ORDER_PLACED"]
    assert sum(isinstance(published, OrderPlacedEvent) for published in bus.published_events) == 1
    assert not any(isinstance(published, ErrorEvent) for published in bus.published_events)
    assert sum("Order placed successfully" in record.getMessage() for record in caplog.records) == 1


@pytest.mark.asyncio
async def test_acknowledged_replay_resumes_delivery_when_live_risk_is_unavailable() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    placement = _placement_result()
    db_adapter = _FakeDBAdapter()
    db_adapter.active_positions_error = RuntimeError("risk database unavailable")
    db_adapter.execution_intent_lookup_result = {
        "state": "ACKNOWLEDGED",
        "request_payload": {},
        "response_payload": placement.to_dict(),
    }
    db_adapter.execution_success_delivery_states = {
        "SNAPSHOT": "PENDING",
        "ORDER_PLACED": "PENDING",
    }
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        bff_client=bff_client,
        router_max_attempts=1,
    )
    event = _make_valid_decision_event()
    db_adapter.execution_success_delivery_payloads = {
        "SNAPSHOT": subscriber._build_snapshot_payload(event, "sig_test123"),
        "ORDER_PLACED": subscriber._build_order_placed_event(
            event,
            placement.to_dict(),
            placement.client_order_ids.main,
            "sig_test123",
        ).model_dump(mode="json"),
    }
    await subscriber.start()

    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()
    assert _bff_post_paths(bff_client) == [
        "/api/signals/alert",
        "/api/internal/trading/order-update",
    ]
    assert db_adapter.execution_success_delivery_states == {
        "SNAPSHOT": "DELIVERED",
        "ORDER_PLACED": "DELIVERED",
    }
    assert not any(
        isinstance(published, ErrorEvent)
        and published.error_type in {"risk_snapshot_unavailable", "risk_limit_exceeded"}
        for published in bus.published_events
    )


@pytest.mark.asyncio
async def test_acknowledged_replay_does_not_fail_when_delivery_has_an_active_lease() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    placement = _placement_result()
    db_adapter = _FakeDBAdapter()
    db_adapter.execution_intent_lookup_result = {
        "state": "ACKNOWLEDGED",
        "request_payload": {},
        "response_payload": placement.to_dict(),
    }
    db_adapter.execution_success_delivery_states = {"ORDER_PLACED": "DELIVERING"}
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        router_max_attempts=1,
    )
    await subscriber.start()

    assert callable(bus.handler)
    await bus.handler(_make_valid_decision_event())

    router_client.place_bracket_order.assert_not_awaited()
    assert not any(isinstance(published, ErrorEvent) for published in bus.published_events)


@pytest.mark.asyncio
async def test_persist_orders_to_db_skips_spot_stop_loss_without_exact_limit_price() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        execution_mode=ExecutionMode.SPOT_TESTNET,
    )

    event = _make_valid_decision_event()
    response = {"bracket_order_id": "bracket-1", "success": True}

    await subscriber._persist_orders_to_db(
        event,
        response,
        router_module._ClientOrderIDs(
            main="entry-1",
            take_profits=["tp-1"],
            stop_loss="sl-1",
        ),
        [Decimal("51000.00")],
        False,
    )

    assert [row["client_order_id"] for row in subscriber._db_adapter.upserted_orders] == [
        "entry-1",
        "tp-1",
    ]
    assert all(row["type"] != "STOP_LOSS_LIMIT" for row in subscriber._db_adapter.upserted_orders)


@pytest.mark.asyncio
async def test_find_duplicate_execution_reason_runs_independent_queries_concurrently() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    db_adapter = _BlockingDuplicateGuardDBAdapter()
    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
    )

    zone_identity = SimpleNamespace(zone_id="zone_1")
    task = asyncio.create_task(
        subscriber._find_duplicate_execution_reason(
            symbol="BTCUSDT",
            side="BUY",
            timeframe="15m",
            zone_identity=zone_identity,
        ),
    )

    await asyncio.wait_for(
        asyncio.gather(
            db_adapter.setup_position_started.wait(),
            db_adapter.active_positions_started.wait(),
            db_adapter.setup_order_started.wait(),
        ),
        timeout=0.1,
    )
    db_adapter.release.set()

    assert await task is None


@pytest.mark.asyncio
async def test_persist_orders_to_db_upserts_legs_concurrently() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    db_adapter = _BlockingUpsertDBAdapter(expected_calls=3)
    subscriber = _make_subscriber(bus=bus, router_client=router_client, db_adapter=db_adapter)

    event = _make_valid_decision_event()
    response = {"bracket_order_id": "bracket-1", "success": True}
    persist_task = asyncio.create_task(
        subscriber._persist_orders_to_db(
            event,
            response,
            router_module._ClientOrderIDs(
                main="entry-1",
                take_profits=["tp-1"],
                stop_loss="sl-1",
            ),
            [Decimal("51000.00")],
            True,
        ),
    )

    await asyncio.wait_for(db_adapter.all_started.wait(), timeout=0.1)
    assert db_adapter.max_in_flight == 3
    db_adapter.release.set()

    await persist_task


@pytest.mark.asyncio
async def test_execution_rejects_quantity_over_max_position_size() -> None:
    from app.engine.models import ErrorEvent

    bus = _FakeBus()
    router_client = AsyncMock()

    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        max_position_size=Decimal("0.0005"),
        router_max_attempts=1,
    )
    await subscriber.start()

    event = _make_valid_decision_event()
    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "risk_limit_exceeded"


@pytest.mark.asyncio
async def test_execution_blocks_when_daily_loss_exceeded() -> None:
    """Execution must fail-closed when daily loss limit is breached."""
    from app.engine.models import ErrorEvent

    class _LossyDBAdapter(_FakeDBAdapter):
        async def get_latest_equity_sample(self):
            return Decimal(9000), datetime.now(UTC)

        async def get_equity_sample_at_or_after(self, _ts: datetime):
            return Decimal(10_000)

    bus = _FakeBus()
    router_client = AsyncMock()

    risk = RiskParameters(
        max_position_size=Decimal("999999"),
        max_daily_loss=Decimal("0.05"),
        max_drawdown=Decimal("1"),
        risk_per_trade=Decimal("0.01"),
        max_correlation=Decimal("1"),
        max_open_positions=100,
        max_total_exposure_leverage=Decimal("100"),
        max_symbol_exposure_pct=Decimal("1"),
        max_position_notional_pct=Decimal("1"),
        risk_data_max_age_seconds=86400,
        drawdown_lookback_days=30,
    )

    subscriber = _track_subscriber(
        RouterExecutionSubscriber(
            bus=bus,
            router_client=router_client,
            db_adapter=_LossyDBAdapter(),  # type: ignore[arg-type]
            risk=risk,
            venue="USD_M",
            execution_mode=ExecutionMode.FUTURES_TESTNET,
            order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
            router_max_attempts=1,
        )
    )
    await subscriber.start()

    event = _make_valid_decision_event()
    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "risk_limit_exceeded"


# =============================================================================
# Tests for RouterExecutionSubscriber Core Functionality
# =============================================================================


@pytest.mark.asyncio
async def test_execution_subscriber_calls_router_place_bracket_with_provenance() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = _placement_result(
        symbol="ETHUSDT",
        side="SELL",
        quantity=Decimal("0.01"),
        id_token="3cfbd12d60a93548",
    )

    subscriber = _make_subscriber(bus=bus, router_client=router_client)

    await subscriber.start()
    assert bus.event_types == [EventType.TRADING_DECISION]

    now = datetime.now(UTC)
    decision = TradingDecision(
        venue="SPOT",
        symbol="ETHUSDT",
        timestamp=now,
        action="SELL",
        entry_price=Decimal("3184.36"),
        stop_loss=Decimal("3187.16"),
        take_profit=Decimal("3152.52"),
        quantity=Decimal("0.01"),
        confidence=Decimal("0.75"),  # Above min_confidence threshold (0.70)
        reasoning="FVG fill with bearish bias",
    )
    event = TradingDecisionEvent(
        symbol="ETHUSDT",
        timestamp=now,
        timeframe=TimeFrame.M15,
        decision=decision,
        metadata={
            "signal_id": "sig_abc123",
            "decision_source": "retest_decision_publisher",
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
    await bus.handler(event)

    router_client.place_bracket_order.assert_awaited_once()
    payload = router_client.place_bracket_order.call_args.args[0]

    assert payload["symbol"] == "ETHUSDT"
    assert payload["side"] == "SELL"
    assert payload["is_futures"] is True
    assert payload["metadata"]["signal_id"] == "sig_abc123"
    assert payload["metadata"]["timeframe"] == "15m"
    assert payload["metadata"]["zone"]["zone_type"] == "FAIR_VALUE_GAP"
    assert payload["metadata"]["decision_source"] == "retest_decision_publisher"


@pytest.mark.asyncio
async def test_execution_subscriber_persists_signal_timeframe_zone_for_all_legs() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = _placement_result(
        symbol="ETHUSDT",
        side="SELL",
        quantity=Decimal("0.01"),
        id_token="3cfbd12d60a93548",
        bracket_order_id="bracket-123",
    )
    db_adapter = _FakeDBAdapter()

    subscriber = _make_subscriber(bus=bus, router_client=router_client, db_adapter=db_adapter)
    await subscriber.start()

    now = datetime.now(UTC)
    zone = {
        "zone_id": "zone_1",
        "zone_type": "FAIR_VALUE_GAP",
        "top_price": Decimal("3190"),
        "bottom_price": Decimal("3180"),
    }
    decision = TradingDecision(
        venue="SPOT",
        symbol="ETHUSDT",
        timestamp=now,
        action="SELL",
        entry_price=Decimal("3184.36"),
        stop_loss=Decimal("3187.16"),
        take_profit=Decimal("3152.52"),
        quantity=Decimal("0.01"),
        confidence=Decimal("0.75"),
        reasoning="FVG fill with bearish bias",
    )
    event = TradingDecisionEvent(
        symbol="ETHUSDT",
        timestamp=now,
        timeframe=TimeFrame.M15,
        decision=decision,
        metadata={
            "signal_id": "sig_abc123",
            "decision_source": "retest_decision_publisher",
            "timeframe": "15m",
            "zone": zone,
        },
    )

    assert callable(bus.handler)
    await bus.handler(event)

    assert len(db_adapter.upserted_orders) == 3
    for row in db_adapter.upserted_orders:
        assert row["signal_id"] == "sig_abc123"
        assert row["timeframe"] == "15m"
        assert row["zone"] == {
            "zone_id": "zone_1",
            "zone_type": "FAIR_VALUE_GAP",
            "top_price": "3190",
            "bottom_price": "3180",
        }


@pytest.mark.asyncio
async def test_execution_subscriber_skips_spot_stop_leg_persistence() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = _placement_result(
        bracket_order_id="bracket-spot-123"
    )
    db_adapter = _FakeDBAdapter()

    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        execution_mode=ExecutionMode.SPOT_TESTNET,
    )
    await subscriber.start()

    event = _make_valid_decision_event()
    event.metadata["timeframe"] = "15m"
    event.metadata["zone"] = {"zone_id": "zone_1", "zone_type": "FAIR_VALUE_GAP"}
    assert callable(bus.handler)
    await bus.handler(event)

    stop_rows = [row for row in db_adapter.upserted_orders if row["type"] == "STOP_LOSS_LIMIT"]
    assert stop_rows == []


@pytest.mark.asyncio
async def test_execution_subscriber_blocks_active_duplicate_setup_before_cooldown() -> None:
    from app.engine.models import ErrorEvent

    bus = _FakeBus()
    router_client = AsyncMock()
    db_adapter = _FakeDBAdapter()
    db_adapter.active_setup_order = {"client_order_id": "existing-entry"}
    cooldown = AsyncMock()

    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        cooldown=cooldown,
    )
    await subscriber.start()

    now = datetime.now(UTC)
    decision = TradingDecision(
        venue="SPOT",
        symbol="ETHUSDT",
        timestamp=now,
        action="SELL",
        entry_price=Decimal("3184.36"),
        stop_loss=Decimal("3187.16"),
        take_profit=Decimal("3152.52"),
        quantity=Decimal("0.01"),
        confidence=Decimal("0.75"),
        reasoning="FVG fill with bearish bias",
    )
    event = TradingDecisionEvent(
        symbol="ETHUSDT",
        timestamp=now,
        timeframe=TimeFrame.M15,
        decision=decision,
        metadata={
            "signal_id": "sig_abc123",
            "decision_source": "retest_decision_publisher",
            "timeframe": "15m",
            "zone": {"zone_id": "zone_1", "zone_type": "FAIR_VALUE_GAP"},
        },
    )

    assert callable(bus.handler)
    await bus.handler(event)

    cooldown.try_acquire_async.assert_not_awaited()
    router_client.place_bracket_order.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "duplicate_active_setup"


@pytest.mark.asyncio
async def test_execution_subscriber_blocks_when_setup_position_is_active() -> None:
    from app.engine.models import ErrorEvent

    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = {"success": True}
    db_adapter = _FakeDBAdapter()
    db_adapter.active_positions = [
        {
            "symbol": "BTCUSDT",
            "size": Decimal("0.01"),
            "current_price": Decimal("50000"),
        },
    ]
    db_adapter.active_setup_position = {
        "position_id": "pos-1",
        "entry_order_id": "ord-1",
    }

    subscriber = _make_subscriber(bus=bus, router_client=router_client, db_adapter=db_adapter)
    await subscriber.start()

    event = _make_valid_decision_event()
    event.metadata["timeframe"] = "15m"
    event.metadata["zone"] = {"zone_id": "zone_1", "zone_type": "FAIR_VALUE_GAP"}
    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "duplicate_active_setup"


@pytest.mark.asyncio
async def test_execution_subscriber_allows_other_setup_when_active_position_origin_differs() -> (
    None
):
    from app.engine.models import ErrorEvent

    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = _placement_result()
    bff_client = AsyncMock()
    bff_client.post.return_value = {"ok": True}
    db_adapter = _FakeDBAdapter()
    db_adapter.active_positions = [
        {
            "symbol": "BTCUSDT",
            "size": Decimal("0.01"),
            "current_price": Decimal("50000"),
            "entry_order_id": "ord-2",
        },
    ]
    db_adapter.active_setup_position = None

    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        bff_client=bff_client,
    )
    await subscriber.start()

    event = _make_valid_decision_event()
    event.metadata["timeframe"] = "15m"
    event.metadata["zone"] = {"zone_id": "zone_1", "zone_type": "FAIR_VALUE_GAP"}
    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_awaited_once()
    assert not any(isinstance(published, ErrorEvent) for published in bus.published_events)


@pytest.mark.asyncio
async def test_execution_subscriber_blocks_when_opposite_side_position_is_active() -> None:
    from app.engine.models import ErrorEvent

    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = _placement_result()
    db_adapter = _FakeDBAdapter()
    db_adapter.active_positions = [
        {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "size": Decimal("0.01"),
            "current_price": Decimal("50000"),
            "entry_order_id": "ord-2",
        },
    ]
    db_adapter.active_setup_position = None

    subscriber = _make_subscriber(bus=bus, router_client=router_client, db_adapter=db_adapter)
    await subscriber.start()

    event = _make_valid_decision_event()
    event.metadata["timeframe"] = "15m"
    event.metadata["zone"] = {"zone_id": "zone_1", "zone_type": "FAIR_VALUE_GAP"}
    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "duplicate_active_setup"


@pytest.mark.asyncio
async def test_execution_subscriber_blocks_when_active_position_origin_is_unknown() -> None:
    from app.engine.models import ErrorEvent

    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = {"success": True}
    db_adapter = _FakeDBAdapter()
    db_adapter.active_positions = [
        {
            "symbol": "BTCUSDT",
            "size": Decimal("0.01"),
            "current_price": Decimal("50000"),
            "entry_order_id": "",
        },
    ]
    db_adapter.active_setup_position = None

    subscriber = _make_subscriber(bus=bus, router_client=router_client, db_adapter=db_adapter)
    await subscriber.start()

    event = _make_valid_decision_event()
    event.metadata["timeframe"] = "15m"
    event.metadata["zone"] = {"zone_id": "zone_1", "zone_type": "FAIR_VALUE_GAP"}
    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "duplicate_active_setup"


@pytest.mark.asyncio
async def test_execution_subscriber_blocks_when_setup_position_lookup_degrades() -> None:
    from app.engine.models import ErrorEvent

    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = {"success": True}
    db_adapter = _FakeDBAdapter()
    db_adapter.active_setup_position_error = RuntimeError("db unavailable")

    subscriber = _make_subscriber(bus=bus, router_client=router_client, db_adapter=db_adapter)
    await subscriber.start()

    event = _make_valid_decision_event()
    event.metadata["timeframe"] = "15m"
    event.metadata["zone"] = {"zone_id": "zone_1", "zone_type": "FAIR_VALUE_GAP"}
    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "duplicate_active_setup"
    assert "unavailable" in bus.published_events[0].error_message.lower()


@pytest.mark.asyncio
async def test_execution_subscriber_blocks_when_active_positions_lookup_degrades() -> None:
    from app.engine.models import ErrorEvent

    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = {"success": True}
    db_adapter = _FakeDBAdapter()
    db_adapter.active_positions_errors = [None, RuntimeError("db unavailable")]

    subscriber = _make_subscriber(bus=bus, router_client=router_client, db_adapter=db_adapter)
    await subscriber.start()

    event = _make_valid_decision_event()
    event.metadata["timeframe"] = "15m"
    event.metadata["zone"] = {"zone_id": "zone_1", "zone_type": "FAIR_VALUE_GAP"}
    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "duplicate_active_setup"
    assert "unavailable" in bus.published_events[0].error_message.lower()


@pytest.mark.asyncio
async def test_execution_subscriber_blocks_when_setup_order_lookup_degrades() -> None:
    from app.engine.models import ErrorEvent

    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = {"success": True}
    db_adapter = _FakeDBAdapter()
    db_adapter.active_setup_order_error = RuntimeError("db unavailable")

    subscriber = _make_subscriber(bus=bus, router_client=router_client, db_adapter=db_adapter)
    await subscriber.start()

    event = _make_valid_decision_event()
    event.metadata["timeframe"] = "15m"
    event.metadata["zone"] = {"zone_id": "zone_1", "zone_type": "FAIR_VALUE_GAP"}
    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "duplicate_active_setup"
    assert "unavailable" in bus.published_events[0].error_message.lower()


@pytest.mark.asyncio
async def test_execution_rejects_missing_decision_source() -> None:
    """Execution must reject decisions without provenance."""
    from app.engine.models import ErrorEvent

    bus = _FakeBus()
    router_client = AsyncMock()

    subscriber = _make_subscriber(bus=bus, router_client=router_client)
    await subscriber.start()

    event = _make_valid_decision_event()
    event.metadata.pop("decision_source", None)

    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "invalid_decision_source"


@pytest.mark.asyncio
async def test_execution_rejects_signal_emitter_bypass_source() -> None:
    """Even if bypass is enabled, it must not execute orders."""
    from app.engine.models import ErrorEvent

    bus = _FakeBus()
    router_client = AsyncMock()

    subscriber = _make_subscriber(bus=bus, router_client=router_client)
    await subscriber.start()

    event = _make_valid_decision_event()
    event.metadata["decision_source"] = "signal_emitter_bypass"

    assert callable(bus.handler)
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()
    assert len(bus.published_events) == 1
    assert isinstance(bus.published_events[0], ErrorEvent)
    assert bus.published_events[0].error_type == "invalid_decision_source"


@pytest.mark.asyncio
async def test_execution_subscriber_ignores_decisions_missing_levels() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()

    subscriber = _make_subscriber(bus=bus, router_client=router_client)
    await subscriber.start()

    now = datetime.now(UTC)
    decision = TradingDecision(
        venue="SPOT",
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
    await bus.handler(event)

    router_client.place_bracket_order.assert_not_awaited()


# =============================================================================
# Tests for Snapshot Timing (Gap 2 fix)
# =============================================================================


@pytest.mark.asyncio
async def test_snapshot_triggered_before_order_placed_event() -> None:
    """Snapshot should be triggered BEFORE OrderPlacedEvent is emitted.

    This ensures the snapshot is available when alert handler runs.
    """
    call_order: list[str] = []

    class _TrackingBus:
        def __init__(self) -> None:
            self.handler: object | None = None
            self.event_types: list[EventType] | None = None
            self.published_events: list[object] = []

        async def subscribe(
            self,
            subscriber_id: str,
            handler: object,
            event_types: list[EventType] | None = None,
            priority: int = 0,
        ) -> str:
            _ = subscriber_id, priority
            self.handler = handler
            self.event_types = event_types
            return "sub-1"

        async def unsubscribe(self, subscription_id: str) -> bool:
            _ = subscription_id
            return True

        async def publish(self, event: object, priority: int = 0) -> bool:
            _ = priority
            self.published_events.append(event)
            if isinstance(event, OrderPlacedEvent):
                call_order.append("publish_order_placed")
            return True

        async def publish_and_wait(self, event: object, priority: int = 0) -> bool:
            return await self.publish(event, priority)

    class _TrackingBffClient:
        async def post(self, endpoint: str, payload: dict) -> dict:
            _ = payload
            call_order.append(endpoint)
            return {"ok": True}

    bus = _TrackingBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = _placement_result()
    bff_client = _TrackingBffClient()

    subscriber = _track_subscriber(
        RouterExecutionSubscriber(
            bus=bus,
            router_client=router_client,
            db_adapter=_FakeDBAdapter(),  # type: ignore[arg-type]
            risk=_default_risk(),
            venue="USD_M",
            execution_mode=ExecutionMode.FUTURES_TESTNET,
            order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
            bff_client=bff_client,
        )
    )
    await subscriber.start()

    event = _make_valid_decision_event()
    assert callable(bus.handler)
    await bus.handler(event)

    assert call_order == [
        "/api/signals/alert",
        "/api/internal/trading/order-update",
        "publish_order_placed",
    ]
    assert sum(isinstance(published, OrderPlacedEvent) for published in bus.published_events) == 1
    assert not any(isinstance(published, ErrorEvent) for published in bus.published_events)
