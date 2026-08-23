from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter


class _FakeConn:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.row: dict[str, object] | None = None
        self.execute_result = "UPDATE 1"
        self.execute_results: list[str] = []
        self.transaction_entries = 0
        self.transaction_exit_error: type[BaseException] | None = None

    async def execute(self, sql: str, *args: object) -> str:
        self.execute_calls.append((sql, args))
        if self.execute_results:
            return self.execute_results.pop(0)
        return self.execute_result

    async def fetchrow(self, sql: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls.append((sql, args))
        return self.row

    def transaction(self) -> _TransactionContext:
        return _TransactionContext(self)


class _TransactionContext:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> None:
        self.conn.transaction_entries += 1

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: object,
        _tb: object,
    ) -> bool:
        self.conn.transaction_exit_error = exc_type
        return False


class _ConnectionContext:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self.conn

    async def __aexit__(self, _exc_type: object, _exc: object, _tb: object) -> bool:
        return False


def _adapter(conn: _FakeConn) -> TimescaleDBAdapter:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )
    adapter.get_connection = lambda: _ConnectionContext(conn)  # type: ignore[assignment, return-value]
    adapter.get_write_connection = lambda: _ConnectionContext(conn)  # type: ignore[assignment, return-value]
    return adapter


def _intent() -> dict[str, Any]:
    return {
        "idempotency_key": "signal-123",
        "decision_id": "00000000-0000-0000-0000-000000000123",
        "signal_id": "signal-123",
        "venue": "SPOT",
        "symbol": "BTCUSDT",
        "request_payload": {"symbol": "BTCUSDT", "quantity": "0.001"},
        "state": "PREPARED",
    }


@pytest.mark.asyncio
async def test_incomplete_execution_intent_outside_venue_is_fail_closed() -> None:
    conn = _FakeConn()
    conn.row = {"has_incomplete_intent": True}
    adapter = _adapter(conn)

    assert await adapter.has_incomplete_execution_intent_outside_venue("USD_M") is True

    sql, args = conn.fetchrow_calls[0]
    assert "venue <> $1" in sql
    assert "state = ANY($2::text[])" in sql
    assert args == ("USD_M", ["SUBMITTING", "AMBIGUOUS"])


@pytest.mark.asyncio
async def test_prepare_execution_intent_accepts_only_matching_prepared_replay() -> None:
    conn = _FakeConn()
    adapter = _adapter(conn)
    intent = _intent()

    conn.row = {"request_hash": "wrong", "state": "PREPARED"}
    assert await adapter.prepare_execution_intent(intent) is False

    inserted_hash = conn.execute_calls[0][1][5]
    conn.row = {"request_hash": inserted_hash, "state": "PREPARED"}
    assert await adapter.prepare_execution_intent(intent) is True

    for recoverable_state in ("SUBMITTING", "AMBIGUOUS"):
        conn.row = {"request_hash": inserted_hash, "state": recoverable_state}
        assert await adapter.prepare_execution_intent(intent) is True


