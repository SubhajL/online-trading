#!/usr/bin/env python3
"""
Generate Golden Vectors for Technical Indicators (Simplified)

This script calculates expected values for all technical indicators using
the fixture data and saves them as golden vectors for regression testing.
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime

# Add the shared math directory directly to path
script_dir = os.path.dirname(os.path.abspath(__file__))
math_dir = os.path.join(script_dir, '..', 'app', 'engine', 'shared', 'math')
sys.path.insert(0, math_dir)

# Import math functions directly
from ema import calculate_ema
from rsi import calculate_rsi
from macd import calculate_macd
from atr import calculate_atr
from bb import calculate_bollinger_bands
from vwap import calculate_vwap, calculate_vwma


def load_fixture_data(fixture_path):
    """Load fixture CSV data"""
    df = pd.read_csv(fixture_path, parse_dates=["timestamp"])
    print(f"Loaded {len(df)} candles from {fixture_path}")
    return df


def calculate_all_indicators(df):
    """Calculate all technical indicators from the fixture data"""
    close_prices = df["close"].values
    high_prices = df["high"].values
    low_prices = df["low"].values
    volumes = df["volume"].values

    results = {}

    # EMA calculations
    for period in [20, 50]:  # Skip 200 as we don't have enough data
        ema_values = calculate_ema(close_prices, period)
        results[f"ema_{period}"] = ema_values.tolist()
        print(f"Calculated EMA({period})")

    # RSI
    rsi_values = calculate_rsi(close_prices, period=14)
    results["rsi_14"] = rsi_values.tolist()
    print("Calculated RSI(14)")

    # MACD
    macd_line, signal_line, histogram = calculate_macd(close_prices, 12, 26, 9)
    results["macd_line"] = macd_line.tolist()
    results["macd_signal"] = signal_line.tolist()
    results["macd_histogram"] = histogram.tolist()
    print("Calculated MACD(12,26,9)")

    # ATR
    atr_values = calculate_atr(high_prices, low_prices, close_prices, period=14)
    results["atr_14"] = atr_values.tolist()
    print("Calculated ATR(14)")

    # Bollinger Bands
    upper, middle, lower = calculate_bollinger_bands(close_prices, period=20, std_dev=2.0)
    results["bb_upper"] = upper.tolist()
    results["bb_middle"] = middle.tolist()
    results["bb_lower"] = lower.tolist()
    print("Calculated Bollinger Bands(20,2)")

    # VWAP
    vwap_values = calculate_vwap(
        high_prices, low_prices, close_prices, volumes, reset_daily=False
    )
    results["vwap"] = vwap_values.tolist()
    print("Calculated VWAP")

    # VWMA
    vwma_values = calculate_vwma(close_prices, volumes, period=20)
    results["vwma_20"] = vwma_values.tolist()
    print("Calculated VWMA(20)")

    return results


def save_golden_vectors(results, output_path):
    """Save calculated values as golden vectors"""
    # Convert NaN to None for JSON serialization
    for key, values in results.items():
        results[key] = [None if np.isnan(v) else round(v, 8) for v in values]

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved golden vectors to {output_path}")


def print_sample_values(results, df):
    """Print sample values for verification"""
    print("\nSample indicator values at last candle:")
    print("-" * 50)

    last_idx = len(df) - 1

    for key, values in results.items():
        if values[last_idx] is not None:
            print(f"{key:20s}: {values[last_idx]:.6f}")
        else:
            print(f"{key:20s}: NaN")

    # Print some statistics
    print("\nIndicator statistics:")
    print("-" * 50)

    for key, values in results.items():
        non_nan_values = [v for v in values if v is not None]
        if non_nan_values:
            print(f"{key:20s}: "
                  f"min={min(non_nan_values):.2f}, "
                  f"max={max(non_nan_values):.2f}, "
                  f"mean={sum(non_nan_values)/len(non_nan_values):.2f}")


def main():
    # Paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    fixture_path = os.path.join(
        script_dir, "..", "tests", "golden", "fixture_btcusdt_15m.csv"
    )
    output_path = os.path.join(
        script_dir, "..", "tests", "golden", "golden_vectors.json"
    )

    print(f"Golden Vector Generator")
    print(f"Generated at: {datetime.now().isoformat()}")
    print(f"=" * 60)

    # Load data
    df = load_fixture_data(fixture_path)

    # Calculate indicators
    print("\nCalculating indicators...")
    results = calculate_all_indicators(df)

    # Save results
    save_golden_vectors(results, output_path)

    # Print sample values
    print_sample_values(results, df)

    print("\nDone!")


if __name__ == "__main__":
    main()