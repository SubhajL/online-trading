"""
Exponential Moving Average (EMA) calculation

Implements EMA using Wilder's smoothing method for consistency
with traditional technical analysis.
"""

from typing import Optional

import numpy as np


def calculate_ema(
    values: np.ndarray, period: int, smoothing: float = 2.0
) -> np.ndarray:
    """
    Calculate Exponential Moving Average.

    Args:
        values: Array of price values
        period: EMA period
        smoothing: Smoothing factor (default 2.0 for standard EMA)

    Returns:
        Array of EMA values with same length as input.
        First (period-1) values will be NaN.
    """
    if len(values) < period:
        return np.full_like(values, np.nan, dtype=np.float64)

    if period <= 0:
        raise ValueError(f"Period must be positive, got {period}")

    values = np.asarray(values, dtype=np.float64)
    ema = np.full_like(values, np.nan, dtype=np.float64)

    # Calculate multiplier
    multiplier = smoothing / (period + 1)

    # Calculate initial SMA as first EMA value
    sma = np.mean(values[:period])
    ema[period - 1] = sma

    # Calculate subsequent EMA values
    for i in range(period, len(values)):
        if np.isnan(values[i]) or np.isnan(ema[i - 1]):
            ema[i] = np.nan
        else:
            ema[i] = values[i] * multiplier + ema[i - 1] * (1 - multiplier)

    return ema


def calculate_ema_wilder(values: np.ndarray, period: int) -> np.ndarray:
    """
    Calculate EMA using Wilder's smoothing (used for RSI, ATR).

    This uses a smoothing factor of 1/period instead of 2/(period+1).

    Args:
        values: Array of values
        period: Period for calculation

    Returns:
        Array of smoothed values
    """
    return calculate_ema(values, period, smoothing=1.0)