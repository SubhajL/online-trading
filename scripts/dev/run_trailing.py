#!/usr/bin/env python3
"""Track-C trailing-stop arm: does an ATR ratchet improve full-notional DD?

Re-runs the two co-primary families at the Track-A decision arm (100%
notional, taker) with trail_atr_mult in {1.5, 2, 3} (ex-ante ladder; 2xATR
initial stop retained). Compare against the no-trail baseline in
2026-07-sizing-arm-results.md.

Usage (repo root):
  python scripts/dev/run_trailing.py generate
  python scripts/dev/run_trailing.py run
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = ROOT / "reports" / "backtest" / "strategies" / "trailing"
ARTIFACTS_DIR = ROOT / "artifacts" / "strategy-runs" / "trailing"
DATA_DIR = ROOT / "data" / "backtest"

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAME = "1d"
START, END = "2019-01-01", "2026-06-30"

FAMILIES = {
    "tsmom28": {"signal_source": "tsmom", "tsmom_lookback": 28, "tsmom_deadband_bps": 0},
    "sma65": {"signal_source": "price_sma", "sma_period": 65},
}
TRAIL_MULTS = ["1.5", "2", "3"]

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


def generate() -> None:
    STRATEGY_DIR.mkdir(parents=True, exist_ok=True)
    for family, signal_fields in FAMILIES.items():
        for mult in TRAIL_MULTS:
            fields = {**_BASE_FIELDS, **signal_fields, "trail_atr_mult": mult}
            lines = [
                f"# Track-C trailing arm (ex-ante): {family}, trail {mult}xATR, "
                "100% notional, taker",
                "backtest:",
            ]
            lines += [f"  {k}: {v}" for k, v in fields.items()]
            name = f"tr-{family}-{mult.replace('.', 'p')}.yaml"
            (STRATEGY_DIR / name).write_text("\n".join(lines) + "\n")
    print(f"wrote {len(FAMILIES) * len(TRAIL_MULTS)} configs to {STRATEGY_DIR}")


def run() -> None:
    sys.path.insert(0, str(ROOT))
    from app.engine.backtest.runner import BacktestRunner

    logging.disable(logging.INFO)
    period = f"{START.replace('-', '')}_{END.replace('-', '')}"
    for config_path in sorted(STRATEGY_DIR.glob("*.yaml")):
        runner = BacktestRunner(str(config_path))
        for symbol in SYMBOLS:
            result = runner.run_backtest(
                symbol=symbol,
                timeframe=TIMEFRAME,
                start_date=START,
                end_date=END,
                data_source="csv",
                data_directory=str(DATA_DIR),
            )
            out_dir = ARTIFACTS_DIR / config_path.stem / f"{symbol}_{TIMEFRAME}_{period}"
            out_dir.mkdir(parents=True, exist_ok=True)
            runner._save_json_report(result, out_dir / "report.json")
            runner._save_trades_csv(result.trades, out_dir / "trades.csv")
            m = result.metrics
            print(
                f"{config_path.stem} {symbol}: ret {float(m.total_pnl_pct):+.1f}% "
                f"dd {float(m.max_drawdown_pct):.1f}% "
                f"sharpe {float(m.sharpe_ratio or 0):.2f} n={m.total_trades} "
                f"exits sl={sum(1 for t in result.trades if t.exit_reason and t.exit_reason.value == 'sl')}",
                flush=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["generate", "run"])
    args = parser.parse_args()
    {"generate": generate, "run": run}[args.command]()


if __name__ == "__main__":
    main()
