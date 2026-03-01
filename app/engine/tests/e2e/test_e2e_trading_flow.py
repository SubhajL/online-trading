"""
CRITICAL: End-to-end trading flow test.

This test validates the live runtime wiring for the most important "money path":
Retest signal -> DecisionPublisher -> RouterExecutionSubscriber -> router client call.

Indicator + SMC correctness are covered by dedicated unit tests run in CI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from app.engine import bus as bus_module
from app.engine.decision.decision_publisher import DecisionPublisher
from app.engine.execution.order_update_correlation import OrderUpdateCorrelationStore
from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    RouterExecutionSubscriber,
)
from app.engine.models import (
    ErrorEvent,
    EventType,
    RetestSignal,
    RetestSignalEvent,
    RiskParameters,
    TimeFrame,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


pytestmark = pytest.mark.e2e


class _InProcBus:
    def __init__(self) -> None:
        self._next_id = 1
        self._subs: dict[str, tuple[list[EventType] | None, Callable[[Any], Awaitable[None]]]] = {}

    async def subscribe(
        self,
        subscriber_id: str,
        handler: object,
        event_types: list[EventType] | None = None,
        priority: int = 0,
        max_retries: int = 0,
        serialize_by_key: bool = False,
        key_extractor: object | None = None,
    ) -> str:
        _ = subscriber_id, priority, max_retries, serialize_by_key, key_extractor
        if not callable(handler):
            raise TypeError("handler must be callable")
        sub_id = f"sub-{self._next_id}"
        self._next_id += 1
        self._subs[sub_id] = (event_types, handler)
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        self._subs.pop(subscription_id, None)
        return True

    async def publish(self, event: Any, priority: int = 0) -> bool:
        _ = priority
        for event_types, handler in list(self._subs.values()):
            if event_types is None or getattr(event, "event_type", None) in event_types:
                await handler(event)
        return True


class _FakeDBAdapter:
    async def get_latest_equity_sample(self):
        return Decimal(10_000), datetime.now(UTC)

    async def get_equity_sample_at_or_after(self, _ts: datetime):
        return Decimal(10_000)

    async def get_peak_equity_since(self, _ts: datetime):
        return Decimal(10_000)

    async def get_active_positions(self, _venue: str):
        return []


@pytest.mark.asyncio
async def test_retest_signal_to_router_order() -> None:
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = {"success": True}

    bus = _InProcBus()
    previous_bus = getattr(bus_module, "_global_event_bus", None)
    bus_module.set_event_bus(bus)  # type: ignore[arg-type]

    db_adapter = _FakeDBAdapter()
    risk = RiskParameters(
        max_position_size=Decimal("999999"),
        max_daily_loss=Decimal("1"),
        max_drawdown=Decimal("1"),
        risk_per_trade=Decimal("0.005"),
        max_correlation=Decimal("1"),
        max_open_positions=100,
        max_total_exposure_leverage=Decimal("100"),
        max_symbol_exposure_pct=Decimal("1"),
        max_position_notional_pct=Decimal("1"),
        risk_data_max_age_seconds=86400,
        drawdown_lookback_days=30,
    )

    decision_publisher = DecisionPublisher(
        db_adapter=db_adapter,  # type: ignore[arg-type]
        risk=risk,
        venue="USD_M",
    )
    execution = RouterExecutionSubscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,  # type: ignore[arg-type]
        risk=risk,
        venue="USD_M",
        execution_mode=ExecutionMode.FUTURES_TESTNET,
        order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
    )

    try:
        await decision_publisher.start()
        await execution.start()

        now = datetime.now(UTC)
        signal = RetestSignal(
            venue="USD_M",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            timestamp=now,
            level_price=Decimal(100),
            direction="BUY",
            stop_loss=Decimal(95),
            take_profit=Decimal(110),
            retest_type="zone_retest",
            success_probability=Decimal("0.80"),
            volume_confirmation=True,
            confluence_factors=["bos", "rsi_bounce"],
        )
        event = RetestSignalEvent(
            timestamp=now,
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            signal=signal,
            metadata={
                "zone": {"zone_id": "zone-1", "zone_type": "OB"},
                "timeframe": "5m",
            },
        )

        await bus.publish(event)
        router_client.place_bracket_order.assert_awaited_once()
        captured = router_client.place_bracket_order.call_args.args[0]

        assert captured["symbol"] == "BTCUSDT"
        assert captured["side"] == "BUY"
        assert captured["metadata"]["decision_source"] == "retest_decision_publisher"
        assert captured["metadata"]["signal_id"] == str(signal.signal_id)
    finally:
        await decision_publisher.stop()
        await execution.stop()
        bus_module._global_event_bus = previous_bus


@pytest.mark.asyncio
async def test_retest_signal_risk_rejection_emits_error_and_skips_execution() -> None:
    router_client = AsyncMock()
    router_client.place_bracket_order.return_value = {"success": True}

    bus = _InProcBus()
    previous_bus = getattr(bus_module, "_global_event_bus", None)
    bus_module.set_event_bus(bus)  # type: ignore[arg-type]

    errors: list[ErrorEvent] = []

    async def _capture_error(event: ErrorEvent) -> None:
        errors.append(event)

    await bus.subscribe(
        subscriber_id="capture_errors",
        handler=_capture_error,
        event_types=[EventType.ERROR],
        priority=0,
    )

    db_adapter = _FakeDBAdapter()
    risk = RiskParameters(
        max_position_size=Decimal("999999"),
        max_daily_loss=Decimal("1"),
        max_drawdown=Decimal("1"),
        risk_per_trade=Decimal("0.005"),
        max_correlation=Decimal("1"),
        max_open_positions=100,
        max_total_exposure_leverage=Decimal("100"),
        max_symbol_exposure_pct=Decimal("1"),
        # Force a pretrade rejection in DecisionPublisher/evaluate_pretrade_risk.
        max_position_notional_pct=Decimal("0.01"),
        risk_data_max_age_seconds=86400,
        drawdown_lookback_days=30,
    )

    decision_publisher = DecisionPublisher(
        db_adapter=db_adapter,  # type: ignore[arg-type]
        risk=risk,
        venue="USD_M",
    )
    execution = RouterExecutionSubscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,  # type: ignore[arg-type]
        risk=risk,
        venue="USD_M",
        execution_mode=ExecutionMode.FUTURES_TESTNET,
        order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
    )

    try:
        await decision_publisher.start()
        await execution.start()

        now = datetime.now(UTC)
        # Tight stop => large notional ratio => expected to exceed max_position_notional_pct=0.01.
        signal = RetestSignal(
            venue="USD_M",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            timestamp=now,
            level_price=Decimal(100),
            direction="BUY",
            stop_loss=Decimal(99),
            take_profit=Decimal(110),
            retest_type="zone_retest",
            success_probability=Decimal("0.80"),
            volume_confirmation=True,
            confluence_factors=["bos", "rsi_bounce"],
        )
        event = RetestSignalEvent(
            timestamp=now,
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            signal=signal,
        )

        await bus.publish(event)

        router_client.place_bracket_order.assert_not_awaited()
        assert errors, "Expected at least one ErrorEvent"
        assert errors[-1].error_type == "risk_limit_exceeded"
    finally:
        await decision_publisher.stop()
        await execution.stop()
        bus_module._global_event_bus = previous_bus
