from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

import app.engine.backtest.simulator as simulator_module
from app.engine.backtest.simulator import BacktestSimulator
from app.engine.backtest.types import BacktestConfig, OrderSide, OrderType

from .series import flat_candles


def make_signal(timestamp: datetime, *, zone_id: str = "zone-1") -> dict[str, Any]:
    return {
        "venue": "SPOT",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "timestamp": timestamp,
        "direction": "LONG",
        "zone_id": zone_id,
        "zone_type": "OB_BULL",
        "bos_level": Decimal(103),
        "entry": Decimal(100),
        "stop_loss": Decimal(98),
        "tp1": Decimal(103),
        "tp2": Decimal(104),
        "tp3": Decimal(106),
    }


def _install_fake_analyze(
    monkeypatch: pytest.MonkeyPatch,
    fire_at: set[datetime],
) -> None:
    async def fake_analyze(**kwargs: Any) -> dict[str, Any] | None:
        open_time = kwargs["candles"][-1]["open_time"]
        if open_time in fire_at:
            return make_signal(open_time)
        return None

    monkeypatch.setattr(simulator_module, "analyze_retest", fake_analyze)


@pytest.mark.asyncio
async def test_signal_places_market_order_sized_fixed_fractional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candles = flat_candles(51)
    _install_fake_analyze(monkeypatch, {candles[-1].open_time})
    simulator = BacktestSimulator(BacktestConfig())

    for candle in candles:
        await simulator.process_candle(candle)

    market_orders = [order for order in simulator.active_orders if order.type == OrderType.MARKET]
    assert len(market_orders) == 1
    order = market_orders[0]
    assert (order.symbol, order.side, order.quantity) == ("BTCUSDT", OrderSide.BUY, Decimal(25))
    bracket = simulator._pending_brackets[order.id]
    assert (bracket.stop_loss, bracket.take_profit, bracket.direction) == (
        Decimal(98),
        Decimal(103),
        "LONG",
    )


@pytest.mark.asyncio
async def test_cooldown_blocks_identical_second_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candles = flat_candles(53)
    _install_fake_analyze(monkeypatch, {candles[-2].open_time, candles[-1].open_time})
    simulator = BacktestSimulator(BacktestConfig(cooldown_seconds=3600))

    for candle in candles:
        await simulator.process_candle(candle)

    assert [order.type for order in simulator.active_orders] == [
        OrderType.STOP_MARKET,
        OrderType.LIMIT,
    ]
    assert simulator._pending_brackets == {}
    assert simulator.positions["BTCUSDT"].quantity == Decimal(25)


@pytest.mark.asyncio
async def test_cooldown_uses_simulated_clock_and_expires_across_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candles = flat_candles(53)
    _install_fake_analyze(monkeypatch, {candles[-2].open_time, candles[-1].open_time})
    simulator = BacktestSimulator(BacktestConfig(cooldown_seconds=300))

    for candle in candles:
        await simulator.process_candle(candle)

    assert sorted(order.type.value for order in simulator.active_orders) == [
        "LIMIT",
        "MARKET",
        "STOP_MARKET",
    ]
    assert len(simulator._pending_brackets) == 1


@pytest.mark.asyncio
async def test_pretrade_risk_gate_blocks_order_placement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candles = flat_candles(51)
    _install_fake_analyze(monkeypatch, {candles[-1].open_time})
    monkeypatch.setattr(
        simulator_module,
        "evaluate_pretrade_risk",
        lambda **kwargs: (False, ["blocked"]),
    )
    simulator = BacktestSimulator(BacktestConfig())

    for candle in candles:
        await simulator.process_candle(candle)

    assert simulator.active_orders == []
    assert simulator._pending_brackets == {}
