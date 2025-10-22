import asyncio
from contextlib import asynccontextmanager

import pytest

from app.engine.bus import EventBus
from app.engine.core.event_bus_factory import EventBusConfig
from app.engine.core.event_processor import EventProcessingResult, EventProcessingStats
from app.engine.models import BaseEvent, EventType


class FakeSubMgr:
    async def add_subscription(self, *args, **kwargs) -> str:  # noqa: ANN001
        return "sub-1"

    async def remove_subscription(self, subscription_id: str) -> bool:
        return True

    async def get_subscriptions_for_event(self, event_type: EventType):  # noqa: ANN001
        return []

    async def get_subscription_count(self) -> int:
        return 0

    async def get_active_subscription_count(self) -> int:
        return 0

    async def record_subscription_failure(self, subscription_id: str, error_message: str) -> None:
        return None

    async def record_subscription_success(self, subscription_id: str) -> None:
        return None


class FakeProcessor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def process_event(self, event, subscriptions):  # noqa: ANN001
        self.calls.append("process")
        return EventProcessingResult(
            event_id=event.event_id,
            successful_handlers=1,
            failed_handlers=0,
            errors=[],
            processing_time=0.0,
        )

    async def get_stats(self) -> EventProcessingStats:
        return EventProcessingStats()

    async def reset_stats(self) -> None:
        return None


class FakeObs:
    def __init__(self) -> None:
        self.metrics_calls: list[tuple[int, float]] = []
        self.trace_calls: list[tuple[str, dict]] = []

    def update_queue_metrics(self, queue_size: int, processing_lag: float) -> None:
        self.metrics_calls.append((queue_size, processing_lag))

    @asynccontextmanager
    async def trace_operation(self, name: str, attributes: dict | None = None, record_metrics: bool = True):
        self.trace_calls.append((name, attributes or {}))
        yield None


def _make_event() -> BaseEvent:
    return BaseEvent(
        event_type=EventType.CANDLE_UPDATE,
        timestamp=__import__("datetime").datetime.utcnow(),
        symbol="BTCUSDT",
    )


@pytest.mark.asyncio
async def test_process_one_event_updates_queue_metrics(monkeypatch):
    # Arrange bus with fakes
    bus = EventBus(FakeSubMgr(), FakeProcessor(), EventBusConfig(num_workers=1))

    # Fake observability
    obs = FakeObs()
    import app.engine.core.observability as obs_mod

    monkeypatch.setattr(obs_mod, "get_observability", lambda: obs)

    # Patch processing method to avoid deeper deps
    async def fake_process(_event):  # noqa: ANN001
        return EventProcessingResult(
            event_id=_event.event_id,
            successful_handlers=1,
            failed_handlers=0,
            errors=[],
            processing_time=0.001,
        )

    monkeypatch.setattr(bus, "_process_event_with_subscriptions", fake_process)

    # Event with prior publish time to create positive lag
    ev = _make_event()
    ev.metadata["published_at"] = asyncio.get_event_loop().time() - 0.01
    ev.metadata["priority"] = 3

    # Act
    result = await bus._process_one_event(ev)  # type: ignore[attr-defined]

    # Assert
    assert result.successful_handlers == 1
    assert len(obs.metrics_calls) == 1
    qs, lag = obs.metrics_calls[0]
    assert isinstance(qs, int)
    assert lag >= 0
    assert obs.trace_calls and obs.trace_calls[0][0] == "event.process"
    attrs = obs.trace_calls[0][1]
    assert attrs.get("event_type") == "CANDLE_UPDATE"
    assert attrs.get("symbol") == "BTCUSDT"
    assert attrs.get("priority") == 3


@pytest.mark.asyncio
async def test_worker_loop_uses_process_one_event_once(monkeypatch):
    bus = EventBus(FakeSubMgr(), FakeProcessor(), EventBusConfig(num_workers=1))
    bus._running = True  # Start loop

    # Enqueue one event using publish (sets published_at/priority)
    ev = _make_event()
    await bus.publish(ev)

    calls: list[BaseEvent] = []

    async def fake_process_one(event: BaseEvent):
        calls.append(event)
        # Stop loop after first event
        bus._running = False
        return EventProcessingResult(
            event_id=event.event_id,
            successful_handlers=1,
            failed_handlers=0,
            errors=[],
            processing_time=0.0,
        )

    monkeypatch.setattr(bus, "_process_one_event", fake_process_one)

    # Act
    task = asyncio.create_task(bus._worker_loop("w0"))
    await asyncio.wait_for(task, timeout=1.0)

    # Assert
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_slow_event_warning_still_logs(monkeypatch, caplog):
    bus = EventBus(FakeSubMgr(), FakeProcessor(), EventBusConfig(num_workers=1, slow_event_warning_threshold_ms=1))
    bus._running = True

    ev = _make_event()
    await bus.publish(ev)

    async def slow_process_one(event: BaseEvent):  # noqa: ARG001
        await asyncio.sleep(0.02)
        bus._running = False
        return EventProcessingResult(
            event_id=ev.event_id,
            successful_handlers=1,
            failed_handlers=0,
            errors=[],
            processing_time=0.02,
        )

    monkeypatch.setattr(bus, "_process_one_event", slow_process_one)

    caplog.set_level("WARNING")
    await bus._worker_loop("w1")

    assert any("Slow event processing" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_dlq_policy_unchanged(monkeypatch):
    bus = EventBus(FakeSubMgr(), FakeProcessor(), EventBusConfig(num_workers=1, dlq_on_any_failure=False))
    bus._running = True

    ev = _make_event()
    await bus.publish(ev)

    async def fail_process_one(event: BaseEvent):  # noqa: ARG001
        bus._running = False
        return EventProcessingResult(
            event_id=ev.event_id,
            successful_handlers=0,
            failed_handlers=1,
            errors=[],
            processing_time=0.0,
        )

    monkeypatch.setattr(bus, "_process_one_event", fail_process_one)
    await bus._worker_loop("w2")

    dlq = await bus.get_dead_letter_events()
    assert len(dlq) == 1
