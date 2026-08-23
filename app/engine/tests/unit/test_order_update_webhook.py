from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.engine.execution.order_update_correlation import OrderUpdateCorrelationStore
from app.engine.execution.order_update_inbox import is_terminal_transition_allowed
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

    async def publish_and_wait(self, event: object, priority: int = 0) -> bool:
        return await self.publish(event, priority)


class _RejectingBus(_CapturingBus):
    async def publish_and_wait(self, event: object, priority: int = 0) -> bool:
        await super().publish_and_wait(event, priority)
        return False


class _QueueOnlyBus:
    async def publish(self, event: object, priority: int = 0) -> bool:
        _ = (event, priority)
        return True


class _CapturingDB:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.lookup_row: dict[str, object] | None = None
        self.lookup_calls: list[tuple[str, str | None]] = []
        self.upsert_result = True
        self.claim_result = "CLAIMED"
        self.claimed: list[dict[str, object]] = []
        self.completed: list[str] = []
        self.failed: list[tuple[str, str]] = []

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

    async def claim_order_update_inbox(self, **event: object) -> str:
        self.claimed.append(event)
        return self.claim_result

    async def complete_order_update_inbox(self, *, event_id: str) -> None:
        self.completed.append(event_id)

    async def fail_order_update_inbox(self, *, event_id: str, error_message: str) -> None:
        self.failed.append((event_id, error_message))


class _FailingCompletionDB(_CapturingDB):
    async def complete_order_update_inbox(self, *, event_id: str) -> None:
        raise RuntimeError("completion failed")


def _order_update_envelope(payload: dict[str, object], *, sequence: int = 1) -> dict[str, object]:
    return {
        "event_id": str(uuid4()),
        "aggregate_id": "SPOT:abc_entry",
        "sequence": sequence,
        "event_version": 1,
        "event_type": "order_update.v1",
        "occurred_at": datetime.now(UTC).isoformat(),
        "payload": payload,
    }


def _valid_order_update_payload() -> dict[str, object]:
    return {
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
        "update_time": datetime.now(UTC).isoformat(),
    }


@pytest.mark.parametrize(
    ("prior_status", "current_status", "expected"),
    [
        (
            prior,
            current,
            prior == current
            or (prior in {"CANCELED", "CANCELLED", "EXPIRED"} and current == "FILLED"),
        )
        for prior in ("FILLED", "REJECTED", "CANCELED", "CANCELLED", "EXPIRED")
        for current in (
            "NEW",
            "PARTIALLY_FILLED",
            "FILLED",
            "REJECTED",
            "CANCELED",
            "CANCELLED",
            "EXPIRED",
        )
    ],
)
def test_terminal_order_update_cannot_change_state(
    prior_status: str,
    current_status: str,
    expected: bool,
) -> None:
    prior_payload = {
        "status": prior_status,
        "quantity": "1",
        "executed_qty": "0.25",
        "update_time": "2026-03-21T20:05:00Z",
    }
    current_payload = {
        "status": current_status,
        "quantity": "1",
        "executed_qty": "1" if current_status == "FILLED" else "0.25",
        "update_time": "2026-03-21T20:06:00Z",
    }

    assert is_terminal_transition_allowed(prior_payload, current_payload) is expected


@pytest.mark.parametrize(
    "current_payload",
    [
        {
            "status": "FILLED",
            "quantity": "1",
            "executed_qty": "0.75",
            "update_time": "2026-03-21T20:06:00Z",
        },
        {
            "status": "FILLED",
            "quantity": "1",
            "executed_qty": "1",
            "update_time": "2026-03-21T20:04:00Z",
        },
        {
            "status": "FILLED",
            "quantity": "1",
            "executed_qty": "1",
            "update_time": None,
        },
    ],
)
def test_terminal_full_fill_upgrade_requires_complete_newer_observation(
    current_payload: dict[str, object],
) -> None:
    prior_payload = {
        "status": "CANCELED",
        "quantity": "1",
        "executed_qty": "0.25",
        "update_time": "2026-03-21T20:05:00Z",
    }

    assert is_terminal_transition_allowed(prior_payload, current_payload) is False


