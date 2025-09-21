"""
Relative Strength Index (RSI) calculation

Implements RSI using the standard Wilder's smoothing method.
"""

import numpy as np

from .ema import calculate_ema_wilder


def calculate_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Calculate Relative Strength Index (RSI).

    Uses Wilder's smoothing method for average gain/loss calculation.

    Args:
        prices: Array of price values (typically close prices)
        period: RSI period (default 14)

    Returns:
        Array of RSI values (0-100 scale) with same length as input.
        First 'period' values will be NaN.
    """
    if len(prices) < period + 1:
        return np.full_like(prices, np.nan, dtype=np.float64)

    if period <= 0:
        raise ValueError(f"Period must be positive, got {period}")

    prices = np.asarray(prices, dtype=np.float64)
    rsi = np.full_like(prices, np.nan, dtype=np.float64)

    # Calculate price changes
    price_changes = np.diff(prices)

    # Separate gains and losses
    gains = np.where(price_changes > 0, price_changes, 0)
    losses = np.where(price_changes < 0, -price_changes, 0)

    # Calculate average gain and loss using Wilder's smoothing
    avg_gains = calculate_ema_wilder(gains, period)
    avg_losses = calculate_ema_wilder(losses, period)

    # Calculate RSI
    # Note: RSI values start from index 'period' (after we have period+1 prices)
    for i in range(period, len(prices)):
        # Map to original prices index (i-1 in gains/losses arrays)
        gain_idx = i - 1

        if np.isnan(avg_gains[gain_idx]) or np.isnan(avg_losses[gain_idx]):
            rsi[i] = np.nan
            continue

        if avg_losses[gain_idx] == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gains[gain_idx] / avg_losses[gain_idx]
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi