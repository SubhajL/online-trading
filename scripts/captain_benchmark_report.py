#!/usr/bin/env python3
"""
Generate a benchmark report for external Telegram signals vs internal system data.

Reads:
- external_telegram_signals
- external_telegram_signal_validations
Optionally evaluates simple TP1/SL outcomes if candle data exists.
Optionally runs robustness sweeps with varying cost assumptions.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter  # noqa: E402
from app.engine.models import TimeFrame  # noqa: E402
from app.engine.telegram_validator.outcome_eval import (  # noqa: E402
    evaluate_trade_outcome,
    evaluate_trade_outcome_with_fill_model,
)
from app.engine.telegram_validator.fill_model import BracketSpec, CostConfig  # noqa: E402
from app.engine.telegram_validator.robustness_sweeps import (  # noqa: E402
    build_sweep_grid,
    run_robustness_sweep,
    SWEEP_PRESETS,
)
from app.engine.telegram_validator.timeframe_utils import timeframe_to_timedelta  # noqa: E402


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _decimal_serializer(obj: Any) -> Any:
    """JSON serializer for Decimal objects."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _write_json_report(report: dict[str, Any], output_dir: Path | None) -> Path:
    """Write JSON report to file."""
    if output_dir is None:
        output_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"captain_benchmark_{timestamp}.json"
    output_path = output_dir / filename

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=_decimal_serializer)

    return output_path


