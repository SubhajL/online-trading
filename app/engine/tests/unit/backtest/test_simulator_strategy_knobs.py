from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

import app.engine.backtest.simulator as simulator_module
from app.engine.backtest.simulator import BacktestSimulator
from app.engine.backtest.types import BacktestConfig, OrderType

from .series import make_candle


def _signal(
    timestamp: datetime, *, entry: str, stop: str, direction: str = "LONG"
) -> dict[str, Any]:
    e = Decimal(entry)
    s = Decimal(stop)
    risk = abs(e - s)
    sign = Decimal(1) if direction == "LONG" else Decimal(-1)
    return {
        "venue": "SPOT",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "timestamp": timestamp,
        "direction": direction,
        "zone_id": "zone-1",
        "zone_type": "OB_BULL",
        "bos_level": e,
        "entry": e,
        "stop_loss": s,
        "tp1": e + sign * risk * Decimal("1.5"),
        "tp2": e + sign * risk * Decimal(2),
        "tp3": e + sign * risk * Decimal(3),
    }


def _install_signal(
    monkeypatch: pytest.MonkeyPatch, sig: dict[str, Any], fire_at: datetime
) -> None:
    async def fake_analyze(**kwargs: Any) -> dict[str, Any] | None:
        if kwargs["candles"][-1]["open_time"] == fire_at:
            return dict(sig)  # fresh copy; sim mutates stop_loss in place
        return None

    monkeypatch.setattr(simulator_module, "analyze_retest", fake_analyze)


def _ramp_candles(count: int, start: str, end: str) -> list:
    """Linear price ramp so a slow EMA lags the last close in a known direction."""
    s = Decimal(start)
    e = Decimal(end)
    out = []
    for i in range(count):
        px = s + (e - s) * Decimal(i) / Decimal(count - 1)
        p = f"{px:.2f}"
        out.append(make_candle(i, p, f"{px + 1:.2f}", f"{px - 1:.2f}", p))
    return out


class TestHtfTrendGate:
    @pytest.mark.asyncio
    async def test_downtrend_vetoes_long(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Falling prices → slow EMA sits ABOVE the last close → long is counter-trend.
        candles = _ramp_candles(60, "130", "100")
        _install_signal(
            monkeypatch,
            _signal(candles[-1].open_time, entry="100", stop="98"),
            candles[-1].open_time,
        )
        sim = BacktestSimulator(BacktestConfig(htf_ema_period=10, warmup_bars=50))

        for c in candles:
            await sim.process_candle(c)

        market_orders = [o for o in sim.active_orders if o.type == OrderType.MARKET]
        assert market_orders == [], "long against a downtrend must be vetoed by the HTF gate"

    @pytest.mark.asyncio
    async def test_uptrend_allows_long(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Rising prices → slow EMA sits BELOW the last close → long is trend-aligned.
        candles = _ramp_candles(60, "70", "100")
        _install_signal(
            monkeypatch,
            _signal(candles[-1].open_time, entry="100", stop="98"),
            candles[-1].open_time,
        )
        sim = BacktestSimulator(BacktestConfig(htf_ema_period=10, warmup_bars=50))

        for c in candles:
            await sim.process_candle(c)

        market_orders = [o for o in sim.active_orders if o.type == OrderType.MARKET]
        assert len(market_orders) == 1, "a trend-aligned long must pass the HTF gate"

    @pytest.mark.asyncio
    async def test_disabled_gate_allows_counter_trend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        candles = _ramp_candles(60, "130", "100")
        _install_signal(
            monkeypatch,
            _signal(candles[-1].open_time, entry="100", stop="98"),
            candles[-1].open_time,
        )
        sim = BacktestSimulator(BacktestConfig(htf_ema_period=0, warmup_bars=50))  # gate off

        for c in candles:
            await sim.process_candle(c)

        assert len([o for o in sim.active_orders if o.type == OrderType.MARKET]) == 1

    @pytest.mark.asyncio
    async def test_strict_dual_ema_allows_when_stacked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Rising ramp → close > fast EMA > slow EMA → strict long allowed.
        candles = _ramp_candles(70, "70", "100")
        _install_signal(
            monkeypatch,
            _signal(candles[-1].open_time, entry="100", stop="98"),
            candles[-1].open_time,
        )
        sim = BacktestSimulator(BacktestConfig(htf_ema_period=50, htf_ema_fast=10, warmup_bars=50))

        for c in candles:
            await sim.process_candle(c)

        assert len([o for o in sim.active_orders if o.type == OrderType.MARKET]) == 1

    @pytest.mark.asyncio
    async def test_strict_dual_ema_vetoes_when_not_stacked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Falling ramp → close < fast < slow → strict long vetoed.
        candles = _ramp_candles(70, "130", "100")
        _install_signal(
            monkeypatch,
            _signal(candles[-1].open_time, entry="100", stop="98"),
            candles[-1].open_time,
        )
        sim = BacktestSimulator(BacktestConfig(htf_ema_period=50, htf_ema_fast=10, warmup_bars=50))

        for c in candles:
            await sim.process_candle(c)

        assert [o for o in sim.active_orders if o.type == OrderType.MARKET] == []


class TestMinStopFloor:
    @pytest.mark.asyncio
    async def test_tight_stop_is_widened_to_floor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Entry 100, structure stop only 10bps away; floor at 100bps (1%) must widen it to 99.0.
        # Fire one bar before the end so the market entry fills and a position opens.
        candles = _ramp_candles(56, "97", "100")
        _install_signal(
            monkeypatch,
            _signal(candles[-2].open_time, entry="100", stop="99.9"),
            candles[-2].open_time,
        )
        sim = BacktestSimulator(BacktestConfig(min_stop_bps=Decimal(100), warmup_bars=50))

        for c in candles:
            await sim.process_candle(c)

        assert sim.positions["BTCUSDT"].stop_loss == Decimal("99.0")

    @pytest.mark.asyncio
    async def test_wide_stop_is_untouched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Structure stop already 2% away; a 1% floor must not move it.
        candles = _ramp_candles(56, "97", "100")
        _install_signal(
            monkeypatch,
            _signal(candles[-2].open_time, entry="100", stop="98"),
            candles[-2].open_time,
        )
        sim = BacktestSimulator(BacktestConfig(min_stop_bps=Decimal(100), warmup_bars=50))

        for c in candles:
            await sim.process_candle(c)

        assert sim.positions["BTCUSDT"].stop_loss == Decimal("98")

    @pytest.mark.asyncio
    async def test_floor_improves_fee_to_risk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # With the 10% notional cap binding in both cases the notional (and thus
        # fee) is identical, but the floor's wider stop makes the trade RISK more
        # per dollar of fees — the whole point. Assert risked_amount rises.
        candles = _ramp_candles(56, "97", "100")

        _install_signal(
            monkeypatch,
            _signal(candles[-2].open_time, entry="100", stop="99.9"),
            candles[-2].open_time,
        )
        floored = BacktestSimulator(BacktestConfig(min_stop_bps=Decimal(100), warmup_bars=50))
        for c in candles:
            await floored.process_candle(c)

        _install_signal(
            monkeypatch,
            _signal(candles[-2].open_time, entry="100", stop="99.9"),
            candles[-2].open_time,
        )
        unfloored = BacktestSimulator(BacktestConfig(min_stop_bps=Decimal(0), warmup_bars=50))
        for c in candles:
            await unfloored.process_candle(c)

        assert (
            floored.positions["BTCUSDT"].risked_amount
            > unfloored.positions["BTCUSDT"].risked_amount
        )
