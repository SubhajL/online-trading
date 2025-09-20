#!/usr/bin/env python
"""
Integration test for Binance WebSocket that runs properly with Docker.
Connects to Binance testnet and stores closed candles in the Dockerized PostgreSQL.
"""
import asyncio
import json
import logging
import subprocess
from datetime import datetime
import websockets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Using production Binance WebSocket URL for testing (testnet WS not available)
WS_URL = "wss://stream.binance.com:9443/ws"
SYMBOLS = ["btcusdt", "ethusdt"]
TIMEFRAMES = ["5m", "15m"]

async def store_candle_in_docker(candle_data):
    """Store a candle in the Dockerized database using docker exec."""
    try:
        insert_sql = f"""
            INSERT INTO candles (
                time, venue, symbol, timeframe, open, high, low, close, volume,
                quote_volume, trade_count, taker_buy_volume, taker_buy_quote_volume
            ) VALUES (
                to_timestamp({candle_data['open_time']}/1000.0), 'spot', '{candle_data['symbol']}',
                '{candle_data['timeframe']}', {float(candle_data['open'])}, {float(candle_data['high'])},
                {float(candle_data['low'])}, {float(candle_data['close'])}, {float(candle_data['volume'])},
                {float(candle_data['quote_volume'])}, {int(candle_data['trade_count'])},
                {float(candle_data['taker_buy_volume'])}, {float(candle_data['taker_buy_quote_volume'])}
            )
            ON CONFLICT (venue, symbol, timeframe, time) DO NOTHING
        """

        # Execute SQL in Docker container
        cmd = [
            'docker', 'exec', 'trading-postgres',
            'psql', '-U', 'trading_user', '-d', 'trading_platform',
            '-c', insert_sql
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info(f"✅ CLOSED candle stored: {candle_data['symbol'].upper()} {candle_data['timeframe']} at {datetime.fromtimestamp(candle_data['open_time']/1000.0)}")
            return True
        else:
            logger.error(f"Error storing candle: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Error storing candle: {e}")
        return False

async def get_candle_count():
    """Get current candle count from Docker PostgreSQL."""
    cmd = [
        'docker', 'exec', 'trading-postgres',
        'psql', '-U', 'trading_user', '-d', 'trading_platform',
        '-t', '-c', 'SELECT COUNT(*) FROM candles'
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return int(result.stdout.strip())
    return 0

async def process_kline_message(msg):
    """Process a kline WebSocket message."""
    try:
        data = json.loads(msg)

        if 'k' in data:
            kline = data['k']
            symbol = data['s'].lower()

            # Only process closed candles
            if kline['x']:  # x = true means candle is closed
                candle_data = {
                    'symbol': symbol,
                    'timeframe': kline['i'],
                    'open_time': kline['t'],
                    'close_time': kline['T'],
                    'open': kline['o'],
                    'high': kline['h'],
                    'low': kline['l'],
                    'close': kline['c'],
                    'volume': kline['v'],
                    'quote_volume': kline['q'],
                    'trade_count': kline['n'],
                    'taker_buy_volume': kline['V'],
                    'taker_buy_quote_volume': kline['Q']
                }

                await store_candle_in_docker(candle_data)
            else:
                logger.debug(f"Received open candle for {symbol} {kline['i']}, waiting for close...")

    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON: {e}")
    except Exception as e:
        logger.error(f"Error processing message: {e}")

async def monitor_database():
    """Monitor database growth in the background."""
    while True:
        count = await get_candle_count()
        logger.info(f"📊 Database candle count: {count}")
        await asyncio.sleep(30)  # Check every 30 seconds

async def main():
    """Main function to run the WebSocket client."""
    logger.info("🚀 Starting Binance Spot WebSocket Docker integration test...")
    logger.info(f"Connecting to: {WS_URL}")
    logger.info(f"Symbols: {', '.join(SYMBOLS)}")
    logger.info(f"Timeframes: {', '.join(TIMEFRAMES)}")

    # Get initial count
    initial_count = await get_candle_count()
    logger.info(f"📊 Initial database candle count: {initial_count}")

    # Build subscription message
    streams = []
    for symbol in SYMBOLS:
        for timeframe in TIMEFRAMES:
            streams.append(f"{symbol}@kline_{timeframe}")

    subscribe_msg = {
        "method": "SUBSCRIBE",
        "params": streams,
        "id": 1
    }

    # Start database monitor
    monitor_task = asyncio.create_task(monitor_database())

    try:
        async with websockets.connect(WS_URL) as ws:
            logger.info("✓ Connected to Binance WebSocket")

            # Subscribe to streams
            await ws.send(json.dumps(subscribe_msg))
            logger.info(f"✓ Subscribed to {len(streams)} streams")

            # Receive messages
            while True:
                msg = await ws.recv()
                await process_kline_message(msg)

    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
        monitor_task.cancel()
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        monitor_task.cancel()

if __name__ == "__main__":
    # Test Docker connectivity first
    try:
        result = subprocess.run(
            ['docker', 'exec', 'trading-postgres', 'psql', '-U', 'trading_user', '-d', 'trading_platform', '-c', 'SELECT 1'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            logger.info("✓ Docker PostgreSQL connection successful")
        else:
            logger.error(f"Docker PostgreSQL connection failed: {result.stderr}")
            exit(1)
    except Exception as e:
        logger.error(f"Docker connectivity test failed: {e}")
        exit(1)

    # Run WebSocket client
    asyncio.run(main())