@pytest.mark.asyncio
async def test_get_execution_intent_for_request_accepts_matching_ambiguous() -> None:
    conn = _FakeConn()
    adapter = _adapter(conn)
    request_payload = {"quantity": "0.001", "symbol": "BTCUSDT"}
    request_hash = hashlib.sha256(
        json.dumps(request_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    conn.row = {
        "request_hash": request_hash,
        "request_payload": request_payload,
        "response_payload": None,
        "state": "AMBIGUOUS",
    }

    result = await adapter.get_execution_intent_for_request(
        "signal-123",
        venue="SPOT",
        request_payload=request_payload,
    )

    assert result == {
        "request_payload": request_payload,
        "response_payload": None,
        "state": "AMBIGUOUS",
    }


@pytest.mark.asyncio
async def test_get_execution_intent_for_request_rejects_hash_conflict() -> None:
    conn = _FakeConn()
    adapter = _adapter(conn)
    conn.row = {
        "request_hash": "0" * 64,
        "request_payload": {"quantity": "0.002", "symbol": "BTCUSDT"},
        "response_payload": None,
        "state": "AMBIGUOUS",
    }

    with pytest.raises(RuntimeError, match="request hash"):
        await adapter.get_execution_intent_for_request(
            "signal-123",
            venue="SPOT",
            request_payload={"quantity": "0.001", "symbol": "BTCUSDT"},
        )


@pytest.mark.asyncio
async def test_transition_execution_intent_uses_guarded_state_update() -> None:
    conn = _FakeConn()
    adapter = _adapter(conn)

    assert await adapter.transition_execution_intent(
        "signal-123",
        "ACKNOWLEDGED",
        venue="SPOT",
        response_payload={"bracket_order_id": "bracket-1"},
    )

    sql, args = conn.execute_calls[0]
    assert "state = ANY" in sql
    assert args[2] == "ACKNOWLEDGED"
    assert args[5] == ["SUBMITTING"]


@pytest.mark.asyncio
async def test_commit_execution_ack_uses_one_transaction() -> None:
    conn = _FakeConn()
    adapter = _adapter(conn)
    order_row = {
        "client_order_id": "signal-123_entry",
        "venue": "SPOT",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "0.001",
        "price": "50000",
        "status": "NEW",
    }

    assert await adapter.commit_execution_ack(
        "signal-123",
        venue="SPOT",
        response_payload={"bracket_order_id": "bracket-1"},
        order_rows=[order_row],
        deliveries=[
            {"delivery_kind": "SNAPSHOT", "delivery_payload": {"signalId": "signal-123"}},
            {
                "delivery_kind": "ORDER_PLACED",
                "delivery_payload": {"event_type": "order_placed"},
            },
        ],
    )

    assert conn.transaction_entries == 1
    assert conn.transaction_exit_error is None
    sql_statements = [sql for sql, _ in conn.execute_calls]
    assert any("INSERT INTO orders" in sql for sql in sql_statements)
    assert any(
        "UPDATE execution_intents" in sql and "state = 'ACKNOWLEDGED'" in sql
        for sql in sql_statements
    )
    assert sum("INSERT INTO execution_success_deliveries" in sql for sql in sql_statements) == 2


@pytest.mark.asyncio
async def test_commit_execution_ack_rolls_back_when_guard_rejects_state() -> None:
    conn = _FakeConn()
    conn.execute_results = ["INSERT 0 1", "UPDATE 0"]
    adapter = _adapter(conn)
    order_row = {
        "client_order_id": "signal-123_entry",
        "venue": "SPOT",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "0.001",
        "price": "50000",
        "status": "NEW",
    }

    with pytest.raises(RuntimeError, match="SUBMITTING"):
        await adapter.commit_execution_ack(
            "signal-123",
            venue="SPOT",
            response_payload={"bracket_order_id": "bracket-1"},
            order_rows=[order_row],
            deliveries=[
                {
                    "delivery_kind": "ORDER_PLACED",
                    "delivery_payload": {"event_type": "order_placed"},
                },
            ],
        )

    assert conn.transaction_entries == 1
    assert conn.transaction_exit_error is RuntimeError
    assert not any(
        "INSERT INTO execution_success_deliveries" in sql for sql, _ in conn.execute_calls
    )


@pytest.mark.asyncio
async def test_claim_execution_success_delivery_enforces_snapshot_first() -> None:
    conn = _FakeConn()
    conn.row = {
        "delivery_kind": "SNAPSHOT",
        "lease_token": "lease-123",
        "delivery_payload": {"signalId": "signal-123"},
    }
    adapter = _adapter(conn)

    claim = await adapter.claim_execution_success_delivery(
        "signal-123",
        venue="SPOT",
    )

    assert claim == {
        "delivery_kind": "SNAPSHOT",
        "lease_token": "lease-123",
        "delivery_payload": {"signalId": "signal-123"},
    }
    sql, _ = conn.fetchrow_calls[0]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "SNAPSHOT" in sql
    assert "ORDER_PLACED" in sql
    assert "NOT EXISTS" in sql


@pytest.mark.asyncio
async def test_delivery_completion_requires_matching_lease() -> None:
    conn = _FakeConn()
    conn.execute_result = "UPDATE 0"
    adapter = _adapter(conn)

    with pytest.raises(RuntimeError, match="lease"):
        await adapter.complete_execution_success_delivery(
            "signal-123",
            venue="SPOT",
            delivery_kind="ORDER_PLACED",
            lease_token="stale-lease",
        )


@pytest.mark.asyncio
async def test_transition_execution_intent_reclaims_ambiguous_for_same_key_replay() -> None:
    conn = _FakeConn()
    adapter = _adapter(conn)

    assert await adapter.transition_execution_intent("signal-123", "SUBMITTING", venue="SPOT")

    _, args = conn.execute_calls[0]
    assert args[5] == ["PREPARED", "SUBMITTING", "AMBIGUOUS"]
