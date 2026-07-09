#!/usr/bin/env python3
"""Track-B walk-forward arm: does the trend edge depend on the fixed lookback?

For each family (tsmom, price>SMA) and symbol (BTC, ETH), rolls 365d-train /
182d-test windows across 2019-01-01 -> 2026-06-30. In each window the
lookback is chosen on train data only (existing WFORunner composite score,
unmodified), then validated out-of-sample; the SAME window is also run with
the fixed ex-ante lookback (tsmom 28 / sma 65). If the ex-ante number were a
lucky pick, the adaptive arm should beat it and chosen lookbacks should
scatter; stability plus comparable OOS returns is the robustness evidence.

Grids (ex-ante): tsmom_lookback [14, 21, 28, 42, 56] · sma_period
[10, 20, 30, 45, 65, 98]. Sizing: the Track-A decision arm (100% notional,
taker). Test windows include each rule's own warmup, which handicaps longer
lookbacks equally in every arm.

Usage (repo root):
  python scripts/dev/run_wfo_trend.py generate   # write the two WFO YAMLs
  python scripts/dev/run_wfo_trend.py run        # run WFO + fixed arm, print tables
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
WFO_DIR = ROOT / "reports" / "backtest" / "strategies" / "wfo"
ARTIFACTS_DIR = ROOT / "artifacts" / "wfo" / "trend"
DATA_DIR = ROOT / "data" / "backtest"

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAME = "1d"
START, END = "2019-01-01", "2026-06-30"

FAMILIES = [
    ("wfo-tsmom", {"tsmom_lookback": [14, 21, 28, 42, 56]}, {"tsmom_lookback": 28}),
    ("wfo-sma", {"sma_period": [10, 20, 30, 45, 65, 98]}, {"sma_period": 65}),
]

_BASE_FIELDS = {
    "fee_bps_spot": 10,
    "slippage_bps": 2,
    "funding_model": "disabled",
    "allow_short": "false",
    "atr_period": 14,
    "atr_stop_mult": 2,
    "sizing_mode": "notional",
    "notional_pct": 1.0,
    "max_position_notional_pct": 1.0,
    "max_symbol_exposure_pct": 1.0,
    "max_total_exposure_leverage": 3,
}
_WFO_FIELDS = {"train_days": 365, "test_days": 182, "step_days": 182}


def generate() -> None:
    WFO_DIR.mkdir(parents=True, exist_ok=True)
    for name, signal_fields in [
        ("wfo-tsmom", {"signal_source": "tsmom", "tsmom_lookback": 28, "tsmom_deadband_bps": 0}),
        ("wfo-sma", {"signal_source": "price_sma", "sma_period": 65}),
    ]:
        lines = ["# Track-B WFO base config (ex-ante; lookback swept by the grid)", "backtest:"]
        lines += [f"  {k}: {v}" for k, v in {**_BASE_FIELDS, **signal_fields}.items()]
        lines.append("wfo:")
        lines += [f"  {k}: {v}" for k, v in _WFO_FIELDS.items()]
        (WFO_DIR / f"{name}.yaml").write_text("\n".join(lines) + "\n")
    print(f"wrote 2 configs to {WFO_DIR}")


def run() -> None:
    sys.path.insert(0, str(ROOT))
    from app.engine.backtest.wfo import WFORunner

    logging.disable(logging.INFO)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    for name, grid, fixed in FAMILIES:
        param_name = next(iter(grid))
        for symbol in SYMBOLS:
            wfo = WFORunner(str(WFO_DIR / f"{name}.yaml"))
            result = wfo.run_wfo(
                symbol,
                TIMEFRAME,
                START,
                END,
                grid,
                data_source="csv",
                data_directory=str(DATA_DIR),
            )
            fixed_tests = [
                wfo._validate_window(
                    window,
                    symbol,
                    TIMEFRAME,
                    fixed,
                    Decimal(10000),
                    "csv",
                    data_directory=str(DATA_DIR),
                )
                for window in result.windows
            ]

            print(f"\n### {name} {symbol} — {len(result.windows)} windows")
            print(f"| Window (test) | Chosen {param_name} | Adaptive OOS ret% | Fixed({fixed[param_name]}) OOS ret% |")
            print("|---|---|---|---|")
            adaptive, fixed_rets, chosen = [], [], []
            for window, params, test, fixed_test in zip(
                result.windows,
                result.best_parameters,
                result.testing_results,
                fixed_tests,
                strict=True,
            ):
                a = float(test.metrics.total_pnl_pct)
                f = float(fixed_test.metrics.total_pnl_pct)
                adaptive.append(a)
                fixed_rets.append(f)
                chosen.append(params[param_name])
                print(
                    f"| {window.test_start.date()} → {window.test_end.date()} "
                    f"| {params[param_name]} | {a:+.1f} | {f:+.1f} |",
                )
            histogram = {value: chosen.count(value) for value in sorted(set(chosen))}
            summary = {
                "family": name,
                "symbol": symbol,
                "windows": len(result.windows),
                "chosen_histogram": histogram,
                "stability": result.parameter_stability,
                "adaptive_mean_oos_ret_pct": sum(adaptive) / len(adaptive),
                "fixed_mean_oos_ret_pct": sum(fixed_rets) / len(fixed_rets),
                "adaptive_positive_windows": sum(1 for a in adaptive if a > 0),
                "fixed_positive_windows": sum(1 for f in fixed_rets if f > 0),
            }
            (ARTIFACTS_DIR / f"{name}-{symbol}.json").write_text(json.dumps(summary, indent=2))
            print(
                f"chosen {param_name} histogram: {histogram} · stability {result.parameter_stability} · "
                f"mean OOS adaptive {summary['adaptive_mean_oos_ret_pct']:+.1f}% "
                f"vs fixed {summary['fixed_mean_oos_ret_pct']:+.1f}% · "
                f"positive windows {summary['adaptive_positive_windows']} vs "
                f"{summary['fixed_positive_windows']} of {len(result.windows)}",
                flush=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["generate", "run"])
    args = parser.parse_args()
    {"generate": generate, "run": run}[args.command]()


if __name__ == "__main__":
    main()
