#!/usr/bin/env python3
"""Track-C regime-filter study: does an ADX gate improve the co-primaries?

Open question from the research pass (zero regime claims survived
verification) — tested, not adopted by default. Vectorized study: both the
gated and ungated arms use the same approximation (signal at close t ->
position over bar t+1, 13bps per side), so the DELTAS are apples-to-apples
even though absolute levels differ slightly from the event engine.

Gate: hold the trend position only when Wilder ADX(14) >= threshold,
thresholds {15, 20, 25, 30}; an inverted gate (ADX < threshold) is run as a
falsification check. Ex-ante adoption bar: gated net Sharpe >= ungated +0.1
on BOTH symbols at some threshold without a worse maxDD. HMM regimes:
deferred (no hmmlearn in the environment; model design would need its own
pre-registration).

Usage (repo root): python scripts/dev/run_regime_study.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "backtest"

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
THRESHOLDS = [15, 20, 25, 30]
ADX_PERIOD = 14
COST_PER_SIDE = 0.0013  # 10bps taker fee + ~3bps slippage, matching the event engine arm
BARS_PER_YEAR = 365.0


def _load_ohlc(symbol: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = list(csv.DictReader(open(DATA_DIR / f"{symbol.lower()}_1d.csv")))
    high = np.array([float(r["high"]) for r in rows])
    low = np.array([float(r["low"]) for r in rows])
    close = np.array([float(r["close"]) for r in rows])
    return high, low, close


def wilder_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    up = high[1:] - high[:-1]
    down = low[:-1] - low[1:]
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])),
    )

    def wilder_smooth(values: np.ndarray) -> np.ndarray:
        smoothed = np.full(len(values), np.nan)
        if len(values) < period:
            return smoothed
        acc = values[:period].sum()
        smoothed[period - 1] = acc
        for i in range(period, len(values)):
            acc = acc - acc / period + values[i]
            smoothed[i] = acc
        return smoothed

    atr = wilder_smooth(tr)
    plus_di = 100.0 * wilder_smooth(plus_dm) / atr
    minus_di = 100.0 * wilder_smooth(minus_dm) / atr
    dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di)

    adx = np.full(len(dx), np.nan)
    valid_start = 2 * period - 2
    if len(dx) > valid_start + period:
        adx[valid_start + period - 1] = np.nanmean(dx[valid_start : valid_start + period])
        for i in range(valid_start + period, len(dx)):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period
    return np.concatenate([[np.nan], adx])  # re-align to close index


def tsmom_positions(close: np.ndarray, lookback: int = 28) -> np.ndarray:
    pos = np.zeros(len(close))
    pos[lookback:] = (close[lookback:] / close[:-lookback] - 1.0) > 0
    return pos


def sma_positions(close: np.ndarray, period: int = 65) -> np.ndarray:
    pos = np.zeros(len(close))
    kernel = np.ones(period) / period
    sma = np.convolve(close, kernel, mode="valid")
    pos[period - 1 :] = close[period - 1 :] > sma
    return pos


def net_metrics(close: np.ndarray, positions: np.ndarray) -> tuple[float, float, float]:
    """(annualized net Sharpe, maxDD %, total return %) for next-bar execution."""
    bar_returns = np.zeros(len(close))
    bar_returns[1:] = close[1:] / close[:-1] - 1.0
    held = np.concatenate([[0.0], positions[:-1]])
    turnover = np.abs(np.diff(np.concatenate([[0.0], positions])))
    strategy = held * bar_returns - turnover * COST_PER_SIDE
    equity = np.cumprod(1.0 + strategy)
    peak = np.maximum.accumulate(equity)
    max_dd = float(((peak - equity) / peak).max() * 100.0)
    total_ret = float((equity[-1] - 1.0) * 100.0)
    sharpe = (
        float(strategy.mean() / strategy.std() * np.sqrt(BARS_PER_YEAR))
        if strategy.std() > 0
        else 0.0
    )
    return sharpe, max_dd, total_ret


def main() -> None:
    families = {"tsmom28": tsmom_positions, "sma65": sma_positions}
    print("| Family | Symbol | Arm | Sharpe | maxDD% | Ret% |")
    print("|---|---|---|---|---|---|")
    for family, signal_fn in families.items():
        for symbol in SYMBOLS:
            high, low, close = _load_ohlc(symbol)
            base_pos = signal_fn(close)
            adx = wilder_adx(high, low, close, ADX_PERIOD)
            sharpe, dd, ret = net_metrics(close, base_pos)
            print(f"| {family} | {symbol} | ungated | {sharpe:.2f} | {dd:.1f} | {ret:+.1f} |")
            for threshold in THRESHOLDS:
                gate = np.nan_to_num(adx, nan=0.0) >= threshold
                sharpe_g, dd_g, ret_g = net_metrics(close, base_pos * gate)
                print(
                    f"| {family} | {symbol} | ADX>={threshold} "
                    f"| {sharpe_g:.2f} | {dd_g:.1f} | {ret_g:+.1f} |",
                )
            inverted = np.nan_to_num(adx, nan=0.0) < 25
            sharpe_i, dd_i, ret_i = net_metrics(close, base_pos * inverted)
            print(
                f"| {family} | {symbol} | ADX<25 (falsif.) "
                f"| {sharpe_i:.2f} | {dd_i:.1f} | {ret_i:+.1f} |",
                flush=True,
            )


if __name__ == "__main__":
    main()
