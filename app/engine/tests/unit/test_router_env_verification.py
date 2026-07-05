"""
Unit tests for engine↔router execution-environment cross-validation at startup.
"""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import Any

import pytest

from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    OrderUpdateCorrelationStore,
    RouterExecutionSubscriber,
)
from app.engine.models import RiskParameters


class _FakeBus:
    def __init__(self) -> None:
        self.subscriptions: list[dict[str, Any]] = []

    async def subscribe(self, **kwargs: Any) -> str:
        self.subscriptions.append(kwargs)
        return "sub-1"

    async def unsubscribe(self, subscription_id: str) -> None:
        return None


class _FakeRouterClient:
    def __init__(self, health: dict[str, Any] | Exception | None):
        self._health = health

    async def place_bracket_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def health_check(self) -> dict[str, Any]:
        if isinstance(self._health, Exception):
            raise self._health
        return self._health or {}


class _ClientWithoutHealth:
    async def place_bracket_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {}


def _risk() -> RiskParameters:
    return RiskParameters(
        max_position_size=Decimal("999999"),
        max_daily_loss=Decimal("1"),
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


def _subscriber(client: Any, mode: ExecutionMode) -> tuple[RouterExecutionSubscriber, _FakeBus]:
    bus = _FakeBus()
    subscriber = RouterExecutionSubscriber(
        bus=bus,  # type: ignore[arg-type]
        router_client=client,
        db_adapter=object(),  # type: ignore[arg-type]
        risk=_risk(),
        venue="SPOT",
        execution_mode=mode,
        order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
    )
    return subscriber, bus


@pytest.mark.asyncio
async def test_start_aborts_when_testnet_mode_hits_mainnet_router() -> None:
    client = _FakeRouterClient({"status": "healthy", "execution_env": "mainnet"})
    subscriber, bus = _subscriber(client, ExecutionMode.SPOT_TESTNET)

    with pytest.raises(RuntimeError, match="mainnet"):
        await subscriber.start()

    assert bus.subscriptions == []


@pytest.mark.asyncio
async def test_start_aborts_when_mainnet_mode_hits_testnet_router() -> None:
    client = _FakeRouterClient({"status": "healthy", "execution_env": "testnet"})
    subscriber, bus = _subscriber(client, ExecutionMode.SPOT_MAINNET)

    with pytest.raises(RuntimeError, match="testnet"):
        await subscriber.start()

    assert bus.subscriptions == []


@pytest.mark.asyncio
async def test_start_subscribes_when_environments_match() -> None:
    client = _FakeRouterClient({"status": "healthy", "execution_env": "testnet"})
    subscriber, bus = _subscriber(client, ExecutionMode.FUTURES_TESTNET)

    await subscriber.start()

    assert len(bus.subscriptions) == 1


@pytest.mark.asyncio
async def test_start_warns_and_proceeds_when_router_lacks_env_field(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeRouterClient({"status": "healthy"})
    subscriber, bus = _subscriber(client, ExecutionMode.SPOT_TESTNET)

    with caplog.at_level(logging.WARNING):
        await subscriber.start()

    assert (len(bus.subscriptions), "execution env" in caplog.text.lower()) == (1, True)


@pytest.mark.asyncio
async def test_start_warns_and_proceeds_when_router_unreachable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeRouterClient(ConnectionError("refused"))
    subscriber, bus = _subscriber(client, ExecutionMode.SPOT_TESTNET)

    with caplog.at_level(logging.WARNING):
        await subscriber.start()

    assert (len(bus.subscriptions), "unverified" in caplog.text) == (1, True)


@pytest.mark.asyncio
async def test_start_proceeds_when_client_has_no_health_check() -> None:
    subscriber, bus = _subscriber(_ClientWithoutHealth(), ExecutionMode.SPOT_TESTNET)

    await subscriber.start()

    assert len(bus.subscriptions) == 1


@pytest.mark.asyncio
async def test_start_subscribes_when_mainnet_environments_match() -> None:
    client = _FakeRouterClient({"status": "healthy", "execution_env": "mainnet"})
    subscriber, bus = _subscriber(client, ExecutionMode.SPOT_MAINNET)

    await subscriber.start()

    assert len(bus.subscriptions) == 1


@pytest.mark.asyncio
async def test_uppercase_router_env_still_hard_fails_on_mismatch() -> None:
    client = _FakeRouterClient({"status": "healthy", "execution_env": " MAINNET "})
    subscriber, bus = _subscriber(client, ExecutionMode.SPOT_TESTNET)

    with pytest.raises(RuntimeError, match="mainnet"):
        await subscriber.start()

    assert bus.subscriptions == []


class _EventuallyHealthyClient:
    """Router that is still booting for the first probes (compose ordering)."""

    def __init__(self, failures_before_healthy: int, execution_env: str):
        self._remaining_failures = failures_before_healthy
        self._execution_env = execution_env
        self.probes = 0

    async def place_bracket_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def health_check(self) -> dict[str, Any]:
        self.probes += 1
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            return {"status": "unhealthy", "error": "connection refused"}
        return {"status": "healthy", "execution_env": self._execution_env}


@pytest.mark.asyncio
async def test_probe_retries_until_router_boots_then_verifies() -> None:
    client = _EventuallyHealthyClient(failures_before_healthy=2, execution_env="mainnet")
    bus = _FakeBus()
    subscriber = RouterExecutionSubscriber(
        bus=bus,  # type: ignore[arg-type]
        router_client=client,
        db_adapter=object(),  # type: ignore[arg-type]
        risk=_risk(),
        venue="SPOT",
        execution_mode=ExecutionMode.SPOT_TESTNET,
        order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
        router_env_probe_attempts=5,
        router_env_probe_delay_seconds=0,
    )

    with pytest.raises(RuntimeError, match="mainnet"):
        await subscriber.start()

    assert (client.probes, bus.subscriptions) == (3, [])
