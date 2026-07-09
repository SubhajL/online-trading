#!/usr/bin/env python3
"""Track-B bootstrap arm: stationary-bootstrap 95% CI on the Sharpe gap.

Consumes the breadth artifacts (equity.csv per run + the raw kline CSVs) and
reports, per co-primary family and symbol, the annualized
Sharpe(strategy) - Sharpe(buy&hold) point estimate and its 95% stationary
bootstrap interval (paired resampling, mean block 20 daily bars ~ 1 month,
2000 replicates, fixed seed). "CI > 0" means the interval excludes zero.

Usage (repo root): python scripts/dev/run_bootstrap_ci.py
"""

from __future__ import annotations

import csv
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT / "artifacts" / "strategy-runs" / "breadth"
DATA_DIR = ROOT / "data" / "backtest"

CONFIGS = ["nt-tsmom28-100-taker", "nt-sma65-100-taker"]
SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "LTCUSDT",
    "ADAUSDT",
    "SOLUSDT",
    "DOGEUSDT",
]
PERIOD = "1d_20190101_20260630"
BARS_PER_YEAR = 365.0
N_BOOT = 2000
MEAN_BLOCK = 20.0
SEED = 7


def _returns(values: np.ndarray) -> np.ndarray:
    return values[1:] / values[:-1] - 1.0


def _load_equity(path: Path) -> np.ndarray:
    rows = list(csv.DictReader(open(path)))
    return np.array([float(r["equity"]) for r in rows])


def _load_closes(symbol: str) -> np.ndarray:
    rows = list(csv.DictReader(open(DATA_DIR / f"{symbol.lower()}_1d.csv")))
    return np.array([float(r["close"]) for r in rows])


def _load_dates(symbol: str) -> list[str]:
    rows = list(csv.DictReader(open(DATA_DIR / f"{symbol.lower()}_1d.csv")))
    return [r["timestamp"][:10] for r in rows]


def _paired_return_maps(config: str, symbol: str) -> tuple[dict, dict]:
    """Per-bar strategy and benchmark returns keyed by the candle's date."""
    equity = _load_equity(ARTIFACTS_DIR / config / f"{symbol}_{PERIOD}" / "equity.csv")
    closes = _load_closes(symbol)
    if len(equity) != len(closes):
        raise ValueError(
            f"{config} {symbol}: equity bars {len(equity)} != closes {len(closes)}",
        )
    dates = _load_dates(symbol)[1:]
    strategy = dict(zip(dates, _returns(equity), strict=True))
    benchmark = dict(zip(dates, _returns(closes), strict=True))
    return strategy, benchmark


def _aggregate_gap(config: str, sharpe_gap_ci) -> None:
    """Equal-weight cross-asset portfolio (daily rebalanced, symbols enter as
    listed) vs the same-weight buy&hold basket — the literature's actual
    cross-asset claim, with ~n x the per-symbol statistical power."""
    per_symbol = [_paired_return_maps(config, symbol) for symbol in SYMBOLS]
    all_dates = sorted(set().union(*[set(s.keys()) for s, _ in per_symbol]))
    strategy_rows, benchmark_rows = [], []
    for date in all_dates:
        strat = [s[date] for s, _ in per_symbol if date in s]
        bench = [b[date] for _, b in per_symbol if date in b]
        strategy_rows.append(sum(strat) / len(strat))
        benchmark_rows.append(sum(bench) / len(bench))
    ci = sharpe_gap_ci(
        strategy_returns=np.array(strategy_rows),
        benchmark_returns=np.array(benchmark_rows),
        bars_per_year=BARS_PER_YEAR,
        n_boot=N_BOOT,
        mean_block=MEAN_BLOCK,
        seed=SEED,
    )
    print(
        f"| {config} | **EW-8 portfolio** | {ci.point:+.2f} "
        f"| [{ci.lower:+.2f}, {ci.upper:+.2f}] "
        f"| {'YES' if ci.lower > 0 else 'no'} |",
        flush=True,
    )


def main() -> None:
    sys.path.insert(0, str(ROOT))
    from app.engine.backtest.bootstrap import sharpe_gap_ci

    print("| Config | Symbol | Gap (point) | 95% CI | CI > 0 |")
    print("|---|---|---|---|---|")
    for config in CONFIGS:
        for symbol in SYMBOLS:
            strategy, benchmark = _paired_return_maps(config, symbol)
            ci = sharpe_gap_ci(
                strategy_returns=np.array(list(strategy.values())),
                benchmark_returns=np.array(list(benchmark.values())),
                bars_per_year=BARS_PER_YEAR,
                n_boot=N_BOOT,
                mean_block=MEAN_BLOCK,
                seed=SEED,
            )
            print(
                f"| {config} | {symbol} | {ci.point:+.2f} "
                f"| [{ci.lower:+.2f}, {ci.upper:+.2f}] "
                f"| {'YES' if ci.lower > 0 else 'no'} |",
                flush=True,
            )
        _aggregate_gap(config, sharpe_gap_ci)


if __name__ == "__main__":
    main()
