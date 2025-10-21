"""
Tests for circuit breaker integration on external clients (Router, Binance REST).
"""

import asyncio
from datetime import datetime

import pytest

from app.engine.adapters.router_client.http_client import RouterHTTPClient
from app.engine.ingest.binance_rest import BinanceRestClient
from app.engine.models import EventType, TimeFrame


class _FailingCtx:
    def __init__(self, exc: Exception):
        self._exc = exc

    async def __aenter__(self):  # noqa: D401
        raise self._exc

    async def __aexit__(self, exc_type, exc, tb):  # noqa: D401, ANN001
        return False


class _FailingSession:
    def __init__(self, exc: Exception):
        self._exc = exc

    # For RouterHTTPClient
    def request(self, *args, **kwargs):  # noqa: D401, ANN001
        return _FailingCtx(self._exc)

    # For BinanceRestClient
    def get(self, *args, **kwargs):  # noqa: D401, ANN001
        return _FailingCtx(self._exc)

    def post(self, *args, **kwargs):  # noqa: D401, ANN001
        return _FailingCtx(self._exc)

    def delete(self, *args, **kwargs):  # noqa: D401, ANN001
        return _FailingCtx(self._exc)


@pytest.mark.asyncio
async def test_router_client_circuit_breaker_opens_and_fast_fails() -> None:
    client = RouterHTTPClient(base_url="http://example").__class__(
        base_url="http://example",
        timeout=1,
        retry_attempts=1,
        retry_delay=0.0,
    )
    # Initialize without real HTTP
    client._initialized = True  # type: ignore[attr-defined]
    client._session = _FailingSession(Exception("network down"))  # type: ignore[attr-defined]

    # Cause consecutive failures to trip the breaker
    tripped = False
    for i in range(6):  # default threshold is 5
        try:
            await client.get_order_status("id")
        except Exception:
            # ignore real exceptions until breaker opens
            pass
        # Try a call that should fast-fail once breaker is open
        try:
            resp = await client._make_request("GET", "/health")  # type: ignore[attr-defined]
            if resp.get("error") == "circuit_breaker_open":
                tripped = True
                break
        except Exception:
            # before breaker opens, the network error propagates
            pass

    assert tripped is True


@pytest.mark.asyncio
async def test_binance_rest_circuit_breaker_opens_and_raises() -> None:
    client = BinanceRestClient(api_key="k", api_secret="s", testnet=True)
    # Avoid real session; inject failing session and mark started
    client._session = _FailingSession(Exception("network down"))  # type: ignore[attr-defined]

    tripped = False
    for i in range(6):  # threshold 5, then open
        try:
            await client.get_server_time()
        except Exception as e:
            if str(e) == "CircuitBreakerOpen":
                tripped = True
                break
            # else continue causing failures

    assert tripped is True
