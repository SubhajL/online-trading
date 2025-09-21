import pytest
import numpy as np
from .ema import calculate_ema, calculate_ema_wilder


def test_calculate_ema_insufficient_data():
    values = np.array([1.0, 2.0, 3.0])
    result = calculate_ema(values, period=5)
    assert np.all(np.isnan(result))
    assert len(result) == len(values)


def test_calculate_ema_negative_period():
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    with pytest.raises(ValueError, match="Period must be positive"):
        calculate_ema(values, period=-1)


def test_calculate_ema_zero_period():
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    with pytest.raises(ValueError, match="Period must be positive"):
        calculate_ema(values, period=0)


def test_calculate_ema_basic():
    values = np.array([10.0, 12.0, 13.0, 11.0, 14.0, 15.0, 16.0, 14.0, 12.0, 11.0])
    result = calculate_ema(values, period=3)

    # First 2 values should be NaN
    assert np.isnan(result[0])
    assert np.isnan(result[1])

    # Third value should be SMA of first 3
    expected_sma = (10.0 + 12.0 + 13.0) / 3
    assert np.isclose(result[2], expected_sma)

    # Check subsequent values use EMA formula
    multiplier = 2.0 / (3 + 1)  # 0.5
    expected_ema4 = 11.0 * multiplier + result[2] * (1 - multiplier)
    assert np.isclose(result[3], expected_ema4)


def test_calculate_ema_with_nan_values():
    values = np.array([10.0, 12.0, np.nan, 11.0, 14.0])
    result = calculate_ema(values, period=2)

    assert np.isnan(result[0])
    assert not np.isnan(result[1])  # SMA of [10, 12]
    assert np.isnan(result[2])  # Propagates NaN
    assert np.isnan(result[3])  # Continues to propagate
    assert np.isnan(result[4])  # Continues to propagate


def test_calculate_ema_wilder():
    values = np.array([10.0, 12.0, 13.0, 11.0, 14.0])
    period = 3

    result = calculate_ema_wilder(values, period)

    # Verify it uses smoothing=1.0
    expected = calculate_ema(values, period, smoothing=1.0)
    np.testing.assert_array_equal(result, expected)

    # Check the multiplier is different from standard EMA
    multiplier_wilder = 1.0 / (period + 1)  # 0.25
    multiplier_standard = 2.0 / (period + 1)  # 0.5
    assert multiplier_wilder != multiplier_standard


def test_calculate_ema_deterministic():
    values = np.array([42.5, 43.0, 42.8, 43.2, 43.5, 44.0, 43.8])
    period = 3

    # Run multiple times to ensure deterministic results
    result1 = calculate_ema(values, period)
    result2 = calculate_ema(values, period)

    np.testing.assert_array_equal(result1, result2)


def test_calculate_ema_preserves_single_value():
    # If all values are the same, EMA should converge to that value
    values = np.full(20, 100.0)
    result = calculate_ema(values, period=5)

    # After initial NaN values, all should be 100.0
    non_nan_values = result[~np.isnan(result)]
    assert np.all(np.isclose(non_nan_values, 100.0))


def test_calculate_ema_large_period():
    values = np.random.randn(100) * 10 + 50
    result = calculate_ema(values, period=50)

    # First 49 values should be NaN
    assert np.sum(np.isnan(result[:49])) == 49
    # Remaining should not be NaN
    assert np.sum(np.isnan(result[49:])) == 0