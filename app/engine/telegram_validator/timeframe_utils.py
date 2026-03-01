"""
Timeframe parsing helpers for benchmarking/reporting.
"""

from __future__ import annotations

from datetime import timedelta
import re


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    token = timeframe.strip().lower()
    match = re.fullmatch(r"(\d+)([mhdw])", token)
    if not match:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    n = int(match.group(1))
    unit = match.group(2)

    if unit == "m":
        return timedelta(minutes=n)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    if unit == "w":
        return timedelta(weeks=n)

    raise ValueError(f"Unsupported timeframe: {timeframe}")
