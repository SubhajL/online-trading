from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.engine.models import Candle, TimeFrame

BAR_DURATION = timedelta(minutes=15)
SERIES_START = datetime(2024, 1, 2, tzinfo=UTC)


def make_candle(
    index: int,
    open_price: str,
    high_price: str,
    low_price: str,
    close_price: str,
    *,
    symbol: str = "BTCUSDT",
    timeframe: TimeFrame = TimeFrame.M15,
    venue: str = "SPOT",
    start: datetime = SERIES_START,
) -> Candle:
    open_time = start + index * BAR_DURATION
    return Candle(
        venue=venue,
        symbol=symbol,
        timeframe=timeframe,
        open_time=open_time,
        close_time=open_time + BAR_DURATION,
        open_price=Decimal(open_price),
        high_price=Decimal(high_price),
        low_price=Decimal(low_price),
        close_price=Decimal(close_price),
        volume=Decimal(10),
        quote_volume=Decimal(1000),
        trades=10,
        taker_buy_base_volume=Decimal(5),
        taker_buy_quote_volume=Decimal(500),
    )


def flat_candles(count: int, *, start_index: int = 0) -> list[Candle]:
    return [make_candle(start_index + i, "100", "100.5", "99.5", "100") for i in range(count)]


IMPULSE_BARS: list[tuple[str, str, str, str]] = [
    ("100", "100.5", "99.5", "100"),
    ("100", "100.4", "99.6", "100"),
    ("100", "100.3", "98", "99"),
    ("99", "99.5", "98.5", "99.2"),
    ("99.2", "102", "99", "101.5"),
    ("101.5", "101.8", "100.8", "101"),
    ("101", "101.2", "99.5", "99.8"),
    ("99.8", "100.5", "99.6", "100.3"),
    ("100.3", "103", "100.2", "102.8"),
    ("102.8", "102.9", "102", "102.5"),
    ("102.5", "103.6", "102.4", "103.4"),
]


def impulse_bos_candles(*, start_index: int = 0) -> list[Candle]:
    return [make_candle(start_index + i, *bar) for i, bar in enumerate(IMPULSE_BARS)]
