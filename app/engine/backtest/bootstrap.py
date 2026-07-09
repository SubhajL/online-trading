"""
Stationary-bootstrap (Politis-Romano 1994) confidence intervals for the
strategy-minus-benchmark annualized Sharpe gap.

Indices are resampled once per replicate and applied to BOTH return series
(paired resampling), preserving their cross-correlation — the quantity under
test is the gap, not each Sharpe in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class SharpeGapCI:
    point: float
    lower: float
    upper: float
    n_boot: int
    mean_block: float
    confidence: float


def stationary_bootstrap_indices(
    n: int,
    mean_block: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Index sequence of length n built from geometric-length blocks
    (mean mean_block) with circular wraparound."""
    restart = rng.random(n) < 1.0 / mean_block
    restart[0] = True
    starts = rng.integers(0, n, size=n)
    last_restart = np.maximum.accumulate(np.where(restart, np.arange(n), -1))
    return (starts[last_restart] + np.arange(n) - last_restart) % n


def _annualized_sharpe(returns: np.ndarray, bars_per_year: float) -> float:
    std = returns.std()
    if std == 0:
        return 0.0
    return float(returns.mean() / std * math.sqrt(bars_per_year))


def sharpe_gap_ci(
    *,
    strategy_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    bars_per_year: float,
    n_boot: int = 2000,
    mean_block: float = 20.0,
    confidence: float = 0.95,
    seed: int = 0,
) -> SharpeGapCI:
    strategy = np.asarray(strategy_returns, dtype=np.float64)
    benchmark = np.asarray(benchmark_returns, dtype=np.float64)
    if strategy.shape != benchmark.shape or strategy.ndim != 1:
        raise ValueError(
            f"strategy and benchmark returns must be 1-d of equal length, "
            f"got {strategy.shape} vs {benchmark.shape}",
        )
    if strategy.shape[0] < 2:
        raise ValueError(
            f"need at least 2 observations to form a Sharpe, got {strategy.shape[0]}",
        )
    if n_boot < 1:
        raise ValueError(f"n_boot must be positive, got {n_boot}")
    if mean_block < 1:
        raise ValueError(f"mean_block must be >= 1, got {mean_block}")

    point = _annualized_sharpe(strategy, bars_per_year) - _annualized_sharpe(
        benchmark,
        bars_per_year,
    )

    rng = np.random.default_rng(seed)
    n = strategy.shape[0]
    gaps = np.empty(n_boot)
    for i in range(n_boot):
        idx = stationary_bootstrap_indices(n, mean_block, rng)
        gaps[i] = _annualized_sharpe(strategy[idx], bars_per_year) - _annualized_sharpe(
            benchmark[idx],
            bars_per_year,
        )

    alpha = (1.0 - confidence) / 2.0
    return SharpeGapCI(
        point=point,
        lower=float(np.quantile(gaps, alpha)),
        upper=float(np.quantile(gaps, 1.0 - alpha)),
        n_boot=n_boot,
        mean_block=mean_block,
        confidence=confidence,
    )
