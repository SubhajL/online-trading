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


class _MockResp:
    def __init__(self, status: int, payload: dict | str):
        self.status = status
        self._payload = payload

    async def json(self):  # noqa: D401
        if isinstance(self._payload, dict):
            return self._payload
        return {}

    async def text(self):  # noqa: D401
        if isinstance(self._payload, str):
            return self._payload
        return ""


class _Ctx:
    def __init__(self, resp: _MockResp):
        self._resp = resp

    async def __aenter__(self):  # noqa: D401
        return self._resp

    async def __aexit__(self, exc_type, exc, tb):  # noqa: D401, ANN001
        return False


class _RouterSession:
    """Stub aiohttp session for Router client with programmable responses."""

    def __init__(self, mapping: dict[tuple[str, str], list[tuple[int, dict | str]]]):
        # mapping[(method, path)] -> list of (status, payload)
        self._mapping = mapping

    def request(self, method, url, **kwargs):  # noqa: ANN001
        from urllib.parse import urlparse

        path = urlparse(url).path
        key = (method.upper(), path)
        seq = self._mapping.get(key, [])
        if seq:
            status, payload = seq.pop(0)
        else:
            status, payload = 200, {"ok": True}
        return _Ctx(_MockResp(status, payload))


class _BinanceSession:
    """Stub aiohttp session for Binance client with programmable responses."""

    def __init__(self, mapping: dict[tuple[str, str], list[tuple[int, dict | str]]]):
        self._mapping = mapping

    def _pick(self, method: str, url: str):
        from urllib.parse import urlparse

        path = urlparse(url).path
        key = (method.upper(), path)
        seq = self._mapping.get(key, [])
        if seq:
            status, payload = seq.pop(0)
        else:
            status, payload = 200, {}
        return _Ctx(_MockResp(status, payload))

    def get(self, url, **kwargs):  # noqa: ANN001
        return self._pick("GET", url)

    def post(self, url, **kwargs):  # noqa: ANN001
        return self._pick("POST", url)

    def delete(self, url, **kwargs):  # noqa: ANN001
        return self._pick("DELETE", url)


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


@pytest.mark.asyncio
async def test_router_per_endpoint_breakers_independent() -> None:
    client = RouterHTTPClient(base_url="http://example", timeout=1, retry_attempts=1, retry_delay=0)
    client._initialized = True  # type: ignore[attr-defined]
    # Trip breaker for /orders, keep /health successful
    mapping = {
        ("GET", "/orders"): [(500, "e")] * 6,
        ("GET", "/health"): [(200, {"ok": True})],
    }
    client._session = _RouterSession(mapping)  # type: ignore[attr-defined]

    # Cause multiple failures on /orders
    for _ in range(5):
        await client._make_request("GET", "/orders")  # type: ignore[attr-defined]
    # Next publish on /orders fast-fails with breaker open
    resp = await client._make_request("GET", "/orders")  # type: ignore[attr-defined]
    assert resp.get("error") == "circuit_breaker_open"

    # Independent endpoint should still work
    ok = await client._make_request("GET", "/health")  # type: ignore[attr-defined]
    assert ok.get("ok") is True


@pytest.mark.asyncio
async def test_router_throttling_429_does_not_trip_breaker() -> None:
    client = RouterHTTPClient(base_url="http://example", timeout=1, retry_attempts=1, retry_delay=0)
    client._initialized = True  # type: ignore[attr-defined]
    mapping = {
        ("GET", "/orders"): [(429, "rate limited")] * 10,
    }
    client._session = _RouterSession(mapping)  # type: ignore[attr-defined]

    # Many throttled responses should not open breaker
    for _ in range(8):
        resp = await client._make_request("GET", "/orders")  # type: ignore[attr-defined]
        assert resp.get("status") == 429
        assert resp.get("error") == "throttled"

    # Should still not be breaker open
    resp = await client._make_request("GET", "/orders")  # type: ignore[attr-defined]
    assert resp.get("status") == 429 and resp.get("error") == "throttled"


@pytest.mark.asyncio
async def test_binance_per_endpoint_breakers_independent() -> None:
    client = BinanceRestClient(api_key="k", api_secret="s", testnet=True)
    # Inject stub session
    mapping = {
        ("GET", "/api/v3/depth"): [(500, {"msg": "error"})] * 6,
        ("GET", "/api/v3/time"): [(200, {"serverTime": 1700000000000})],
    }
    client._session = _BinanceSession(mapping)  # type: ignore[attr-defined]

    # Trip breaker on depth
    tripped = False
    for _ in range(6):
        try:
            await client.get_order_book(symbol="BTCUSDT", limit=5)
        except Exception as e:
            if str(e) == "CircuitBreakerOpen":
                tripped = True
                break
    assert tripped is True

    # get_server_time should still succeed (different endpoint breaker)
    ts = await client.get_server_time()
    assert isinstance(ts, datetime)


@pytest.mark.asyncio
async def test_binance_throttling_does_not_trip_breaker() -> None:
    client = BinanceRestClient(api_key="k", api_secret="s", testnet=True)
    # 429 responses repeatedly for time endpoint
    mapping = {
        ("GET", "/api/v3/time"): [(429, {"msg": "throttled"})] * 8,
    }
    client._session = _BinanceSession(mapping)  # type: ignore[attr-defined]

    # Ensure repeated throttling doesn't produce CircuitBreakerOpen
    for _ in range(7):
        try:
            await client.get_server_time()
        except Exception as e:
            # Allowed: API raises regular error, but NOT CircuitBreakerOpen
            assert str(e) != "CircuitBreakerOpen"

    # Still not CircuitBreakerOpen on next call
    try:
        await client.get_server_time()
    except Exception as e:
        assert str(e) != "CircuitBreakerOpen"
