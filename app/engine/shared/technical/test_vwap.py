import numpy as np
import pytest

from .vwap import calculate_vwap, calculate_vwma


def test_calculate_vwap_mismatched_lengths() -> None:
    high = np.array([10.0, 11.0])
    low = np.array([9.0, 10.0])
    close = np.array([9.5, 10.5])
    volume = np.array([100.0])  # Different length

    with pytest.raises(ValueError, match="All arrays must have the same length"):
        calculate_vwap(high, low, close, volume)


def test_calculate_vwap_simple() -> None:
    # Simple case with known values
    high = np.array([101.0, 102.0, 103.0])
    low = np.array([99.0, 100.0, 101.0])
    close = np.array([100.0, 101.0, 102.0])
    volume = np.array([100.0, 200.0, 300.0])

    vwap = calculate_vwap(high, low, close, volume, reset_daily=False)

    # Typical prices: [100, 101, 102]
    # VWAP[0] = 100*100 / 100 = 100
    # VWAP[1] = (100*100 + 101*200) / (100+200) = 30200/300 = 100.667
    # VWAP[2] = (100*100 + 101*200 + 102*300) / 600 = 60900/600 = 101.5

    assert np.isclose(vwap[0], 100.0)
    assert np.isclose(vwap[1], 100.666666, rtol=1e-5)
    assert np.isclose(vwap[2], 101.5)


def test_calculate_vwap_zero_volume() -> None:
    high = np.array([101.0, 102.0, 103.0])
    low = np.array([99.0, 100.0, 101.0])
    close = np.array([100.0, 101.0, 102.0])
    volume = np.array([0.0, 0.0, 0.0])

    vwap = calculate_vwap(high, low, close, volume, reset_daily=False)

    # All should be NaN due to zero volume
    assert np.all(np.isnan(vwap))


def test_calculate_vwap_with_nan_values() -> None:
    high = np.array([101.0, np.nan, 103.0])
    low = np.array([99.0, 100.0, 101.0])
    close = np.array([100.0, 101.0, 102.0])
    volume = np.array([100.0, 200.0, 300.0])

    vwap = calculate_vwap(high, low, close, volume, reset_daily=False)

    assert not np.isnan(vwap[0])
    assert np.isnan(vwap[1])  # NaN in typical price
    assert np.isnan(vwap[2])  # Affected by previous NaN


def test_calculate_vwap_daily_reset_requires_timestamps() -> None:
    high = np.array([101.0, 102.0])
    low = np.array([99.0, 100.0])
    close = np.array([100.0, 101.0])
    volume = np.array([100.0, 200.0])

    with pytest.raises(ValueError, match="Timestamps required for daily reset"):
        calculate_vwap(high, low, close, volume, reset_daily=True)


def test_calculate_vwap_daily_reset() -> None:
    # Two days of data
    high = np.array([101.0, 102.0, 103.0, 104.0])
    low = np.array([99.0, 100.0, 101.0, 102.0])
    close = np.array([100.0, 101.0, 102.0, 103.0])
    volume = np.array([100.0, 200.0, 300.0, 400.0])

    # Timestamps: first two are day 1, last two are day 2
    timestamps = np.array([0, 3600, 86400, 90000])  # Second day starts at 86400

    vwap = calculate_vwap(
        high,
        low,
        close,
        volume,
        reset_daily=True,
        timestamps=timestamps,
    )

    # Day 1 calculations
    assert np.isclose(vwap[0], 100.0)
    assert np.isclose(vwap[1], 100.666666, rtol=1e-5)

    # Day 2 should reset - VWAP[2] should only consider day 2 data
    # Typical price = 102, volume = 300
    assert np.isclose(vwap[2], 102.0)

    # VWAP[3] = (102*300 + 103*400) / 700
    assert np.isclose(vwap[3], 102.571428, rtol=1e-5)


def test_calculate_vwma_insufficient_data() -> None:
    prices = np.array([100.0, 101.0])
    volume = np.array([100.0, 200.0])

    result = calculate_vwma(prices, volume, period=5)
    assert np.all(np.isnan(result))


