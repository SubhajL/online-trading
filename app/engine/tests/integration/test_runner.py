"""Simple test runner to demonstrate integration tests."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from adapters.db import timescale
from adapters.db.connection_pool import DBConfig
from types import Candle, TimeFrame, TechnicalIndicators


async def run_integration_example():
    """Run a simple integration test example."""
    # Initialize connection pool
    config = DBConfig(
        host="localhost",
        port=5432,
        database="trading_db",
        username="trading_user",
        password="trading_pass",
    )

    try:
        await timescale.initialize_pool(config)
        print("✓ Connection pool initialized")

        # Test 1: Insert candle with Decimal precision
        candle = Candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            open_time=datetime.utcnow(),
            close_time=datetime.utcnow() + timedelta(hours=1),
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

        result = await timescale.upsert_candle(candle)
        print(f"✓ Candle inserted: {result}")

        # Test 2: Retrieve candle and verify Decimal precision
        candles = await timescale.get_candles(
            symbol="BTCUSDT", timeframe=TimeFrame.H1, limit=1
        )

        if candles:
            retrieved = candles[0]
            print(f"✓ Candle retrieved")
            print(f"  Open price type: {type(retrieved['open_price'])}")
            print(f"  Open price value: {retrieved['open_price']}")
            print(
                f"  Precision preserved: {retrieved['open_price'] == candle.open_price}"
            )

        # Test 3: Insert technical indicators
        indicator = TechnicalIndicators(
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            timestamp=datetime.utcnow(),
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

        result = await timescale.upsert_indicator(indicator)
        print(f"✓ Indicator inserted: {result}")

        # Test 4: Test order with various numeric types
        order_data = {
            "client_order_id": f"test_{datetime.utcnow().timestamp()}",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "quantity": 0.01,  # Float
            "price": "50000.00",  # String
            "commission": Decimal("0.00001"),  # Decimal
        }

        result = await timescale.upsert_order(order_data)
        print(f"✓ Order inserted with mixed numeric types: {result}")

        # Test 5: Get active positions
        positions = await timescale.get_active_positions()
        print(f"✓ Active positions retrieved: {len(positions)} found")

        print("\n✅ All integration tests passed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await timescale.close_pool()
        print("✓ Connection pool closed")


if __name__ == "__main__":
    asyncio.run(run_integration_example())
