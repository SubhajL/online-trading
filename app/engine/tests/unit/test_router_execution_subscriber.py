"""Unit tests for RouterExecutionSubscriber."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    RouterExecutionSubscriber,
)
from app.engine.models import EventType, TimeFrame, TradingDecision, TradingDecisionEvent


class _FakeBus:
    def __init__(self) -> None:
        self.handler: object | None = None
        self.event_types: list[EventType] | None = None
        self.unsubscribed: list[str] = []

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


@pytest.mark.asyncio
async def test_execution_subscriber_calls_router_place_bracket_with_provenance() -> None:
    bus = _FakeBus()
    router_client = AsyncMock()

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
