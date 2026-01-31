from datetime import UTC, datetime

import pytest

from app.engine.ingest.bar_index import bar_index_from_open_time
from app.engine.models import TimeFrame


@pytest.mark.parametrize(
    ("tf", "open_time", "expected"),
    [
        (TimeFrame.M5, datetime(2025, 1, 1, 0, 0, tzinfo=UTC), 0),
        (TimeFrame.M5, datetime(2025, 1, 1, 0, 5, tzinfo=UTC), 1),
        (TimeFrame.M15, datetime(2025, 1, 1, 0, 15, tzinfo=UTC), 1),
        (TimeFrame.H1, datetime(2025, 1, 1, 1, 0, tzinfo=UTC), 1),
        (TimeFrame.H4, datetime(2025, 1, 1, 4, 0, tzinfo=UTC), 1),
    ],
)
def test_bar_index_from_open_time_is_stable(tf: TimeFrame, open_time: datetime, expected: int) -> None:
    origin = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    base = bar_index_from_open_time(origin, tf)
    current = bar_index_from_open_time(open_time, tf)
    assert base is not None
    assert current - base == expected

