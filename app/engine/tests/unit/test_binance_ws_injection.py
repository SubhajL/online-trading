import pytest

from app.engine.bus import create_event_bus
from app.engine.ingest.binance_ws import BinanceWebSocketClient


class DummyWS:
    closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def send(self, msg):  # noqa: D401
        return None


@pytest.mark.asyncio
async def test_binance_ws_uses_injected_connector(monkeypatch):
    base_url = "wss://stream.binance.com:9443/ws/"
    client = BinanceWebSocketClient(base_url=base_url, event_bus=create_event_bus())

    called = {}

    def fake_connector(url: str, **kwargs):
        called["url"] = url
        called["kwargs"] = kwargs
        return DummyWS()

    # Inject fake connector
    import app.engine.ingest.binance_ws as mod

    monkeypatch.setattr(mod, "get_ws_connector", lambda: fake_connector)

    await client._connect_and_listen()

    assert called["url"].startswith(base_url.rstrip("/"))
    assert "ping_interval" in called["kwargs"]
    assert "ping_timeout" in called["kwargs"]
