from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from aiohttp import web
import pytest
import yaml

from app.engine.paper import server as server_module
from app.engine.paper.server import (
    PaperBrokerServer,
    build_cost_calculator,
    build_fill_engine,
    build_order_update_publisher_from_env,
)

ORDER_UPDATE_PAYLOAD = {
    "event_type": "FILLED",
    "symbol": "BTCUSDT",
    "client_order_id": "paper-abc",
    "status": "FILLED",
}


def test_build_cost_calculator_maps_config_bps() -> None:
    calculator = build_cost_calculator(
        {"fee_bps_spot": 8, "fee_bps_futures": 2, "funding_model": "constant"},
    )

    assert (
        calculator.fee_bps_spot,
        calculator.fee_bps_futures,
        calculator.funding_model,
        calculator.spot_fee_rate,
    ) == (Decimal(8), Decimal(2), "constant", Decimal("0.0008"))


def test_build_cost_calculator_defaults_match_backtest() -> None:
    calculator = build_cost_calculator({})

    assert (
        calculator.fee_bps_spot,
        calculator.fee_bps_futures,
        calculator.funding_model,
    ) == (Decimal(10), Decimal(4), "disabled")


def test_build_fill_engine_maps_slippage() -> None:
    assert build_fill_engine({"slippage_bps": 3}).slippage_bps == Decimal(3)


def test_publisher_absent_without_order_update_url() -> None:
    assert build_order_update_publisher_from_env({}) is None


async def _run_publisher_against(
    handler,
    environ_extra: dict[str, str],
    topic: str = "order_update.v1",
    timeout_seconds: float = 5,
):
    app = web.Application()
    app.router.add_post("/internal/order_update", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]

    publisher = build_order_update_publisher_from_env(
        {
            "ORDER_UPDATE_URL": f"http://127.0.0.1:{port}/internal/order_update",
            **environ_extra,
        },
        timeout_seconds=timeout_seconds,
    )
    try:
        result = await publisher(topic, dict(ORDER_UPDATE_PAYLOAD))
    finally:
        await runner.cleanup()
    return result


@pytest.mark.asyncio
async def test_publisher_posts_payload_with_bearer_token() -> None:
    received: dict = {}

    async def handler(request: web.Request) -> web.Response:
        received["authorization"] = request.headers.get("Authorization")
        received["json"] = await request.json()
        return web.json_response({"status": "accepted"})

    result = await _run_publisher_against(
        handler,
        {"ENGINE_INTERNAL_API_TOKEN": "secret-token"},
    )

    assert (result, received["authorization"], received["json"]) == (
        True,
        "Bearer secret-token",
        ORDER_UPDATE_PAYLOAD,
    )


@pytest.mark.asyncio
async def test_publisher_returns_false_on_engine_error() -> None:
    async def handler(request: web.Request) -> web.Response:
        return web.json_response({"detail": "boom"}, status=500)

    assert await _run_publisher_against(handler, {}) is False


@pytest.mark.asyncio
async def test_publisher_returns_false_on_engine_timeout() -> None:
    async def handler(request: web.Request) -> web.Response:
        await asyncio.sleep(0.2)
        return web.json_response({"status": "accepted"})

    assert await _run_publisher_against(handler, {}, timeout_seconds=0.05) is False


@pytest.mark.asyncio
async def test_publisher_omits_authorization_without_token() -> None:
    received: dict = {}

    async def handler(request: web.Request) -> web.Response:
        received["authorization"] = request.headers.get("Authorization")
        return web.json_response({"status": "accepted"})

    result = await _run_publisher_against(handler, {})

    assert (result, received["authorization"]) == (True, None)


def test_broker_order_update_payload_matches_engine_contract() -> None:
    from uuid import uuid4

    from app.engine.backtest.types import OrderSide, OrderStatus, OrderType
    from app.engine.models import OrderUpdate as EngineOrderUpdate
    from app.engine.paper.broker import OrderUpdate as PaperOrderUpdate

    paper_update = PaperOrderUpdate(
        event_type="FILLED",
        symbol="BTCUSDT",
        venue="SPOT",
        order_id=hash(uuid4()) % 1000000,
        client_order_id="engine-supplied-id",
        status=OrderStatus.FILLED.value,
        side=OrderSide.BUY.value,
        order_type=OrderType.MARKET.value,
        price=Decimal("50000.5"),
        quantity=Decimal("0.01"),
        executed_qty=Decimal("0.01"),
        update_time=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
    )

    parsed = EngineOrderUpdate.model_validate(paper_update.model_dump())

    assert (parsed.venue, parsed.client_order_id, parsed.price, parsed.update_time) == (
        "SPOT",
        "engine-supplied-id",
        Decimal("50000.5"),
        datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_publisher_skips_non_order_update_topics() -> None:
    received: dict = {}

    async def handler(request: web.Request) -> web.Response:
        received["json"] = await request.json()
        return web.json_response({"status": "accepted"})

    result = await _run_publisher_against(handler, {}, topic="candles.v1")

    assert (result, received) == (True, {})


@pytest.mark.asyncio
async def test_initialize_wires_builders_and_publisher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict = {}

    class RecordingBroker:
        def __init__(
            self,
            database_url: str,
            cost_calculator=None,
            fill_engine=None,
            event_publisher=None,
        ):
            recorded["database_url"] = database_url
            recorded["cost_calculator"] = cost_calculator
            recorded["fill_engine"] = fill_engine
            recorded["event_publisher"] = event_publisher

        async def initialize(self) -> None:
            recorded["initialized"] = True

    monkeypatch.setattr(server_module, "PaperBroker", RecordingBroker)
    monkeypatch.setattr(server_module, "create_paper_broker_app", lambda broker: object())
    monkeypatch.setenv("ORDER_UPDATE_URL", "http://127.0.0.1:9/internal/order_update")

    config_path = tmp_path / "paper.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "database_url": "postgresql://paper:paper@localhost:5432/paper",
                "server": {"host": "127.0.0.1", "port": 8001},
                "backtest": {"fee_bps_spot": 8, "slippage_bps": 3},
            },
        ),
    )

    server = PaperBrokerServer(str(config_path))
    await server.initialize()

    assert (
        recorded["initialized"],
        recorded["cost_calculator"].fee_bps_spot,
        recorded["fill_engine"].slippage_bps,
        recorded["event_publisher"] is not None,
    ) == (True, Decimal(8), Decimal(3), True)
