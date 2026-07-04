from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

import app.engine.backtest.simulator as simulator_module
from app.engine.backtest.simulator import BacktestSimulator
from app.engine.backtest.types import (
    BacktestConfig,
    ExitReason,
    OrderStatus,
    OrderType,
)

from .series import flat_candles, make_candle
from .test_simulator_signal_gates import make_signal


async def _run_until_entry_filled(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[BacktestSimulator, Any]:
    warmup = flat_candles(51)
    fire_at = warmup[-1].open_time

    async def fake_analyze(**kwargs: Any) -> dict[str, Any] | None:
        if kwargs["candles"][-1]["open_time"] == fire_at:
            return make_signal(fire_at)
        return None

    monkeypatch.setattr(simulator_module, "analyze_retest", fake_analyze)
    simulator = BacktestSimulator(BacktestConfig())

    for candle in warmup:
        await simulator.process_candle(candle)

    fill_bar = make_candle(51, "100", "100.5", "99.5", "100")
    await simulator.process_candle(fill_bar)
    return simulator, fill_bar


@pytest.mark.asyncio
async def test_entry_fills_next_bar_open_plus_slippage_and_places_oco(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator, _ = await _run_until_entry_filled(monkeypatch)

    position = simulator.positions["BTCUSDT"]
    assert (position.side, position.quantity, position.entry_price) == (
        "LONG",
        Decimal(25),
        Decimal("100.03"),
    )
    assert (position.stop_loss, position.take_profit) == (Decimal(98), Decimal(103))
    assert [(order.type, order.side.value) for order in simulator.active_orders] == [
        (OrderType.STOP_MARKET, "SELL"),
        (OrderType.LIMIT, "SELL"),
    ]
    assert simulator._pending_brackets == {}


@pytest.mark.asyncio
async def test_tp_limit_exit_records_tp_cancels_stop_and_deducts_fees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator, _ = await _run_until_entry_filled(monkeypatch)
    stop_order = next(o for o in simulator.active_orders if o.type == OrderType.STOP_MARKET)

    await simulator.process_candle(make_candle(52, "100", "103.5", "99.8", "103"))

    assert len(simulator.completed_trades) == 1
    trade = simulator.completed_trades[0]
    entry_fee = Decimal("100.03") * Decimal(25) * Decimal("0.001")
    exit_fee = Decimal(103) * Decimal(25) * Decimal("0.001")
    gross_pnl = (Decimal(103) - Decimal("100.03")) * Decimal(25)
    stop_distance = Decimal("100.03") - Decimal(98)
    assert (
        trade.exit_reason,
        trade.exit_price,
        trade.entry_price,
        trade.size,
        trade.gross_pnl,
        trade.fees,
        trade.net_pnl,
        trade.gross_pnl_r,
        trade.net_pnl_r,
    ) == (
        ExitReason.TP,
        Decimal(103),
        Decimal("100.03"),
        Decimal(25),
        gross_pnl,
        entry_fee + exit_fee,
        gross_pnl - entry_fee - exit_fee,
        gross_pnl / (stop_distance * Decimal(25)),
        (gross_pnl - entry_fee - exit_fee) / (stop_distance * Decimal(25)),
    )
    assert stop_order.status == OrderStatus.CANCELLED
    assert simulator.active_orders == []
    assert simulator.current_balance == Decimal(10_000) + gross_pnl - entry_fee - exit_fee


@pytest.mark.asyncio
async def test_sl_stop_exit_records_sl_and_cancels_tp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator, _ = await _run_until_entry_filled(monkeypatch)
    tp_order = next(o for o in simulator.active_orders if o.type == OrderType.LIMIT)

    await simulator.process_candle(make_candle(52, "100", "100.5", "97.5", "98.5"))

    assert len(simulator.completed_trades) == 1
    trade = simulator.completed_trades[0]
    expected_exit = Decimal(98) - Decimal(98) * Decimal("0.0002") * Decimal("1.5")
    assert (trade.exit_reason, trade.exit_price) == (ExitReason.SL, expected_exit)
    assert tp_order.status == OrderStatus.CANCELLED
    assert simulator.active_orders == []


@pytest.mark.asyncio
async def test_same_bar_double_touch_is_stop_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulator, _ = await _run_until_entry_filled(monkeypatch)

    await simulator.process_candle(make_candle(52, "100", "103.5", "97.5", "100"))

    assert len(simulator.completed_trades) == 1
    trade = simulator.completed_trades[0]
    assert trade.exit_reason == ExitReason.SL
    assert simulator.active_orders == []
    assert simulator.positions["BTCUSDT"].quantity == Decimal(0)
