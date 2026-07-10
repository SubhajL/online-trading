"""
Unit tests for trend_live restart recovery.

Open paper positions must map back to their (strategy × symbol) sleeve via the
deterministic client_order_id embedded in the bracket's entry order.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.engine.trend_live.recovery import (
    load_open_trend_sleeves,
    parse_trend_client_order_id,
)


@pytest.mark.parametrize(
    ("client_order_id", "expected"),
    [
        ("trend-tsmom28-BTCUSDT-1d-20260307-long", ("tsmom28", "BTCUSDT")),
        ("trend-sma65-ETHUSDT-1d-20261231-long-sl", ("sma65", "ETHUSDT")),
        ("trend-tsmom28-BTCUSDT-1d-20260307-close", ("tsmom28", "BTCUSDT")),
        ("paper_ab12cd34", None),
        ("trend-tsmom28-BTCUSDT-4h-20260307-long", None),
        ("trend-tsmom28", None),
        ("engine-main-1", None),
    ],
)
def test_parse_trend_client_order_id(
    client_order_id: str,
    expected: tuple[str, str] | None,
) -> None:
    """Only 1d trend ids parse; everything else is ignored."""
    assert parse_trend_client_order_id(client_order_id) == expected


def _pool_returning(rows: list[dict]) -> MagicMock:
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch.return_value = rows
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None
    return pool


@pytest.mark.asyncio
async def test_load_open_trend_sleeves_maps_rows() -> None:
    """DB rows become OpenSleeves keyed by the parsed strategy and symbol."""
    bracket_a, bracket_b = uuid4(), uuid4()
    rows = [
        {
            "symbol": "BTCUSDT",
            "paper_session_id": bracket_a,
            "side": "LONG",
            "client_order_id": "trend-tsmom28-BTCUSDT-1d-20260301-long",
        },
        {
            "symbol": "ETHUSDT",
            "paper_session_id": bracket_b,
            "side": "LONG",
            "client_order_id": "trend-sma65-ETHUSDT-1d-20260302-long",
        },
    ]

    sleeves = await load_open_trend_sleeves(_pool_returning(rows))

    assert [(s.strategy_id, s.symbol, s.bracket_id, s.side) for s in sleeves] == [
        ("tsmom28", "BTCUSDT", bracket_a, "LONG"),
        ("sma65", "ETHUSDT", bracket_b, "LONG"),
    ]


@pytest.mark.asyncio
async def test_load_open_trend_sleeves_skips_unparsable_and_mismatched_rows() -> None:
    """Foreign ids and symbol mismatches are dropped, not crashed on."""
    rows = [
        {
            "symbol": "BTCUSDT",
            "paper_session_id": uuid4(),
            "side": "LONG",
            "client_order_id": "paper_ab12cd34",
        },
        {
            "symbol": "ETHUSDT",
            "paper_session_id": uuid4(),
            "side": "LONG",
            "client_order_id": "trend-tsmom28-BTCUSDT-1d-20260301-long",
        },
    ]

    sleeves = await load_open_trend_sleeves(_pool_returning(rows))

    assert sleeves == []
