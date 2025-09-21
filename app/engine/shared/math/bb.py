"""
Bollinger Bands calculation

Implements Bollinger Bands with standard parameters (20-period SMA, 2 std dev).
"""

import numpy as np
from typing import Tuple


def calculate_bollinger_bands(
    prices: np.ndarray,
    period: int = 20,
    std_dev: float = 2.0
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Calculate Bollinger Bands.

    Args:
        prices: Array of price values (typically close prices)
        period: Period for moving average and standard deviation (default 20)
        std_dev: Number of standard deviations for bands (default 2.0)

    Returns:
        Tuple containing:
        - Upper band (middle + std_dev * std)
        - Middle band (SMA)
        - Lower band (middle - std_dev * std)
        All arrays have same length as input prices.
    """
    if len(prices) < period:
        nan_array = np.full_like(prices, np.nan, dtype=np.float64)
        return nan_array, nan_array, nan_array

    if period <= 0:
        raise ValueError(f"Period must be positive, got {period}")

    if std_dev < 0:
        raise ValueError(f"Standard deviation multiplier must be non-negative, got {std_dev}")

    prices = np.asarray(prices, dtype=np.float64)

    # Calculate SMA (middle band)
    middle = calculate_sma(prices, period)

    # Calculate rolling standard deviation
    std = calculate_rolling_std(prices, period)

    # Calculate bands
    upper = middle + std_dev * std
    lower = middle - std_dev * std

    return upper, middle, lower


def calculate_sma(values: np.ndarray, period: int) -> np.ndarray:
    """
    Calculate Simple Moving Average.

    Args:
        values: Array of values
        period: SMA period

    Returns:
        Array of SMA values with same length as input.
        First (period-1) values will be NaN.
    """
    if len(values) < period:
        return np.full_like(values, np.nan, dtype=np.float64)

    sma = np.full_like(values, np.nan, dtype=np.float64)

    # Use cumsum for efficient rolling mean calculation
    cumsum = np.nancumsum(values)
    sma[period-1] = cumsum[period-1] / period

    for i in range(period, len(values)):
        if np.isnan(values[i]):
            sma[i] = np.nan
        else:
            sma[i] = (cumsum[i] - cumsum[i-period]) / period

    return sma


def calculate_rolling_std(values: np.ndarray, period: int) -> np.ndarray:
    """
    Calculate rolling standard deviation.

    Args:
        values: Array of values
        period: Period for standard deviation

    Returns:
        Array of rolling std values with same length as input.
        First (period-1) values will be NaN.
    """
    if len(values) < period:
        return np.full_like(values, np.nan, dtype=np.float64)

    std = np.full_like(values, np.nan, dtype=np.float64)

    for i in range(period-1, len(values)):
        window = values[i-period+1:i+1]
        if np.any(np.isnan(window)):
            std[i] = np.nan
        else:
            std[i] = np.std(window, ddof=0)  # Population standard deviation

    return std