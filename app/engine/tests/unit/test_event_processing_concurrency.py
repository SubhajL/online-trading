"""
Tests for concurrent per-event subscription processing in EventProcessor.

Covers:
- Parallel handlers reduce total processing time versus sequential.
- Per-handler timeout is enforced without blocking other handlers.
- Errors are aggregated across handlers while successes are counted.
"""

import asyncio
from datetime import datetime
from decimal import Decimal

import pytest

from app.engine.core.event_processor import (
    EventProcessor,
    EventProcessingConfig,
)
from app.engine.core.subscription_manager import EventSubscription
from app.engine.models import BaseEvent, EventType


def make_event(symbol: str = "BTCUSDT") -> BaseEvent:
    return BaseEvent(
        event_type=EventType.CANDLE_UPDATE,
        timestamp=datetime.utcnow(),
        symbol=symbol,
    )


def make_subscription(subscriber_id: str, handler, priority: int = 0) -> EventSubscription:
    return EventSubscription(
        subscription_id=f"sub-{subscriber_id}",
        subscriber_id=subscriber_id,
        handler=handler,
        event_types=None,
        priority=priority,
        max_retries=0,
    )


@pytest.mark.asyncio
async def test_parallel_handlers_reduce_total_time() -> None:
    # Handlers that each take ~50ms
    async def h1(event):
        await asyncio.sleep(0.05)

    async def h2(event):
        await asyncio.sleep(0.05)

    async def h3(event):
        await asyncio.sleep(0.05)

    # Configure high concurrency to allow parallel execution
    processor = EventProcessor(
        EventProcessingConfig(max_processing_time_seconds=1.0, max_concurrent_handlers=10)
    )
    subs = [
        make_subscription("h1", h1, priority=5),
        make_subscription("h2", h2, priority=5),
        make_subscription("h3", h3, priority=5),
    ]

    event = make_event()

    start = asyncio.get_event_loop().time()
    result = await processor.process_event(event, subs)
    elapsed = asyncio.get_event_loop().time() - start

    # If sequential, ~0.15s; if parallel, close to ~0.05s (+ small overhead)
    assert result.successful_handlers == 3
    assert result.failed_handlers == 0
    assert elapsed < 0.12


@pytest.mark.asyncio
async def test_per_handler_timeout_is_enforced() -> None:
    async def slow(event):
        await asyncio.sleep(0.2)

    async def fast(event):
        await asyncio.sleep(0.01)

    config = EventProcessingConfig(
        max_processing_time_seconds=0.05,  # 50ms timeout
        max_concurrent_handlers=10,
    )
    processor = EventProcessor(config)
    subs = [
        make_subscription("slow", slow, priority=5),
        make_subscription("fast", fast, priority=5),
    ]

    event = make_event()
    result = await processor.process_event(event, subs)

    # One succeeds, one times out
    assert result.successful_handlers == 1
    assert result.failed_handlers == 1
    assert any(e.error_type in ("TimeoutError", "asyncio.TimeoutError") for e in result.errors)


@pytest.mark.asyncio
async def test_errors_are_aggregated_across_handlers() -> None:
    async def ok(event):
        return 42

    async def boom(event):
        raise RuntimeError("boom")

    processor = EventProcessor(
        EventProcessingConfig(max_processing_time_seconds=1.0, max_concurrent_handlers=10)
    )
    subs = [
        make_subscription("ok", ok, priority=5),
        make_subscription("boom", boom, priority=5),
    ]

    event = make_event()
    result = await processor.process_event(event, subs)

    assert result.successful_handlers == 1
    assert result.failed_handlers == 1
    assert len(result.errors) == 1
    assert result.errors[0].error_type == "RuntimeError"