@pytest.mark.asyncio
async def test_envelope_aggregate_must_match_payload_before_inbox_claim() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        db = _CapturingDB()
        services.update(event_bus=bus, database=db)
        envelope = _order_update_envelope(_valid_order_update_payload())
        envelope["aggregate_id"] = "SPOT:different-order"

        with pytest.raises(HTTPException) as exc_info:
            await ingest_order_update(envelope)

        assert exc_info.value.status_code == 400
        assert db.claimed == []
        assert bus.published == []
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_duplicate_order_update_is_effectively_once() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        db = _CapturingDB()
        db.claim_result = "DUPLICATE"
        services.update(event_bus=bus, database=db)

        response = await ingest_order_update(_order_update_envelope(_valid_order_update_payload()))

        assert response == {"status": "duplicate"}
        assert bus.published == []
        assert db.rows == []
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_conflicting_duplicate_order_update_returns_conflict() -> None:
    previous = dict(services)
    services.clear()
    try:
        db = _CapturingDB()
        db.claim_result = "CONFLICT"
        services.update(event_bus=_CapturingBus(), database=db)

        with pytest.raises(HTTPException) as exc_info:
            await ingest_order_update(_order_update_envelope(_valid_order_update_payload()))

        assert exc_info.value.status_code == 409
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_sequence_gap_parks_later_update() -> None:
    previous = dict(services)
    services.clear()
    try:
        db = _CapturingDB()
        db.claim_result = "GAP"
        services.update(event_bus=_CapturingBus(), database=db)

        with pytest.raises(HTTPException) as exc_info:
            await ingest_order_update(
                _order_update_envelope(_valid_order_update_payload(), sequence=3)
            )

        assert exc_info.value.status_code == 425
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_order_update_envelope_completes_after_projection_and_publication() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        db = _CapturingDB()
        store = OrderUpdateCorrelationStore(ttl_seconds=3600)
        await store.register(
            client_order_id="abc_entry",
            metadata={"decision_id": "decision-1", "signal_id": "signal-1"},
        )
        services.update(
            event_bus=bus,
            database=db,
            order_update_correlation_store=store,
        )
        envelope = _order_update_envelope(_valid_order_update_payload())

        response = await ingest_order_update(envelope)

        assert response == {"status": "ok"}
        assert len(db.rows) == 1
        assert len(bus.published) == 1
        assert db.completed == [envelope["event_id"]]
        assert db.failed == []
        assert bus.published[0].metadata["order_update_event_id"] == envelope["event_id"]
        assert bus.published[0].metadata["decision_id"] == "decision-1"
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_inbox_completion_failure_keeps_stable_bus_event_identity() -> None:
    previous = dict(services)
    services.clear()
    try:
        bus = _CapturingBus()
        db = _FailingCompletionDB()
        services.update(event_bus=bus, database=db)
        envelope = _order_update_envelope(_valid_order_update_payload())

        with pytest.raises(HTTPException) as exc_info:
            await ingest_order_update(envelope)

        assert exc_info.value.status_code == 503
        assert len(bus.published) == 1
        assert str(bus.published[0].event_id) == envelope["event_id"]
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_order_update_bus_rejection_keeps_inbox_retryable() -> None:
    previous = dict(services)
    services.clear()
    try:
        db = _CapturingDB()
        envelope = _order_update_envelope(_valid_order_update_payload())
        services.update(event_bus=_RejectingBus(), database=db)

        with pytest.raises(HTTPException) as exc_info:
            await ingest_order_update(envelope)

        assert exc_info.value.status_code == 503
        assert db.completed == []
        assert db.failed and db.failed[0][0] == envelope["event_id"]
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_enveloped_order_update_requires_acknowledged_dispatch() -> None:
    previous = dict(services)
    services.clear()
    try:
        db = _CapturingDB()
        envelope = _order_update_envelope(_valid_order_update_payload())
        services.update(event_bus=_QueueOnlyBus(), database=db)

        with pytest.raises(HTTPException) as exc_info:
            await ingest_order_update(envelope)

        assert exc_info.value.status_code == 503
        assert db.completed == []
        assert db.failed == [(str(envelope["event_id"]), "acknowledged event dispatch unavailable")]
    finally:
        services.clear()
        services.update(previous)


@pytest.fixture(autouse=True)
def _reset_order_update_hydration_flag_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_LEGACY_ORDER_UPDATES", "true")
    _order_update_db_hydration_enabled_from_env.cache_clear()
    yield
    _order_update_db_hydration_enabled_from_env.cache_clear()


