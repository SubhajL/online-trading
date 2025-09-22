"""
Volume Weighted Average Price (VWAP) and Volume Weighted Moving Average (VWMA) calculations

VWAP resets daily and is commonly used for intraday trading.
VWMA is a moving average weighted by volume.
"""

from typing import Any

import numpy as np


def calculate_vwap(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    reset_daily: bool = True,
    timestamps: np.ndarray | None = None,
) -> np.ndarray:
    """
    Calculate Volume Weighted Average Price (VWAP).

    VWAP = Cumulative(Typical Price × Volume) / Cumulative(Volume)
    where Typical Price = (High + Low + Close) / 3

    Args:
        high: Array of high prices
        low: Array of low prices
        close: Array of close prices
        volume: Array of volumes
        reset_daily: Whether to reset VWAP daily (requires timestamps)
        timestamps: Array of timestamps for daily reset detection

    Returns:
        Array of VWAP values with same length as input.
    """
    if len(high) != len(low) or len(high) != len(close) or len(high) != len(volume):
        raise ValueError("All arrays must have the same length")

    if reset_daily and timestamps is None:
        raise ValueError("Timestamps required for daily reset")

    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    close = np.asarray(close, dtype=np.float64)
    volume = np.asarray(volume, dtype=np.float64)

    # Calculate typical price
    typical_price = (high + low + close) / 3.0

    if not reset_daily or timestamps is None:
        # Simple cumulative VWAP
        return _calculate_cumulative_vwap(typical_price, volume)

    # Daily reset VWAP
    timestamps = np.asarray(timestamps)
    vwap = np.full_like(typical_price, np.nan)

    # Find day boundaries
    # Assuming timestamps are datetime objects or can be converted to dates
    current_day_start = 0

    for i in range(len(timestamps)):
        if i > 0 and _is_new_day(timestamps[i - 1], timestamps[i]):
            current_day_start = i

        # Calculate VWAP from start of current day
        day_slice = slice(current_day_start, i + 1)
        day_tp = typical_price[day_slice]
        day_vol = volume[day_slice]

        vwap[i] = _calculate_single_vwap(day_tp, day_vol)

    return vwap


def calculate_vwma(
    prices: np.ndarray,
    volume: np.ndarray,
    period: int = 20,
) -> np.ndarray:
    """
    Calculate Volume Weighted Moving Average (VWMA).

    VWMA = Sum(Price × Volume, period) / Sum(Volume, period)

    Args:
        prices: Array of price values (typically close prices)
        volume: Array of volumes
        period: Period for the moving average

    Returns:
        Array of VWMA values with same length as input.
        First (period-1) values will be NaN.
    """
    if len(prices) != len(volume):
        raise ValueError("Price and volume arrays must have the same length")

    if len(prices) < period:
        return np.full_like(prices, np.nan, dtype=np.float64)

    if period <= 0:
        raise ValueError(f"Period must be positive, got {period}")

    prices = np.asarray(prices, dtype=np.float64)
    volume = np.asarray(volume, dtype=np.float64)
    vwma = np.full_like(prices, np.nan, dtype=np.float64)

    # Calculate VWMA for each window
    for i in range(period - 1, len(prices)):
        window_start = i - period + 1
        window_prices = prices[window_start : i + 1]
        window_volume = volume[window_start : i + 1]

        if np.any(np.isnan(window_prices)) or np.any(np.isnan(window_volume)):
            vwma[i] = np.nan
        elif np.sum(window_volume) == 0:
            vwma[i] = np.nan  # Avoid division by zero
        else:
            vwma[i] = np.sum(window_prices * window_volume) / np.sum(window_volume)

    return vwma


def _calculate_cumulative_vwap(
    typical_price: np.ndarray,
    volume: np.ndarray,
) -> np.ndarray:
    """Calculate cumulative VWAP without daily resets."""
    vwap = np.full_like(typical_price, np.nan)

    cumulative_pv = 0.0
    cumulative_v = 0.0

    for i in range(len(typical_price)):
        if np.isnan(typical_price[i]) or np.isnan(volume[i]):
            vwap[i] = np.nan
        else:
            cumulative_pv += typical_price[i] * volume[i]
            cumulative_v += volume[i]

            if cumulative_v == 0:
                vwap[i] = np.nan
            else:
                vwap[i] = cumulative_pv / cumulative_v

    return vwap


def _calculate_single_vwap(typical_price: np.ndarray, volume: np.ndarray) -> float:
    """Calculate VWAP for a single period."""
    if np.any(np.isnan(typical_price)) or np.any(np.isnan(volume)):
        return np.nan

    total_volume = np.sum(volume)
    if total_volume == 0:
        return np.nan

    return float(np.sum(typical_price * volume) / total_volume)


def _is_new_day(timestamp1: Any, timestamp2: Any) -> bool:
    """Check if timestamp2 is a new day compared to timestamp1."""
    # This is a simplified check - in production you'd use proper datetime handling
    # For now, assume timestamps are unix timestamps
    try:
        # Convert to days since epoch
        day1 = int(timestamp1 // 86400)  # 86400 seconds in a day
        day2 = int(timestamp2 // 86400)
        return day2 > day1
    except:
        return False
