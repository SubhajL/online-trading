#!/usr/bin/env python3
"""Summarize strategy backtest runs: period returns, trade stats, costs, vs buy-and-hold.

Reads artifacts/strategy-runs/<strategy>/<SYMBOL>_<tf>_<range>/{trades.csv,report.json},
reconstructs the realized equity curve from the trade ledger (initial + cumulative
net_pnl by exit time — the ledger already embeds fixed-fractional compounding), and
reports cumulative returns at 1/3/6/12/24-month horizons from inception.

When report.json carries the benchmark fields (v3 runs onward) the buy-and-hold
comparison comes straight from the report — computed over the exact candle window
the simulator processed — instead of being re-derived from the raw CSV.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

ROOT = Path("/Users/subhajlimanond/dev/online trader")
INITIAL = 10000.0
HORIZONS = [("1m", 30), ("3m", 91), ("6m", 182), ("12m", 365), ("24m", 730)]


def f(x: str) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def load_trades(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(open(path)))


def load_benchmark(path: Path) -> dict | None:
    """Benchmark fields from report.json, when the run produced them."""
    if not path.exists():
        return None
    try:
        metrics = json.loads(path.read_text()).get("metrics", {})
    except (json.JSONDecodeError, OSError):
        return None
    if metrics.get("benchmark_return_pct") is None:
        return None
    return {
        "return_pct": metrics["benchmark_return_pct"],
        "max_dd_pct": metrics.get("benchmark_max_drawdown_pct"),
        "sharpe": metrics.get("benchmark_sharpe_ratio"),
        "excess_pct": metrics.get("excess_return_pct"),
    }


def equity_at(trades: list[dict], when: datetime) -> float:
    eq = INITIAL
    for t in trades:
        xt = t.get("exit_time") or ""
        if not xt:
            continue
        try:
            et = datetime.fromisoformat(xt.replace("Z", "+00:00"))
        except ValueError:
            continue
        if et <= when:
            eq += f(t["net_pnl"])
    return eq


def buy_hold_return(symbol: str, tf: str, start: datetime, when: datetime) -> float | None:
    path = ROOT / "data" / "backtest" / f"{symbol.lower()}_{tf}.csv"
    if not path.exists():
        return None
    start_px = end_px = None
    for r in csv.DictReader(open(path)):
        try:
            ts = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            continue
        if start_px is None and ts >= start:
            start_px = f(r["close"])
        if ts <= when:
            end_px = f(r["close"])
    if start_px and end_px:
        return (end_px / start_px - 1) * 100
    return None


def trade_stats(trades: list[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0}
    nets = [f(t["net_pnl_r"]) for t in trades if abs(f(t["net_pnl_r"])) < 50]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    gross_win = sum(f(t["net_pnl"]) for t in trades if f(t["net_pnl"]) > 0)
    gross_loss = -sum(f(t["net_pnl"]) for t in trades if f(t["net_pnl"]) < 0)
    fees = sum(f(t["fees"]) for t in trades)
    slip = sum(f(t["slippage"]) for t in trades)
    fund = sum(f(t["funding"]) for t in trades)
    longs = [f(t["net_pnl_r"]) for t in trades if t["side"] == "long" and abs(f(t["net_pnl_r"])) < 50]
    shorts = [f(t["net_pnl_r"]) for t in trades if t["side"] == "short" and abs(f(t["net_pnl_r"])) < 50]
    return {
        "n": n,
        "hit": len(wins) / len(nets) * 100 if nets else 0,
        "avg_r": sum(nets) / len(nets) if nets else 0,
        "avg_win_r": sum(wins) / len(wins) if wins else 0,
        "avg_loss_r": sum(losses) / len(losses) if losses else 0,
        "pf": gross_win / gross_loss if gross_loss else float("inf"),
        "fees": fees,
        "slip": slip,
        "fund": fund,
        "n_long": len(longs),
        "n_short": len(shorts),
        "long_r": sum(longs) / len(longs) if longs else 0,
        "short_r": sum(shorts) / len(shorts) if shorts else 0,
    }


def max_drawdown(trades: list[dict]) -> float:
    eq = INITIAL
    peak = INITIAL
    mdd = 0.0
    for t in sorted(trades, key=lambda r: r.get("exit_time") or ""):
        eq += f(t["net_pnl"])
        peak = max(peak, eq)
        if peak > 0:
            mdd = max(mdd, (peak - eq) / peak)
    return mdd * 100


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--strats",
        default="baseline,s1,s2,s3",
        help="Comma-separated strategy run names under artifacts/strategy-runs/",
    )
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    parser.add_argument("--tf", default="1h", help="Timeframe segment of the run dirs")
    parser.add_argument("--range", dest="range_", default="20240701_20260630")
    parser.add_argument("--start", default="2024-07-01", help="Inception date (UTC)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    strats = [s for s in args.strats.split(",") if s]
    symbols = [s for s in args.symbols.split(",") if s]
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)

    for symbol in symbols:
        print(f"\n{'=' * 100}\n{symbol} — {args.tf} — {args.range_}\n{'=' * 100}")
        bh = {h: buy_hold_return(symbol, args.tf, start, start + timedelta(days=d)) for h, d in HORIZONS}
        if all(v is not None for v in bh.values()):
            print(f"{'Buy & Hold':16} | " + " ".join(f"{h}:{bh[h]:+7.1f}%" for h, _ in HORIZONS))
        print("-" * 100)
        header = f"{'Strategy':16} | " + " ".join(f"{h:>10}" for h, _ in HORIZONS)
        print(header)
        for strat in strats:
            d = ROOT / "artifacts" / "strategy-runs" / strat / f"{symbol}_{args.tf}_{args.range_}"
            trades = load_trades(d / "trades.csv")
            if not trades:
                print(f"{strat:16} | (no data — run may be incomplete)")
                continue
            rets = []
            for h, days in HORIZONS:
                eq = equity_at(trades, start + timedelta(days=days))
                rets.append((eq / INITIAL - 1) * 100)
            print(f"{strat:16} | " + " ".join(f"{r:+9.1f}%" for r in rets))
        print("-" * 100)
        print(f"{'Strategy':16} | {'trades':>7} {'hit%':>6} {'PF':>5} {'avgR':>6} {'winR':>6} {'lossR':>7} {'maxDD%':>7} {'fees$':>8} {'slip$':>7} {'fund$':>7} | long/short R")
        for strat in strats:
            d = ROOT / "artifacts" / "strategy-runs" / strat / f"{symbol}_{args.tf}_{args.range_}"
            trades = load_trades(d / "trades.csv")
            if not trades:
                continue
            s = trade_stats(trades)
            mdd = max_drawdown(trades)
            pf = s["pf"]
            pfs = f"{pf:.2f}" if pf != float("inf") else "inf"
            print(
                f"{strat:16} | {s['n']:7d} {s['hit']:5.1f} {pfs:>5} {s['avg_r']:+6.2f} "
                f"{s['avg_win_r']:+6.2f} {s['avg_loss_r']:+7.2f} {mdd:7.1f} "
                f"{s['fees']:8.0f} {s['slip']:7.0f} {s['fund']:7.0f} | "
                f"L {s['long_r']:+.2f}({s['n_long']}) S {s['short_r']:+.2f}({s['n_short']})"
            )
        print("-" * 100)
        print(f"{'Strategy':16} | {'B&H ret%':>9} {'B&H maxDD%':>11} {'B&H Sharpe':>11} {'excess%':>9}  (from report.json)")
        for strat in strats:
            d = ROOT / "artifacts" / "strategy-runs" / strat / f"{symbol}_{args.tf}_{args.range_}"
            bench = load_benchmark(d / "report.json")
            if bench is None:
                print(f"{strat:16} | (no benchmark fields in report)")
                continue
            sharpe = f"{bench['sharpe']:11.2f}" if bench["sharpe"] is not None else f"{'—':>11}"
            print(
                f"{strat:16} | {bench['return_pct']:+9.1f} {bench['max_dd_pct']:11.1f} "
                f"{sharpe} {bench['excess_pct']:+9.1f}"
            )


if __name__ == "__main__":
    main()
