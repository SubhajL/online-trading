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
from app.engine.models import EventType, RetestSignal, RetestSignalEvent, TimeFrame

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

    decision_publisher = DecisionPublisher(
        account_balance=Decimal(10000),
        risk_per_trade=Decimal("0.005"),
    )
    execution = RouterExecutionSubscriber(
        bus=bus,
        router_client=router_client,
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
