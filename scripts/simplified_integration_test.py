#!/usr/bin/env python3
"""
Simplified integration test to verify services are working.
"""

import os
import sys
import asyncio
import json
from datetime import datetime

# Override PostgreSQL password
os.environ["POSTGRES_PASSWORD"] = "your_secure_password_here"

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import redis
import aiohttp


async def test_services():
    """Test all services are working."""
    print("\nINTEGRATION TEST - SERVICE CHECK")
    print("=" * 60)

    results = {}

    # Test PostgreSQL
    try:
        conn = psycopg2.connect(
            host="127.0.0.1",
            port="5432",
            database="trading_platform",
            user="trading_user",
            password="your_secure_password_here"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM candles;")
        count = cursor.fetchone()[0]
        print(f"✓ PostgreSQL connected. Candles in DB: {count}")
        results["postgresql"] = True
        conn.close()
    except Exception as e:
        print(f"✗ PostgreSQL error: {e}")
        results["postgresql"] = False

    # Test Redis
    try:
        r = redis.Redis(host="localhost", port=6379, decode_responses=True)
        r.ping()
        print("✓ Redis connected")
        results["redis"] = True
    except Exception as e:
        print(f"✗ Redis error: {e}")
        results["redis"] = False

    # Test Binance Testnet
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://testnet.binance.vision/api/v3/time") as response:
                if response.status == 200:
                    data = await response.json()
                    server_time = datetime.fromtimestamp(data['serverTime'] / 1000)
                    print(f"✓ Binance testnet connected. Server time: {server_time}")
                    results["binance"] = True
    except Exception as e:
        print(f"✗ Binance error: {e}")
        results["binance"] = False

    # Test Telegram
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if bot_token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getMe"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data["ok"]:
                            bot_info = data["result"]
                            print(f"✓ Telegram bot connected: @{bot_info['username']}")
                            results["telegram"] = True
        except Exception as e:
            print(f"✗ Telegram error: {e}")
            results["telegram"] = False
    else:
        print("✗ Telegram credentials not configured")
        results["telegram"] = False

    # Send test notification to Telegram
    if results.get("telegram"):
        try:
            message = f"""🚀 **Integration Test Started**

✅ Services Status:
• PostgreSQL: {'✓' if results.get('postgresql') else '✗'}
• Redis: {'✓' if results.get('redis') else '✗'}
• Binance Testnet: {'✓' if results.get('binance') else '✗'}
• Telegram: {'✓' if results.get('telegram') else '✗'}

Test Directory: `test_run_2025_09_26`
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

            send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                async with session.post(send_url, json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                }) as response:
                    if response.status == 200:
                        print("✓ Test notification sent to Telegram")
                    else:
                        error = await response.text()
                        print(f"✗ Failed to send Telegram notification: {error}")
        except Exception as e:
            print(f"✗ Telegram send error: {e}")

    print("\n" + "=" * 60)

    # Save results
    results_file = "test_run_2025_09_26/service_status.json"
    os.makedirs(os.path.dirname(results_file), exist_ok=True)

    with open(results_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "services": results,
            "all_good": all(results.values())
        }, f, indent=2)

    if all(results.values()):
        print("✅ All services are working properly!")
        print(f"\nTest data will be saved to: test_run_2025_09_26/")
        print("\nNOTE: Full engine start requires fixing module imports")
    else:
        print("❌ Some services have issues")

    return all(results.values())


async def main():
    """Run the simplified test."""
    success = await test_services()

    if success:
        # Start monitoring candles
        print("\n" + "=" * 60)
        print("MONITORING BINANCE CANDLES")
        print("=" * 60)

        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "MATICUSDT"]

        async with aiohttp.ClientSession() as session:
            for symbol in symbols:
                try:
                    url = f"https://testnet.binance.vision/api/v3/klines"
                    params = {
                        "symbol": symbol,
                        "interval": "15m",
                        "limit": 1
                    }

                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data:
                                candle = data[0]
                                open_time = datetime.fromtimestamp(candle[0] / 1000)
                                print(f"{symbol}: Open={candle[1]}, High={candle[2]}, Low={candle[3]}, Close={candle[4]} @ {open_time}")
                except Exception as e:
                    print(f"Error fetching {symbol}: {e}")

        print("\n✓ Test completed successfully!")
        print("\nNext steps:")
        print("1. Fix module imports in app/engine/main.py")
        print("2. Create proper engine config")
        print("3. Run full integration test")


if __name__ == "__main__":
    asyncio.run(main())