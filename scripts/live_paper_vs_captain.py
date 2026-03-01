#!/usr/bin/env python3
"""
Live paper trading vs Captain signal comparison.

Orchestrates:
1. Captain Telegram listener (spawned as subprocess)
2. Paper trading harness (WebSocket → pipeline → paper broker)
3. Periodic comparison using validate_external_signals()

Reuses StreamComparisonResult.timing_delta_seconds from outcome_comparison.py.
"""

from __future__ import annotations

import argparse
import asyncio
from asyncio import StreamReader
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
import logging
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter
from app.engine.models import TimeFrame
from app.engine.paper.live_harness import LivePaperTradingHarness
from app.engine.telegram_validator.benchmark_validator import validate_external_signals
from app.engine.telegram_validator.outcome_comparison import (
    compare_captain_vs_internal_outcomes,
)

logger = logging.getLogger(__name__)


async def _drain_stream(stream: StreamReader, prefix: str) -> AsyncIterator[str]:
    """Drain lines from async stream, yielding each decoded line.

    Args:
        stream: Async stream reader (stdout or stderr from subprocess)
        prefix: Log prefix for identifying stream source

    Yields:
        Decoded line with trailing whitespace stripped
    """
    while True:
        line = await stream.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").rstrip()
        logger.debug("[%s] %s", prefix, decoded)
        yield decoded


def build_argument_parser() -> argparse.ArgumentParser:
    """Build argument parser for the comparison script."""
    parser = argparse.ArgumentParser(
        description="Run live paper trading with Captain signal comparison",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="captain",
        help="Source identifier for external signals (default: captain)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=60,
        help="Comparison poll interval in seconds (default: 60)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="BTCUSDT",
        help="Comma-separated list of symbols (default: BTCUSDT)",
    )
    parser.add_argument(
        "--time-window",
        type=int,
        default=300,
        help="Signal matching time window in seconds (default: 300)",
    )
    parser.add_argument(
        "--entry-tolerance",
        type=float,
        default=0.002,
        help="Entry price tolerance for matching (default: 0.002 = 0.2%%)",
    )
    return parser


def build_captain_listener_command(source: str) -> list[str]:
    """Build command to spawn captain_benchmark_ingest.py listener."""
    script_path = PROJECT_ROOT / "scripts" / "captain_benchmark_ingest.py"
    return [
        sys.executable,
        str(script_path),
        "--listen",
        "--source",
        source,
    ]


async def _consume_drain(drain_gen: AsyncIterator[str]) -> None:
    """Consume all lines from a drain generator, logging each line."""
    async for _ in drain_gen:
        pass


async def start_captain_listener_async(
    source: str,
    command: list[str] | None = None,
) -> tuple[asyncio.subprocess.Process, list[asyncio.Task[None]]]:
    """Spawn captain_benchmark_ingest.py as async subprocess with drain tasks.

    Args:
        source: Signal source identifier
        command: Optional command override (for testing)

    Returns:
        Tuple of (process, drain_tasks) where drain_tasks continuously read
        stdout/stderr to prevent pipe buffer deadlock.
    """
    cmd = command if command is not None else build_captain_listener_command(source)
    logger.info("Starting Captain listener: %s", " ".join(cmd))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    drain_tasks: list[asyncio.Task[None]] = []
    if process.stdout:
        stdout_task = asyncio.create_task(
            _consume_drain(_drain_stream(process.stdout, f"captain-{source}-stdout"))
        )
        drain_tasks.append(stdout_task)
    if process.stderr:
        stderr_task = asyncio.create_task(
            _consume_drain(_drain_stream(process.stderr, f"captain-{source}-stderr"))
        )
        drain_tasks.append(stderr_task)

    return process, drain_tasks


