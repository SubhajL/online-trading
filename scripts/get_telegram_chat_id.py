#!/usr/bin/env python3
"""
Script to get your Telegram chat ID.

Usage:
1. Export TELEGRAM_BOT_TOKEN in your shell
2. Send a message to your bot in Telegram
3. Run this script to see your chat ID
"""

import json
import os
from urllib.error import URLError
from urllib.request import urlopen


def get_updates(bot_token: str):
    """Get recent messages sent to the bot."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"

    try:
        with urlopen(url) as response:
            data = json.load(response)

        if data["ok"] and data["result"]:
            print("Recent messages:")
            print("-" * 50)

            for update in data["result"]:
                if "message" in update:
                    msg = update["message"]
                    chat_id = msg["chat"]["id"]
                    chat_type = msg["chat"]["type"]
                    from_user = msg["from"]["first_name"]
                    text = msg.get("text", "")

                    print(f"Chat ID: {chat_id}")
                    print(f"Type: {chat_type}")
                    print(f"From: {from_user}")
                    print(f"Message: {text}")
                    print("-" * 50)

                    if chat_type == "private":
                        print(f"\n✓ Your personal chat ID is: {chat_id}")
                        print("Add this to your .env file as TELEGRAM_CHAT_ID")

        else:
            print("No messages found. Please:")
            print("1. Make sure you've sent a message to your bot")
            print("2. Try sending '/start' to your bot")
            print("3. Run this script again")

    except (URLError, ValueError) as e:
        print(f"Error: {e}")
        print("\nMake sure:")
        print("1. Your TELEGRAM_BOT_TOKEN is correct")
        print("2. You have internet connection")


def main() -> int:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        print("ERROR: Please set TELEGRAM_BOT_TOKEN in your environment")
        print("Get your token from @BotFather in Telegram")
        return 1

    get_updates(bot_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
