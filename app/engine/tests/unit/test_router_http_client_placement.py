from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlparse

import pytest

from app.engine.adapters.router_client.http_client import (
    BracketClientOrderIDs,
    BracketPlacementResult,
    RouterCircuitOpenError,
    RouterHTTPClient,
    RouterHTTPError,
    RouterProtocolError,
)
from app.engine.execution.router_execution_subscriber import validate_bracket_placement


class _Response:
    def __init__(self, status: int, payload: object):
        self.status = status
        self._payload = payload

    async def json(self) -> object:
        return self._payload

    async def text(self) -> str:
        return str(self._payload)


class _RequestContext:
    def __init__(self, response: _Response):
        self._response = response

    async def __aenter__(self) -> _Response:
        return self._response

    async def __aexit__(self, *_args: object) -> bool:
        return False


class _Session:
    def __init__(self, responses: list[_Response]):
        self.responses = responses
        self.requests: list[tuple[str, str]] = []

    def request(self, *, method: str, url: str, **_kwargs: object) -> _RequestContext:
        self.requests.append((method, urlparse(url).path))
        return _RequestContext(self.responses.pop(0))


class _OpenBreaker:
    async def should_allow_request(self) -> bool:
        return False


def _client(*responses: _Response) -> RouterHTTPClient:
    client = RouterHTTPClient(
        base_url="http://router",
        retry_attempts=3,
        retry_delay=0,
    )
    client._initialized = True
    client._session = _Session(list(responses))  # type: ignore[assignment]
    return client


def _valid_payload() -> dict[str, object]:
    return {
        "bracket_order_id": "bracket-1",
        "client_order_ids": {
            "main": "intent-entry",
            "take_profits": ["intent-tp1"],
            "stop_loss": "intent-sl",
        },
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": "0.001",
        "created_at": datetime(2026, 8, 13, tzinfo=UTC).isoformat(),
        "partial_failure": False,
        "errors": [],
        "legs_pending_trigger": True,
    }


@pytest.mark.asyncio
async def test_http_400_raises_router_http_error() -> None:
    client = _client(_Response(400, {"error": "invalid bracket"}))

    with pytest.raises(RouterHTTPError) as exc_info:
        await client.place_bracket_order({"symbol": "BTCUSDT"})

    assert exc_info.value.status == 400


@pytest.mark.asyncio
async def test_circuit_open_never_returns_success_payload() -> None:
    client = _client()
    client._get_breaker_for = lambda *_args: _OpenBreaker()  # type: ignore[method-assign]

    with pytest.raises(RouterCircuitOpenError):
        await client.place_bracket_order({"symbol": "BTCUSDT"})


@pytest.mark.asyncio
async def test_malformed_2xx_raises_protocol_error() -> None:
    client = _client(_Response(200, {"bracket_order_id": ""}))

    with pytest.raises(RouterProtocolError):
        await client.place_bracket_order({"symbol": "BTCUSDT"})


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["partial_failure", "errors", "legs_pending_trigger"])
async def test_success_verdict_fields_are_mandatory(field: str) -> None:
    response = _valid_payload()
    del response[field]
    client = _client(_Response(200, response))

    with pytest.raises(RouterProtocolError, match="boolean fields|invalid errors"):
        await client.place_bracket_order({"symbol": "BTCUSDT"})


@pytest.mark.asyncio
async def test_valid_201_returns_immutable_placement_result() -> None:
    client = _client(_Response(201, _valid_payload()))

    result = await client.place_bracket_order({"symbol": "BTCUSDT"})

    assert result == BracketPlacementResult(
        bracket_order_id="bracket-1",
        client_order_ids=BracketClientOrderIDs(
            main="intent-entry",
            take_profits=("intent-tp1",),
            stop_loss="intent-sl",
        ),
        symbol="BTCUSDT",
        side="BUY",
        quantity=Decimal("0.001"),
        created_at=datetime(2026, 8, 13, tzinfo=UTC),
        partial_failure=False,
        errors=(),
        legs_pending_trigger=True,
    )


@pytest.mark.asyncio
async def test_bracket_transport_has_one_http_attempt() -> None:
    client = _client(
        _Response(503, {"error": "unavailable"}),
        _Response(200, _valid_payload()),
    )
    session = client._session

    with pytest.raises(RouterHTTPError):
        await client.place_bracket_order({"symbol": "BTCUSDT"})

    assert isinstance(session, _Session)
    assert session.requests == [("POST", "/place_bracket")]


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", ["Infinity", "0.02", "0.0005"])
async def test_unsafe_placement_quantity_is_rejected(quantity: str) -> None:
    response = _valid_payload()
    response["quantity"] = quantity
    client = _client(_Response(200, response))
    request = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": "0.001",
        "client_order_ids": {
            "main": "intent-entry",
            "take_profits": ["intent-tp1"],
            "stop_loss": "intent-sl",
        },
    }

    with pytest.raises(RouterProtocolError, match="quantity"):
        result = await client.place_bracket_order(request)
        validate_bracket_placement(result, request)
