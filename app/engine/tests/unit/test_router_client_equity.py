from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.engine.adapters.router_client.http_client import RouterHTTPClient


@pytest.mark.asyncio
async def test_get_internal_equity_parses_equity_and_timestamp() -> None:
    client = RouterHTTPClient(base_url="http://router")
    client._make_request = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "venue": "USD_M",
            "equity_usd": "1234.56",
            "timestamp": "2026-02-06T12:00:00+00:00",
        },
    )

    equity, ts = await client.get_internal_equity(venue="USD_M")

    assert equity == Decimal("1234.56")
    assert ts == datetime(2026, 2, 6, 12, 0, tzinfo=UTC)
