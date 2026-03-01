import asyncio
import pytest

from app.engine.core.event_processor import EventProcessor, EventProcessingConfig
from app.engine.core.subscription_manager import EventSubscription
from app.engine.models import BaseEvent, EventType, TimeFrame
from datetime import datetime


def _make_event() -> BaseEvent:
    return BaseEvent(
        event_type=EventType.CANDLE_UPDATE,
        timestamp=datetime.utcnow(),
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
    )


class _FakeBreaker:
    def __init__(self) -> None:
        self.allow_calls = 0
        self.success = 0
        self.failure = 0

    async def should_allow_request(self) -> bool:
        self.allow_calls += 1
        return True

    async def record_success(self) -> None:
        self.success += 1

    async def record_failure(self) -> None:
        self.failure += 1

    async def get_state(self):  # noqa: D401
        class S:
            name = "CLOSED"

        return S()


@pytest.mark.asyncio
async def test_circuit_breaker_precheck_and_success(monkeypatch):
    async def handler(_evt):  # noqa: ANN001
        return None

    sub = EventSubscription(
        subscription_id="s1",
        subscriber_id="worker",
        handler=handler,
        event_types={EventType.CANDLE_UPDATE},
        priority=0,
        max_retries=0,
    )

    processor = EventProcessor(EventProcessingConfig())
    br = _FakeBreaker()
    monkeypatch.setattr(processor, "_get_circuit_breaker", lambda _sid: asyncio.Future())
    # Make _get_circuit_breaker return a resolved future to br
    fut = processor._get_circuit_breaker("worker")
    # Manually set future result for lambda above (simplify)
    # Instead, patch method to regular coroutine
    async def _get_cb(_sid):
        return br

    monkeypatch.setattr(processor, "_get_circuit_breaker", _get_cb)

    evt = _make_event()
    result = await processor.process_event(evt, [sub])

    assert result.successful_handlers == 1
    assert br.allow_calls == 1
    assert br.success == 1
    assert br.failure == 0


@pytest.mark.asyncio
async def test_circuit_breaker_records_failure(monkeypatch):
    async def failing(_evt):  # noqa: ANN001
        raise RuntimeError("boom")

    sub = EventSubscription(
        subscription_id="s2",
        subscriber_id="worker2",
        handler=failing,
        event_types={EventType.CANDLE_UPDATE},
        priority=0,
        max_retries=0,
    )

    processor = EventProcessor(EventProcessingConfig())
    br = _FakeBreaker()

    async def _get_cb(_sid):
        return br

    monkeypatch.setattr(processor, "_get_circuit_breaker", _get_cb)

    evt = _make_event()
    result = await processor.process_event(evt, [sub])

    assert result.failed_handlers == 1
    assert br.allow_calls == 1
    assert br.failure == 1
