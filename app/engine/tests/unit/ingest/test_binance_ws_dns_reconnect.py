from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine.ingest.binance_ws import BinanceWebSocketClient


@pytest.mark.asyncio
async def test_health_check_records_dns_connect_errors_without_incrementing_generic_failures() -> None:
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)

    client = BinanceWebSocketClient(event_bus=bus)

    err = socket.gaierror(-3, "Temporary failure in name resolution")
    await client._on_connection_failure(err)

    health = await client.health_check()
    assert health["last_connect_error_kind"] == "dns"
    assert "Temporary failure" in str(health["last_connect_error"])
    assert isinstance(health["last_connect_error_ago_seconds"], float)
    assert health["consecutive_dns_failures"] == 1
    assert health["consecutive_failures"] == 0


@pytest.mark.asyncio
async def test_connection_manager_dns_failure_triggers_dns_wait_and_skips_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)

    client = BinanceWebSocketClient(event_bus=bus)
    client._running = True

    err = socket.gaierror(-3, "Temporary failure in name resolution")
    monkeypatch.setattr(client, "_connect_and_listen", AsyncMock(side_effect=err))

    async def fake_wait(_host: str, _port: int) -> None:
        client._running = False

    wait_mock = AsyncMock(side_effect=fake_wait)
    monkeypatch.setattr(client, "_wait_for_dns_recovery", wait_mock)

    monkeypatch.setattr(
        client._backoff,
        "next_delay",
        MagicMock(side_effect=AssertionError("should not use backoff for DNS failures")),
    )

    await client._connection_manager()

    wait_mock.assert_awaited()
