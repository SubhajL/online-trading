from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine.bus import create_event_bus, set_event_bus
from app.engine.models import TimeFrame


@pytest.fixture(autouse=True)
def event_bus_fixture():
    bus = create_event_bus()
    set_event_bus(bus)
    return bus


@pytest.mark.asyncio
async def test_start_runs_backfill_before_ws_start(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.engine.ingest.ingest_service import IngestService

    calls: list[str] = []

    service = IngestService(
        binance_config={
            "api_key": "test",
            "api_secret": "test",
            "testnet": True,
        },
        symbols=["BTCUSDT"],
        timeframes=[TimeFrame.M5],
        enable_realtime=True,
        enable_backfill=True,
        db_adapter=None,
    )

    rest = MagicMock()
    rest.start = AsyncMock(side_effect=lambda: calls.append("rest_start"))
    rest.stop = AsyncMock()
    service.rest_client = rest

    ws = MagicMock()
    ws.start = AsyncMock(side_effect=lambda: calls.append("ws_start"))
    ws.stop = AsyncMock()
    ws.subscribe_klines = AsyncMock()
    ws.subscribe_ticker = AsyncMock()
    service.ws_client = ws

    monkeypatch.setattr(service, "_setup_realtime_streams", AsyncMock())
    monkeypatch.setattr(
        service, "_start_backfill", AsyncMock(side_effect=lambda: calls.append("backfill_start"))
    )
    monkeypatch.setattr(
        service,
        "_monitor_backfill_completion",
        AsyncMock(side_effect=lambda: calls.append("backfill_wait")),
    )

    await service.start()

    assert calls.index("backfill_start") < calls.index("ws_start")


@pytest.mark.asyncio
async def test_setup_realtime_streams_skips_ticker_by_default() -> None:
    from app.engine.ingest.ingest_service import IngestService

    service = IngestService(
        binance_config={
            "api_key": "test",
            "api_secret": "test",
            "testnet": True,
        },
        symbols=["BTCUSDT"],
        timeframes=[TimeFrame.M5],
        enable_realtime=True,
        enable_backfill=False,
        db_adapter=None,
    )

    ws = MagicMock()
    ws.subscribe_klines = AsyncMock()
    ws.subscribe_ticker = AsyncMock()
    service.ws_client = ws

    await service._setup_realtime_streams()

    ws.subscribe_klines.assert_awaited_once()
    ws.subscribe_ticker.assert_not_awaited()