def test_calculate_vwma_mismatched_lengths() -> None:
    prices = np.array([100.0, 101.0, 102.0])
    volume = np.array([100.0, 200.0])  # Different length

    with pytest.raises(
        ValueError,
        match="Price and volume arrays must have the same length",
    ):
        calculate_vwma(prices, volume)


def test_calculate_vwma_negative_period() -> None:
    prices = np.array([100.0, 101.0, 102.0])
    volume = np.array([100.0, 200.0, 300.0])

    with pytest.raises(ValueError, match="Period must be positive"):
        calculate_vwma(prices, volume, period=-1)


def test_calculate_vwma_simple() -> None:
    prices = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
    volume = np.array([100.0, 200.0, 300.0, 400.0, 500.0])

    vwma = calculate_vwma(prices, volume, period=3)

    # First two values should be NaN
    assert np.isnan(vwma[0])
    assert np.isnan(vwma[1])

    # VWMA[2] = (100*100 + 101*200 + 102*300) / (100+200+300)
    # = (10000 + 20200 + 30600) / 600 = 60800 / 600 = 101.333
    assert np.isclose(vwma[2], 101.333333, rtol=1e-5)

    # VWMA[3] = (101*200 + 102*300 + 103*400) / (200+300+400)
    # = (20200 + 30600 + 41200) / 900 = 92000 / 900 = 102.222
    assert np.isclose(vwma[3], 102.222222, rtol=1e-5)


def test_calculate_vwma_zero_volume() -> None:
    prices = np.array([100.0, 101.0, 102.0])
    volume = np.array([0.0, 0.0, 0.0])

    vwma = calculate_vwma(prices, volume, period=2)

    # All should be NaN due to zero volume
    assert np.all(np.isnan(vwma))


def test_calculate_vwma_equal_volume() -> None:
    # When volume is constant, VWMA equals SMA
    prices = np.array([100.0, 102.0, 104.0, 106.0, 108.0])
    volume = np.full(5, 1000.0)  # Constant volume

    vwma = calculate_vwma(prices, volume, period=3)

    # Should equal simple moving average
    assert np.isnan(vwma[0])
    assert np.isnan(vwma[1])
    assert np.isclose(vwma[2], np.mean([100.0, 102.0, 104.0]))
    assert np.isclose(vwma[3], np.mean([102.0, 104.0, 106.0]))
    assert np.isclose(vwma[4], np.mean([104.0, 106.0, 108.0]))


def test_calculate_vwma_high_volume_weight() -> None:
    # High volume should have more weight
    prices = np.array([100.0, 110.0, 100.0])
    volume = np.array([100.0, 1000.0, 100.0])  # Middle has high volume

    vwma = calculate_vwma(prices, volume, period=3)

    # VWMA should be closer to 110 due to high volume
    # VWMA = (100*100 + 110*1000 + 100*100) / 1200 = 108.33
    assert np.isclose(vwma[2], 108.333333, rtol=1e-5)

    # Compare with simple average (103.33) - VWMA is pulled toward high volume price
    simple_avg = np.mean(prices)
    assert vwma[2] > simple_avg


def test_calculate_vwma_deterministic() -> None:
    prices = np.array([100, 102, 101, 103, 102, 104])
    volume = np.array([1000, 1200, 900, 1100, 1000, 1300])

    # Run multiple times to ensure deterministic results
    result1 = calculate_vwma(prices, volume, period=3)
    result2 = calculate_vwma(prices, volume, period=3)

    np.testing.assert_array_equal(result1, result2)


def test_calculate_vwma_with_nan_values() -> None:
    prices = np.array([100.0, 101.0, np.nan, 103.0, 104.0])
    volume = np.array([100.0, 200.0, 300.0, 400.0, 500.0])

    vwma = calculate_vwma(prices, volume, period=3)

    assert np.isnan(vwma[0])
    assert np.isnan(vwma[1])
    assert np.isnan(vwma[2])  # Contains NaN in window
    assert np.isnan(vwma[3])  # Contains NaN in window
    assert not np.isnan(vwma[4])  # No NaN in window [101, 103, 104]
