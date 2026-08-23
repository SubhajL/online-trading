from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from app.engine import bus as bus_module
from app.engine.adapters.router_client.http_client import (
    BracketClientOrderIDs,
    BracketPlacementResult,
)
from app.engine.decision.decision_publisher import DecisionPublisher
from app.engine.execution.order_update_correlation import OrderUpdateCorrelationStore
from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    RouterExecutionSubscriber,
)
from app.engine.models import (
    EventType,
    RetestSignal,
    RetestSignalEvent,
    RiskParameters,
    TimeFrame,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


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

    async def publish_and_wait(self, event: Any, priority: int = 0) -> bool:
        return await self.publish(event, priority)


class _FakeDBAdapter:
    def __init__(self) -> None:
        self.delivery_state = "PENDING"

    async def has_incomplete_execution_intent_outside_venue(
        self,
        active_venue: str,
    ) -> bool:
        _ = active_venue
        return False

    async def get_execution_intent_for_request(self, *_args, **_kwargs):
        return None

    async def prepare_execution_intent(self, _intent):
        return True

    async def transition_execution_intent(self, *_args, **_kwargs):
        return True

    async def commit_execution_ack(self, *_args, **_kwargs):
        self.delivery_state = "PENDING"
        return True

    async def claim_execution_success_delivery(self, *_args, **_kwargs):
        if self.delivery_state != "PENDING":
            return None
        self.delivery_state = "DELIVERING"
        return {"delivery_kind": "ORDER_PLACED", "lease_token": "lease-1"}

    async def complete_execution_success_delivery(self, *_args, **_kwargs):
        self.delivery_state = "DELIVERED"

    async def fail_execution_success_delivery(self, *_args, **_kwargs):
        self.delivery_state = "PENDING"

    async def has_pending_execution_success_delivery(self, *_args, **_kwargs):
        return self.delivery_state != "DELIVERED"

    async def get_latest_equity_sample(self):
        return Decimal(10_000), datetime.now(UTC)

    async def get_equity_sample_at_or_after(self, _ts: datetime):
        return Decimal(10_000)

    async def get_peak_equity_since(self, _ts: datetime):
        return Decimal(10_000)

    async def get_active_positions(self, _venue: str):
        return []


def _placement_result(payload: dict[str, object]) -> BracketPlacementResult:
    client_order_ids = payload["client_order_ids"]
    assert isinstance(client_order_ids, dict)
    take_profits = client_order_ids["take_profits"]
    assert isinstance(take_profits, list)
    return BracketPlacementResult(
        bracket_order_id="bracket-test",
        client_order_ids=BracketClientOrderIDs(
            main=str(client_order_ids["main"]),
            take_profits=tuple(str(value) for value in take_profits),
            stop_loss=str(client_order_ids["stop_loss"]),
        ),
        symbol=str(payload["symbol"]),
        side=str(payload["side"]),
        quantity=Decimal(str(payload["quantity"])),
        created_at=datetime.now(UTC),
        partial_failure=False,
        errors=(),
        legs_pending_trigger=False,
    )


@pytest.mark.asyncio
async def test_flow_retest_signal_to_router_order() -> None:
    router_client = AsyncMock()
    router_client.place_bracket_order.side_effect = _placement_result

    bus = _InProcBus()
    previous_bus = getattr(bus_module, "_global_event_bus", None)
    bus_module.set_event_bus(bus)  # type: ignore[arg-type]  # DecisionPublisher pulls from global bus

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
