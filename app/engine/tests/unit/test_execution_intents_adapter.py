from __future__ import annotations

from typing import Any

import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter


class _FakeConn:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.row: dict[str, object] | None = None
        self.execute_result = "UPDATE 1"

    async def execute(self, sql: str, *args: object) -> str:
        self.execute_calls.append((sql, args))
        return self.execute_result

    async def fetchrow(self, _sql: str, *_args: object) -> dict[str, object] | None:
        return self.row


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
async def test_transition_execution_intent_reclaims_ambiguous_for_same_key_replay() -> None:
    conn = _FakeConn()
    adapter = _adapter(conn)

    assert await adapter.transition_execution_intent("signal-123", "SUBMITTING", venue="SPOT")

    _, args = conn.execute_calls[0]
    assert args[5] == ["PREPARED", "SUBMITTING", "AMBIGUOUS"]
