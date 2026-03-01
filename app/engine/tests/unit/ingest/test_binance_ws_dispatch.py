from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine.ingest.binance_ws import BinanceWebSocketClient


class _DummyWS:
    def __init__(self, messages: list[str]) -> None:
        self._messages = list(messages)
        self.close = AsyncMock()

    async def __aenter__(self) -> "_DummyWS":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    def __aiter__(self) -> "_DummyWS":
        return self

    async def __anext__(self) -> str:
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)

    async def send(self, _msg: str) -> None:
        return None


@pytest.mark.asyncio
async def test_connect_and_listen_does_not_await_slow_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.engine.ingest.binance_ws as mod

    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)

    client = BinanceWebSocketClient(event_bus=bus)

    async def slow_route(_data: dict[str, Any]) -> None:
        await asyncio.sleep(0.5)

    monkeypatch.setattr(client, "_route_message", AsyncMock(side_effect=slow_route))

    msgs = [
        json.dumps({"e": "24hrTicker", "s": "BTCUSDT", "c": "1.0", "P": "0.0"}) for _ in range(3)
    ]

    def fake_connector(_url: str, **_kwargs: object) -> _DummyWS:
        return _DummyWS(msgs)

    monkeypatch.setattr(mod, "get_ws_connector", lambda: fake_connector)

    start = asyncio.get_event_loop().time()
    await client._connect_and_listen()
    elapsed = asyncio.get_event_loop().time() - start

    # If the receive loop awaited slow_route 3x, elapsed would be ~1.5s.
    assert elapsed < 0.4


@pytest.mark.asyncio
async def test_drops_ticker_messages_when_dispatch_queue_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.engine.ingest.binance_ws as mod

    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)

    client = BinanceWebSocketClient(event_bus=bus)
    # Force tiny dispatch queue so a single list-message overflows it.
    client._dispatch_queue_maxsize = 1  # type: ignore[attr-defined]

    payload = [
        {
            "stream": "btcusdt@ticker",
            "data": {"e": "24hrTicker", "s": "BTCUSDT", "c": "1.0", "P": "0.0"},
        }
        for _ in range(5)
    ]
    msgs = [json.dumps(payload)]

    def fake_connector(_url: str, **_kwargs: object) -> _DummyWS:
        return _DummyWS(msgs)

    monkeypatch.setattr(mod, "get_ws_connector", lambda: fake_connector)

    await client._connect_and_listen()

    health = await client.health_check()
    dropped = health.get("dispatch_dropped_messages_total")
    assert isinstance(dropped, int)
    assert dropped > 0
