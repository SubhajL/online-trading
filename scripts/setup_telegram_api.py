#!/usr/bin/env python3
# Run with: python3 scripts/setup_telegram_api.py
"""
Telegram API Credentials Setup Script
Configures .env.telegram with your Telethon API credentials
"""
import re
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def read_env_file(filepath: Path) -> str:
    """Read the current .env.telegram file."""
    if filepath.exists():
        return filepath.read_text()
    return ""


def update_env_value(content: str, key: str, value: str) -> str:
    """Update a single environment variable in the content."""
    pattern = rf"^{key}=.*$"
    replacement = f"{key}={value}"

    if re.search(pattern, content, re.MULTILINE):
        return re.sub(pattern, replacement, content, flags=re.MULTILINE)
    else:
        # Key doesn't exist, append it
        return content + f"\n{key}={value}"


def main():
    print()
    print("=" * 60)
    print("   TELEGRAM API CREDENTIALS SETUP")
    print("   For Captain Trading Channel Monitoring")
    print("=" * 60)
    print()
    print("This script will configure your Telegram User API credentials")
    print("for reading messages from Captain Trading's channel.")
    print()
    print("You need credentials from: https://my.telegram.org/apps")
    print()
    print("-" * 60)

    # Get credentials from user
    print()
    api_id = input("Enter your TELEGRAM_API_ID (number): ").strip()

    if not api_id.isdigit():
        print("Error: API ID must be a number!")
        return

    print()
    api_hash = input("Enter your TELEGRAM_API_HASH (string): ").strip()

    if len(api_hash) < 10:
        print("Error: API Hash seems too short. Please check your credentials.")
        return

    print()
    phone = input("Enter your TELEGRAM_PHONE (e.g., +66812345678): ").strip()

    if not phone.startswith("+"):
        print("Warning: Phone should start with '+' for international format.")
        confirm = input("Continue anyway? (y/n): ").strip().lower()
        if confirm != 'y':
            return

    print()
    channel = input("Enter Captain Trading channel (default: @SMC_Hybrid_Automation): ").strip()
    if not channel:
        channel = "@SMC_Hybrid_Automation"

    # Read current file
    project_root = get_project_root()
    env_file = project_root / ".env.telegram"

    content = read_env_file(env_file)

    # Update values
    content = update_env_value(content, "TELEGRAM_API_ID", api_id)
    content = update_env_value(content, "TELEGRAM_API_HASH", api_hash)
    content = update_env_value(content, "TELEGRAM_PHONE", phone)
    content = update_env_value(content, "CAPTAIN_TRADING_CHANNEL", channel)

    # Write back
    env_file.write_text(content)

    print()
    print("=" * 60)
    print("   CONFIGURATION SAVED!")
    print("=" * 60)
    print()
    print(f"File updated: {env_file}")
    print()
    print("Your credentials:")
    print(f"  TELEGRAM_API_ID     = {api_id}")
    print(f"  TELEGRAM_API_HASH   = {api_hash[:8]}...{api_hash[-4:]}")
    print(f"  TELEGRAM_PHONE      = {phone}")
    print(f"  CAPTAIN_CHANNEL     = {channel}")
    print()
    print("-" * 60)
    print("NEXT STEPS:")
    print("-" * 60)
    print()
    print("1. Install Telethon:")
    print("   pip install telethon")
    print()
    print("2. Source the environment:")
    print("   source .env.telegram")
    print()
    print("3. Run the listener:")
    print("   python3 scripts/captain_trading_listener.py")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