def format_comparison_metrics(metrics: dict[str, Any]) -> str:
    """Format comparison metrics for display."""
    lines = [
        "=== Comparison Metrics ===",
        f"Captain signals:  {metrics.get('captain_count', 0)}",
        f"Internal signals: {metrics.get('internal_count', 0)}",
        f"Matched pairs:    {metrics.get('matched_count', 0)}",
        f"Timing delta:     {metrics.get('timing_delta_seconds', 0):.2f}s",
    ]

    if "captain_win_rate" in metrics:
        lines.append(f"Captain win rate: {float(metrics['captain_win_rate']):.1%}")
    if "internal_win_rate" in metrics:
        lines.append(f"Internal win rate: {float(metrics['internal_win_rate']):.1%}")
    if "avg_pnl_delta" in metrics:
        lines.append(f"Avg PnL delta:    {metrics['avg_pnl_delta']}")

    return "\n".join(lines)


async def run_comparison_loop(
    db: TimescaleDBAdapter,
    *,
    source: str,
    poll_interval: int,
    time_window_seconds: int,
    entry_tolerance: float,
) -> None:
    """Run periodic comparison between Captain and internal signals.

    Args:
        db: Database adapter
        source: Signal source identifier
        poll_interval: Seconds between comparison runs
        time_window_seconds: Window for matching external to internal signals
        entry_tolerance: Price tolerance for signal matching (as fraction, e.g., 0.005 = 0.5%)
    """
    logger.info(
        "Starting comparison loop (source=%s, interval=%ds, window=%ds)",
        source,
        poll_interval,
        time_window_seconds,
    )

    try:
        while True:
            try:
                end_time = datetime.now(UTC)
                start_time = end_time - timedelta(hours=24)

                # Validate external signals (match to internal)
                await validate_external_signals(
                    db,
                    source=source,
                    start_time=start_time,
                    end_time=end_time,
                    time_window_seconds=time_window_seconds,
                    entry_tolerance=entry_tolerance,
                )

                # Compare outcomes
                result = await compare_captain_vs_internal_outcomes(
                    db,
                    source=source,
                    start_time=start_time,
                    end_time=end_time,
                )

                metrics = {
                    "captain_count": result.captain_count,
                    "internal_count": result.internal_count,
                    "matched_count": result.matched_count,
                    "captain_win_rate": result.captain_win_rate,
                    "internal_win_rate": result.internal_win_rate,
                    "avg_pnl_delta": result.avg_pnl_delta,
                    "timing_delta_seconds": result.timing_delta_seconds,
                }

                logger.info("\n%s", format_comparison_metrics(metrics))

            except asyncio.CancelledError:
                raise  # Re-raise to exit loop cleanly
            except Exception:
                logger.exception("Error in comparison loop, will retry")
                await asyncio.sleep(5)  # Brief pause before retry
                continue

            await asyncio.sleep(poll_interval)

    except asyncio.CancelledError:
        logger.info("Comparison loop cancelled")


async def async_main(args: argparse.Namespace) -> None:
    """Async main entry point."""
    # Initialize database
    db = TimescaleDBAdapter(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "trading_engine"),
        username=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "password"),
    )
    await db.initialize()

    # Start Captain listener (async subprocess with drain tasks)
    captain_process, drain_tasks = await start_captain_listener_async(args.source)

    # Build database URL from components
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASSWORD", "password")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "trading_engine")
    default_db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    # Start paper trading harness
    harness_config = {
        "symbols": args.symbols.split(","),
        "timeframes": [TimeFrame.M1],
        "database_url": os.getenv("DATABASE_URL", default_db_url),
        "testnet": True,
    }
    harness = LivePaperTradingHarness(harness_config)

    try:
        await harness.start()

        # Run comparison loop
        await run_comparison_loop(
            db,
            source=args.source,
            poll_interval=args.poll_interval,
            time_window_seconds=args.time_window,
            entry_tolerance=args.entry_tolerance,
        )

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Clean up each resource independently to ensure all get cleaned up
        try:
            await harness.stop()
        except Exception:
            logger.exception("Error stopping harness")

        # Cancel drain tasks
        for task in drain_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Terminate subprocess
        try:
            captain_process.terminate()
            await captain_process.wait()
        except Exception:
            logger.exception("Error terminating captain process")

        # Close database
        try:
            await db.close()
        except Exception:
            logger.exception("Error closing database")


def main() -> None:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = build_argument_parser()
    args = parser.parse_args()

    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
