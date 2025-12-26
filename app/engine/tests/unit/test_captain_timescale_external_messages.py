"""
Unit tests for TimescaleDBAdapter external Captain ingestion tables.
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
async def test_upsert_external_telegram_message_uses_on_conflict_upsert() -> None:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )

    fake_conn = _FakeConn()
    adapter.get_write_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment]

    await adapter.upsert_external_telegram_message(
        source="captain",
        chat_id=2079536184,
        message_id=123,
        grouped_id=None,
        timestamp=datetime(2025, 12, 26, 8, 0, tzinfo=UTC),
        text="📈สัญญาณ : SELL",
        has_photo=True,
        photo_path="snapshots/captain/2079536184/123.jpg",
        raw_json={"k": "v"},
    )

    assert fake_conn.execute_calls, "expected at least one execute call"
    sql, args = fake_conn.execute_calls[0]
    assert "INSERT INTO external_telegram_messages" in sql
    assert "ON CONFLICT" in sql
    assert args[0] == "captain"
    assert args[1] == 2079536184
    assert args[2] == 123

