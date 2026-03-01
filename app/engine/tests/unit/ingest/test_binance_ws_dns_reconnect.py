from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine.ingest.binance_ws import BinanceWebSocketClient


class TestBinanceWebSocketDnsReconnect:
    @pytest.mark.asyncio
    async def test_dns_connect_failure_does_not_increment_generic_failures_or_trip_breaker(
        self,
    ) -> None:
        circuit_breaker = MagicMock()
        circuit_breaker.record_failure = AsyncMock(return_value=None)
        circuit_breaker.record_success = AsyncMock(return_value=None)

        client = BinanceWebSocketClient(event_bus=MagicMock(), circuit_breaker=circuit_breaker)

        err = socket.gaierror(-3, "Temporary failure in name resolution")

        kind = await client._on_connection_failure(err)  # type: ignore[attr-defined]

        assert kind == "dns"
        assert client._consecutive_failures == 0
        assert client._consecutive_dns_failures == 1
        circuit_breaker.record_failure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_connection_manager_waits_for_dns_recovery_instead_of_backoff_sleep(self) -> None:
        from app.engine.ingest import binance_ws

        circuit_breaker = MagicMock()
        circuit_breaker.should_allow_request = AsyncMock(return_value=True)
        circuit_breaker.record_failure = AsyncMock(return_value=None)

        client = BinanceWebSocketClient(event_bus=MagicMock(), circuit_breaker=circuit_breaker)
        client._running = True

        client._connect_and_listen = AsyncMock(  # type: ignore[method-assign]
            side_effect=socket.gaierror(-3, "Temporary failure in name resolution"),
        )

        async def fake_wait_for_dns_recovery(_host: str, _port: int) -> None:
            client._running = False

        client._wait_for_dns_recovery = AsyncMock(  # type: ignore[attr-defined]
            side_effect=fake_wait_for_dns_recovery,
        )

        client._backoff.next_delay = MagicMock(return_value=999.0)

        async def fail_sleep(_seconds: float) -> None:
            raise AssertionError("expected DNS recovery probe, not exponential backoff sleep")

        original_sleep = binance_ws.asyncio.sleep
        binance_ws.asyncio.sleep = fail_sleep  # type: ignore[assignment]
        try:
            await client._connection_manager()
        finally:
            binance_ws.asyncio.sleep = original_sleep

        client._wait_for_dns_recovery.assert_awaited()
