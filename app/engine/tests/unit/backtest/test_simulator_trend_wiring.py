from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

import app.engine.backtest.simulator as simulator_module
from app.engine.backtest.simulator import BacktestSimulator
from app.engine.backtest.trend_signals import TrendTarget
from app.engine.backtest.types import BacktestConfig, ExitReason, OrderType

from .series import flat_candles, make_candle


def _long(entry: str = "100", stop: str = "98") -> TrendTarget:
    return TrendTarget(
        desired="LONG",
        entry=Decimal(entry),
        stop_loss=Decimal(stop),
        ready=True,
    )


def _short(entry: str = "100", stop: str = "102") -> TrendTarget:
    return TrendTarget(
        desired="SHORT",
        entry=Decimal(entry),
        stop_loss=Decimal(stop),
        ready=True,
    )


def _flat() -> TrendTarget:
    return TrendTarget(desired="FLAT", ready=True)


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


class TestTrendEntry:
    @pytest.mark.asyncio
    async def test_trend_source_places_market_entry_with_stop_only_bracket(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_engine(monkeypatch, [_long()])
        sim = BacktestSimulator(_trend_config())

        await _run(sim, flat_candles(3))

        position = sim.positions["BTCUSDT"]
        assert position.side == "LONG"
        assert position.quantity > 0
        assert position.stop_loss == Decimal(98)
        assert position.take_profit is None
        resting = [(o.type, o.reduce_only) for o in sim.active_orders]
        assert resting == [(OrderType.STOP_MARKET, True)]

    @pytest.mark.asyncio
    async def test_trend_source_skips_smc_engine_and_analyze_retest(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_engine(monkeypatch, [_long()])
        calls = {"retest": 0, "smc": 0}

        async def counting_retest(**kwargs: Any) -> None:
            calls["retest"] += 1
            return None

        monkeypatch.setattr(simulator_module, "analyze_retest", counting_retest)
        sim = BacktestSimulator(_trend_config(warmup_bars=1))

        async def counting_smc(candle: Any, emit_events: bool = True) -> None:
            calls["smc"] += 1

        sim.smc_engine.process_candle = counting_smc  # type: ignore[method-assign]

        await _run(sim, flat_candles(60))

        assert calls == {"retest": 0, "smc": 0}

    @pytest.mark.asyncio
    async def test_trend_tp_r_positive_places_limit_tp_with_oco(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # risk = 2, trend_tp_r = 1.5 -> TP at 103; TP and stop are OCO-paired.
        _install_engine(monkeypatch, [_long()])
        sim = BacktestSimulator(_trend_config(trend_tp_r=Decimal("1.5")))

        await _run(sim, flat_candles(3))

        stop = next(o for o in sim.active_orders if o.type == OrderType.STOP_MARKET)
        tp = next(o for o in sim.active_orders if o.type == OrderType.LIMIT)
        assert stop.stop_price == Decimal(98)
        assert tp.price == Decimal(103)
        assert sim._oco_pairs[stop.id] == tp.id
        assert sim._oco_pairs[tp.id] == stop.id
        assert sim.positions["BTCUSDT"].take_profit == Decimal(103)

    @pytest.mark.asyncio
    async def test_htf_gate_still_vetoes_counter_trend_entries(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Falling prices keep the slow EMA above the close, so the scripted
        # LONG target must be vetoed by the reused trend-alignment gate.
        _install_engine(monkeypatch, [_long()])
        sim = BacktestSimulator(_trend_config(htf_ema_period=10))
        candles = []
        for i in range(40):
            px = Decimal(130) - Decimal(i)
            candles.append(
                make_candle(i, str(px), str(px + 1), str(px - 1), str(px)),
            )

        await _run(sim, candles)

        assert sim.positions == {}
        assert sim.active_orders == []


class TestFlipAndClose:
    @pytest.mark.asyncio
    async def test_flip_cancels_brackets_closes_then_reverses_next_bar(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_engine(monkeypatch, [_long(), _long(), _short(), _short(), _short()])
        sim = BacktestSimulator(_trend_config(allow_short=True))
        candles = flat_candles(5)

        await _run(sim, candles[:3])
        # At the flip bar the close order must be queued BEFORE the reverse
        # entry, or the entry hits the netting-unsupported branch on fill.
        market_orders = [o for o in sim.active_orders if o.type == OrderType.MARKET]
        assert [(o.reduce_only, o.side.value) for o in market_orders] == [
            (True, "SELL"),
            (False, "SELL"),
        ]
        assert all(o.type != OrderType.STOP_MARKET for o in sim.active_orders)

        await _run(sim, candles[3:])
        assert sim.positions["BTCUSDT"].side == "SHORT"
        assert [t.side for t in sim.completed_trades] == ["long"]

    @pytest.mark.asyncio
    async def test_flip_close_records_exit_reason_flip(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_engine(monkeypatch, [_long(), _long(), _short(), _short()])
        sim = BacktestSimulator(_trend_config(allow_short=True))

        await _run(sim, flat_candles(4))

        assert [t.exit_reason for t in sim.completed_trades] == [ExitReason.FLIP]

    @pytest.mark.asyncio
    async def test_allow_short_false_closes_long_without_reversing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Default long/cash mode: a SHORT target degrades to FLAT — the long
        # is closed but no short entry may ever be placed.
        _install_engine(monkeypatch, [_long(), _long(), _short(), _short()])
        sim = BacktestSimulator(_trend_config())

        await _run(sim, flat_candles(5))

        assert [t.exit_reason for t in sim.completed_trades] == [ExitReason.FLIP]
        assert sim.positions["BTCUSDT"].side is None
        assert sim.active_orders == []
        assert all(t.side == "long" for t in sim.completed_trades)

    @pytest.mark.asyncio
    async def test_stale_stop_cannot_double_fill_after_flip_close(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # After the flip-close cancels the brackets, a bar sweeping the old
        # stop level (98) must not produce a second exit fill: the phantom fee
        # would show up as sim.total_fees > the single trade's fees.
        _install_engine(monkeypatch, [_long(), _long(), _flat(), _flat()])
        sim = BacktestSimulator(_trend_config())
        candles = flat_candles(3)
        candles.append(make_candle(3, "100", "100.5", "97", "100"))

        await _run(sim, candles)

        assert len(sim.completed_trades) == 1
        assert sim.total_fees == sim.completed_trades[0].fees
        assert sim.active_orders == []

    @pytest.mark.asyncio
    async def test_max_hold_bars_closes_position_with_timeout_reason(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install_engine(monkeypatch, [_long()])
        sim = BacktestSimulator(_trend_config(max_hold_bars=2))

        await _run(sim, flat_candles(5))

        assert sim.completed_trades, "the timeout must have closed the position"
        assert sim.completed_trades[0].exit_reason == ExitReason.TIMEOUT


class TestGuardsAndDefaults:
    @pytest.mark.asyncio
    async def test_default_config_still_runs_smc_retest_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls = {"retest": 0}

        async def counting_retest(**kwargs: Any) -> None:
            calls["retest"] += 1
            return None

        monkeypatch.setattr(simulator_module, "analyze_retest", counting_retest)
        sim = BacktestSimulator(BacktestConfig())

        await _run(sim, flat_candles(55))

        assert sim._trend_engine is None
        assert calls["retest"] > 0

    def test_invert_signals_with_trend_source_raises(self) -> None:
        with pytest.raises(ValueError, match="invert_signals"):
            BacktestSimulator(
                BacktestConfig(signal_source="price_sma", invert_signals=True),
            )
