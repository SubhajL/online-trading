import numpy as np
import pytest

from .bb import calculate_bollinger_bands, calculate_rolling_std, calculate_sma


def test_calculate_bollinger_bands_insufficient_data():
    prices = np.array([100.0, 101.0, 102.0])
    upper, middle, lower = calculate_bollinger_bands(prices, period=5)

    assert np.all(np.isnan(upper))
    assert np.all(np.isnan(middle))
    assert np.all(np.isnan(lower))
    assert len(upper) == len(prices)


def test_calculate_bollinger_bands_negative_period():
    prices = np.array([100.0] * 25)
    with pytest.raises(ValueError, match="Period must be positive"):
        calculate_bollinger_bands(prices, period=-1)


def test_calculate_bollinger_bands_negative_std_dev():
    prices = np.array([100.0] * 25)
    with pytest.raises(
        ValueError,
        match="Standard deviation multiplier must be non-negative",
    ):
        calculate_bollinger_bands(prices, period=20, std_dev=-2.0)


def test_calculate_bollinger_bands_flat_prices():
    # Flat prices should have zero standard deviation
    prices = np.full(30, 100.0)
    upper, middle, lower = calculate_bollinger_bands(prices, period=20, std_dev=2.0)

    # After initial NaN values, all bands should be at 100
    valid_start = 19
    assert np.all(np.isclose(upper[valid_start:], 100.0))
    assert np.all(np.isclose(middle[valid_start:], 100.0))
    assert np.all(np.isclose(lower[valid_start:], 100.0))


def test_calculate_bollinger_bands_symmetry():
    # Bands should be symmetric around the middle
    prices = np.random.randn(50) * 10 + 100
    upper, middle, lower = calculate_bollinger_bands(prices, period=20, std_dev=2.0)

    # Check symmetry where all values are valid
    valid_mask = ~np.isnan(upper)
    if np.any(valid_mask):
        upper_distance = upper[valid_mask] - middle[valid_mask]
        lower_distance = middle[valid_mask] - lower[valid_mask]
        np.testing.assert_allclose(upper_distance, lower_distance, rtol=1e-10)


def test_calculate_bollinger_bands_with_zero_std_dev():
    prices = np.random.randn(50) * 10 + 100
    upper, middle, lower = calculate_bollinger_bands(prices, period=20, std_dev=0.0)

    # With 0 std dev, all bands should equal the SMA
    valid_mask = ~np.isnan(middle)
    if np.any(valid_mask):
        np.testing.assert_allclose(upper[valid_mask], middle[valid_mask], rtol=1e-10)
        np.testing.assert_allclose(lower[valid_mask], middle[valid_mask], rtol=1e-10)


def test_calculate_sma_basic():
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    result = calculate_sma(values, period=3)

    assert np.isnan(result[0])
    assert np.isnan(result[1])
    assert np.isclose(result[2], 2.0)  # (1+2+3)/3
    assert np.isclose(result[3], 3.0)  # (2+3+4)/3
    assert np.isclose(result[4], 4.0)  # (3+4+5)/3


def test_calculate_sma_with_nan():
    values = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
    result = calculate_sma(values, period=3)

    assert np.isnan(result[2])  # Contains NaN in window
    assert np.isnan(result[3])  # Contains NaN in window
    assert np.isclose(result[4], 9.0 / 3)  # (nan+4+5)/3 with nancumsum


def test_calculate_rolling_std_basic():
    # Constant values should have std=0
    values = np.full(10, 5.0)
    result = calculate_rolling_std(values, period=3)

    valid_values = result[~np.isnan(result)]
    assert np.all(np.isclose(valid_values, 0.0))


def test_calculate_rolling_std_increasing():
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    result = calculate_rolling_std(values, period=3)

    # Std of [1,2,3] = sqrt(2/3) ≈ 0.816
    assert np.isnan(result[0])
    assert np.isnan(result[1])
    assert np.isclose(result[2], np.std([1.0, 2.0, 3.0]))
    assert np.isclose(result[3], np.std([2.0, 3.0, 4.0]))


def test_calculate_bollinger_bands_squeeze():
    # Create data with decreasing volatility (squeeze)
    np.random.seed(42)
    trend = np.linspace(100, 110, 50)
    noise = np.concatenate(
        [
            np.random.randn(25) * 2,  # High volatility
            np.random.randn(25) * 0.5,  # Low volatility
        ],
    )
    prices = trend + noise

    upper, middle, lower = calculate_bollinger_bands(prices, period=10, std_dev=2.0)

    # Band width should decrease in second half
    valid_start = 10
    first_half_width = np.mean(upper[valid_start:25] - lower[valid_start:25])
    second_half_width = np.mean(upper[35:] - lower[35:])

    assert second_half_width < first_half_width


def test_calculate_bollinger_bands_expansion():
    # Create data with increasing volatility (expansion)
    np.random.seed(42)
    trend = np.linspace(100, 110, 50)
    noise = np.concatenate(
        [
            np.random.randn(25) * 0.5,  # Low volatility
            np.random.randn(25) * 2,  # High volatility
        ],
    )
    prices = trend + noise

    upper, middle, lower = calculate_bollinger_bands(prices, period=10, std_dev=2.0)

    # Band width should increase in second half
    valid_start = 10
    first_half_width = np.mean(upper[valid_start:25] - lower[valid_start:25])
    second_half_width = np.mean(upper[35:] - lower[35:])

    assert second_half_width > first_half_width


def test_calculate_bollinger_bands_deterministic():
    prices = np.array([100, 102, 101, 103, 102, 104, 103, 105, 104, 106] * 3)

    # Run multiple times to ensure deterministic results
    result1 = calculate_bollinger_bands(prices, period=5, std_dev=2.0)
    result2 = calculate_bollinger_bands(prices, period=5, std_dev=2.0)

    for arr1, arr2 in zip(result1, result2, strict=False):
        np.testing.assert_array_equal(arr1, arr2)


def test_calculate_bollinger_bands_custom_parameters():
    prices = np.random.randn(50) * 10 + 100

    # Different parameters should give different results
    bands1 = calculate_bollinger_bands(prices, period=10, std_dev=1.0)
    bands2 = calculate_bollinger_bands(prices, period=20, std_dev=2.0)

    # Check widths are different
    valid_start = 20
    width1 = bands1[0][valid_start:] - bands1[2][valid_start:]
    width2 = bands2[0][valid_start:] - bands2[2][valid_start:]

    assert not np.array_equal(width1, width2)