@pytest.mark.asyncio
async def test_legacy_order_update_is_rejected_when_durable_delivery_is_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ALLOW_LEGACY_ORDER_UPDATES", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await ingest_order_update(_valid_order_update_payload())

    assert exc_info.value.status_code == 400


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
async def test_stop_market_update_persists_canonical_stop_loss_type() -> None:
    previous = dict(services)
    services.clear()
    try:
        db = _CapturingDB()
        bus = _CapturingBus()
        payload = _valid_order_update_payload()
        payload["order_type"] = "STOP_MARKET"
        payload["price"] = "49000.00"
        services.update(event_bus=bus, database=db)

        response = await ingest_order_update(payload)

        assert response == {"status": "ok"}
        assert len(db.rows) == 1
        assert {
            "type": db.rows[0]["type"],
            "price": db.rows[0]["price"],
            "stop_price": db.rows[0].get("stop_price"),
        } == {
            "type": "STOP_LOSS",
            "price": None,
            "stop_price": Decimal("49000.00"),
        }
        assert len(bus.published) == 1
        event = bus.published[0]
        assert isinstance(event, OrderUpdateEvent)
        assert {
            "order_type": event.update.order_type,
            "price": event.update.price,
            "stop_price": event.update.stop_price,
        } == {
            "order_type": "STOP_MARKET",
            "price": None,
            "stop_price": Decimal("49000.00"),
        }
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_spot_stop_limit_update_preserves_limit_and_trigger_prices() -> None:
    previous = dict(services)
    services.clear()
    try:
        db = _CapturingDB()
        bus = _CapturingBus()
        payload = _valid_order_update_payload()
        payload.update(
            venue="SPOT",
            order_type="STOP_LOSS_LIMIT",
            price="49000.00",
            stop_price="49500.00",
        )
        services.update(event_bus=bus, database=db)

        response = await ingest_order_update(payload)

        assert response == {"status": "ok"}
        assert len(db.rows) == 1
        assert {
            "type": db.rows[0]["type"],
            "price": db.rows[0]["price"],
            "stop_price": db.rows[0].get("stop_price"),
        } == {
            "type": "STOP_LOSS_LIMIT",
            "price": Decimal("49000.00"),
            "stop_price": Decimal("49500.00"),
        }
        assert len(bus.published) == 1
        event = bus.published[0]
        assert isinstance(event, OrderUpdateEvent)
        assert {
            "order_type": event.update.order_type,
            "price": event.update.price,
            "stop_price": event.update.stop_price,
        } == {
            "order_type": "STOP_LOSS_LIMIT",
            "price": Decimal("49000.00"),
            "stop_price": Decimal("49500.00"),
        }
    finally:
        services.clear()
        services.update(previous)


@pytest.mark.asyncio
async def test_market_update_persists_null_price() -> None:
    previous = dict(services)
    services.clear()
    try:
        db = _CapturingDB()
        bus = _CapturingBus()
        payload = _valid_order_update_payload()
        payload["order_type"] = "MARKET"
        payload["price"] = "0"
        services.update(event_bus=bus, database=db)

        response = await ingest_order_update(payload)

        assert response == {"status": "ok"}
        assert len(db.rows) == 1
        assert {
            "type": db.rows[0]["type"],
            "price": db.rows[0]["price"],
            "stop_price": db.rows[0].get("stop_price"),
        } == {
            "type": "MARKET",
            "price": None,
            "stop_price": None,
        }
        assert len(bus.published) == 1
        event = bus.published[0]
        assert isinstance(event, OrderUpdateEvent)
        assert {
            "order_type": event.update.order_type,
            "price": event.update.price,
            "stop_price": event.update.stop_price,
        } == {
            "order_type": "MARKET",
            "price": None,
            "stop_price": None,
        }
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
            "price": "50000.00",
            "quantity": "0.02",
            "executed_qty": "0.02",
            "average_fill_price": "50020.00",
            "update_time": now.isoformat(),
        }

        resp = await ingest_order_update(payload)

        assert resp == {"status": "ok"}
        assert len(db.rows) == 1
        assert db.rows[0]["price"] == Decimal("50000.00")
        assert db.rows[0]["average_fill_price"] == Decimal("50020.00")
        assert db.rows[0]["filled_quantity"] == Decimal("0.02")
        assert len(bus.published) == 1
        assert bus.published[0].update.average_fill_price == Decimal("50020.00")
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
