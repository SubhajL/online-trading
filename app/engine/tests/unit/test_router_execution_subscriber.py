"""Unit tests for RouterExecutionSubscriber."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.engine.execution.order_update_correlation import OrderUpdateCorrelationStore
import app.engine.execution.router_execution_subscriber as router_module
from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    RouterExecutionSubscriber,
    _sanitize_value_for_json,
)
from app.engine.models import (
    EventType,
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

    async def upsert_order(self, _order: dict[str, object]) -> bool:
        self.upserted_orders.append(_order)
        return True

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
    return RouterExecutionSubscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,  # type: ignore[arg-type]
        risk=_default_risk(),
        venue=_venue_for_mode(execution_mode),
        execution_mode=execution_mode,
        order_update_correlation_store=correlation_store,
        **kwargs,
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
    async def test_emits_error_event_on_unsuccessful_response(self) -> None:
        """Router returns success=False triggers ErrorEvent."""
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

        subscriber = _make_subscriber(bus=bus, router_client=router_client)
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
        Exception("timeout"),
        Exception("connection reset"),
        {"success": True, "order_id": "ok"},
    ]

    sleep = AsyncMock()
    monkeypatch.setattr(router_module.asyncio, "sleep", sleep)

    subscriber = _make_subscriber(
        bus=bus,
        router_client=router_client,
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
    subscriber = _make_subscriber(bus=bus, router_client=router_client, db_adapter=db_adapter)

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

    subscriber = RouterExecutionSubscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=_LossyDBAdapter(),  # type: ignore[arg-type]
        risk=risk,
        venue="USD_M",
        execution_mode=ExecutionMode.FUTURES_TESTNET,
        order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
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


# =============================================================================
# Tests for RouterExecutionSubscriber Core Functionality
# =============================================================================


@pytest.mark.asyncio
async def test_execution_subscriber_calls_router_place_bracket_with_provenance() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = {"success": True}

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
    router_client.place_bracket_order.return_value = {
        "success": True,
        "bracket_order_id": "bracket-123",
    }
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
    router_client.place_bracket_order.return_value = {
        "success": True,
        "bracket_order_id": "bracket-spot-123",
    }
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
    router_client.place_bracket_order.return_value = {"success": True}
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

    subscriber = _make_subscriber(bus=bus, router_client=router_client, db_adapter=db_adapter)
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
    router_client.place_bracket_order.return_value = {"success": True}
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
            _ = event, priority
            call_order.append("publish_order_placed")
            return True

    class _TrackingBffClient:
        async def post(self, endpoint: str, payload: dict) -> dict:
            _ = endpoint, payload
            call_order.append("notify_snapshot")
            return {"success": True}

    bus = _TrackingBus()
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = {"success": True}
    bff_client = _TrackingBffClient()

    subscriber = RouterExecutionSubscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=_FakeDBAdapter(),  # type: ignore[arg-type]
        risk=_default_risk(),
        venue="USD_M",
        execution_mode=ExecutionMode.FUTURES_TESTNET,
        order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
        bff_client=bff_client,
    )
    await subscriber.start()

    event = _make_valid_decision_event()
    assert callable(bus.handler)
    await bus.handler(event)

    # Verify snapshot is triggered BEFORE order placed event is published
    assert call_order == ["notify_snapshot", "publish_order_placed"]
