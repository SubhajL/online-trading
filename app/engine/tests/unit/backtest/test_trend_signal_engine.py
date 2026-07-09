from __future__ import annotations

from collections import deque
from decimal import Decimal

import pytest

from app.engine.backtest.trend_signals import (
    TrendTarget,
    _StreamingAtr,
    create_trend_engine,
)
from app.engine.backtest.types import BacktestConfig
from app.engine.features.indicators import TechnicalIndicatorsCalculator

from .series import make_candle

# high = close+2, low = close-2 with |close step| <= 2 keeps every Wilder TR
# pinned at 4, so ATR stays exactly 4 and stop math is exact in assertions.
_PINNED_ATR = Decimal(4)


def _banded_candles(closes: list[str]) -> list:
    out = []
    for i, close in enumerate(closes):
        c = Decimal(close)
        out.append(make_candle(i, str(c), str(c + 2), str(c - 2), str(c)))
    return out


def _ramp(start: int, step: int, count: int) -> list[str]:
    return [str(start + step * i) for i in range(count)]


def _run(engine, candles) -> list[TrendTarget]:
    return [engine.on_bar(c) for c in candles]


class TestPriceSmaEngine:
    def _engine(self):
        return create_trend_engine(
            BacktestConfig(
                signal_source="price_sma",
                sma_period=4,
                atr_period=3,
                atr_stop_mult=Decimal(2),
            ),
        )

    def test_price_sma_long_when_close_above_sma(self) -> None:
        # Rising ramp: last close 108 > SMA4(105..108) = 106.5 -> long/cash rule fires.
        targets = _run(self._engine(), _banded_candles(_ramp(100, 1, 9)))
        assert targets[-1] == TrendTarget(
            desired="LONG",
            entry=Decimal(108),
            stop_loss=Decimal(108) - Decimal(2) * _PINNED_ATR,
            ready=True,
        )

    def test_price_sma_flat_when_close_below_sma(self) -> None:
        # Falling ramp: close < SMA -> exit to cash; the engine must never
        # emit SHORT (the evidenced form is long/cash).
        targets = _run(self._engine(), _banded_candles(_ramp(110, -1, 9)))
        assert targets[-1] == TrendTarget(
            desired="FLAT",
            entry=None,
            stop_loss=None,
            ready=True,
        )
        assert all(t.desired in {"LONG", "FLAT"} for t in targets)


class TestTsmomEngine:
    def _engine(self, deadband_bps: int = 0):
        return create_trend_engine(
            BacktestConfig(
                signal_source="tsmom",
                tsmom_lookback=4,
                tsmom_deadband_bps=Decimal(deadband_bps),
                atr_period=3,
                atr_stop_mult=Decimal(2),
            ),
        )

    def test_tsmom_goes_long_after_positive_trailing_return(self) -> None:
        targets = _run(self._engine(), _banded_candles(_ramp(100, 1, 8)))
        assert targets[-1] == TrendTarget(
            desired="LONG",
            entry=Decimal(107),
            stop_loss=Decimal(107) - Decimal(2) * _PINNED_ATR,
            ready=True,
        )

    def test_tsmom_deadband_holds_previous_state_in_chop(self) -> None:
        # Strong rise establishes LONG, then a flat stretch puts the trailing
        # return inside the 1% dead-band: hysteresis keeps the LONG state.
        closes = _ramp(100, 2, 6) + ["110"] * 4
        targets = _run(self._engine(deadband_bps=100), _banded_candles(closes))
        assert targets[-1].desired == "LONG"

    def test_tsmom_not_ready_before_lookback_filled(self) -> None:
        # A trailing 4-bar return needs 5 closes; the first 4 bars must stay silent.
        targets = _run(self._engine(), _banded_candles(_ramp(100, 1, 4)))
        assert all(
            t == TrendTarget(desired="FLAT", entry=None, stop_loss=None, ready=False)
            for t in targets
        )


class TestEmaCrossEngine:
    def _engine(self):
        return create_trend_engine(
            BacktestConfig(
                signal_source="ema_cross",
                ema_fast=3,
                ema_slow=6,
                atr_period=3,
                atr_stop_mult=Decimal(2),
            ),
        )

    def test_ema_cross_flips_short_when_fast_crosses_below(self) -> None:
        # Rise then a hard fall: the fast EMA crosses below the slow EMA.
        closes = _ramp(100, 2, 8) + _ramp(112, -2, 8)
        targets = _run(self._engine(), _banded_candles(closes))
        last_close = Decimal(closes[-1])
        assert targets[-1] == TrendTarget(
            desired="SHORT",
            entry=last_close,
            stop_loss=last_close + Decimal(2) * _PINNED_ATR,
            ready=True,
        )

    def test_ema_cross_stop_is_k_atr_below_entry(self) -> None:
        targets = _run(self._engine(), _banded_candles(_ramp(100, 2, 10)))
        last_close = Decimal("118")
        assert targets[-1] == TrendTarget(
            desired="LONG",
            entry=last_close,
            stop_loss=last_close - Decimal(2) * _PINNED_ATR,
            ready=True,
        )


