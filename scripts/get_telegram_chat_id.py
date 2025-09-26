#!/usr/bin/env python3
"""
Script to get your Telegram chat ID.

Usage:
1. Replace YOUR_BOT_TOKEN with your actual bot token
2. Send a message to your bot in Telegram
3. Run this script to see your chat ID
"""

import requests
import json

# Replace with your bot token from BotFather
BOT_TOKEN = "8289541020:AAHd-sruzaADQO_3-aQ-6-C6_5izZ6s5edI"

def get_updates():
    """Get recent messages sent to the bot."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

    try:
        response = requests.get(url)
        response.raise_for_status()

        data = response.json()

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

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        print("\nMake sure:")
        print("1. Your bot token is correct")
        print("2. You have internet connection")

if __name__ == "__main__":
    if BOT_TOKEN == "YOUR_BOT_TOKEN":
        print("ERROR: Please replace YOUR_BOT_TOKEN with your actual bot token")
        print("Get your token from @BotFather in Telegram")
    else:
        get_updates()