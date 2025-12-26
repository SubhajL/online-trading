#!/usr/bin/env python3
"""
Validate external Captain Trading Telegram signals against internal system data.

Writes results into `external_telegram_signal_validations`.

Environment:
- DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
- Optional: SIGNAL_TIME_WINDOW_SECONDS (default 300), SIGNAL_ENTRY_TOLERANCE (default 0.002)
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter  # noqa: E402
from app.engine.telegram_validator.benchmark_validator import (  # noqa: E402
    validate_external_signals,
)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


async def _run(*, source: str, hours: int) -> None:
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

    window_seconds = int(os.getenv("SIGNAL_TIME_WINDOW_SECONDS", "300"))
    entry_tolerance = float(os.getenv("SIGNAL_ENTRY_TOLERANCE", "0.002"))

    await validate_external_signals(
        db,
        source=source,
        start_time=start,
        end_time=end,
        time_window_seconds=window_seconds,
        entry_tolerance=entry_tolerance,
    )

    await db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="captain")
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()
    asyncio.run(_run(source=args.source, hours=args.hours))


if __name__ == "__main__":
    main()