class TestDonchianEngine:
    def _engine(self):
        return create_trend_engine(
            BacktestConfig(
                signal_source="donchian",
                donchian_entry=4,
                donchian_exit=2,
                atr_period=3,
                atr_stop_mult=Decimal(2),
            ),
        )

    def test_donchian_breaks_prior_n_bar_high_excluding_current(self) -> None:
        # Six flat bars pin the prior 4-bar high at 102; the breakout close
        # 102.5 clears it. Were the current bar's own high (104.5) wrongly
        # included in the channel, no breakout would register.
        candles = _banded_candles(["100"] * 6 + ["102.5"])
        engine = self._engine()
        targets = _run(engine, candles)
        breakout_tr = max(
            Decimal(4),  # high-low of the breakout bar
            abs(Decimal("104.5") - Decimal(100)),
            abs(Decimal("100.5") - Decimal(100)),
        )
        expected_atr = (_PINNED_ATR * 2 + breakout_tr) / 3
        assert targets[-1] == TrendTarget(
            desired="LONG",
            entry=Decimal("102.5"),
            stop_loss=Decimal("102.5") - Decimal(2) * expected_atr,
            ready=True,
        )
        assert all(t.desired == "FLAT" for t in targets[:-1])

    def test_donchian_exits_on_exit_channel_break_not_entry_channel(self) -> None:
        # Turtle asymmetry: the LONG exits when close breaks the prior 2-bar
        # low (98) even though it stays above the prior 4-bar low (90). The
        # exit must not flip to SHORT (95 is above the entry channel's low).
        bars = [
            ("100", "102", "90", "100"),
            ("100", "102", "90", "100"),
            ("100", "102", "98", "100"),
            ("100", "102", "98", "100"),
            ("103", "104", "101", "103"),  # close > prior 4-bar high 102 -> LONG
            ("95", "96", "94", "95"),  # close < prior 2-bar low 98 -> FLAT
        ]
        candles = [make_candle(i, *bar) for i, bar in enumerate(bars)]
        engine = self._engine()
        targets = _run(engine, candles)
        assert targets[-2].desired == "LONG"
        assert targets[-1].desired == "FLAT"


class TestStreamingAtr:
    def test_streaming_atr_matches_indicators_batch_atr(self) -> None:
        # Parity invariant against the batch Wilder ATR on an irregular walk.
        closes = [
            "100",
            "103",
            "99",
            "104",
            "101",
            "108",
            "107",
            "95",
            "102",
            "110",
            "109",
            "111",
            "104",
            "106",
            "113",
            "112",
            "108",
            "115",
            "114",
            "118",
        ]
        candles = []
        for i, close in enumerate(closes):
            c = Decimal(close)
            candles.append(
                make_candle(i, str(c), str(c + 3 + (i % 4)), str(c - 2 - (i % 3)), str(c)),
            )
        period = 14
        batch = TechnicalIndicatorsCalculator.atr(candles, period=period)
        streaming_atr = _StreamingAtr(period)
        streamed = [streaming_atr.update(c) for c in candles]
        assert streamed == batch


class TestEngineHousekeeping:
    @pytest.mark.parametrize(
        "source",
        ["price_sma", "tsmom", "ema_cross", "donchian"],
    )
    def test_engine_memory_stays_bounded_at_lookback(self, source: str) -> None:
        # Every internal buffer must be a bounded deque; 300 bars through a
        # <=6-bar-lookback engine cannot grow state.
        engine = create_trend_engine(
            BacktestConfig(
                signal_source=source,
                sma_period=5,
                tsmom_lookback=5,
                ema_fast=3,
                ema_slow=6,
                donchian_entry=5,
                donchian_exit=3,
                atr_period=3,
            ),
        )
        for c in _banded_candles(["100"] * 300):
            engine.on_bar(c)
        buffers = [
            value
            for holder in (engine, *vars(engine).values())
            if hasattr(holder, "__dict__")
            for value in vars(holder).values()
            if isinstance(value, deque)
        ]
        assert buffers, "expected at least one internal deque buffer"
        assert all(b.maxlen is not None and len(b) <= b.maxlen for b in buffers)

    def test_factory_raises_on_unknown_signal_source(self) -> None:
        with pytest.raises(ValueError, match="signal_source"):
            create_trend_engine(BacktestConfig(signal_source="astrology"))
