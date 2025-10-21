"""
Subscription status tests for DI EventBus (circuit breaker state).
"""

import asyncio
import pytest
from datetime import datetime

from app.engine.core.event_bus_factory import EventBusFactory, EventBusConfig
from app.engine.models import BaseEvent, EventType
from app.engine.resilience.thread_safe_circuit_breaker import CircuitBreakerState


@pytest.mark.asyncio
async def test_subscription_status_includes_circuit_breaker_state() -> None:
    factory = EventBusFactory()
    config = EventBusConfig(
        max_queue_size=50,
        num_workers=1,
        dead_letter_queue_size=5,
        slow_event_warning_threshold_ms=100,
        processing_config={"failure_threshold": 2},
    )
    bus = factory.create_with_config(config)

    async def failing(_):  # noqa: ANN001
        raise RuntimeError("boom")

    await bus.start()
    try:
        sub_id = await bus.subscribe("failer", failing, [EventType.CANDLE_UPDATE])
        # Cause enough failures to trip default threshold (5)
        for _ in range(10):
            evt = BaseEvent(event_type=EventType.CANDLE_UPDATE, timestamp=datetime.utcnow(), symbol="BTCUSDT")
            await bus.publish(evt)
            await asyncio.sleep(0.03)

        # Give worker time to update CB
        await asyncio.sleep(0.4)

        status = await bus.get_subscription_status(sub_id)
        assert status is not None
        assert status["subscription_id"] == sub_id
        assert status["circuit_breaker_state"] == CircuitBreakerState.OPEN.name
    finally:
        await bus.stop()