async def _run(
    *,
    source: str,
    hours: int,
    outcomes: bool,
    sweep: bool = False,
    sweep_preset: str = "moderate",
    output_json: bool = False,
    output_dir: Path | None = None,
) -> None:
    _load_env_file(PROJECT_ROOT / ".env.telegram")

    end = datetime.now(UTC)
    start = end - timedelta(hours=hours)

    db = TimescaleDBAdapter(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "trading_engine"),
        username=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "password"),
    )
    await db.initialize()

    signals = await db.get_external_telegram_signals(
        source=source,
        start_time=start,
        end_time=end,
        limit=5000,
    )
    validations = await db.get_external_telegram_signal_validations(
        source=source,
        start_time=start,
        end_time=end,
        limit=5000,
    )
    validations_by_key = {
        (int(v["chat_id"]), int(v["message_id"])): v for v in validations
    }

    trade_signals = [
        s
        for s in signals
        if s.get("kind") == "TRADE_SIGNAL" and s.get("symbol") and s.get("direction")
    ]

    matched = 0
    scores: list[float] = []
    for s in trade_signals:
        v = validations_by_key.get((int(s["chat_id"]), int(s["message_id"])))
        if not v:
            continue
        scores.append(float(v.get("score") or 0.0))
        if v.get("internal_id"):
            matched += 1

    avg_score = (sum(scores) / len(scores)) if scores else 0.0

    # Build report data
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": source,
        "window_hours": hours,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "agreement_metrics": {
            "total_trade_signals": len(trade_signals),
            "matched_count": matched,
            "match_rate": (matched / len(trade_signals)) if trade_signals else 0,
            "average_score": avg_score,
            "scores_count": len(scores),
        },
    }

    print("Captain Benchmark Report")
    print(f"Window: last {hours}h")
    print(f"Signals (trade): {len(trade_signals)}")
    print(f"Matched: {matched} ({(matched / len(trade_signals) * 100) if trade_signals else 0:.1f}%)")
    print(f"Average score: {avg_score:.3f}")

    if not outcomes and not sweep:
        if output_json:
            output_path = _write_json_report(report, output_dir)
            print(f"\nJSON report: {output_path}")
        await db.close()
        return

    horizon_bars = int(os.getenv("SIGNAL_OUTCOME_HORIZON_BARS", "48"))
    tp1_count = 0
    sl_count = 0
    none_count = 0
    eligible = 0
    detailed_outcomes: list[dict[str, Any]] = []

    # For sweep mode, collect signals with candles
    sweep_signals: list[tuple[dict[str, Any], list[Any]]] = []

    for s in trade_signals:
        timeframe = s.get("timeframe")
        if not timeframe:
            continue
        tp_list = s.get("take_profits")
        stop_loss = _as_decimal(s.get("stop_loss"))
        entry_price = _as_decimal(s.get("entry_price"))
        if not tp_list or stop_loss is None:
            continue

        tp1 = _as_decimal(tp_list[0]) if isinstance(tp_list, list) else None
        if tp1 is None:
            continue

        try:
            tf = TimeFrame(str(timeframe))
        except Exception:
            continue

        ts = s["timestamp"]
        end_ts = ts + (timeframe_to_timedelta(str(timeframe)) * horizon_bars)
        candles = await db.get_candles(
            symbol=str(s["symbol"]),
            timeframe=tf,
            start_time=ts,
            end_time=end_ts,
            limit=horizon_bars + 10,
        )
        if not candles:
            continue

        eligible += 1

        if sweep and entry_price is not None:
            sweep_signals.append((s, candles))

        if outcomes or sweep:
            direction = str(s["direction"]).upper()

            if entry_price is not None:
                # Use detailed fill model
                detailed_outcome = evaluate_trade_outcome_with_fill_model(
                    direction=direction,  # type: ignore[arg-type]
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=tp1,
                    candles=candles,
                )
                detailed_outcomes.append({
                    "signal_id": f"{s['chat_id']}_{s['message_id']}",
                    "symbol": s["symbol"],
                    "direction": direction,
                    "outcome": detailed_outcome.outcome,
                    "gross_pnl": str(detailed_outcome.gross_pnl),
                    "net_pnl": str(detailed_outcome.net_pnl),
                    "fees": str(detailed_outcome.fees),
                    "slippage_cost": str(detailed_outcome.slippage_cost),
                    "funding_cost": str(detailed_outcome.funding_cost),
                    "candles_held": detailed_outcome.candles_held,
                })
                label = detailed_outcome.outcome
            else:
                # Use simple evaluation
                outcome = evaluate_trade_outcome(
                    direction=direction,  # type: ignore[arg-type]
                    stop_loss=stop_loss,
                    take_profit=tp1,
                    candles=candles,
                )
                label = outcome.outcome

            if label == "TP1":
                tp1_count += 1
            elif label == "SL":
                sl_count += 1
            else:
                none_count += 1

    report["outcome_metrics"] = {
        "eligible_count": eligible,
        "tp1_count": tp1_count,
        "sl_count": sl_count,
        "none_count": none_count,
        "win_rate": (tp1_count / (tp1_count + sl_count)) if (tp1_count + sl_count) > 0 else 0,
    }

    if detailed_outcomes:
        report["detailed_outcomes"] = detailed_outcomes

    print(f"Outcome eligible: {eligible}")
    print(f"TP1: {tp1_count}  SL: {sl_count}  NONE: {none_count}")

    decided = tp1_count + sl_count
    if decided:
        print(f"Win rate (TP1 / (TP1+SL)): {(tp1_count / decided) * 100:.1f}%")

    # Run robustness sweep if requested
    if sweep and sweep_signals:
        print(f"\nRunning robustness sweep ({sweep_preset} preset)...")

        preset = SWEEP_PRESETS.get(sweep_preset, SWEEP_PRESETS["moderate"])
        sweep_configs = build_sweep_grid(
            CostConfig(),
            fee_range=preset["fee_range"],
            slippage_range=preset["slippage_range"],
            funding_range=preset["funding_range"],
        )

        all_sweep_results: list[dict[str, Any]] = []
        total_pass_rates: list[float] = []

        for s, candles in sweep_signals:
            entry_price = _as_decimal(s.get("entry_price"))
            stop_loss = _as_decimal(s.get("stop_loss"))
            tp_list = s.get("take_profits")
            tp1 = _as_decimal(tp_list[0]) if isinstance(tp_list, list) else None

            if entry_price is None or stop_loss is None or tp1 is None:
                continue

            bracket = BracketSpec(
                side=str(s["direction"]).upper(),  # type: ignore[arg-type]
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profits=[tp1],
                tp_sizes=[Decimal("1.0")],
            )

            try:
                sweep_result = run_robustness_sweep(
                    candles=candles,
                    bracket=bracket,
                    sweep_configs=sweep_configs,
                )
                total_pass_rates.append(sweep_result.pass_rate)
                all_sweep_results.append({
                    "signal_id": f"{s['chat_id']}_{s['message_id']}",
                    "symbol": s["symbol"],
                    "pass_rate": sweep_result.pass_rate,
                    "pnl_p10": str(sweep_result.pnl_p10),
                    "pnl_p50": str(sweep_result.pnl_p50),
                    "pnl_p90": str(sweep_result.pnl_p90),
                })
            except Exception as e:
                print(f"  Sweep error for {s['symbol']}: {e}")

        avg_pass_rate = (sum(total_pass_rates) / len(total_pass_rates)) if total_pass_rates else 0
        report["robustness_sweep"] = {
            "preset": sweep_preset,
            "configs_tested": len(sweep_configs),
            "signals_swept": len(all_sweep_results),
            "avg_pass_rate": avg_pass_rate,
            "results": all_sweep_results,
        }

        print(f"Sweep complete: {len(all_sweep_results)} signals tested")
        print(f"Average pass rate: {avg_pass_rate * 100:.1f}%")
        print(f"Configs per signal: {len(sweep_configs)}")

    if output_json:
        output_path = _write_json_report(report, output_dir)
        print(f"\nJSON report: {output_path}")

    await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate benchmark report for Captain Trading signals."
    )
    parser.add_argument("--source", default="captain", help="Signal source (default: captain)")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back (default: 24)")
    parser.add_argument("--outcomes", action="store_true", help="Evaluate TP1/SL outcomes")
    parser.add_argument("--sweep", action="store_true", help="Run robustness sweep")
    parser.add_argument(
        "--sweep-preset",
        choices=["conservative", "moderate", "aggressive"],
        default="moderate",
        help="Sweep cost preset (default: moderate)",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON report to reports/")
    parser.add_argument("--output-dir", type=Path, help="Output directory for JSON report")

    args = parser.parse_args()

    asyncio.run(
        _run(
            source=args.source,
            hours=args.hours,
            outcomes=args.outcomes,
            sweep=args.sweep,
            sweep_preset=args.sweep_preset,
            output_json=args.json,
            output_dir=args.output_dir,
        )
    )


if __name__ == "__main__":
    main()

