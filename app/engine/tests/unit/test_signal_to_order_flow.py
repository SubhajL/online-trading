from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from aiohttp import web
import pytest

from app.engine import bus as bus_module
from app.engine.adapters.router_client.http_client import RouterHTTPClient
from app.engine.decision.decision_publisher import DecisionPublisher
from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    RouterExecutionSubscriber,
)
from app.engine.models import (
    EventType,
    RetestSignal,
    RetestSignalEvent,
    RiskParameters,
    TimeFrame,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class _InProcBus:
    def __init__(self) -> None:
        self._next_id = 1
        self._subs: dict[str, tuple[list[EventType] | None, Callable[[Any], Awaitable[None]]]] = {}

    async def subscribe(
        self,
        subscriber_id: str,
        handler: object,
        event_types: list[EventType] | None = None,
        priority: int = 0,
        max_retries: int = 0,
    ) -> str:
        _ = subscriber_id, priority, max_retries
        if not callable(handler):
            raise TypeError("handler must be callable")
        sub_id = f"sub-{self._next_id}"
        self._next_id += 1
        self._subs[sub_id] = (event_types, handler)  # type: ignore[assignment]
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        self._subs.pop(subscription_id, None)
        return True

    async def publish(self, event: Any, priority: int = 0) -> bool:
        _ = priority
        for event_types, handler in list(self._subs.values()):
            if event_types is None or getattr(event, "event_type", None) in event_types:
                await handler(event)
        return True


class _FakeDBAdapter:
    async def get_latest_equity_sample(self):
        return Decimal(10_000), datetime.now(UTC)

    async def get_equity_sample_at_or_after(self, _ts: datetime):
        return Decimal(10_000)

    async def get_peak_equity_since(self, _ts: datetime):
        return Decimal(10_000)

    async def get_active_positions(self, _venue: str):
        return []


@pytest.mark.asyncio
async def test_flow_retest_signal_to_router_order() -> None:
    captured: dict[str, Any] = {}
    got_request = asyncio.Event()

    async def handle_place_bracket(request: web.Request) -> web.Response:
        nonlocal captured
        captured = await request.json()
        got_request.set()
        return web.json_response({"success": True})

    app = web.Application()
    app.router.add_post("/place_bracket", handle_place_bracket)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[attr-defined]

    router_client = RouterHTTPClient(base_url=f"http://127.0.0.1:{port}")
    await router_client.initialize()

    bus = _InProcBus()
    previous_bus = getattr(bus_module, "_global_event_bus", None)
    bus_module.set_event_bus(bus)  # DecisionPublisher pulls from global bus

    db_adapter = _FakeDBAdapter()
    risk = RiskParameters(
        max_position_size=Decimal("999999"),
        max_daily_loss=Decimal("1"),
        max_drawdown=Decimal("1"),
        risk_per_trade=Decimal("0.005"),
        max_correlation=Decimal("1"),
        max_open_positions=100,
        max_total_exposure_leverage=Decimal("100"),
        max_symbol_exposure_pct=Decimal("1"),
        max_position_notional_pct=Decimal("1"),
        risk_data_max_age_seconds=86400,
        drawdown_lookback_days=30,
    )

    decision_publisher = DecisionPublisher(
        db_adapter=db_adapter,
        risk=risk,
        venue="USD_M",
    )
    execution = RouterExecutionSubscriber(
        bus=bus,
        router_client=router_client,
        db_adapter=db_adapter,
        risk=risk,
        venue="USD_M",
        execution_mode=ExecutionMode.FUTURES_TESTNET,
    )

    try:
        await decision_publisher.start()
        await execution.start()

        now = datetime.now(UTC)
        signal = RetestSignal(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            timestamp=now,
            level_price=Decimal(100),
            direction="BUY",
            stop_loss=Decimal(95),
            take_profit=Decimal(110),
            retest_type="zone_retest",
            success_probability=Decimal("0.80"),
            volume_confirmation=True,
            confluence_factors=["bos", "rsi_bounce"],
        )
        event = RetestSignalEvent(
            timestamp=now,
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            signal=signal,
            metadata={
                "zone": {"zone_id": "zone-1", "zone_type": "OB"},
                "timeframe": "5m",
            },
        )

        await bus.publish(event)
        await asyncio.wait_for(got_request.wait(), timeout=2)

        assert captured["symbol"] == "BTCUSDT"
        assert captured["side"] == "BUY"
        assert captured["metadata"]["decision_source"] == "retest_decision_publisher"
        assert captured["metadata"]["signal_id"] == str(signal.signal_id)
    finally:
        await decision_publisher.stop()
        await execution.stop()
        await router_client.close()
        await runner.cleanup()
        bus_module._global_event_bus = previous_bus
