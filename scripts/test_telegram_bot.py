#!/usr/bin/env python3
"""
Test script for Telegram bot functionality.

This script tests:
1. Bot connection
2. Sending text messages
3. Sending formatted messages with emojis
4. Sending images
"""

import os
import asyncio
from datetime import datetime
from decimal import Decimal

# Add parent directory to path
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engine.delivery.telegram import TelegramDelivery
from app.engine.models import TimeFrame, RetestSignal


async def test_telegram_bot():
    """Test Telegram bot functionality."""
    # Load configuration from environment
    config = {
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "chat_id": os.getenv("TELEGRAM_CHAT_ID"),
        "timeout": 30,
        "max_retries": 3
    }

    if not config["bot_token"] or not config["chat_id"]:
        print("ERROR: Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file")
        return

    # Initialize Telegram delivery
    telegram = TelegramDelivery(config)

    print("Testing Telegram Bot...")
    print(f"Chat ID: {config['chat_id']}")
    print("-" * 50)

    # Test 1: Simple text message
    print("\n[Test 1] Sending text alert...")
    result = await telegram.send_text_alert("🚀 Trading bot test message!\n\nThis is a test alert.")
    print(f"Result: {result}")

    # Test 2: Formatted signal message
    print("\n[Test 2] Sending formatted signal...")

    # Create a mock signal
    signal = RetestSignal(
        timestamp=datetime.now(),
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
        retest_type="support_retest",
        level_price=Decimal("50000"),
        level_strength=4,
        level_touches=3,
        approach_angle=25.5,
        distance_to_level=0.1,
        volume_confirmation=True,
        volume_increase_pct=35.2,
        macd_momentum=0.0015,
        rsi_value=42.5,
        bounce_count=2,
        false_breaks=0,
        time_at_level=180,
        confluence_score=0.88,
        confluence_factors=["BOS", "EMA_support", "volume_spike"],
        success_probability=0.82,
        metadata={
            "ema20": 50200,
            "ema50": 49800,
            "atr": 750,
            "trend_strength": 0.75
        }
    )

    # Generate caption
    caption = telegram._format_signal_caption(signal)

    # Send as text (without image)
    result = await telegram.send_text_alert(caption)
    print(f"Result: {result}")

    # Test 3: Test with mock image
    print("\n[Test 3] Sending signal with chart...")

    # Create mock PNG data
    mock_image = b"PNG_MOCK_DATA" * 1000  # ~13KB mock image

    result = await telegram.send_snapshot(
        image_data=mock_image,
        caption=caption
    )
    print(f"Result: {result}")

    # Test 4: Multiple alerts
    print("\n[Test 4] Sending multiple alerts...")

    symbols = ["ETHUSDT", "SOLUSDT", "BNBUSDT"]
    for i, symbol in enumerate(symbols):
        alert = f"📊 {symbol} Alert #{i+1}\n\n🎯 Test alert for {symbol}"
        result = await telegram.send_text_alert(alert)
        print(f"{symbol}: {result}")
        await asyncio.sleep(1)  # Avoid rate limiting

    print("\n" + "=" * 50)
    print("✅ Telegram bot test completed!")
    print("Check your Telegram for the messages")


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()

    # Run test
    asyncio.run(test_telegram_bot())