"""
Moving Average Convergence Divergence (MACD) calculation

Implements MACD with standard parameters (12, 26, 9).
"""

from typing import Tuple

import numpy as np

from .ema import calculate_ema


def calculate_macd(
    prices: np.ndarray,  # type: ignore[type-arg]
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:  # type: ignore[type-arg]
    """
    Calculate MACD indicator components.

    Args:
        prices: Array of price values (typically close prices)
        fast: Fast EMA period (default 12)
        slow: Slow EMA period (default 26)
        signal: Signal line EMA period (default 9)

    Returns:
        Tuple containing:
        - MACD line (fast EMA - slow EMA)
        - Signal line (EMA of MACD line)
        - Histogram (MACD line - Signal line)
        All arrays have same length as input prices.
    """
    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError("All periods must be positive")

    if fast >= slow:
        raise ValueError("Fast period must be less than slow period")

    prices = np.asarray(prices, dtype=np.float64)

    # Calculate EMAs
    fast_ema = calculate_ema(prices, fast)
    slow_ema = calculate_ema(prices, slow)

    # Calculate MACD line
    macd_line = fast_ema - slow_ema

    # Calculate signal line (EMA of MACD line)
    # Only use non-NaN MACD values for signal calculation
    first_valid_idx = slow - 1  # First index where we have both EMAs
    if first_valid_idx >= len(macd_line):
        # Not enough data
        signal_line = np.full_like(prices, np.nan, dtype=np.float64)
        histogram = np.full_like(prices, np.nan, dtype=np.float64)
    else:
        # Extract valid MACD values
        valid_macd = macd_line[first_valid_idx:]

        if len(valid_macd) < signal:
            # Not enough MACD values for signal line
            signal_line = np.full_like(prices, np.nan, dtype=np.float64)
        else:
            # Calculate signal EMA
            signal_ema = calculate_ema(valid_macd, signal)

            # Align signal line with original array
            signal_line = np.full_like(prices, np.nan, dtype=np.float64)
            signal_line[first_valid_idx:] = signal_ema

        # Calculate histogram
        histogram = macd_line - signal_line

    return macd_line, signal_line, histogram
