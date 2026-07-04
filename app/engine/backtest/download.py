"""
Historical kline downloader producing CSVDataset-ready files.
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path

from ..ingest.binance_rest import BinanceRestClient
from ..models import Candle, TimeFrame
from .dataset import export_candles_to_csv, parse_utc_date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_PAGE_LIMIT = 1000
_DEFAULT_PAGE_PAUSE_SECONDS = 0.1


async def download_klines(
    symbol: str,
    timeframe: TimeFrame,
    start: datetime,
    end: datetime,
    out_dir: Path | str,
    client: BinanceRestClient | None = None,
    page_pause_seconds: float = _DEFAULT_PAGE_PAUSE_SECONDS,
) -> Path:
    """
    Download klines for [start, end] and write a CSVDataset-compatible file.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        timeframe: Kline interval
        start: Range start (inclusive, tz-aware)
        end: Range end (inclusive, tz-aware)
        out_dir: Directory for the CSV file
        client: Optional pre-started client; a public mainnet client is
            created and managed when omitted
        page_pause_seconds: Pause between paginated requests

    Returns:
        Path to the written CSV file
    """
    owns_client = client is None
    if client is None:
        client = BinanceRestClient(api_key="", api_secret="")

    if owns_client:
        await client.start()
    try:
        candles = await _fetch_all_klines(
            client,
            symbol,
            timeframe,
            start,
            end,
            page_pause_seconds,
        )
    finally:
        if owns_client:
            await client.stop()

    now = datetime.now(UTC)
    closed_candles = [candle for candle in candles if candle.close_time <= now]
    if len(closed_candles) < len(candles):
        logger.info(f"Dropped {len(candles) - len(closed_candles)} unclosed candle(s)")

    if not closed_candles:
        raise ValueError(
            f"No klines returned for {symbol} {timeframe.value} between {start} and {end}",
        )

    candles = closed_candles

    out_path = Path(out_dir) / f"{symbol.lower()}_{timeframe.value}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    export_candles_to_csv(candles, str(out_path))
    return out_path


async def _fetch_all_klines(
    client: BinanceRestClient,
    symbol: str,
    timeframe: TimeFrame,
    start: datetime,
    end: datetime,
    page_pause_seconds: float,
) -> list[Candle]:
    candles: list[Candle] = []
    current_start = start

    while current_start <= end:
        page = await client.get_klines(
            symbol=symbol,
            timeframe=timeframe,
            start_time=current_start,
            end_time=end,
            limit=_PAGE_LIMIT,
        )
        fresh = [
            candle
            for candle in page
            if candle.open_time <= end and (not candles or candle.open_time > candles[-1].open_time)
        ]
        if not fresh:
            break

        candles.extend(fresh)
        current_start = candles[-1].close_time + timedelta(milliseconds=1)

        if page_pause_seconds > 0:
            await asyncio.sleep(page_pause_seconds)

    logger.info(
        f"Downloaded {len(candles)} {timeframe.value} klines for {symbol} "
        f"({start.date()} → {end.date()})",
    )
    return candles


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download Binance klines into CSVDataset-ready files",
    )
    parser.add_argument("--symbol", required=True, help="Trading symbol, e.g. BTCUSDT")
    parser.add_argument(
        "--tf",
        required=True,
        choices=[timeframe.value for timeframe in TimeFrame],
        help="Kline timeframe",
    )
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD (UTC)")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD (UTC)")
    parser.add_argument("--out", required=True, help="Output directory for CSV files")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    csv_path = asyncio.run(
        download_klines(
            symbol=args.symbol,
            timeframe=TimeFrame(args.tf),
            start=parse_utc_date(args.start),
            end=parse_utc_date(args.end, end_of_day=True),
            out_dir=Path(args.out),
        ),
    )
    logger.info(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
