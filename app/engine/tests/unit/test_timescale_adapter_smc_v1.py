"""Tests for TimescaleDBAdapter.insert_smc_event_v1 targeting smc_events_v1 table.

Verifies:
- SQL targets smc_events_v1 (not legacy smc_events)
- No legacy columns (structure_type, price, trend_direction) in INSERT
- All 12 contract columns are present
- Correct parameter count and types
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter

SAMPLE_PAYLOAD: dict[str, Any] = {
    "venue": "binance_spot",
    "symbol": "BTCUSDT",
    "timeframe": "15m",
    "event_time": "2025-01-15T10:30:00Z",
    "event_type": "choch",
    "direction": "bearish",
    "price_level": "49000.12345678",
    "previous_pivot_price": "49500.00000000",
    "previous_pivot_time": "2025-01-15T09:00:00Z",
    "broken_pivot_price": "51500.00000000",
    "broken_pivot_time": "2025-01-15T08:00:00Z",
    "version": "1.0.0",
}


def _make_adapter_with_fake_pool() -> tuple[TimescaleDBAdapter, AsyncMock]:
    """Create adapter with a fake write pool that captures execute calls."""
    adapter = TimescaleDBAdapter(
        host="localhost",
        port=5432,
        database="test",
        username="test",
        password="test",
    )
    mock_conn = AsyncMock()

    @asynccontextmanager
    async def fake_write_connection():
        yield mock_conn

    adapter.get_write_connection = fake_write_connection  # type: ignore[assignment]
    return adapter, mock_conn


class TestInsertSmcEventV1:
    """Verify insert_smc_event_v1 SQL targets correct table with correct columns."""

    @pytest.mark.asyncio
    async def test_sql_targets_smc_events_v1_table(self) -> None:
        """INSERT must target smc_events_v1, not legacy smc_events."""
        adapter, mock_conn = _make_adapter_with_fake_pool()
        await adapter.insert_smc_event_v1(SAMPLE_PAYLOAD)

        sql = mock_conn.execute.call_args[0][0]
        assert "smc_events_v1" in sql
        # Must NOT contain bare "smc_events" without "_v1" suffix
        stripped = sql.replace("smc_events_v1", "")
        assert "smc_events" not in stripped, "SQL must not reference legacy smc_events table"

    @pytest.mark.asyncio
    async def test_sql_has_no_legacy_columns(self) -> None:
        """INSERT must not include structure_type, price, or trend_direction."""
        adapter, mock_conn = _make_adapter_with_fake_pool()
        await adapter.insert_smc_event_v1(SAMPLE_PAYLOAD)

        sql = mock_conn.execute.call_args[0][0]
        assert "structure_type" not in sql
        assert "trend_direction" not in sql
        # "price" could appear in column names like "price_level", so check for standalone
        # The column list should NOT have a bare "price" column
        lines = [line.strip().rstrip(",") for line in sql.split("\n")]
        column_lines = [tok for tok in lines if tok and not tok.startswith(("INSERT", "VALUES", "ON", ")", "(", "$", "--"))]
        bare_price = [tok for tok in column_lines if tok == "price"]
        assert bare_price == [], f"Found bare 'price' column in SQL: {column_lines}"

    @pytest.mark.asyncio
    async def test_sql_includes_all_12_contract_columns(self) -> None:
        """INSERT must include all smc_events.v1 contract columns."""
        adapter, mock_conn = _make_adapter_with_fake_pool()
        await adapter.insert_smc_event_v1(SAMPLE_PAYLOAD)

        sql = mock_conn.execute.call_args[0][0]
        expected_columns = [
            "venue", "symbol", "timeframe", "event_time",
            "event_type", "direction", "price_level",
            "previous_pivot_price", "previous_pivot_time",
            "broken_pivot_price", "broken_pivot_time",
            "version",
        ]
        for col in expected_columns:
            assert col in sql, f"Missing column {col!r} in INSERT SQL"

    @pytest.mark.asyncio
    async def test_passes_exactly_12_parameters(self) -> None:
        """INSERT must pass exactly 12 positional parameters ($1..$12)."""
        adapter, mock_conn = _make_adapter_with_fake_pool()
        await adapter.insert_smc_event_v1(SAMPLE_PAYLOAD)

        args = mock_conn.execute.call_args[0]
        sql = args[0]
        params = args[1:]
        assert len(params) == 12, f"Expected 12 params, got {len(params)}"
        assert "$12" in sql
        assert "$13" not in sql

    @pytest.mark.asyncio
    async def test_event_type_uppercased(self) -> None:
        """event_type should be stored as uppercase (CHOCH, BOS)."""
        adapter, mock_conn = _make_adapter_with_fake_pool()
        await adapter.insert_smc_event_v1(SAMPLE_PAYLOAD)

        args = mock_conn.execute.call_args[0]
        # event_type is the 5th param ($5)
        event_type_param = args[5]
        assert event_type_param == "CHOCH"

    @pytest.mark.asyncio
    async def test_numeric_fields_are_decimal(self) -> None:
        """price_level, previous_pivot_price, broken_pivot_price must be Decimal."""
        adapter, mock_conn = _make_adapter_with_fake_pool()
        await adapter.insert_smc_event_v1(SAMPLE_PAYLOAD)

        args = mock_conn.execute.call_args[0]
        # price_level=$7, previous_pivot_price=$8, broken_pivot_price=$10
        assert isinstance(args[7], Decimal), "price_level must be Decimal"
        assert isinstance(args[8], Decimal), "previous_pivot_price must be Decimal"
        assert isinstance(args[10], Decimal), "broken_pivot_price must be Decimal"

    @pytest.mark.asyncio
    async def test_timestamp_fields_are_datetime(self) -> None:
        """event_time, previous_pivot_time, broken_pivot_time must be datetime."""
        adapter, mock_conn = _make_adapter_with_fake_pool()
        await adapter.insert_smc_event_v1(SAMPLE_PAYLOAD)

        args = mock_conn.execute.call_args[0]
        # event_time=$4, previous_pivot_time=$9, broken_pivot_time=$11
        assert isinstance(args[4], datetime), "event_time must be datetime"
        assert isinstance(args[9], datetime), "previous_pivot_time must be datetime"
        assert isinstance(args[11], datetime), "broken_pivot_time must be datetime"

    @pytest.mark.asyncio
    async def test_on_conflict_do_nothing(self) -> None:
        """INSERT uses ON CONFLICT DO NOTHING for idempotency."""
        adapter, mock_conn = _make_adapter_with_fake_pool()
        await adapter.insert_smc_event_v1(SAMPLE_PAYLOAD)

        sql = mock_conn.execute.call_args[0][0]
        assert "ON CONFLICT DO NOTHING" in sql
