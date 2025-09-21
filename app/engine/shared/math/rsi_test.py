import pytest
import numpy as np
from .rsi import calculate_rsi


def test_calculate_rsi_insufficient_data():
    prices = np.array([100.0, 101.0, 102.0])
    result = calculate_rsi(prices, period=14)
    assert np.all(np.isnan(result))
    assert len(result) == len(prices)


def test_calculate_rsi_negative_period():
    prices = np.array([100.0, 101.0, 102.0, 103.0])
    with pytest.raises(ValueError, match="Period must be positive"):
        calculate_rsi(prices, period=-1)


def test_calculate_rsi_zero_period():
    prices = np.array([100.0, 101.0, 102.0, 103.0])
    with pytest.raises(ValueError, match="Period must be positive"):
        calculate_rsi(prices, period=0)


def test_calculate_rsi_all_gains():
    # Prices only going up - RSI should approach 100
    prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    result = calculate_rsi(prices, period=3)

    # First 3 values should be NaN
    assert np.sum(np.isnan(result[:3])) == 3

    # RSI values should be very high (close to 100)
    non_nan_values = result[~np.isnan(result)]
    assert np.all(non_nan_values > 70)  # Overbought territory


def test_calculate_rsi_all_losses():
    # Prices only going down - RSI should approach 0
    prices = np.array([105.0, 104.0, 103.0, 102.0, 101.0, 100.0])
    result = calculate_rsi(prices, period=3)

    # First 3 values should be NaN
    assert np.sum(np.isnan(result[:3])) == 3

    # RSI values should be very low (close to 0)
    non_nan_values = result[~np.isnan(result)]
    assert np.all(non_nan_values < 30)  # Oversold territory


def test_calculate_rsi_no_change():
    # Flat prices - RSI should be around 50
    prices = np.full(20, 100.0)
    result = calculate_rsi(prices, period=14)

    # After initial NaN values, RSI should be undefined (NaN)
    # because avg_losses would be 0
    assert np.sum(~np.isnan(result)) == 0 or np.all(np.isnan(result[14:]))


def test_calculate_rsi_alternating():
    # Alternating up/down pattern
    prices = np.array([100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0, 101.0])
    result = calculate_rsi(prices, period=3)

    # RSI should stabilize around 50 (neutral)
    non_nan_values = result[~np.isnan(result)]
    if len(non_nan_values) > 0:
        # Should be in neutral territory
        assert np.mean(non_nan_values) > 40
        assert np.mean(non_nan_values) < 60


def test_calculate_rsi_with_nan_values():
    prices = np.array([100.0, 101.0, np.nan, 103.0, 104.0])
    result = calculate_rsi(prices, period=2)

    # NaN should propagate through calculations
    assert np.isnan(result[2])  # Direct NaN
    assert np.isnan(result[3])  # Affected by previous NaN
    assert np.isnan(result[4])  # Continues to propagate


def test_calculate_rsi_known_values():
    # Test with known RSI calculation
    # Example: if we have 14 days of gains at +1 and 0 losses
    # Average gain = 1, Average loss = 0, RS = inf, RSI = 100
    prices = np.arange(100.0, 115.0, 1.0)  # 15 prices, 14 gains of 1
    result = calculate_rsi(prices, period=14)

    # At index 14, RSI should be 100 (all gains)
    assert np.isclose(result[14], 100.0, rtol=1e-5)


def test_calculate_rsi_bounds():
    # RSI should always be between 0 and 100
    prices = np.random.randn(100) * 10 + 50
    result = calculate_rsi(prices, period=14)

    non_nan_values = result[~np.isnan(result)]
    assert np.all(non_nan_values >= 0.0)
    assert np.all(non_nan_values <= 100.0)


def test_calculate_rsi_deterministic():
    prices = np.array([44.0, 44.25, 44.5, 43.75, 44.75, 45.0, 45.5, 45.0])
    period = 3

    # Run multiple times to ensure deterministic results
    result1 = calculate_rsi(prices, period)
    result2 = calculate_rsi(prices, period)

    np.testing.assert_array_equal(result1, result2)