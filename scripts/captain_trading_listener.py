"""
Captain Trading Telegram Channel Listener

Connects to Captain Trading's SMC Hybrid Automation channel
and captures trading signals for comparison with our system.
"""

import asyncio
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from telethon import TelegramClient, events
from telethon.tl.types import Message, MessageMediaPhoto


def load_env_telegram():
    """Load credentials from .env.telegram file."""
    env_file = PROJECT_ROOT / ".env.telegram"
    if env_file.exists():
        print(f"Loading credentials from {env_file}")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()
    else:
        print(f"Warning: {env_file} not found")


# Load from .env.telegram first
load_env_telegram()

# Configuration - from .env.telegram or environment
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
PHONE = os.getenv("TELEGRAM_PHONE")
CAPTAIN_CHANNEL = os.getenv("CAPTAIN_TRADING_CHANNEL", "")

# Captain Trading channel(s) to monitor
CHANNELS_TO_MONITOR = [CAPTAIN_CHANNEL] if CAPTAIN_CHANNEL else []

# Session file location
SESSION_FILE = Path(__file__).parent.parent / "captain_trading_session"


class CaptainTradingListener:
    """Listen to Captain Trading's Telegram channel for signals."""

    def __init__(self):
        self.client = None
        self.signals_received = []

    async def start(self):
        """Initialize and start the Telegram client."""
        if not API_ID or not API_HASH:
            print("Error: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set")
            print("\nSet them in your environment:")
            print("  export TELEGRAM_API_ID=your_api_id")
            print("  export TELEGRAM_API_HASH=your_api_hash")
            print("  export TELEGRAM_PHONE=+66xxxxxxxxx")
            return False

        self.client = TelegramClient(
            str(SESSION_FILE),
            int(API_ID),
            API_HASH
        )

        await self.client.start(phone=PHONE)
        print(f"Connected as: {(await self.client.get_me()).first_name}")
        return True

    async def list_dialogs(self):
        """List all channels/groups you're a member of."""
        print("\n=== Your Telegram Channels & Groups ===\n")

        async for dialog in self.client.iter_dialogs():
            if dialog.is_channel or dialog.is_group:
                entity = dialog.entity
                print(f"Name: {dialog.name}")
                print(f"  ID: {entity.id}")
                if hasattr(entity, 'username') and entity.username:
                    print(f"  Username: @{entity.username}")
                print(f"  Type: {'Channel' if dialog.is_channel else 'Group'}")
                print()

    async def get_recent_messages(self, channel, limit=10):
        """Get recent messages from a channel."""
        print(f"\n=== Recent {limit} messages from {channel} ===\n")

        messages = await self.client.get_messages(channel, limit=limit)

        for msg in messages:
            print(f"[{msg.date}] ID: {msg.id}")
            if msg.text:
                print(f"Text: {msg.text[:200]}...")
            if msg.media:
                print(f"Media: {type(msg.media).__name__}")
            print("-" * 50)

        return messages

    async def listen_live(self, channels):
        """Listen for live messages from specified channels."""
        if not channels:
            print("No channels specified to monitor!")
            print("Add channel usernames or IDs to CHANNELS_TO_MONITOR")
            return

        print(f"\nListening for signals from: {channels}")
        print("Press Ctrl+C to stop\n")

        @self.client.on(events.NewMessage(chats=channels))
        async def handler(event: events.NewMessage.Event):
            msg: Message = event.message

            print(f"\n{'='*60}")
            print(f"NEW SIGNAL RECEIVED - {datetime.now(UTC).isoformat()}")
            print(f"{'='*60}")
            print(f"Channel: {event.chat.title if hasattr(event.chat, 'title') else event.chat_id}")
            print(f"Message ID: {msg.id}")
            print(f"Time: {msg.date}")

            if msg.text:
                print(f"\nText:\n{msg.text}")

            if isinstance(msg.media, MessageMediaPhoto):
                print("\n[Chart image attached]")
                # Optionally download the image
                # path = await msg.download_media(file="signals/")
                # print(f"Downloaded to: {path}")

            # Store for later analysis
            self.signals_received.append({
                "timestamp": msg.date,
                "message_id": msg.id,
                "text": msg.text,
                "has_image": isinstance(msg.media, MessageMediaPhoto),
            })

            print(f"\nTotal signals received: {len(self.signals_received)}")

        await self.client.run_until_disconnected()

    async def stop(self):
        """Disconnect the client."""
        if self.client:
            await self.client.disconnect()


async def main():
    """Main entry point."""
    listener = CaptainTradingListener()

    if not await listener.start():
        return

    print("\nWhat would you like to do?")
    print("1. List all your channels/groups")
    print("2. Get recent messages from a channel")
    print("3. Listen for live signals")
    print("4. Exit")

    choice = input("\nEnter choice (1-4): ").strip()

    if choice == "1":
        await listener.list_dialogs()

    elif choice == "2":
        channel = input("Enter channel username (e.g., @channel) or ID: ").strip()
        limit = int(input("How many messages? (default 10): ").strip() or "10")
        await listener.get_recent_messages(channel, limit)

    elif choice == "3":
        if not CHANNELS_TO_MONITOR:
            channel = input("Enter channel to monitor (e.g., @channel): ").strip()
            channels = [channel] if channel else []
        else:
            channels = CHANNELS_TO_MONITOR
        await listener.listen_live(channels)

    elif choice == "4":
        print("Goodbye!")

    await listener.stop()


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║     Captain Trading Telegram Channel Listener              ║
║     SMC Hybrid Automation Signal Monitor                   ║
╚═══════════════════════════════════════════════════════════╝
    """)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopped by user")
