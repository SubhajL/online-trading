from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.engine.backtest.dataset import CSVDataset
from app.engine.models import TimeFrame


def test_csv_dataset_loads_candles_with_spot_venue(tmp_path: Path) -> None:
    csv_path = tmp_path / "btcusdt_15m.csv"
    csv_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-02T00:00:00Z,100,101,99,100.5,10\n"
        "2024-01-02T00:15:00Z,100.5,102,100,101,12\n",
    )

    dataset = CSVDataset(str(tmp_path))
    candles = dataset.load_candles(
        "BTCUSDT",
        TimeFrame.M15,
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 1, 3, tzinfo=UTC),
    )

    assert [(c.venue, c.symbol, c.close_price) for c in candles] == [
        ("SPOT", "BTCUSDT", Decimal("100.5")),
        ("SPOT", "BTCUSDT", Decimal("101")),
    ]
