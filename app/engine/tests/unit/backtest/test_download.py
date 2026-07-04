from __future__ import annotations

import asyncio
import csv
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.engine.backtest import download
from app.engine.backtest.dataset import CSVDataset
from app.engine.backtest.download import build_parser, download_klines
from app.engine.models import Candle, TimeFrame

from .series import BAR_DURATION, SERIES_START, make_candle

RANGE_START = datetime(2024, 1, 2, tzinfo=UTC)
RANGE_END = datetime(2024, 1, 3, tzinfo=UTC)


def _bar_open(index: int) -> datetime:
    return SERIES_START + index * BAR_DURATION


class FakeKlinesClient:
    """Serves canned kline pages, mimicking BinanceRestClient.get_klines."""

    def __init__(self, pages: list[list[Candle]]):
        self._pages = list(pages)
        self.calls: list[dict] = []

    async def get_klines(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[Candle]:
        self.calls.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
            },
        )
        if not self._pages:
            return []
        return self._pages.pop(0)


def _download(client: FakeKlinesClient, out_dir: Path) -> Path:
    return asyncio.run(
        download_klines(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            start=RANGE_START,
            end=RANGE_END,
            out_dir=out_dir,
            client=client,
            page_pause_seconds=0,
        ),
    )


def test_download_pages_klines_and_writes_loader_ready_csv(tmp_path: Path) -> None:
    pages = [
        [make_candle(0, "100", "101", "99", "100.5"), make_candle(1, "100.5", "102", "100", "101")],
        [make_candle(2, "101", "103", "100.5", "102"), make_candle(3, "102", "104", "101", "103")],
    ]
    client = FakeKlinesClient(pages)

    csv_path = _download(client, tmp_path)

    assert csv_path == tmp_path / "btcusdt_15m.csv"
    loaded = CSVDataset(str(tmp_path)).load_candles(
        "BTCUSDT",
        TimeFrame.M15,
        RANGE_START,
        RANGE_END,
    )
    assert [(c.open_time, c.open_price, c.close_price) for c in loaded] == [
        (_bar_open(i), expected_open, expected_close)
        for i, (expected_open, expected_close) in enumerate(
            [
                (Decimal("100"), Decimal("100.5")),
                (Decimal("100.5"), Decimal("101")),
                (Decimal("101"), Decimal("102")),
                (Decimal("102"), Decimal("103")),
            ],
        )
    ]


def test_download_paginates_from_last_close_time(tmp_path: Path) -> None:
    pages = [
        [make_candle(0, "100", "101", "99", "100.5")],
        [make_candle(1, "100.5", "102", "100", "101")],
    ]
    client = FakeKlinesClient(pages)

    _download(client, tmp_path)

    first_page_last_close = _bar_open(0) + BAR_DURATION
    assert (client.calls[0]["start_time"], len(client.calls)) == (RANGE_START, 3)
    assert client.calls[1]["start_time"] == first_page_last_close + timedelta(milliseconds=1)


def test_download_dedupes_overlapping_pages(tmp_path: Path) -> None:
    shared = make_candle(1, "100.5", "102", "100", "101")
    pages = [
        [make_candle(0, "100", "101", "99", "100.5"), shared],
        [shared, make_candle(2, "101", "103", "100.5", "102")],
    ]
    client = FakeKlinesClient(pages)

    csv_path = _download(client, tmp_path)

    with open(csv_path) as file:
        rows = list(csv.DictReader(file))
    assert [row["timestamp"] for row in rows] == [_bar_open(i).isoformat() for i in range(3)]


def test_download_drops_unclosed_final_candle(tmp_path: Path) -> None:
    series_start = datetime.now(UTC) - timedelta(minutes=20)
    closed = make_candle(0, "100", "101", "99", "100.5", start=series_start)
    unclosed = make_candle(1, "100.5", "102", "100", "101", start=series_start)
    client = FakeKlinesClient([[closed, unclosed]])

    csv_path = asyncio.run(
        download_klines(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            start=series_start,
            end=series_start + timedelta(hours=1),
            out_dir=tmp_path,
            client=client,
            page_pause_seconds=0,
        ),
    )

    with open(csv_path) as file:
        rows = list(csv.DictReader(file))
    assert [row["timestamp"] for row in rows] == [closed.open_time.isoformat()]


def test_download_excludes_candles_beyond_end(tmp_path: Path) -> None:
    pages = [
        [
            make_candle(0, "100", "101", "99", "100.5"),
            make_candle(1, "100.5", "102", "100", "101"),
            make_candle(2, "101", "103", "100.5", "102"),
        ],
    ]
    client = FakeKlinesClient(pages)

    csv_path = asyncio.run(
        download_klines(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            start=RANGE_START,
            end=_bar_open(1) + timedelta(minutes=1),
            out_dir=tmp_path,
            client=client,
            page_pause_seconds=0,
        ),
    )

    with open(csv_path) as file:
        rows = list(csv.DictReader(file))
    assert [row["timestamp"] for row in rows] == [_bar_open(i).isoformat() for i in range(2)]


def test_download_raises_when_no_candles_returned(tmp_path: Path) -> None:
    client = FakeKlinesClient([])

    with pytest.raises(ValueError, match="BTCUSDT"):
        _download(client, tmp_path)


def test_download_defaults_to_public_mainnet_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict = {}

    class RecordingClient(FakeKlinesClient):
        def __init__(self, api_key: str, api_secret: str, **kwargs):
            super().__init__([[make_candle(0, "100", "101", "99", "100.5")]])
            recorded["api_key"] = api_key
            recorded["api_secret"] = api_secret
            recorded["kwargs"] = kwargs
            recorded["started"] = False
            recorded["stopped"] = False

        async def start(self) -> None:
            recorded["started"] = True

        async def stop(self) -> None:
            recorded["stopped"] = True

    monkeypatch.setattr(download, "BinanceRestClient", RecordingClient)

    asyncio.run(
        download_klines(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            start=RANGE_START,
            end=RANGE_END,
            out_dir=tmp_path,
            page_pause_seconds=0,
        ),
    )

    assert (
        recorded["api_key"],
        recorded["api_secret"],
        recorded["kwargs"],
        recorded["started"],
        recorded["stopped"],
    ) == ("", "", {}, True, True)


def test_build_parser_parses_cli_arguments() -> None:
    args = build_parser().parse_args(
        [
            "--symbol",
            "ETHUSDT",
            "--tf",
            "1h",
            "--start",
            "2024-07-01",
            "--end",
            "2026-06-30",
            "--out",
            "data/backtest",
        ],
    )

    assert (args.symbol, args.tf, args.start, args.end, args.out) == (
        "ETHUSDT",
        "1h",
        "2024-07-01",
        "2026-06-30",
        "data/backtest",
    )


def test_main_converts_args_and_invokes_download(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_download(**kwargs) -> Path:
        captured.update(kwargs)
        return Path("data/backtest/ethusdt_1h.csv")

    monkeypatch.setattr(download, "download_klines", fake_download)

    download.main(
        [
            "--symbol",
            "ETHUSDT",
            "--tf",
            "1h",
            "--start",
            "2024-07-01",
            "--end",
            "2026-06-30",
            "--out",
            "data/backtest",
        ],
    )

    assert (
        captured["symbol"],
        captured["timeframe"],
        captured["start"],
        captured["end"],
        captured["out_dir"],
    ) == (
        "ETHUSDT",
        TimeFrame.H1,
        datetime(2024, 7, 1, tzinfo=UTC),
        datetime(2026, 6, 30, 23, 59, 59, 999999, tzinfo=UTC),
        Path("data/backtest"),
    )
