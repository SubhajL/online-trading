from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter
from app.engine.execution.order_update_correlation import OrderUpdateCorrelationStore
from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    RouterExecutionSubscriber,
)
from app.engine.models import (
    ErrorEvent,
    RiskParameters,
    TimeFrame,
    TradingDecision,
    TradingDecisionEvent,
)
from app.engine.tests.integration.db_config import load_test_database_config


class _CapturingBus:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def subscribe(self, *args, **kwargs) -> str:
        _ = args, kwargs
        return "sub-1"

    async def unsubscribe(self, subscription_id: str) -> bool:
        _ = subscription_id
        return True

    async def publish(self, event: object, priority: int = 0) -> bool:
        _ = priority
        self.published.append(event)
        return True

    async def publish_and_wait(self, event: object, priority: int = 0) -> bool:
        return await self.publish(event, priority)


@pytest.mark.asyncio
async def test_execution_blocks_router_call_when_daily_loss_exceeded() -> None:
    cfg = load_test_database_config()
    db = TimescaleDBAdapter(
        host=cfg.host,
        port=cfg.port,
        database=cfg.database,
        username=cfg.username,
        password=cfg.password,
    )
    await db.initialize()
    try:
        now = datetime.now(UTC).replace(microsecond=0)
        day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)

        async with db.get_write_connection() as conn:
            await conn.execute("TRUNCATE TABLE equity_samples CASCADE")
            await conn.execute(
                "INSERT INTO equity_samples (timestamp, equity) VALUES ($1, $2), ($3, $4)",
                day_start,
                Decimal(10_000),
                now,
                Decimal(9000),
            )

        bus = _CapturingBus()
        router_client = AsyncMock()

        risk = RiskParameters(
            max_position_size=Decimal("999999"),
            max_daily_loss=Decimal("0.05"),
            max_drawdown=Decimal("1"),
            risk_per_trade=Decimal("0.01"),
            max_correlation=Decimal("1"),
            max_open_positions=100,
            max_total_exposure_leverage=Decimal("100"),
            max_symbol_exposure_pct=Decimal("1"),
            max_position_notional_pct=Decimal("1"),
            risk_data_max_age_seconds=86400,
            drawdown_lookback_days=30,
        )

        subscriber = RouterExecutionSubscriber(
            bus=bus,
            router_client=router_client,
            db_adapter=db,
            risk=risk,
            venue="USD_M",
            execution_mode=ExecutionMode.FUTURES_TESTNET,
            order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
            router_max_attempts=1,
        )

        decision = TradingDecision(
            venue="USD_M",
            symbol="BTCUSDT",
            timestamp=now,
            action="BUY",
            entry_price=Decimal(100),
            stop_loss=Decimal(95),
            take_profit=Decimal(110),
            quantity=Decimal("0.01"),
            confidence=Decimal("0.9"),
            reasoning="risk gate test",
        )
        event = TradingDecisionEvent(
            symbol="BTCUSDT",
            timestamp=now,
            timeframe=TimeFrame.M5,
            decision=decision,
            metadata={
                "decision_source": "retest_decision_publisher",
                "signal_id": "sig-1",
            },
        )

        await subscriber._on_trading_decision(event)

        router_client.place_bracket_order.assert_not_awaited()
        assert len(bus.published) == 1
        assert isinstance(bus.published[0], ErrorEvent)
        assert bus.published[0].error_type == "risk_limit_exceeded"
    finally:
        await db.close()
