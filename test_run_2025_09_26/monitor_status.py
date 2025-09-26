#!/usr/bin/env python3
"""
Monitor integration test progress.
Run this to see current status.
"""

import json
import os
from datetime import datetime
from pathlib import Path


def get_test_status():
    """Get current test status."""
    config_path = "config/test_config.json"

    with open(config_path, "r") as f:
        config = json.load(f)

    print("=" * 60)
    print(f"INTEGRATION TEST STATUS - {datetime.now()}")
    print("=" * 60)

    # Count signals
    signal_count = 0
    for symbol_dir in Path("signals").iterdir():
        if symbol_dir.is_dir():
            signals = len(list(symbol_dir.glob("*.json")))
            if signals > 0:
                print(f"{symbol_dir.name}: {signals} signals")
                signal_count += signals

    print(f"\nTotal signals: {signal_count}")

    # Count orders
    executed = len(list(Path("orders/executed").glob("*.json")))
    failed = len(list(Path("orders/failed").glob("*.json")))
    cancelled = len(list(Path("orders/cancelled").glob("*.json")))

    print(f"\nOrders:")
    print(f"  Executed: {executed}")
    print(f"  Failed: {failed}")
    print(f"  Cancelled: {cancelled}")

    # Check latest balance
    balance_file = "account_history/balance_history.csv"
    if os.path.exists(balance_file):
        with open(balance_file, "r") as f:
            lines = f.readlines()
            if len(lines) > 1:
                last_line = lines[-1].strip()
                print(f"\nLatest balance: {last_line}")

    print("=" * 60)


if __name__ == "__main__":
    get_test_status()
