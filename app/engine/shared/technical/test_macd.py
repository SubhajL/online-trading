import numpy as np
import pytest

from .macd import calculate_macd


def test_calculate_macd_insufficient_data():
    prices = np.array([100.0, 101.0, 102.0])
    macd, signal, hist = calculate_macd(prices)

    # All should be NaN
    assert np.all(np.isnan(macd))
    assert np.all(np.isnan(signal))
    assert np.all(np.isnan(hist))


def test_calculate_macd_negative_periods():
    prices = np.array([100.0] * 30)

    with pytest.raises(ValueError, match="All periods must be positive"):
        calculate_macd(prices, fast=-12, slow=26, signal=9)

    with pytest.raises(ValueError, match="All periods must be positive"):
        calculate_macd(prices, fast=12, slow=-26, signal=9)

    with pytest.raises(ValueError, match="All periods must be positive"):
        calculate_macd(prices, fast=12, slow=26, signal=-9)


def test_calculate_macd_invalid_period_order():
    prices = np.array([100.0] * 30)

    # Fast period must be less than slow period
    with pytest.raises(ValueError, match="Fast period must be less than slow period"):
        calculate_macd(prices, fast=26, slow=12, signal=9)

    with pytest.raises(ValueError, match="Fast period must be less than slow period"):
        calculate_macd(prices, fast=26, slow=26, signal=9)


def test_calculate_macd_flat_prices():
    # Flat prices should result in zero MACD
    prices = np.full(50, 100.0)
    macd, signal, hist = calculate_macd(prices, fast=12, slow=26, signal=9)

    # After initial NaN values, MACD should be close to 0
    first_valid = 25  # slow period - 1
    non_nan_macd = macd[first_valid:]
    assert np.all(np.abs(non_nan_macd) < 1e-10)

    # Signal should also be close to 0
    signal_valid_start = first_valid + 8  # signal period - 1
    non_nan_signal = signal[signal_valid_start:]
    assert np.all(np.abs(non_nan_signal) < 1e-10)


def test_calculate_macd_rising_prices():
    # Steadily rising prices
    prices = np.linspace(100, 150, 50)
    macd, signal, hist = calculate_macd(prices, fast=12, slow=26, signal=9)

    # MACD should be positive (fast EMA > slow EMA for rising prices)
    first_valid = 25  # slow period - 1
    later_macd = macd[first_valid + 5 :]  # Give it time to diverge
    assert np.all(later_macd > 0)

    # Histogram should eventually be positive (MACD accelerating)
    signal_valid_start = first_valid + 8
    later_hist = hist[signal_valid_start + 5 :]
    if len(later_hist) > 0:
        assert np.mean(later_hist) > 0


def test_calculate_macd_falling_prices():
    # Steadily falling prices
    prices = np.linspace(150, 100, 50)
    macd, signal, hist = calculate_macd(prices, fast=12, slow=26, signal=9)

    # MACD should be negative (fast EMA < slow EMA for falling prices)
    first_valid = 25  # slow period - 1
    later_macd = macd[first_valid + 5 :]  # Give it time to diverge
    assert np.all(later_macd < 0)


def test_calculate_macd_with_nan_values():
    prices = np.array([100.0] * 30)
    prices[15] = np.nan

    macd, signal, hist = calculate_macd(prices, fast=12, slow=26, signal=9)

    # NaN should propagate
    assert np.isnan(macd[15])
    # And affect subsequent values
    assert np.all(np.isnan(macd[15:]))


def test_calculate_macd_output_shapes():
    prices = np.random.randn(100) * 10 + 100
    macd, signal, hist = calculate_macd(prices)

    # All outputs should have same shape as input
    assert macd.shape == prices.shape
    assert signal.shape == prices.shape
    assert hist.shape == prices.shape


def test_calculate_macd_histogram_calculation():
    prices = np.random.randn(100) * 10 + 100
    macd, signal, hist = calculate_macd(prices)

    # Histogram should be MACD - Signal
    # Check where both are not NaN
    valid_mask = ~np.isnan(macd) & ~np.isnan(signal)
    if np.any(valid_mask):
        expected_hist = macd[valid_mask] - signal[valid_mask]
        np.testing.assert_allclose(hist[valid_mask], expected_hist, rtol=1e-10)


def test_calculate_macd_deterministic():
    prices = np.array([100, 102, 101, 103, 105, 104, 106, 108, 107, 109] * 5)
    fast, slow, signal_period = 5, 10, 3

    # Run multiple times to ensure deterministic results
    result1 = calculate_macd(prices, fast, slow, signal_period)
    result2 = calculate_macd(prices, fast, slow, signal_period)

    for arr1, arr2 in zip(result1, result2):
        np.testing.assert_array_equal(arr1, arr2)


def test_calculate_macd_custom_periods():
    prices = np.random.randn(100) * 10 + 100

    # Test with custom periods
    macd1, signal1, hist1 = calculate_macd(prices, fast=5, slow=10, signal=5)
    macd2, signal2, hist2 = calculate_macd(prices, fast=12, slow=26, signal=9)

    # Different parameters should give different results
    # Check after both have valid values
    valid_start = max(10, 26)
    assert not np.array_equal(macd1[valid_start:], macd2[valid_start:])
