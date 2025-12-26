#!/usr/bin/env python3
"""
Generate a benchmark report for external Telegram signals vs internal system data.

Reads:
- external_telegram_signals
- external_telegram_signal_validations
Optionally evaluates simple TP1/SL outcomes if candle data exists.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter  # noqa: E402
from app.engine.models import TimeFrame  # noqa: E402
from app.engine.telegram_validator.outcome_eval import evaluate_trade_outcome  # noqa: E402
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


async def _run(*, source: str, hours: int, outcomes: bool) -> None:
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

    print("Captain Benchmark Report")
    print(f"Window: last {hours}h")
    print(f"Signals (trade): {len(trade_signals)}")
    print(f"Matched: {matched} ({(matched / len(trade_signals) * 100) if trade_signals else 0:.1f}%)")
    print(f"Average score: {avg_score:.3f}")

    if not outcomes:
        await db.close()
        return

    horizon_bars = int(os.getenv("SIGNAL_OUTCOME_HORIZON_BARS", "48"))
    tp1_count = 0
    sl_count = 0
    none_count = 0
    eligible = 0

    for s in trade_signals:
        timeframe = s.get("timeframe")
        if not timeframe:
            continue
        tp_list = s.get("take_profits")
        stop_loss = _as_decimal(s.get("stop_loss"))
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
        outcome = evaluate_trade_outcome(
            direction=str(s["direction"]).upper(),  # type: ignore[arg-type]
            stop_loss=stop_loss,
            take_profit=tp1,
            candles=candles,
        )
        if outcome.outcome == "TP1":
            tp1_count += 1
        elif outcome.outcome == "SL":
            sl_count += 1
        else:
            none_count += 1

    print(f"Outcome eligible: {eligible}")
    print(f"TP1: {tp1_count}  SL: {sl_count}  NONE: {none_count}")

    decided = tp1_count + sl_count
    if decided:
        print(f"Win rate (TP1 / (TP1+SL)): {(tp1_count / decided) * 100:.1f}%")

    await db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="captain")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--outcomes", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(source=args.source, hours=args.hours, outcomes=args.outcomes))


if __name__ == "__main__":
    main()

