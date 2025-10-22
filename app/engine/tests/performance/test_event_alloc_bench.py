import os
import time

import pytest

from app.engine.models import BaseEvent, EventType, TimeFrame
from datetime import datetime, timezone


@pytest.mark.performance
def test_event_alloc_smoke_benchmark():
    if os.getenv("PERF_ENABLE") != "1":
        pytest.skip("PERF_ENABLE=1 to run benchmark")

    n = int(os.getenv("PERF_N", "10000"))
    t0 = time.perf_counter()
    for i in range(n):
        _ = BaseEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.now(timezone.utc),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            metadata={"i": i},
        )
    elapsed = time.perf_counter() - t0
    print(f"Allocated {n} BaseEvent in {elapsed:.4f}s")
