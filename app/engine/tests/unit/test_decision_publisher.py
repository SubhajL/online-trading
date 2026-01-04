from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.engine.bus import create_event_bus, set_event_bus
from app.engine.decision.decision_publisher import DecisionPublisher
from app.engine.models import (
    EventType,
    RetestSignal,
    RetestSignalEvent,
    TimeFrame,
    TradingDecisionEvent,
)


@pytest.mark.asyncio
async def test_decision_publisher_emits_buy_decision_from_retest_signal() -> None:
    bus = create_event_bus()
    set_event_bus(bus)
    await bus.start(num_workers=1)

    try:
        publisher = DecisionPublisher(
            account_balance=Decimal(10_000),
            risk_per_trade=Decimal("0.01"),
        )
        await publisher.start()

        decisions: list[TradingDecisionEvent] = []
        got_event = asyncio.Event()

        async def on_decision(event: TradingDecisionEvent) -> None:
            decisions.append(event)
            got_event.set()

        await bus.subscribe(
            subscriber_id="test_decision_capture",
            handler=on_decision,
            event_types=[EventType.TRADING_DECISION],
        )

        signal = RetestSignal(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            level_price=Decimal(100),
            direction="BUY",
            stop_loss=Decimal(99),
            take_profit=Decimal("101.5"),
            retest_type="zone_retest",
            success_probability=Decimal("0.8"),
            volume_confirmation=True,
            confluence_factors=["bos_confirmation"],
        )
        await bus.publish(
            RetestSignalEvent(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                signal=signal,
            ),
        )

        await asyncio.wait_for(got_event.wait(), timeout=1.0)

        assert len(decisions) == 1
        decision_event = decisions[0]
        assert decision_event.symbol == "BTCUSDT"
        assert decision_event.timeframe == TimeFrame.M15
        assert decision_event.decision.action == "BUY"
        assert decision_event.decision.entry_price == Decimal(100)
        assert decision_event.decision.stop_loss == Decimal(99)
        assert decision_event.decision.take_profit == Decimal("101.5")
        assert decision_event.decision.quantity == Decimal(100)
        assert decision_event.metadata["signal_id"] == str(signal.signal_id)
    finally:
        await bus.stop()
