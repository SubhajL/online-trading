"""
Unit tests for TimescaleDBAdapter external Telegram signal tables.
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
async def test_create_tables_includes_external_signal_tables() -> None:
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="db",
        username="user",
        password="pass",
    )

    fake_conn = _FakeConn()
    adapter.get_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment]

    await adapter._create_tables()

    sql = "\n".join(call[0] for call in fake_conn.execute_calls)
    assert "CREATE TABLE IF NOT EXISTS external_telegram_signals" in sql
    assert "CREATE TABLE IF NOT EXISTS external_telegram_signal_validations" in sql


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
    adapter.get_write_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment]

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
    adapter.get_write_connection = lambda: _FakePoolCtx(fake_conn)  # type: ignore[assignment]

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
