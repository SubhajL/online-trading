"""
Unit tests for TimescaleDBAdapter external Telegram signal tables.
"""

import json
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
async def test_upsert_external_telegram_signal_uses_on_conflict_upsert() -> None:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )

    fake_conn = _FakeConn()
    adapter.get_write_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment, return-value]

    await adapter.upsert_external_telegram_signal(
        source="captain",
        chat_id=2079536184,
        message_id=123,
        timestamp=datetime(2025, 12, 26, 8, 0, tzinfo=UTC),
        kind="TRADE_SIGNAL",
        strategy="SMC_HYBRID",
        symbol="BTCUSDT",
        timeframe="30m",
        direction="SELL",
        entry_price="4499.70",
        stop_loss="4525.87",
        take_profits=["4482.73", "4430.57"],
        parse_confidence=0.9,
        parse_sources=["text", "image"],
        ocr_raw_text="ENTRY 4499.70",
    )

    assert fake_conn.execute_calls, "expected at least one execute call"
    sql, args = fake_conn.execute_calls[0]
    assert "INSERT INTO external_telegram_signals" in sql
    assert "ON CONFLICT" in sql
    assert args[0] == "captain"
    assert args[1] == 2079536184
    assert args[2] == 123


@pytest.mark.asyncio
async def test_upsert_external_telegram_signal_validation_uses_on_conflict_upsert() -> None:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )

    fake_conn = _FakeConn()
    adapter.get_write_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment, return-value]

    await adapter.upsert_external_telegram_signal_validation(
        source="captain",
        chat_id=2079536184,
        message_id=123,
        timestamp=datetime(2025, 12, 26, 8, 0, tzinfo=UTC),
        internal_kind="smc_signal",
        internal_id="11111111-1111-1111-1111-111111111111",
        internal_timestamp=datetime(2025, 12, 26, 8, 2, tzinfo=UTC),
        score=0.82,
        breakdown={"direction": 1, "time": 0.8},
    )

    assert fake_conn.execute_calls, "expected at least one execute call"
    sql, args = fake_conn.execute_calls[0]
    assert "INSERT INTO external_telegram_signal_validations" in sql
    assert "ON CONFLICT" in sql
    assert args[0] == "captain"
    assert args[1] == 2079536184
    assert args[2] == 123


@pytest.mark.asyncio
async def test_upsert_external_telegram_signal_validation_serializes_breakdown_to_json() -> None:
    """Verify that breakdown dict is serialized to JSON string for asyncpg JSONB column."""
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )

    fake_conn = _FakeConn()
    adapter.get_write_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment, return-value]

    breakdown_dict = {"direction": 1.0, "time": 0.8, "entry": 0.95}
    await adapter.upsert_external_telegram_signal_validation(
        source="captain",
        chat_id=2079536184,
        message_id=456,
        timestamp=datetime(2025, 12, 26, 8, 0, tzinfo=UTC),
        internal_kind="smc_signal",
        internal_id="22222222-2222-2222-2222-222222222222",
        internal_timestamp=datetime(2025, 12, 26, 8, 5, tzinfo=UTC),
        score=0.91,
        breakdown=breakdown_dict,
    )

    assert fake_conn.execute_calls, "expected at least one execute call"
    _, args = fake_conn.execute_calls[0]
    # args[8] is the breakdown parameter ($9 in the SQL)
    breakdown_arg = args[8]
    assert isinstance(breakdown_arg, str), f"expected str for JSONB, got {type(breakdown_arg)}"
    assert json.loads(breakdown_arg) == breakdown_dict


@pytest.mark.asyncio
async def test_upsert_external_telegram_signal_validation_handles_none_breakdown() -> None:
    """Verify that None breakdown is passed as None (not serialized)."""
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )

    fake_conn = _FakeConn()
    adapter.get_write_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment, return-value]

    await adapter.upsert_external_telegram_signal_validation(
        source="captain",
        chat_id=2079536184,
        message_id=789,
        timestamp=datetime(2025, 12, 26, 8, 0, tzinfo=UTC),
        internal_kind=None,
        internal_id=None,
        internal_timestamp=None,
        score=0.0,
        breakdown=None,
    )

    assert fake_conn.execute_calls, "expected at least one execute call"
    _, args = fake_conn.execute_calls[0]
    # args[8] is the breakdown parameter ($9 in the SQL)
    assert args[8] is None
