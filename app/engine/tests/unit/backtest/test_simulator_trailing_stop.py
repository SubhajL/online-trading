from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

import app.engine.backtest.simulator as simulator_module
from app.engine.backtest.simulator import BacktestSimulator
from app.engine.backtest.trend_signals import TrendTarget
from app.engine.backtest.types import BacktestConfig, OrderType

from .series import flat_candles, make_candle


def _target(desired: str, entry: str, stop: str) -> TrendTarget:
    return TrendTarget(
        desired=desired,
        entry=Decimal(entry),
        stop_loss=Decimal(stop),
        ready=True,
    )


class _ScriptedEngine:
    """Replays a fixed target per bar; holds the last target once exhausted."""

    def __init__(self, targets: list[TrendTarget]):
        self._targets = list(targets)
        self._index = 0

    def on_bar(self, candle: Any) -> TrendTarget:
        target = self._targets[min(self._index, len(self._targets) - 1)]
        self._index += 1
        return target


def _install_engine(monkeypatch: pytest.MonkeyPatch, targets: list[TrendTarget]) -> None:
    monkeypatch.setattr(
        simulator_module,
        "create_trend_engine",
        lambda config: _ScriptedEngine(targets),
    )


def _trend_config(**overrides: Any) -> BacktestConfig:
    defaults: dict[str, Any] = {
        "signal_source": "price_sma",
        "slippage_bps": Decimal(0),
    }
    defaults.update(overrides)
    return BacktestConfig(**defaults)


async def _run(sim: BacktestSimulator, candles: list) -> None:
    for candle in candles:
        await sim.process_candle(candle)


def _resting_stop(sim: BacktestSimulator):
    return next(o for o in sim.active_orders if o.type == OrderType.STOP_MARKET)


class TestTrailingStop:
    @pytest.mark.asyncio
    async def test_trailing_ratchets_stop_up_on_long(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # atr_stop_mult=2, so target(entry 104, stop 102) implies ATR=1;
        # trail_atr_mult=1 puts the trail at 104 - 1x1 = 103 > initial 98.
        _install_engine(
            monkeypatch,
            [
                _target("LONG", "100", "98"),
                _target("LONG", "100", "98"),
                _target("LONG", "104", "102"),
            ],
        )
        sim = BacktestSimulator(_trend_config(trail_atr_mult=Decimal(1)))
        candles = flat_candles(2)
        candles.append(make_candle(2, "100", "104.5", "99.5", "104"))

        await _run(sim, candles)

        assert _resting_stop(sim).stop_price == Decimal(103)
        assert sim.positions["BTCUSDT"].stop_loss == Decimal(103)

    @pytest.mark.asyncio
    async def test_trailing_never_lowers_a_long_stop(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # After ratcheting to 103, a weaker bar (trail level 102.5) must not
        # loosen the stop back down.
        _install_engine(
            monkeypatch,
            [
                _target("LONG", "100", "98"),
                _target("LONG", "100", "98"),
                _target("LONG", "104", "102"),
                _target("LONG", "103.5", "101.5"),
            ],
        )
        sim = BacktestSimulator(_trend_config(trail_atr_mult=Decimal(1)))
        candles = flat_candles(2)
        candles.append(make_candle(2, "100", "104.5", "99.5", "104"))
        candles.append(make_candle(3, "104", "104.2", "103.2", "103.5"))

        await _run(sim, candles)

        assert _resting_stop(sim).stop_price == Decimal(103)

    @pytest.mark.asyncio
    async def test_trailing_disabled_by_default_keeps_entry_stop(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_engine(
            monkeypatch,
            [
                _target("LONG", "100", "98"),
                _target("LONG", "100", "98"),
                _target("LONG", "104", "102"),
            ],
        )
        sim = BacktestSimulator(_trend_config())
        candles = flat_candles(2)
        candles.append(make_candle(2, "100", "104.5", "99.5", "104"))

        await _run(sim, candles)

        assert _resting_stop(sim).stop_price == Decimal(98)

    @pytest.mark.asyncio
    async def test_trailing_ratchets_stop_down_on_short(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Short entered at 100 with stop 102; target(entry 96, stop 98)
        # implies ATR=1, trail at 96 + 1x1 = 97 < 102 -> tighten to 97.
        _install_engine(
            monkeypatch,
            [
                _target("SHORT", "100", "102"),
                _target("SHORT", "100", "102"),
                _target("SHORT", "96", "98"),
            ],
        )
        sim = BacktestSimulator(
            _trend_config(allow_short=True, trail_atr_mult=Decimal(1)),
        )
        candles = flat_candles(2)
        candles.append(make_candle(2, "100", "100.5", "95.5", "96"))

        await _run(sim, candles)

        assert _resting_stop(sim).stop_price == Decimal(97)

    def test_trailing_with_smc_retest_raises(self) -> None:
        with pytest.raises(ValueError, match="trail_atr_mult"):
            BacktestSimulator(BacktestConfig(trail_atr_mult=Decimal(1)))

    def test_negative_trail_atr_mult_raises(self) -> None:
        # A negative multiplier would fall through the >0 guard and silently
        # disable trailing; reject it instead.
        with pytest.raises(ValueError, match="trail_atr_mult"):
            BacktestSimulator(
                BacktestConfig(signal_source="price_sma", trail_atr_mult=Decimal(-1)),
            )


def test_runner_parses_trail_atr_mult(tmp_path) -> None:
    from app.engine.backtest.runner import BacktestRunner

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "backtest:\n  signal_source: tsmom\n  trail_atr_mult: 1.5\n",
    )

    runner = BacktestRunner(str(config_path))

    assert runner.config.trail_atr_mult == Decimal("1.5")
