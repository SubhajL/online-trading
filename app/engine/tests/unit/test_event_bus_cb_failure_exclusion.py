"""An open circuit breaker must not count as a subscription failure.

The breaker owns recovery (half-open probes); recording CircuitBreakerOpen
results as failures raced the breaker and permanently deactivated the
subscription before it could recover. Such results are excluded from both
failure AND success recording (success would reset retry_count and mask
real pre-open failures).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.engine.bus import set_event_bus
from app.engine.core.event_bus_factory import EventBusConfig, EventBusFactory
from app.engine.core.event_processor import EventProcessingError, EventProcessingResult
from app.engine.models import ErrorEvent

SUB_ID = "sub-1"


def _make_bus():
    cfg = EventBusConfig(
        use_priority_queue=False,
        dlq_on_any_failure=False,
        num_workers=1,
        max_queue_size=100,
        dead_letter_queue_size=10,
    )
    return EventBusFactory().create_with_config(cfg)


def _make_event() -> ErrorEvent:
    return ErrorEvent(
        timestamp=datetime.now(UTC),
        component="test",
        error_type="probe",
        error_message="probe",
        symbol="BTCUSDT",
        metadata={},
    )


def _result_with(error_type: str) -> EventProcessingResult:
    event = _make_event()
    return EventProcessingResult(
        event_id=event.event_id,
        successful_handlers=0,
        failed_handlers=1,
        errors=[
            EventProcessingError(
                subscription_id=SUB_ID,
                subscriber_id="features",
                error_type=error_type,
                error_message=error_type,
            ),
        ],
        processing_time=0.001,
    )


@pytest.fixture(autouse=True)
def _bus_context():
    bus = _make_bus()
    set_event_bus(bus)
    yield bus
    set_event_bus(None)


async def _dispatch_with(bus, error_type: str) -> tuple[AsyncMock, AsyncMock]:
    bus._event_processor.process_event = AsyncMock(return_value=_result_with(error_type))
    fake_sub = type("FakeSub", (), {"subscription_id": SUB_ID})()
    bus._subscription_manager.get_subscriptions_for_event = AsyncMock(return_value=[fake_sub])
    failure = AsyncMock()
    success = AsyncMock()
    bus._subscription_manager.record_subscription_failure = failure
    bus._subscription_manager.record_subscription_success = success
    await bus._process_event_with_subscriptions(_make_event())
    return failure, success


class TestCircuitBreakerOpenExclusion:
    @pytest.mark.asyncio
    async def test_cb_open_does_not_record_failure(self, _bus_context) -> None:
        failure, _ = await _dispatch_with(_bus_context, "CircuitBreakerOpen")

        failure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cb_open_does_not_record_success_either(self, _bus_context) -> None:
        _, success = await _dispatch_with(_bus_context, "CircuitBreakerOpen")

        success.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_real_errors_still_recorded_as_failures(self, _bus_context) -> None:
        failure, success = await _dispatch_with(_bus_context, "RuntimeError")

        failure.assert_awaited_once()
        success.assert_not_awaited()
