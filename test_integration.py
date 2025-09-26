#!/usr/bin/env python3
"""
Quick test to verify integration test can start.
"""

import os
import asyncio
from datetime import datetime

# Override password
os.environ["POSTGRES_PASSWORD"] = "password"

from dotenv import load_dotenv
load_dotenv()

async def test_services():
    """Test basic service connections."""
    print("Testing service connections...")
    print("=" * 60)

    # Test PostgreSQL
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost",
            port="5432",
            database="trading_platform",
            user="trading_user",
            password="password"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM candles;")
        count = cursor.fetchone()[0]
        print(f"✓ PostgreSQL connected. Candles in DB: {count}")
        conn.close()
    except Exception as e:
        print(f"✗ PostgreSQL error: {e}")

    # Test Redis
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, decode_responses=True)
        r.ping()
        print("✓ Redis connected")
    except Exception as e:
        print(f"✗ Redis error: {e}")

    # Test Binance API
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("https://testnet.binance.vision/api/v3/time") as response:
                if response.status == 200:
                    data = await response.json()
                    server_time = datetime.fromtimestamp(data['serverTime'] / 1000)
                    print(f"✓ Binance testnet connected. Server time: {server_time}")
    except Exception as e:
        print(f"✗ Binance error: {e}")

    # Test Telegram
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if bot_token and chat_id:
        print(f"✓ Telegram configured. Chat ID: {chat_id}")
    else:
        print("✗ Telegram not configured")

    print("\n" + "=" * 60)
    print("Ready to start integration test!")
    print("Run: python scripts/start_integration_test.py")


if __name__ == "__main__":
    asyncio.run(test_services())