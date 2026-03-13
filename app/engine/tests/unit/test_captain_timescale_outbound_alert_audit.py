"""
Unit tests for TimescaleDBAdapter outbound alert audit persistence.
"""

from datetime import UTC, datetime

import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter


class _FakeConn:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, sql: str, *args: object) -> None:  # noqa: D401
        self.execute_calls.append((sql, args))


class _FakePoolCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:  # noqa: D401
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: D401, ANN001
        return False


@pytest.mark.asyncio
async def test_insert_outbound_alert_audit_inserts_attempt_row() -> None:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )

    fake_conn = _FakeConn()
    adapter.get_write_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment, return-value]

    await adapter.insert_outbound_alert_audit(
        channel="telegram",
        alert_type="decision",
        delivery_method="text",
        status="sent",
        reason=None,
        chat_id="test-chat-id",
        dedup_key="decision:BTCUSDT:long:2025-01-26T10:00:00Z",
        telegram_message_id=321,
        message_text="Test outbound message",
        response_status=200,
        response_body='{"ok":true}',
        payload={"symbol": "BTCUSDT", "event_type": "order_update.v1"},
        attempted_at=datetime(2026, 3, 12, 8, 0, tzinfo=UTC),
    )

    assert fake_conn.execute_calls
    sql, args = fake_conn.execute_calls[0]
    assert "INSERT INTO outbound_alert_audit" in sql
    assert args[1] == "telegram"
    assert args[2] == "decision"
    assert args[3] == "text"
    assert args[4] == "sent"
    assert args[6] == "test-chat-id"
    assert args[8] == 321
