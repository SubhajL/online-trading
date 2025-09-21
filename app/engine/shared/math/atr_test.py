import numpy as np
import pytest

from .atr import calculate_atr, calculate_true_range


def test_calculate_atr_insufficient_data():
    high = np.array([10.0, 11.0, 12.0])
    low = np.array([9.0, 10.0, 11.0])
    close = np.array([9.5, 10.5, 11.5])

    result = calculate_atr(high, low, close, period=14)
    assert np.all(np.isnan(result))
    assert len(result) == len(high)


def test_calculate_atr_mismatched_lengths():
    high = np.array([10.0, 11.0, 12.0])
    low = np.array([9.0, 10.0])  # Different length
    close = np.array([9.5, 10.5, 11.5])

    with pytest.raises(ValueError, match="All price arrays must have the same length"):
        calculate_atr(high, low, close)


def test_calculate_atr_negative_period():
    high = np.array([10.0, 11.0, 12.0, 13.0])
    low = np.array([9.0, 10.0, 11.0, 12.0])
    close = np.array([9.5, 10.5, 11.5, 12.5])

    with pytest.raises(ValueError, match="Period must be positive"):
        calculate_atr(high, low, close, period=-1)


def test_calculate_atr_zero_volatility():
    # No price movement - ATR should be 0 after initial value
    high = np.full(20, 100.0)
    low = np.full(20, 100.0)
    close = np.full(20, 100.0)

    result = calculate_atr(high, low, close, period=5)

    # Skip initial NaN values
    non_nan_values = result[~np.isnan(result)]
    assert np.all(np.isclose(non_nan_values, 0.0))


def test_calculate_atr_simple_volatility():
    # Consistent 1-point range
    high = np.array([101, 102, 103, 104, 105, 106, 107, 108])
    low = np.array([100, 101, 102, 103, 104, 105, 106, 107])
    close = np.array([100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5])

    result = calculate_atr(high, low, close, period=3)

    # True range should be 1.0 for each candle
    # ATR should converge to 1.0
    assert np.all(np.isnan(result[:3]))
    assert np.isclose(result[3], 1.0, atol=0.1)


def test_calculate_true_range_first_candle():
    high = np.array([110.0])
    low = np.array([100.0])
    close = np.array([105.0])

    tr = calculate_true_range(high, low, close)
    assert tr[0] == 10.0  # high - low


def test_calculate_true_range_gap_up():
    # Gap up scenario: previous close below current range
    high = np.array([100, 110])
    low = np.array([95, 108])
    close = np.array([98, 109])

    tr = calculate_true_range(high, low, close)
    assert tr[0] == 5.0  # 100 - 95
    # TR[1] = max(110-108=2, |110-98|=12, |108-98|=10) = 12
    assert tr[1] == 12.0


def test_calculate_true_range_gap_down():
    # Gap down scenario: previous close above current range
    high = np.array([110, 95])
    low = np.array([105, 90])
    close = np.array([108, 92])

    tr = calculate_true_range(high, low, close)
    assert tr[0] == 5.0  # 110 - 105
    # TR[1] = max(95-90=5, |95-108|=13, |90-108|=18) = 18
    assert tr[1] == 18.0


def test_calculate_atr_with_nan_values():
    high = np.array([100, 101, np.nan, 103, 104])
    low = np.array([99, 100, 101, 102, 103])
    close = np.array([99.5, 100.5, 101.5, 102.5, 103.5])

    result = calculate_atr(high, low, close, period=2)

    # NaN should propagate
    assert np.isnan(result[2])
    assert np.isnan(result[3])  # Affected by previous TR with NaN


def test_calculate_atr_increasing_volatility():
    # Increasing range over time
    high = np.array([101, 102, 104, 107, 111, 116, 122, 129])
    low = np.array([100, 100, 100, 100, 100, 100, 100, 100])
    close = np.array([100.5, 101, 102, 103.5, 105.5, 108, 111, 114.5])

    result = calculate_atr(high, low, close, period=3)

    # ATR should be increasing
    valid_atr = result[~np.isnan(result)]
    if len(valid_atr) > 1:
        # Check trend is increasing
        assert valid_atr[-1] > valid_atr[0]


def test_calculate_atr_deterministic():
    high = np.array([102, 103, 101, 104, 106, 105, 107, 108])
    low = np.array([100, 101, 99, 102, 104, 103, 105, 106])
    close = np.array([101, 102, 100, 103, 105, 104, 106, 107])

    # Run multiple times to ensure deterministic results
    result1 = calculate_atr(high, low, close, period=3)
    result2 = calculate_atr(high, low, close, period=3)

    np.testing.assert_array_equal(result1, result2)


def test_calculate_true_range_empty_arrays():
    high = np.array([])
    low = np.array([])
    close = np.array([])

    tr = calculate_true_range(high, low, close)
    assert len(tr) == 0