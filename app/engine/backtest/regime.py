"""
Pure, testable building blocks for the regime-filter studies (ADX, HMM).

Signal generation (tsmom/SMA long/cash), regime-feature construction, state
labeling, gate application and next-bar-execution net metrics live here so
both study scripts share one verified definition rather than duplicating it.
The stochastic model fitting (hmmlearn) stays in the study script; everything
here is deterministic.
"""

from __future__ import annotations

import math

import numpy as np


def tsmom_positions(closes: np.ndarray, lookback: int = 28) -> np.ndarray:
    """Long/cash: long when the trailing lookback-bar return is positive."""
    pos = np.zeros(len(closes))
    if len(closes) > lookback:
        pos[lookback:] = (closes[lookback:] / closes[:-lookback] - 1.0) > 0
    return pos


def sma_positions(closes: np.ndarray, period: int = 65) -> np.ndarray:
    """Long/cash: long when close is above its trailing SMA(period)."""
    pos = np.zeros(len(closes))
    if len(closes) >= period:
        sma = np.convolve(closes, np.ones(period) / period, mode="valid")
        pos[period - 1 :] = closes[period - 1 :] > sma
    return pos


def regime_features(closes: np.ndarray, vol_window: int) -> np.ndarray:
    """Per-bar [log_return, trailing realized vol] aligned to the bar's close.

    Row i corresponds to close index i+1 (log returns have one fewer element
    than closes). Trailing realized vol is the population std of log returns
    over the last vol_window bars; the first vol_window-1 rows are nan
    (insufficient history) and must be excluded before fitting/gating.
    """
    if len(closes) < 2:
        return np.empty((0, 2))
    log_returns = np.diff(np.log(closes))
    vol = np.full(len(log_returns), np.nan)
    for i in range(vol_window - 1, len(log_returns)):
        window = log_returns[i - vol_window + 1 : i + 1]
        vol[i] = window.std()  # population std (ddof=0)
    return np.column_stack([log_returns, vol])


def label_trend_on_states(state_means: np.ndarray) -> set[int]:
    """State indices whose fitted mean log-return (column 0) is >= 0.

    These are the "hold the long/cash trend position" regimes. Uses only the
    fitted model's means, never future observations.
    """
    return {i for i in range(state_means.shape[0]) if state_means[i, 0] >= 0}


def apply_regime_gate(positions: np.ndarray, in_regime: np.ndarray) -> np.ndarray:
    """Zero out positions on bars whose regime is not trend-on."""
    if len(positions) != len(in_regime):
        raise ValueError(
            f"positions and in_regime must have equal length, "
            f"got {len(positions)} vs {len(in_regime)}",
        )
    return positions * in_regime.astype(float)


def strategy_net_metrics(
    closes: np.ndarray,
    positions: np.ndarray,
    cost_per_side: float,
    bars_per_year: float,
) -> tuple[float, float, float]:
    """(annualized net Sharpe, maxDD %, total return %) for next-bar execution.

    The position decided at bar t is held over bar t+1's return; each change
    in position charges cost_per_side per unit of turnover.
    """
    bar_returns = np.zeros(len(closes))
    bar_returns[1:] = closes[1:] / closes[:-1] - 1.0
    held = np.concatenate([[0.0], positions[:-1]])
    turnover = np.abs(np.diff(np.concatenate([[0.0], positions])))
    strategy = held * bar_returns - turnover * cost_per_side

    equity = np.cumprod(1.0 + strategy)
    peak = np.maximum.accumulate(equity)
    max_dd = float(((peak - equity) / peak).max() * 100.0)
    total_ret = float((equity[-1] - 1.0) * 100.0)
    sharpe = (
        float(strategy.mean() / strategy.std() * math.sqrt(bars_per_year))
        if strategy.std() > 0
        else 0.0
    )
    return sharpe, max_dd, total_ret
