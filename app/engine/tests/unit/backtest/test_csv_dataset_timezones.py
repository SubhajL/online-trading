from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.engine.backtest.dataset import CSVDataset, export_candles_to_csv, parse_utc_date
from app.engine.models import TimeFrame

from .series import make_candle


def test_load_candles_accepts_naive_bounds_for_aware_rows(tmp_path: Path) -> None:
    candles = [
        make_candle(0, "100", "101", "99", "100.5"),
        make_candle(1, "100.5", "102", "100", "101"),
    ]
    export_candles_to_csv(candles, str(tmp_path / "btcusdt_15m.csv"))

    loaded = CSVDataset(str(tmp_path)).load_candles(
        "BTCUSDT",
        TimeFrame.M15,
        datetime(2024, 1, 1),
        datetime(2024, 1, 3),
    )

    assert [c.open_time for c in loaded] == [c.open_time for c in candles]


def test_load_candles_parses_epoch_ms_as_utc(tmp_path: Path) -> None:
    epoch_ms_2024_01_02 = 1704153600000
    (tmp_path / "btcusdt_15m.csv").write_text(
        f"timestamp,open,high,low,close,volume\n{epoch_ms_2024_01_02},100,101,99,100.5,10\n",
    )

    loaded = CSVDataset(str(tmp_path)).load_candles(
        "BTCUSDT",
        TimeFrame.M15,
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 1, 3, tzinfo=UTC),
    )

    assert [c.open_time for c in loaded] == [datetime(2024, 1, 2, tzinfo=UTC)]


def test_parse_utc_date_reads_bare_date_as_utc_midnight() -> None:
    assert parse_utc_date("2024-07-01") == datetime(2024, 7, 1, tzinfo=UTC)


def test_parse_utc_date_end_of_day_covers_whole_date() -> None:
    assert parse_utc_date("2024-07-01", end_of_day=True) == datetime(
        2024, 7, 1, 23, 59, 59, 999999, tzinfo=UTC
    )


def test_parse_utc_date_keeps_explicit_datetime_and_zone() -> None:
    assert parse_utc_date("2024-07-01T06:30:00+00:00", end_of_day=True) == datetime(
        2024, 7, 1, 6, 30, tzinfo=UTC
    )
