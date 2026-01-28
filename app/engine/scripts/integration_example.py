"""Manual integration example (not collected by pytest).

This script is a convenience utility for quickly exercising DB adapter behavior
against a live Postgres/Timescale instance.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.engine.adapters.db import timescale
from app.engine.adapters.db.connection_pool import DBConfig
from app.engine.models import Candle, TechnicalIndicators, TimeFrame


async def run_integration_example() -> None:
    config = DBConfig(
        host="localhost",
        port=5432,
        database="trading_platform",
        username="trading_user",
        password="your_secure_password_here",
    )

    await timescale.initialize_pool(config)
    try:
        candle = Candle(
            venue="spot",
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            open_time=datetime.now(UTC),
            close_time=datetime.now(UTC) + timedelta(hours=1),
            open_price=Decimal("50000.12345678"),
            high_price=Decimal("51000.87654321"),
            low_price=Decimal("49000.11111111"),
            close_price=Decimal("50500.99999999"),
            volume=Decimal("100.12345678"),
            quote_volume=Decimal("5050000.12345678"),
            trades=1000,
            taker_buy_base_volume=Decimal("50.12345678"),
            taker_buy_quote_volume=Decimal("2525000.12345678"),
        )

        await timescale.upsert_candle(candle)

        indicator = TechnicalIndicators(
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            timestamp=datetime.now(UTC),
            ema_9=Decimal("50100.12"),
            ema_21=Decimal("50050.34"),
            ema_50=Decimal("50000.56"),
            ema_200=Decimal("49800.78"),
            rsi_14=Decimal("65.43"),
            macd_line=Decimal("150.12"),
            macd_signal=Decimal("145.34"),
            macd_histogram=Decimal("4.78"),
            atr_14=Decimal("500.25"),
            bb_upper=Decimal("51000.00"),
            bb_middle=Decimal("50000.00"),
            bb_lower=Decimal("49000.00"),
            bb_width=Decimal("2000.00"),
            bb_percent=Decimal("0.75"),
        )

        await timescale.upsert_indicator(indicator)
    finally:
        await timescale.close_pool()


def main() -> None:
    asyncio.run(run_integration_example())


if __name__ == "__main__":
    main()

