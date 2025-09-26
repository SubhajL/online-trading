#!/usr/bin/env python3
"""
Test sending a real chart image to Telegram.
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


async def test_chart_with_real_image():
    """Test sending a real chart image."""
    # Load configuration
    config = {
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "chat_id": os.getenv("TELEGRAM_CHAT_ID"),
        "timeout": 30,
        "max_retries": 3
    }

    if not config["bot_token"] or not config["chat_id"]:
        print("ERROR: Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return

    telegram = TelegramDelivery(config)

    # Create a sample chart using matplotlib
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        import numpy as np
        from io import BytesIO

        # Generate sample price data
        x = np.linspace(0, 100, 100)
        price = 50000 + 1000 * np.sin(x/10) + 200 * np.random.randn(100)

        # Create chart
        fig, ax = plt.subplots(figsize=(10, 6))

        # Plot candlestick-like data
        ax.plot(x, price, 'b-', linewidth=2, label='Price')

        # Add EMA lines
        ema20 = np.convolve(price, np.ones(20)/20, mode='valid')
        ema50 = np.convolve(price, np.ones(50)/50, mode='valid')
        ax.plot(x[19:], ema20, 'g-', linewidth=1, label='EMA 20')
        ax.plot(x[49:], ema50, 'r-', linewidth=1, label='EMA 50')

        # Add signal marker
        signal_idx = 80
        ax.plot(signal_idx, price[signal_idx], 'go', markersize=15, label='BUY Signal')
        ax.annotate('BUY', (signal_idx, price[signal_idx]),
                   xytext=(signal_idx-10, price[signal_idx]+500),
                   arrowprops=dict(arrowstyle='->', color='green', lw=2))

        # Add support level
        support_level = 49800
        ax.axhline(y=support_level, color='blue', linestyle='--', alpha=0.7, label='Support')

        # Formatting
        ax.set_title('BTCUSDT - 15m Chart', fontsize=16, fontweight='bold')
        ax.set_xlabel('Time', fontsize=12)
        ax.set_ylabel('Price (USDT)', fontsize=12)
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Convert to PNG bytes
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        chart_bytes = buffer.read()
        plt.close()

        print(f"Generated chart: {len(chart_bytes)} bytes")

        # Create signal for caption
        signal = RetestSignal(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            retest_type="support_retest",
            level_price=Decimal("49800"),
            level_strength=4,
            level_touches=5,
            approach_angle=28.5,
            distance_to_level=0.15,
            volume_confirmation=True,
            volume_increase_pct=42.3,
            macd_momentum=0.0018,
            rsi_value=38.2,
            bounce_count=3,
            false_breaks=0,
            time_at_level=240,
            confluence_score=0.92,
            confluence_factors=["BOS", "EMA_support", "volume_spike", "demand_zone"],
            success_probability=0.85,
            metadata={
                "entry": 50200,
                "stop_loss": 49600,
                "take_profit": 51400
            }
        )

        # Format caption
        caption = telegram._format_signal_caption(signal)
        caption += "\n\n📊 *Chart Analysis:*\n"
        caption += "• Price bounced from support level\n"
        caption += "• EMA alignment confirms trend\n"
        caption += "• Strong volume on retest"

        # Send chart with caption
        print("\nSending chart to Telegram...")
        result = await telegram.send_snapshot(
            image_data=chart_bytes,
            caption=caption
        )

        print(f"Result: {result}")

        if result["success"]:
            print("\n✅ Chart sent successfully! Check your Telegram.")
        else:
            print(f"\n❌ Failed to send chart: {result.get('error')}")

    except ImportError:
        print("\nTo send a real chart, install matplotlib:")
        print("pip install matplotlib")

        # Alternative: use a sample image file
        print("\nAlternatively, you can test with any PNG/JPEG file:")
        print("1. Save any chart image as 'test_chart.png'")
        print("2. Modify this script to read that file")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    asyncio.run(test_chart_with_real_image())