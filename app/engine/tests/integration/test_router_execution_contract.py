from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from aiohttp import web
import pytest

from app.engine.adapters.router_client.http_client import RouterHTTPClient
from app.engine.models import RiskParameters
from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    RouterExecutionSubscriber,
)
from app.engine.models import EventType, TimeFrame, TradingDecision, TradingDecisionEvent


class _FakeBus:
    def __init__(self) -> None:
        self.handler: object | None = None

    async def subscribe(
        self,
        subscriber_id: str,
        handler: object,
        event_types: list[EventType] | None = None,
        priority: int = 0,
    ) -> str:
        _ = subscriber_id, event_types, priority
        self.handler = handler
        return "sub-1"

    async def unsubscribe(self, subscription_id: str) -> bool:
        _ = subscription_id
        return True


class _FakeDBAdapter:
    async def get_latest_equity_sample(self):
        return Decimal("10000"), datetime.now(UTC)

    async def get_equity_sample_at_or_after(self, _ts: datetime):
        return Decimal("10000")

    async def get_peak_equity_since(self, _ts: datetime):
        return Decimal("10000")

    async def get_active_positions(self, _venue: str):
        return []


@pytest.mark.asyncio
async def test_contract_decision_to_place_bracket_includes_provenance() -> None:
    captured: dict[str, Any] = {}
    got_request = asyncio.Event()

    async def handle_place_bracket(request: web.Request) -> web.Response:
        nonlocal captured
        captured = await request.json()
        got_request.set()
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_post("/place_bracket", handle_place_bracket)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[attr-defined]
    base_url = f"http://127.0.0.1:{port}"

    router_client = RouterHTTPClient(base_url=base_url)
    await router_client.initialize()

    bus = _FakeBus()
    subscriber = RouterExecutionSubscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=_FakeDBAdapter(),
        risk=RiskParameters(
            max_position_size=Decimal("999999"),
            max_daily_loss=Decimal("1"),
            max_drawdown=Decimal("1"),
            risk_per_trade=Decimal("0.02"),
            max_correlation=Decimal("1"),
            max_open_positions=100,
            max_total_exposure_leverage=Decimal("100"),
            max_symbol_exposure_pct=Decimal("1"),
            max_position_notional_pct=Decimal("1"),
            risk_data_max_age_seconds=86400,
            drawdown_lookback_days=30,
        ),
        venue="USD_M",
        execution_mode=ExecutionMode.FUTURES_TESTNET,
    )
    await subscriber.start()

    now = datetime.now(UTC)
    decision = TradingDecision(
        symbol="BTCUSDT",
        timestamp=now,
        action="BUY",
        entry_price=Decimal(100),
        stop_loss=Decimal(95),
        take_profit=Decimal(110),
        quantity=Decimal("0.01"),
        confidence=Decimal("0.7"),
        reasoning="contract-test",
    )
    event = TradingDecisionEvent(
        symbol="BTCUSDT",
        timestamp=now,
        timeframe=TimeFrame.M5,
        decision=decision,
        metadata={
            "signal_id": "sig-1",
            "decision_source": "retest_decision_publisher",
            "timeframe": "5m",
            "zone": {"kind": "OB"},
        },
    )

    assert callable(bus.handler)
    await bus.handler(event)  # type: ignore[misc]
    await asyncio.wait_for(got_request.wait(), timeout=2)

    assert captured["symbol"] == "BTCUSDT"
    assert captured["side"] == "BUY"
    assert captured["metadata"]["signal_id"] == "sig-1"
    assert captured["metadata"]["timeframe"] == "5m"
    assert captured["metadata"]["zone"]["kind"] == "OB"
    assert captured["metadata"]["decision_source"] == "retest_decision_publisher"

    ids = captured["client_order_ids"]
    assert ids["main"].endswith("_entry")
    assert ids["stop_loss"].endswith("_sl")
    assert ids["take_profits"][0].endswith("_tp1")

    await router_client.close()
    await runner.cleanup()
