"""
Unit tests for honest trade bookkeeping in the simulator.

Regression coverage for the 2026-07 baseline findings: recorded trade size was
the residual position quantity (Decimal dust after partial exits) while PnL and
fees covered the whole aggregate, poisoning R metrics; fill slippage was never
attributed to trades; and the backtest risk caps did not mirror the live ones.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.engine.backtest.simulator import BacktestSimulator, _BracketSpec
from app.engine.backtest.types import BacktestConfig, BacktestFill, ExitReason, OrderSide
from app.engine.models import Candle, TimeFrame

# Driving simulator internals directly is intentional in these unit tests.
# ruff: noqa: SLF001

FILL_TIME = datetime(2024, 1, 2, tzinfo=UTC)
INITIAL_BALANCE = Decimal(10000)


def _candle(close: str) -> Candle:
    return Candle(
        venue="SPOT",
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
        open_time=FILL_TIME,
        close_time=FILL_TIME,
        open_price=Decimal(close),
        high_price=Decimal(close),
        low_price=Decimal(close),
        close_price=Decimal(close),
        volume=Decimal(10),
        quote_volume=Decimal(1000),
        trades=10,
        taker_buy_base_volume=Decimal(5),
        taker_buy_quote_volume=Decimal(500),
    )


def _fill(
    quantity: str, price: str, side: OrderSide = OrderSide.BUY, slippage: str = "0"
) -> BacktestFill:
    return BacktestFill(
        symbol="BTCUSDT",
        side=side,
        quantity=Decimal(quantity),
        price=Decimal(price),
        slippage=Decimal(slippage),
        fill_time=FILL_TIME,
    )


def _simulator() -> BacktestSimulator:
    return BacktestSimulator(BacktestConfig(), INITIAL_BALANCE)


def test_recorded_size_is_total_entry_quantity_after_partial_exits() -> None:
    simulator = _simulator()
    bracket = _BracketSpec(stop_loss=Decimal(95), take_profit=Decimal(110), direction="LONG")
    simulator._open_position(_fill("1", "100"), _candle("100"), bracket)
    simulator._open_position(_fill("1", "100"), _candle("100"), bracket)

    simulator._close_position(_fill("1", "110", OrderSide.SELL), ExitReason.TP)
    simulator._close_position(_fill("1", "95", OrderSide.SELL), ExitReason.SL)

    assert len(simulator.completed_trades) == 1
    trade = simulator.completed_trades[0]
    # partial TP: +10 on 1 unit; final SL: -5 on remaining 1 unit
    assert (trade.size, trade.gross_pnl) == (Decimal(2), Decimal(5))


def test_r_multiple_uses_entry_quantity_not_residual_dust() -> None:
    simulator = _simulator()
    bracket = _BracketSpec(stop_loss=Decimal(95), take_profit=Decimal(110), direction="LONG")
    simulator._open_position(_fill("1", "100"), _candle("100"), bracket)
    simulator._open_position(_fill("1E-28", "100"), _candle("100"), bracket)

    simulator._close_position(_fill("1", "110", OrderSide.SELL), ExitReason.TP)
    simulator._close_position(_fill("1E-28", "95", OrderSide.SELL), ExitReason.SL)

    trade = simulator.completed_trades[0]
    # risk basis = per-bracket risk (5*1 + 5*1e-28 ≈ 5), not the 1e-28 residual
    assert trade.gross_pnl_r == Decimal(2)


def test_r_multiple_sums_risk_per_bracket_stop() -> None:
    simulator = _simulator()
    simulator._open_position(
        _fill("1", "100"),
        _candle("100"),
        _BracketSpec(stop_loss=Decimal(95), take_profit=Decimal(110), direction="LONG"),
    )
    simulator._open_position(
        _fill("1", "100"),
        _candle("100"),
        _BracketSpec(stop_loss=Decimal(90), take_profit=Decimal(110), direction="LONG"),
    )

    simulator._close_position(_fill("2", "110", OrderSide.SELL), ExitReason.TP)

    trade = simulator.completed_trades[0]
    # gross 20 over summed risk 1*5 + 1*10 = 15
    assert trade.gross_pnl_r == Decimal(20) / Decimal(15)


def test_trade_slippage_is_dollar_cost_per_unit_times_quantity() -> None:
    simulator = _simulator()
    bracket = _BracketSpec(stop_loss=Decimal(95), take_profit=Decimal(110), direction="LONG")
    simulator._open_position(_fill("2", "100", slippage="1.5"), _candle("100"), bracket)

    simulator._close_position(_fill("2", "110", OrderSide.SELL, slippage="2.5"), ExitReason.TP)

    # (1.5 + 2.5 per unit) × 2 units
    assert simulator.completed_trades[0].slippage == Decimal("8.0")


def test_simulator_risk_caps_mirror_live_defaults() -> None:
    simulator = _simulator()

    assert (
        simulator._risk.max_position_notional_pct,
        simulator._risk.max_symbol_exposure_pct,
        simulator._risk.max_open_positions,
    ) == (Decimal("0.10"), Decimal("0.25"), 5)
