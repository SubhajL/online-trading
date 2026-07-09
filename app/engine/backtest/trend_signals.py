"""
Streaming trend-following signal engines for the backtest simulator.

Each engine is a self-contained state machine over closed bars: it owns its
lookback buffers (bounded deques) and an O(1) Wilder ATR, and emits a desired
position state every bar. The simulator diffs that desired state against the
open position, so a blocked entry self-heals on the next bar.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Candle
    from .types import BacktestConfig

LONG = "LONG"
SHORT = "SHORT"
FLAT = "FLAT"


@dataclass(frozen=True)
class TrendTarget:
    """Desired position state for the current bar."""

    desired: str
    entry: Decimal | None = None
    stop_loss: Decimal | None = None
    ready: bool = False


class _StreamingAtr:
    """O(1) Wilder ATR; arithmetic mirrors TechnicalIndicatorsCalculator.atr
    (simple mean of the first N true ranges, then Wilder smoothing) so the
    streaming and batch values match exactly."""

    def __init__(self, period: int):
        self._period = period
        self._prev_close: Decimal | None = None
        self._seed_trs: deque[Decimal] = deque(maxlen=period)
        self._atr: Decimal | None = None

    def update(self, candle: Candle) -> Decimal | None:
        if self._prev_close is None:
            true_range = candle.high_price - candle.low_price
        else:
            true_range = max(
                candle.high_price - candle.low_price,
                abs(candle.high_price - self._prev_close),
                abs(candle.low_price - self._prev_close),
            )
        self._prev_close = candle.close_price

        if self._atr is None:
            self._seed_trs.append(true_range)
            if len(self._seed_trs) == self._period:
                self._atr = sum(self._seed_trs, Decimal(0)) / self._period
        else:
            self._atr = (self._atr * (self._period - 1) + true_range) / self._period
        return self._atr


class _TrendEngineBase:
    """Shared ATR stop construction; subclasses implement the desired-state rule."""

    def __init__(self, config: BacktestConfig):
        self._atr = _StreamingAtr(config.atr_period)
        self._stop_mult = config.atr_stop_mult

    def _target(self, desired: str, close: Decimal, atr: Decimal) -> TrendTarget:
        if desired == FLAT:
            return TrendTarget(desired=FLAT, ready=True)
        offset = self._stop_mult * atr
        stop = close - offset if desired == LONG else close + offset
        return TrendTarget(desired=desired, entry=close, stop_loss=stop, ready=True)

    @staticmethod
    def _warming_up() -> TrendTarget:
        return TrendTarget(desired=FLAT, ready=False)


class PriceSmaEngine(_TrendEngineBase):
    """Long/cash rule: hold while close > SMA(sma_period), else cash. Never short."""

    def __init__(self, config: BacktestConfig):
        super().__init__(config)
        self._period = config.sma_period
        self._closes: deque[Decimal] = deque(maxlen=config.sma_period)

    def on_bar(self, candle: Candle) -> TrendTarget:
        atr = self._atr.update(candle)
        self._closes.append(candle.close_price)
        if len(self._closes) < self._period or atr is None:
            return self._warming_up()
        sma = sum(self._closes, Decimal(0)) / self._period
        desired = LONG if candle.close_price > sma else FLAT
        return self._target(desired, candle.close_price, atr)


class TsmomEngine(_TrendEngineBase):
    """Time-series momentum: sign of the trailing lookback-bar return, with a
    dead-band inside which the previous state is held (hysteresis)."""

    def __init__(self, config: BacktestConfig):
        super().__init__(config)
        self._lookback = config.tsmom_lookback
        self._threshold = config.tsmom_deadband_bps / Decimal(10000)
        self._closes: deque[Decimal] = deque(maxlen=config.tsmom_lookback + 1)
        self._state = FLAT

    def on_bar(self, candle: Candle) -> TrendTarget:
        atr = self._atr.update(candle)
        self._closes.append(candle.close_price)
        if len(self._closes) <= self._lookback or atr is None:
            return self._warming_up()
        trailing_return = candle.close_price / self._closes[0] - 1
        if trailing_return > self._threshold:
            self._state = LONG
        elif trailing_return < -self._threshold:
            self._state = SHORT
        return self._target(self._state, candle.close_price, atr)


class EmaCrossEngine(_TrendEngineBase):
    """Streaming fast/slow EMA cross: LONG while fast > slow, SHORT while below."""

    def __init__(self, config: BacktestConfig):
        super().__init__(config)
        self._fast_period = config.ema_fast
        self._slow_period = config.ema_slow
        self._fast: Decimal | None = None
        self._slow: Decimal | None = None
        self._bars_seen = 0

    @staticmethod
    def _advance(prev: Decimal | None, close: Decimal, period: int) -> Decimal:
        if prev is None:
            return close
        k = Decimal(2) / Decimal(period + 1)
        return close * k + prev * (Decimal(1) - k)

    def on_bar(self, candle: Candle) -> TrendTarget:
        atr = self._atr.update(candle)
        close = candle.close_price
        self._fast = self._advance(self._fast, close, self._fast_period)
        self._slow = self._advance(self._slow, close, self._slow_period)
        self._bars_seen += 1
        if self._bars_seen < self._slow_period or atr is None:
            return self._warming_up()
        if self._fast > self._slow:
            desired = LONG
        elif self._fast < self._slow:
            desired = SHORT
        else:
            desired = FLAT
        return self._target(desired, close, atr)


class DonchianEngine(_TrendEngineBase):
    """Turtle channels: enter on a break of the prior donchian_entry-bar
    extreme, exit on a break of the (shorter) prior donchian_exit-bar extreme.
    Channels exclude the current bar. SHORT states are emitted; the simulator
    enforces allow_short."""

    def __init__(self, config: BacktestConfig):
        super().__init__(config)
        self._entry_n = config.donchian_entry
        self._exit_n = config.donchian_exit
        window = max(config.donchian_entry, config.donchian_exit)
        self._highs: deque[Decimal] = deque(maxlen=window)
        self._lows: deque[Decimal] = deque(maxlen=window)
        self._state = FLAT

    def on_bar(self, candle: Candle) -> TrendTarget:
        atr = self._atr.update(candle)
        close = candle.close_price
        ready = len(self._highs) >= self._entry_n and atr is not None

        if ready:
            highs = list(self._highs)
            lows = list(self._lows)
            if self._state == LONG and close < min(lows[-self._exit_n :]):
                self._state = FLAT
            elif self._state == SHORT and close > max(highs[-self._exit_n :]):
                self._state = FLAT
            if self._state == FLAT:
                if close > max(highs[-self._entry_n :]):
                    self._state = LONG
                elif close < min(lows[-self._entry_n :]):
                    self._state = SHORT

        self._highs.append(candle.high_price)
        self._lows.append(candle.low_price)
        if not ready:
            return self._warming_up()
        assert atr is not None
        return self._target(self._state, close, atr)


TrendEngine = PriceSmaEngine | TsmomEngine | EmaCrossEngine | DonchianEngine

_ENGINES: dict[str, type] = {
    "price_sma": PriceSmaEngine,
    "tsmom": TsmomEngine,
    "ema_cross": EmaCrossEngine,
    "donchian": DonchianEngine,
}


def create_trend_engine(config: BacktestConfig) -> TrendEngine:
    engine_cls = _ENGINES.get(config.signal_source)
    if engine_cls is None:
        raise ValueError(
            f"Unknown trend signal_source {config.signal_source!r}; "
            f"expected one of {sorted(_ENGINES)}",
        )
    return engine_cls(config)
