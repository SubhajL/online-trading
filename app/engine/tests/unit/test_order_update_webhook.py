from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.execution.order_update_correlation import OrderUpdateCorrelationStore
from app.engine.main import ingest_order_update, services
from app.engine.models import OrderUpdateEvent


class _CapturingBus:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish(self, event: object, priority: int = 0) -> bool:
        _ = priority
        self.published.append(event)
        return True


@pytest.mark.asyncio
async def test_ingest_order_update_attaches_metadata_when_correlated() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        store = OrderUpdateCorrelationStore(ttl_seconds=3600)
        await store.register(
            client_order_id="abc_entry",
            metadata={"decision_source": "retest_decision_publisher", "signal_id": "sig-1"},
        )

        services["event_bus"] = bus
        services["order_update_correlation_store"] = store

        now = datetime.now(UTC).replace(microsecond=0)
        payload = {
            "event_type": "order_update.v1",
            "symbol": "BTCUSDT",
            "order_id": 123,
            "client_order_id": "abc_entry",
            "status": "NEW",
            "side": "BUY",
            "order_type": "LIMIT",
            "price": "50000.00",
            "quantity": "0.01",
            "executed_qty": "0",
            "update_time": now.isoformat(),
        }

        resp = await ingest_order_update(payload)
        assert resp == {"status": "ok"}
        assert len(bus.published) == 1

        event = bus.published[0]
        assert isinstance(event, OrderUpdateEvent)
        assert event.metadata["decision_source"] == "retest_decision_publisher"
        assert event.metadata["signal_id"] == "sig-1"
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_ingest_order_update_has_empty_metadata_when_uncorrelated() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        services["event_bus"] = bus
        services["order_update_correlation_store"] = OrderUpdateCorrelationStore(ttl_seconds=3600)

        now = datetime.now(UTC).replace(microsecond=0)
        payload = {
            "event_type": "order_update.v1",
            "symbol": "BTCUSDT",
            "order_id": 123,
            "client_order_id": "unknown_entry",
            "status": "NEW",
            "side": "BUY",
            "order_type": "LIMIT",
            "price": "50000.00",
            "quantity": "0.01",
            "executed_qty": "0",
            "update_time": now.isoformat(),
        }

        resp = await ingest_order_update(payload)
        assert resp == {"status": "ok"}
        assert len(bus.published) == 1

        event = bus.published[0]
        assert isinstance(event, OrderUpdateEvent)
        assert event.metadata == {}
    finally:
        services.clear()
        services.update(previous)
