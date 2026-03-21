from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.engine.execution.order_update_correlation import OrderUpdateCorrelationStore
from app.engine.main import (
    _order_update_db_hydration_enabled_from_env,
    ingest_order_update,
    services,
)
from app.engine.models import OrderUpdateEvent


class _CapturingBus:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish(self, event: object, priority: int = 0) -> bool:
        _ = priority
        self.published.append(event)
        return True


class _CapturingDB:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.lookup_row: dict[str, object] | None = None
        self.lookup_calls: list[tuple[str, str | None]] = []
        self.upsert_result = True

    async def upsert_order(self, order: dict[str, object]) -> bool:
        self.rows.append(order)
        return self.upsert_result

    async def get_order_by_client_order_id(
        self,
        *,
        client_order_id: str,
        venue: str | None = None,
    ) -> dict[str, object] | None:
        self.lookup_calls.append((client_order_id, venue))
        return self.lookup_row


@pytest.fixture(autouse=True)
def _reset_order_update_hydration_flag_cache() -> None:
    _order_update_db_hydration_enabled_from_env.cache_clear()
    yield
    _order_update_db_hydration_enabled_from_env.cache_clear()


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


@pytest.mark.asyncio
async def test_ingest_order_update_persists_to_db_when_database_available() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        db = _CapturingDB()
        services["event_bus"] = bus
        services["database"] = db

        now = datetime.now(UTC).replace(microsecond=0)
        payload = {
            "event_type": "order_update.v1",
            "venue": "SPOT",
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
        assert len(db.rows) == 1
        assert db.rows[0]["venue"] == "SPOT"
        assert db.rows[0]["client_order_id"] == "abc_entry"
        assert db.rows[0]["symbol"] == "BTCUSDT"
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_ingest_order_update_persists_reconciled_spot_average_fill_price() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        db = _CapturingDB()
        services["event_bus"] = bus
        services["database"] = db

        now = datetime.now(UTC).replace(microsecond=0)
        payload = {
            "event_type": "order_update.v1",
            "venue": "SPOT",
            "symbol": "BTCUSDT",
            "order_id": 123,
            "client_order_id": "abc_entry",
            "status": "FILLED",
            "side": "BUY",
            "order_type": "LIMIT",
            "price": "50020.00",
            "quantity": "0.02",
            "executed_qty": "0.02",
            "update_time": now.isoformat(),
        }

        resp = await ingest_order_update(payload)

        assert resp == {"status": "ok"}
        assert len(db.rows) == 1
        assert db.rows[0]["average_fill_price"] == Decimal("50020.00")
        assert db.rows[0]["filled_quantity"] == Decimal("0.02")
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_ingest_order_update_hydrates_metadata_from_db_when_store_misses() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        db = _CapturingDB()
        decision_id = uuid4()
        db.lookup_row = {
            "venue": "SPOT",
            "decision_id": decision_id,
            "signal_id": "sig-1",
            "timeframe": "15m",
            "zone": {"zone_id": "zone-1", "zone_type": "FAIR_VALUE_GAP"},
        }

        services["event_bus"] = bus
        services["database"] = db
        services["order_update_correlation_store"] = OrderUpdateCorrelationStore(ttl_seconds=3600)

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
        assert db.lookup_calls == [("abc_entry", None)]
        assert len(bus.published) == 1

        event = bus.published[0]
        assert isinstance(event, OrderUpdateEvent)
        assert event.metadata["decision_id"] == str(decision_id)
        assert event.metadata["signal_id"] == "sig-1"
        assert event.metadata["timeframe"] == "15m"
        assert event.metadata["zone"] == {"zone_id": "zone-1", "zone_type": "FAIR_VALUE_GAP"}
        assert event.metadata["venue"] == "SPOT"
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_ingest_order_update_persists_db_hydrated_provenance() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        db = _CapturingDB()
        decision_id = uuid4()
        db.lookup_row = {
            "venue": "SPOT",
            "decision_id": decision_id,
            "signal_id": "sig-1",
            "timeframe": "15m",
            "zone": {"zone_id": "zone-1", "zone_type": "FAIR_VALUE_GAP"},
        }

        services["event_bus"] = bus
        services["database"] = db
        services["order_update_correlation_store"] = OrderUpdateCorrelationStore(ttl_seconds=3600)

        now = datetime.now(UTC).replace(microsecond=0)
        payload = {
            "event_type": "order_update.v1",
            "symbol": "BTCUSDT",
            "order_id": 123,
            "client_order_id": "abc_entry",
            "status": "FILLED",
            "side": "BUY",
            "order_type": "LIMIT",
            "price": "50000.00",
            "quantity": "0.01",
            "executed_qty": "0.01",
            "update_time": now.isoformat(),
        }

        resp = await ingest_order_update(payload)
        assert resp == {"status": "ok"}
        assert len(db.rows) == 1
        assert db.rows[0]["venue"] == "SPOT"
        assert db.rows[0]["decision_id"] == str(decision_id)
        assert db.rows[0]["signal_id"] == "sig-1"
        assert db.rows[0]["timeframe"] == "15m"
        assert db.rows[0]["zone"] == {"zone_id": "zone-1", "zone_type": "FAIR_VALUE_GAP"}
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_ingest_order_update_deletes_terminal_correlation_after_successful_persist() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        db = _CapturingDB()
        store = OrderUpdateCorrelationStore(ttl_seconds=3600)
        await store.register(
            client_order_id="abc_entry",
            metadata={"decision_source": "retest_decision_publisher", "signal_id": "sig-1"},
        )

        services["event_bus"] = bus
        services["database"] = db
        services["order_update_correlation_store"] = store

        now = datetime.now(UTC).replace(microsecond=0)
        payload = {
            "event_type": "order_update.v1",
            "venue": "SPOT",
            "symbol": "BTCUSDT",
            "order_id": 123,
            "client_order_id": "abc_entry",
            "status": "FILLED",
            "side": "BUY",
            "order_type": "LIMIT",
            "price": "50000.00",
            "quantity": "0.01",
            "executed_qty": "0.01",
            "update_time": now.isoformat(),
        }

        resp = await ingest_order_update(payload)
        assert resp == {"status": "ok"}
        assert await store.get(client_order_id="abc_entry") is None
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_ingest_order_update_keeps_terminal_correlation_when_persist_fails() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        db = _CapturingDB()
        db.upsert_result = False
        store = OrderUpdateCorrelationStore(ttl_seconds=3600)
        await store.register(
            client_order_id="abc_entry",
            metadata={"decision_source": "retest_decision_publisher", "signal_id": "sig-1"},
        )

        services["event_bus"] = bus
        services["database"] = db
        services["order_update_correlation_store"] = store

        now = datetime.now(UTC).replace(microsecond=0)
        payload = {
            "event_type": "order_update.v1",
            "venue": "SPOT",
            "symbol": "BTCUSDT",
            "order_id": 123,
            "client_order_id": "abc_entry",
            "status": "FILLED",
            "side": "BUY",
            "order_type": "LIMIT",
            "price": "50000.00",
            "quantity": "0.01",
            "executed_qty": "0.01",
            "update_time": now.isoformat(),
        }

        resp = await ingest_order_update(payload)
        assert resp == {"status": "ok"}
        corr = await store.get(client_order_id="abc_entry")
        assert corr is not None
        assert corr.metadata["signal_id"] == "sig-1"
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_ingest_order_update_skips_db_hydration_when_flag_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = dict(services)
    services.clear()
    monkeypatch.setenv("ORDER_UPDATE_DB_HYDRATION_ENABLED", "0")
    _order_update_db_hydration_enabled_from_env.cache_clear()
    try:
        bus = _CapturingBus()
        db = _CapturingDB()
        db.lookup_row = {
            "venue": "SPOT",
            "decision_id": uuid4(),
            "signal_id": "sig-1",
            "timeframe": "15m",
            "zone": {"zone_id": "zone-1", "zone_type": "FAIR_VALUE_GAP"},
        }
        services["event_bus"] = bus
        services["database"] = db
        services["order_update_correlation_store"] = OrderUpdateCorrelationStore(ttl_seconds=3600)

        now = datetime.now(UTC).replace(microsecond=0)
        payload = {
            "event_type": "order_update.v1",
            "venue": "SPOT",
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
        assert db.lookup_calls == []
        assert db.rows == []
        assert len(bus.published) == 1

        event = bus.published[0]
        assert isinstance(event, OrderUpdateEvent)
        assert event.metadata == {}
    finally:
        _order_update_db_hydration_enabled_from_env.cache_clear()
        services.clear()
        services.update(previous)


def test_order_update_db_hydration_flag_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _order_update_db_hydration_enabled_from_env.cache_clear()
    monkeypatch.setenv("ORDER_UPDATE_DB_HYDRATION_ENABLED", "0")

    assert _order_update_db_hydration_enabled_from_env() is False

    monkeypatch.setenv("ORDER_UPDATE_DB_HYDRATION_ENABLED", "1")
    assert _order_update_db_hydration_enabled_from_env() is False

    _order_update_db_hydration_enabled_from_env.cache_clear()
    assert _order_update_db_hydration_enabled_from_env() is True
