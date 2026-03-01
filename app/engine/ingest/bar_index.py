"""Bar index utilities.

`bar_index` is used by SMC components to track pivots and zone expiry with a stable,
time-based index that is consistent across backfill and realtime ingestion.
"""

from __future__ import annotations

from datetime import datetime

from app.engine.models import TimeFrame

_TF_SECONDS: dict[str, int] = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def bar_index_from_open_time(open_time: datetime, timeframe: TimeFrame) -> int | None:
    """Compute a stable bar index from candle open time and timeframe.

    Returns None for unsupported timeframes (e.g., 1M month-based).
    """
    tf_value = timeframe.value
    suffix = tf_value[-1]
    if suffix not in _TF_SECONDS:
        return None
    try:
        quantity = int(tf_value[:-1])
    except ValueError:
        return None
    seconds = quantity * _TF_SECONDS[suffix]
    return int(open_time.timestamp()) // seconds
