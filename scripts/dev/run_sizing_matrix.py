#!/usr/bin/env python3
"""Track-A sizing-arm matrix: notional 25/50/100% + vol-target ladder.

The v3 trend results (reports/backtest/2026-07-trend-signals-v3-results.md)
were exposure-confounded: fixed-fractional risk sizing plus the hardcoded 10%
notional cap kept mean deployment at 6.5-9% of equity, so the return gate was
unreachable by construction. This matrix re-runs the six v3 daily families at
comparable exposure using the sizing_mode knobs from PR #204.

Usage (from repo root, app/engine venv):
  python scripts/dev/run_sizing_matrix.py generate   # write ex-ante YAMLs (commit BEFORE running)
  python scripts/dev/run_sizing_matrix.py run        # run all configs x symbols -> artifacts
  python scripts/dev/run_sizing_matrix.py summarize  # markdown table + gate evaluation
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
STRATEGY_DIR = ROOT / "reports" / "backtest" / "strategies" / "sizing"
ARTIFACTS_DIR = ROOT / "artifacts" / "strategy-runs" / "sizing"
DATA_DIR = ROOT / "data" / "backtest"

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAME = "1d"
START, END = "2019-01-01", "2026-06-30"
INITIAL = 10000.0

# Same six ex-ante daily families as the v3 primary arm — no re-tuning.
FAMILIES: dict[str, dict] = {
    "tsmom28": {"signal_source": "tsmom", "tsmom_lookback": 28, "tsmom_deadband_bps": 0},
    "sma20": {"signal_source": "price_sma", "sma_period": 20},
    "sma65": {"signal_source": "price_sma", "sma_period": 65},
    "sma200": {"signal_source": "price_sma", "sma_period": 200},
    "cross-10-40": {"signal_source": "ema_cross", "ema_fast": 10, "ema_slow": 40},
    "donch-20-10": {"signal_source": "donchian", "donchian_entry": 20, "donchian_exit": 10},
}
FEES_BPS = {"taker": 10, "maker": 4}
NOTIONAL_PCTS = ["0.25", "0.5", "1.0"]
VT_FAMILIES = ["tsmom28", "sma20", "sma65"]  # v3 passing set only
VT_TARGETS = [20, 30, 40]  # annual vol %, taker fees, vol_lookback_bars=20 ex-ante

# Caps lifted so the requested notional is actually reachable; the 1.0
# notional cap doubles as the no-leverage clamp for the vol-target arm
# (long/cash spot semantics).
COMMON = {
    "slippage_bps": 2,
    "funding_model": "disabled",
    "allow_short": "false",
    "atr_period": 14,
    "atr_stop_mult": 2,
    "max_position_notional_pct": 1.0,
    "max_symbol_exposure_pct": 1.0,
    "max_total_exposure_leverage": 3,
}


def _yaml_text(header: str, fields: dict) -> str:
    lines = [f"# {header}", "backtest:"]
    lines += [f"  {key}: {value}" for key, value in fields.items()]
    return "\n".join(lines) + "\n"


def generate() -> None:
    STRATEGY_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for family, family_fields in FAMILIES.items():
        for fee_name, fee_bps in FEES_BPS.items():
            for pct in NOTIONAL_PCTS:
                fields = {
                    "fee_bps_spot": fee_bps,
                    **COMMON,
                    **family_fields,
                    "sizing_mode": "notional",
                    "notional_pct": pct,
                }
                name = f"nt-{family}-{int(float(pct) * 100)}-{fee_name}.yaml"
                header = (
                    f"sizing arm (ex-ante): {family}, {int(float(pct) * 100)}% notional, "
                    f"{fee_name} fees, daily long/cash"
                )
                (STRATEGY_DIR / name).write_text(_yaml_text(header, fields))
                count += 1
    for family in VT_FAMILIES:
        for target in VT_TARGETS:
            fields = {
                "fee_bps_spot": FEES_BPS["taker"],
                **COMMON,
                **FAMILIES[family],
                "sizing_mode": "vol_target",
                "vol_target_annual_pct": target,
                "vol_lookback_bars": 20,
            }
            name = f"vt-{family}-{target}.yaml"
            header = (
                f"sizing arm (ex-ante): {family}, {target}% annual vol target "
                "(20-bar realized, weight capped at 1.0), taker fees, daily long/cash"
            )
            (STRATEGY_DIR / name).write_text(_yaml_text(header, fields))
            count += 1
    print(f"wrote {count} configs to {STRATEGY_DIR}")


def run() -> None:
    sys.path.insert(0, str(ROOT))
    from app.engine.backtest.runner import BacktestRunner

    logging.disable(logging.INFO)
    period = f"{START.replace('-', '')}_{END.replace('-', '')}"
    configs = sorted(STRATEGY_DIR.glob("*.yaml"))
    for i, config_path in enumerate(configs, 1):
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
                f"[{i}/{len(configs)}] {config_path.stem} {symbol}: "
                f"ret {float(m.total_pnl_pct):+.1f}% dd {float(m.max_drawdown_pct):.1f}% "
                f"sharpe {float(m.sharpe_ratio or 0):.2f} n={m.total_trades}",
                flush=True,
            )


def _mean_entry_notional(trades_path: Path) -> float:
    rows = list(csv.DictReader(open(trades_path)))
    if not rows:
        return 0.0
    notionals = [float(r["entry_price"]) * float(r["size"]) for r in rows]
    return sum(notionals) / len(notionals)


def summarize() -> None:
    rows = []
    for report_path in sorted(ARTIFACTS_DIR.glob("*/*/report.json")):
        report = json.loads(report_path.read_text())
        m = report["metrics"]
        symbol = report_path.parent.name.split("_")[0]
        bench_ret = m["benchmark_return_pct"]
        bench_dd = m["benchmark_max_drawdown_pct"]
        bench_sharpe = m["benchmark_sharpe_ratio"]
        sharpe = m["sharpe_ratio"] or 0.0
        gate1 = bench_sharpe is not None and sharpe >= 0.9 * bench_sharpe
        gate2 = m["max_drawdown_pct"] <= 0.8 * bench_dd
        gate3 = m["total_pnl_pct"] >= 0.75 * bench_ret
        rows.append(
            {
                "config": report_path.parent.parent.name,
                "symbol": symbol,
                "ret": m["total_pnl_pct"],
                "dd": m["max_drawdown_pct"],
                "sharpe": sharpe,
                "n": m["total_trades"],
                "fees": m["total_fees"],
                "avg_notional": _mean_entry_notional(report_path.parent / "trades.csv"),
                "bench_ret": bench_ret,
                "bench_dd": bench_dd,
                "bench_sharpe": bench_sharpe,
                "g1": gate1,
                "g2": gate2,
                "g3": gate3,
            },
        )
    print(
        "| Config | Sym | Ret% | DD% | Sharpe | N | Fees$ | AvgNtl$ | "
        "B&H Ret% | B&H DD% | B&H Shp | G1 | G2 | G3 |",
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['config']} | {r['symbol'][:3]} | {r['ret']:+.1f} | {r['dd']:.1f} "
            f"| {r['sharpe']:.2f} | {r['n']} | {r['fees']:.0f} | {r['avg_notional']:.0f} "
            f"| {r['bench_ret']:+.1f} | {r['bench_dd']:.1f} | {r['bench_sharpe']:.2f} "
            f"| {'P' if r['g1'] else 'f'} | {'P' if r['g2'] else 'f'} "
            f"| {'P' if r['g3'] else 'f'} |",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["generate", "run", "summarize"])
    args = parser.parse_args()
    {"generate": generate, "run": run, "summarize": summarize}[args.command]()


if __name__ == "__main__":
    main()
