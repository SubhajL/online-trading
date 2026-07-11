#!/usr/bin/env python3
"""Track-B breadth arm: the v3 co-primary trend families across 8 symbols.

Runs tsmom28 + sma65 (co-primaries) and sma20 (watch-only) at the Track-A
decision arm (100% notional, taker fees — reports/backtest/strategies/sizing/
nt-*-100-taker.yaml) over every long-history USDT pair we hold daily data
for. Trend-following is a cross-asset claim; 6-8 passing symbols is the
evidence 2 symbols cannot provide. Ex-ante params, no per-symbol tuning.

Also writes equity.csv (close_time,equity) and closes.csv per run so the
bootstrap-CI step can consume per-bar strategy and benchmark returns without
re-running.

Usage (repo root):
  python scripts/dev/run_breadth.py run
  python scripts/dev/run_breadth.py summarize
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = ROOT / "reports" / "backtest" / "strategies" / "sizing"
ARTIFACTS_DIR = ROOT / "artifacts" / "strategy-runs" / "breadth"
DATA_DIR = ROOT / "data" / "backtest"

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
CONFIGS = ["nt-tsmom28-100-taker", "nt-sma65-100-taker", "nt-sma20-100-taker"]
TIMEFRAME = "1d"
START, END = "2019-01-01", "2026-06-30"


def run() -> None:
    sys.path.insert(0, str(ROOT))
    from app.engine.backtest.runner import BacktestRunner

    logging.disable(logging.INFO)
    period = f"{START.replace('-', '')}_{END.replace('-', '')}"
    for config_name in CONFIGS:
        runner = BacktestRunner(str(STRATEGY_DIR / f"{config_name}.yaml"))
        for symbol in SYMBOLS:
            result = runner.run_backtest(
                symbol=symbol,
                timeframe=TIMEFRAME,
                start_date=START,
                end_date=END,
                data_source="csv",
                data_directory=str(DATA_DIR),
            )
            out_dir = ARTIFACTS_DIR / config_name / f"{symbol}_{TIMEFRAME}_{period}"
            out_dir.mkdir(parents=True, exist_ok=True)
            runner._save_json_report(result, out_dir / "report.json")
            runner._save_trades_csv(result.trades, out_dir / "trades.csv")
            with open(out_dir / "equity.csv", "w") as fh:
                fh.write("close_time,equity\n")
                for ts, equity in result.equity_curve:
                    fh.write(f"{ts.isoformat()},{equity}\n")
            m = result.metrics
            print(
                f"{config_name} {symbol}: ret {float(m.total_pnl_pct):+.1f}% "
                f"dd {float(m.max_drawdown_pct):.1f}% "
                f"sharpe {float(m.sharpe_ratio or 0):.2f} n={m.total_trades} "
                f"| B&H {float(m.benchmark_return_pct):+.1f}% "
                f"dd {float(m.benchmark_max_drawdown_pct):.1f}% "
                f"shp {float(m.benchmark_sharpe_ratio or 0):.2f}",
                flush=True,
            )


def summarize() -> None:
    print(
        "| Config | Symbol | Ret% | DD% | Sharpe | N | B&H Ret% | B&H DD% | "
        "B&H Shp | G1 | G2 | G3 |",
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    passes: dict[str, list[str]] = {}
    for report_path in sorted(ARTIFACTS_DIR.glob("*/*/report.json")):
        report = json.loads(report_path.read_text())
        m = report["metrics"]
        config = report_path.parent.parent.name
        symbol = report_path.parent.name.split("_")[0]
        sharpe = m["sharpe_ratio"] or 0.0
        bench_sharpe = m["benchmark_sharpe_ratio"]
        gate1 = bench_sharpe is not None and sharpe >= 0.9 * bench_sharpe
        gate2 = m["max_drawdown_pct"] <= 0.8 * m["benchmark_max_drawdown_pct"]
        gate3 = m["total_pnl_pct"] >= 0.75 * m["benchmark_return_pct"]
        if gate1:
            passes.setdefault(config, []).append(symbol)
        print(
            f"| {config} | {symbol} | {m['total_pnl_pct']:+.1f} "
            f"| {m['max_drawdown_pct']:.1f} | {sharpe:.2f} | {m['total_trades']} "
            f"| {m['benchmark_return_pct']:+.1f} | {m['benchmark_max_drawdown_pct']:.1f} "
            f"| {bench_sharpe:.2f} | {'P' if gate1 else 'f'} "
            f"| {'P' if gate2 else 'f'} | {'P' if gate3 else 'f'} |",
        )
    print()
    for config, symbols in sorted(passes.items()):
        print(f"{config}: G1 (Sharpe >= 0.9x B&H) passes on {len(symbols)}/8 — {', '.join(symbols)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "summarize"])
    args = parser.parse_args()
    {"run": run, "summarize": summarize}[args.command]()


if __name__ == "__main__":
    main()
