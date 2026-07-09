from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

import app.engine.backtest.simulator as simulator_module
from app.engine.backtest.simulator import BacktestSimulator
from app.engine.backtest.trend_signals import TrendTarget
from app.engine.backtest.types import BacktestConfig

from .series import flat_candles


def _long(entry: str = "100", stop: str = "98") -> TrendTarget:
    return TrendTarget(
        desired="LONG",
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


class TestNotionalSizing:
    @pytest.mark.asyncio
    async def test_notional_mode_sizes_qty_as_equity_fraction_over_entry(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # 10000 equity * 0.5 notional / 100 entry = 50 units
        _install_engine(monkeypatch, [_long()])
        sim = BacktestSimulator(
            _trend_config(
                sizing_mode="notional",
                notional_pct=Decimal("0.5"),
                max_position_notional_pct=Decimal(1),
                max_symbol_exposure_pct=Decimal(1),
            ),
        )

        await _run(sim, flat_candles(3))

        assert sim.positions["BTCUSDT"].quantity == Decimal(50)

    @pytest.mark.asyncio
    async def test_notional_mode_is_clamped_by_configured_caps(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Full notional requested but the default 10% position cap re-binds:
        # 10000 * 0.10 / 100 entry = 10 units
        _install_engine(monkeypatch, [_long()])
        sim = BacktestSimulator(
            _trend_config(sizing_mode="notional", notional_pct=Decimal(1)),
        )

        await _run(sim, flat_candles(3))

        assert sim.positions["BTCUSDT"].quantity == Decimal(10)


class TestVolTargetSizing:
    @pytest.mark.asyncio
    async def test_vol_target_sizes_from_realized_vol(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # 40% target / 100% realized vol -> 0.4 weight -> 10000 * 0.4 / 100 = 40
        _install_engine(monkeypatch, [_long()])
        monkeypatch.setattr(
            simulator_module,
            "annualized_volatility",
            lambda closes, bars_per_year: Decimal(1),
        )
        sim = BacktestSimulator(
            _trend_config(
                sizing_mode="vol_target",
                vol_target_annual_pct=Decimal(40),
                vol_lookback_bars=2,
                max_position_notional_pct=Decimal(1),
                max_symbol_exposure_pct=Decimal(1),
            ),
        )

        await _run(sim, flat_candles(6))

        assert sim.positions["BTCUSDT"].quantity == Decimal(40)

    @pytest.mark.asyncio
    async def test_vol_target_skips_entry_without_enough_history(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_engine(monkeypatch, [_long()])
        sim = BacktestSimulator(
            _trend_config(
                sizing_mode="vol_target",
                vol_target_annual_pct=Decimal(40),
                vol_lookback_bars=5,
                max_position_notional_pct=Decimal(1),
                max_symbol_exposure_pct=Decimal(1),
            ),
        )

        await _run(sim, flat_candles(3))

        assert sim.positions == {}
        assert sim.active_orders == []

    @pytest.mark.asyncio
    async def test_vol_target_skips_entry_on_zero_realized_vol(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Flat closes -> realized vol 0 -> weight undefined -> no entry, ever.
        _install_engine(monkeypatch, [_long()])
        sim = BacktestSimulator(
            _trend_config(
                sizing_mode="vol_target",
                vol_target_annual_pct=Decimal(40),
                vol_lookback_bars=3,
                max_position_notional_pct=Decimal(1),
                max_symbol_exposure_pct=Decimal(1),
            ),
        )

        await _run(sim, flat_candles(10))

        assert sim.positions == {}
        assert sim.active_orders == []


class TestSizingValidationAndDefaults:
    @pytest.mark.asyncio
    async def test_default_risk_mode_preserves_fixed_fractional_sizing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # 10000 * 0.005 risk / 2 stop distance = 25, clamped by the 10%
        # notional cap to 10000 * 0.10 / 100 = 10 — the historical sizing.
        _install_engine(monkeypatch, [_long()])
        sim = BacktestSimulator(_trend_config())

        await _run(sim, flat_candles(3))

        assert sim.positions["BTCUSDT"].quantity == Decimal(10)

    def test_non_risk_sizing_with_smc_retest_raises(self) -> None:
        with pytest.raises(ValueError, match="sizing_mode"):
            BacktestSimulator(BacktestConfig(sizing_mode="notional"))

    def test_unknown_sizing_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="sizing_mode"):
            BacktestSimulator(
                BacktestConfig(signal_source="price_sma", sizing_mode="kelly"),
            )

    def test_vol_target_requires_positive_target(self) -> None:
        with pytest.raises(ValueError, match="vol_target_annual_pct"):
            BacktestSimulator(
                BacktestConfig(
                    signal_source="price_sma",
                    sizing_mode="vol_target",
                    vol_target_annual_pct=Decimal(0),
                ),
            )

    @pytest.mark.parametrize("vol_lookback_bars", [1, 200])
    def test_vol_target_rejects_lookback_outside_candle_buffer(
        self,
        vol_lookback_bars: int,
    ) -> None:
        # Outside [2, 199] the buffer can never supply lookback+1 closes and
        # the arm would silently never trade — fail loudly at construction.
        with pytest.raises(ValueError, match="vol_lookback_bars"):
            BacktestSimulator(
                BacktestConfig(
                    signal_source="price_sma",
                    sizing_mode="vol_target",
                    vol_target_annual_pct=Decimal(40),
                    vol_lookback_bars=vol_lookback_bars,
                ),
            )

    def test_caps_flow_from_config_into_risk_parameters(self) -> None:
        sim = BacktestSimulator(
            BacktestConfig(
                signal_source="price_sma",
                max_position_notional_pct=Decimal(1),
                max_symbol_exposure_pct=Decimal("0.8"),
                max_total_exposure_leverage=Decimal(2),
            ),
        )

        assert (
            sim._risk.max_position_notional_pct,
            sim._risk.max_symbol_exposure_pct,
            sim._risk.max_total_exposure_leverage,
        ) == (Decimal(1), Decimal("0.8"), Decimal(2))
