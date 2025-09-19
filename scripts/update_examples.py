#!/usr/bin/env python3
"""Update example JSON files to use strings for numeric values."""

import json
from pathlib import Path

# Define which fields should be converted to strings
NUMERIC_FIELDS = {
    "open", "high", "low", "close", "volume", "quote_volume",
    "taker_buy_volume", "taker_buy_quote_volume",
    "price", "quantity", "size", "leverage", "risk_amount",
    "atr", "sl", "tp", "entry", "stop_loss", "take_profit",
    "entry_price", "stop_loss", "take_profit_1", "take_profit_2", "take_profit_3",
    "upper_bound", "lower_bound", "price_level",
    "previous_pivot_price", "broken_pivot_price",
    "stop_price", "filled_quantity", "average_fill_price",
    "position_size"
}

def convert_numerics_to_strings(data):
    """Recursively convert numeric fields to strings."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in NUMERIC_FIELDS and value is not None and isinstance(value, (int, float)):
                data[key] = str(value)
            elif isinstance(value, (dict, list)):
                convert_numerics_to_strings(value)
    elif isinstance(data, list):
        for item in data:
            convert_numerics_to_strings(item)

def main():
    examples_dir = Path("contracts/examples")

    for example_file in examples_dir.glob("*.example.json"):
        print(f"Updating {example_file.name}...")

        with open(example_file, "r") as f:
            data = json.load(f)

        # Convert numeric fields to strings
        convert_numerics_to_strings(data)

        # Write back with proper formatting
        with open(example_file, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")  # Add trailing newline

    print("✅ Updated all example files")

if __name__ == "__main__":
    main()