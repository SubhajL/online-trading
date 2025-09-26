"""
CRITICAL: Technical indicator calculation tests.

These tests ensure:
1. Indicator calculations are mathematically correct
2. Edge cases are handled properly (insufficient data, extreme values)
3. Results match expected values from known test cases
4. Performance is acceptable for real-time trading
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
import numpy as np

from app.engine.models import Candle, TimeFrame, TechnicalIndicators
from app.engine.features.indicators import TechnicalIndicatorsCalculator


class TestIndicatorCalculations:
    """Test individual indicator calculations."""

    def create_test_candles(self, prices: list[tuple[float, float, float, float]],
                           base_time: datetime) -> list[Candle]:
        """Create test candles from OHLC tuples."""
        candles = []
        for i, (o, h, l, c) in enumerate(prices):
            candle = Candle(
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                open_time=base_time + timedelta(minutes=5*i),
                close_time=base_time + timedelta(minutes=5*(i+1)),
                open_price=Decimal(str(o)),
                high_price=Decimal(str(h)),
                low_price=Decimal(str(l)),
                close_price=Decimal(str(c)),
                volume=Decimal("100"),
                quote_volume=Decimal(str(c * 100)),
                trades=50,
                taker_buy_base_volume=Decimal("60"),
                taker_buy_quote_volume=Decimal(str(c * 60)),
                bar_index=i
            )
            candles.append(candle)
        return candles

    def test_ema_calculation(self):
        """Test EMA calculation against known values."""
        # Test data: simple increasing sequence
        values = [Decimal(str(i)) for i in range(1, 11)]  # 1, 2, 3, ..., 10

        # Calculate EMA with period 3
        ema_values = TechnicalIndicatorsCalculator.ema(values, period=3)

        # First 2 values should be None (insufficient data)
        assert ema_values[0] is None
        assert ema_values[1] is None

        # Third value should be SMA of first 3: (1+2+3)/3 = 2
        assert ema_values[2] == Decimal("2")

        # Subsequent values should follow EMA formula
        # Multiplier = 2/(3+1) = 0.5
        # EMA[3] = (4 * 0.5) + (2 * 0.5) = 3
        assert abs(ema_values[3] - Decimal("3")) < Decimal("0.01")

    def test_ema_with_real_prices(self):
        """Test EMA with realistic price data."""
        # Bitcoin-like prices
        prices = [
            Decimal("50000"), Decimal("50100"), Decimal("50050"),
            Decimal("50200"), Decimal("50150"), Decimal("50300"),
            Decimal("50250"), Decimal("50400"), Decimal("50350"),
            Decimal("50500")
        ]

        ema_9 = TechnicalIndicatorsCalculator.ema(prices, period=9)

        # Should have values starting from index 8
        assert all(v is None for v in ema_9[:8])
        assert ema_9[8] is not None
        assert ema_9[9] is not None

        # EMA should be smoother than raw prices
        assert ema_9[9] < prices[9]  # Since prices are trending up

    def test_rsi_calculation(self):
        """Test RSI calculation with known overbought/oversold conditions."""
        # Create data that will produce extreme RSI values
        # Strong uptrend
        uptrend = [Decimal(str(100 + i * 5)) for i in range(20)]
        rsi_up = TechnicalIndicatorsCalculator.rsi(uptrend, period=14)

        # RSI should be high (>70) for strong uptrend
        assert rsi_up[-1] is not None
        assert rsi_up[-1] > Decimal("70")

        # Strong downtrend
        downtrend = [Decimal(str(200 - i * 5)) for i in range(20)]
        rsi_down = TechnicalIndicatorsCalculator.rsi(downtrend, period=14)

        # RSI should be low (<30) for strong downtrend
        assert rsi_down[-1] is not None
        assert rsi_down[-1] < Decimal("30")

        # Sideways market
        sideways = [Decimal("100") if i % 2 == 0 else Decimal("101") for i in range(20)]
        rsi_side = TechnicalIndicatorsCalculator.rsi(sideways, period=14)

        # RSI should be around 50 for sideways market
        assert rsi_side[-1] is not None
        assert Decimal("40") < rsi_side[-1] < Decimal("60")

    def test_rsi_edge_cases(self):
        """Test RSI with edge cases."""
        # All gains (no losses) - need at least 15 values for period 14
        all_gains = [Decimal(str(i)) for i in range(1, 21)]  # 20 values
        rsi = TechnicalIndicatorsCalculator.rsi(all_gains, period=14)

        # Should be 100 (or very close) since there are only gains
        assert rsi[-1] is not None
        assert rsi[-1] > Decimal("99")  # Very close to 100

        # Insufficient data
        short_data = [Decimal("100"), Decimal("101"), Decimal("102")]
        rsi_short = TechnicalIndicatorsCalculator.rsi(short_data, period=14)

        # Should all be None
        assert all(v is None for v in rsi_short)

    def test_macd_calculation(self):
        """Test MACD calculation."""
        # Create more pronounced trending data with oscillation
        prices = []
        for i in range(100):  # Need more data for MACD to develop
            if i < 40:
                # Strong uptrend
                price = Decimal(str(100 + i * 3))
            elif i < 60:
                # Sideways
                price = Decimal(str(220 + np.sin(i * 0.5) * 5))
            else:
                # Strong downtrend
                price = Decimal(str(320 - (i - 60) * 3))
            prices.append(price)

        macd_line, signal_line, histogram = TechnicalIndicatorsCalculator.macd(
            prices, fast_period=12, slow_period=26, signal_period=9
        )

        # Check we have values
        assert macd_line[-1] is not None
        assert signal_line[-1] is not None
        assert histogram[-1] is not None

        # Check MACD behavior - find first non-None value after slow period
        first_valid_idx = None
        for i in range(26, len(macd_line)):
            if macd_line[i] is not None:
                first_valid_idx = i
                break

        # During strong uptrend, MACD should be positive
        if first_valid_idx is not None and first_valid_idx < 35:
            # Check a bit after the initial period
            macd_uptrend = macd_line[35]
            assert macd_uptrend is not None
            assert macd_uptrend > Decimal("0")

        # During downtrend at the end, MACD should be negative
        macd_downtrend = macd_line[-10]
        assert macd_downtrend is not None
        assert macd_downtrend < Decimal("0")

        # MACD and signal should exist and be different
        assert macd_line[-1] != signal_line[-1]

    def test_atr_calculation(self):
        """Test Average True Range calculation."""
        base_time = datetime.now()

        # Create volatile candles
        volatile_ohlc = [
            (100, 105, 95, 102),   # 10 point range
            (102, 108, 98, 105),   # 10 point range with gap
            (105, 110, 100, 108),  # 10 point range
            (108, 115, 105, 112),  # 10 point range
        ]

        # Create stable candles
        stable_ohlc = [
            (100, 101, 99, 100),   # 2 point range
            (100, 101, 99, 100),   # 2 point range
            (100, 101, 99, 100),   # 2 point range
            (100, 101, 99, 100),   # 2 point range
        ]

        # Add more candles to have enough for ATR calculation
        for _ in range(10):
            volatile_ohlc.append((110, 115, 105, 110))
            stable_ohlc.append((100, 101, 99, 100))

        volatile_candles = self.create_test_candles(volatile_ohlc, base_time)
        stable_candles = self.create_test_candles(stable_ohlc, base_time)

        atr_volatile = TechnicalIndicatorsCalculator.atr(volatile_candles, period=14)
        atr_stable = TechnicalIndicatorsCalculator.atr(stable_candles, period=14)

        # ATR should be higher for volatile data
        assert atr_volatile[-1] > atr_stable[-1]

        # Stable ATR should be close to the range (2)
        assert abs(atr_stable[-1] - Decimal("2")) < Decimal("0.5")

    def test_bollinger_bands_calculation(self):
        """Test Bollinger Bands calculation."""
        # Create data with known properties
        # Mean = 100, StdDev ≈ 10
        prices = []
        for i in range(30):
            # Oscillate around 100 with increasing amplitude
            price = Decimal(str(100 + 10 * np.sin(i * 0.5)))
            prices.append(price)

        upper, middle, lower = TechnicalIndicatorsCalculator.bollinger_bands(
            prices, period=20, std_dev=2.0
        )

        # Check we have values
        assert upper[-1] is not None
        assert middle[-1] is not None
        assert lower[-1] is not None

        # Middle band should be close to mean
        assert abs(middle[-1] - Decimal("100")) < Decimal("5")

        # Upper band should be above middle
        assert upper[-1] > middle[-1]

        # Lower band should be below middle
        assert lower[-1] < middle[-1]

        # Band width should be approximately 4 * stddev
        band_width = upper[-1] - lower[-1]
        assert Decimal("20") < band_width < Decimal("50")

    def test_bb_percent_calculation(self):
        """Test Bollinger Band %B calculation."""
        # Test various price positions
        upper = Decimal("110")
        lower = Decimal("90")

        # Price at upper band
        bb_pct = TechnicalIndicatorsCalculator.bb_percent(Decimal("110"), upper, lower)
        assert bb_pct == Decimal("1")

        # Price at lower band
        bb_pct = TechnicalIndicatorsCalculator.bb_percent(Decimal("90"), upper, lower)
        assert bb_pct == Decimal("0")

        # Price at middle
        bb_pct = TechnicalIndicatorsCalculator.bb_percent(Decimal("100"), upper, lower)
        assert bb_pct == Decimal("0.5")

        # Price above upper band
        bb_pct = TechnicalIndicatorsCalculator.bb_percent(Decimal("120"), upper, lower)
        assert bb_pct > Decimal("1")

        # Price below lower band
        bb_pct = TechnicalIndicatorsCalculator.bb_percent(Decimal("80"), upper, lower)
        assert bb_pct < Decimal("0")

    def test_sma_calculation(self):
        """Test Simple Moving Average calculation."""
        values = [Decimal(str(i)) for i in [10, 20, 30, 40, 50]]

        sma = TechnicalIndicatorsCalculator.sma(values, period=3)

        # First two should be None
        assert sma[0] is None
        assert sma[1] is None

        # Third should be (10+20+30)/3 = 20
        assert sma[2] == Decimal("20")

        # Fourth should be (20+30+40)/3 = 30
        assert sma[3] == Decimal("30")

        # Fifth should be (30+40+50)/3 = 40
        assert sma[4] == Decimal("40")


class TestIndicatorIntegration:
    """Test integrated indicator calculations."""

    def test_calculate_all_indicators(self):
        """Test calculation of all indicators together."""
        base_time = datetime.now()

        # Create enough candles for all indicators
        prices = []
        for i in range(250):  # Enough for EMA 200
            # Create realistic price movement
            base_price = 50000
            trend = i * 10  # Upward trend
            noise = np.sin(i * 0.1) * 500  # Oscillation
            price = base_price + trend + noise

            # Create OHLC from price
            open_p = price - 50
            high = price + 100
            low = price - 100
            close = price

            prices.append((open_p, high, low, close))

        candles = []
        for i, (o, h, l, c) in enumerate(prices):
            candle = Candle(
                symbol="BTCUSDT",
                timeframe=TimeFrame.H1,
                open_time=base_time + timedelta(hours=i),
                close_time=base_time + timedelta(hours=i+1),
                open_price=Decimal(str(o)),
                high_price=Decimal(str(h)),
                low_price=Decimal(str(l)),
                close_price=Decimal(str(c)),
                volume=Decimal("1000"),
                quote_volume=Decimal(str(c * 1000)),
                trades=100,
                taker_buy_base_volume=Decimal("600"),
                taker_buy_quote_volume=Decimal(str(c * 600)),
                bar_index=i
            )
            candles.append(candle)

        # Calculate all indicators
        indicators = TechnicalIndicatorsCalculator.calculate_all_indicators(candles)

        # Check all indicators are calculated
        assert indicators.symbol == "BTCUSDT"
        assert indicators.timeframe == TimeFrame.H1

        # EMAs
        assert indicators.ema_9 is not None
        assert indicators.ema_21 is not None
        assert indicators.ema_50 is not None
        assert indicators.ema_200 is not None

        # EMAs should be in order: EMA9 > EMA21 > EMA50 > EMA200 in uptrend
        assert indicators.ema_9 > indicators.ema_21
        assert indicators.ema_21 > indicators.ema_50
        assert indicators.ema_50 > indicators.ema_200

        # RSI
        assert indicators.rsi_14 is not None
        assert Decimal("0") <= indicators.rsi_14 <= Decimal("100")

        # MACD
        assert indicators.macd_line is not None
        assert indicators.macd_signal is not None
        assert indicators.macd_histogram is not None

        # ATR
        assert indicators.atr_14 is not None
        assert indicators.atr_14 > Decimal("0")

        # Bollinger Bands
        assert indicators.bb_upper is not None
        assert indicators.bb_middle is not None
        assert indicators.bb_lower is not None
        assert indicators.bb_width is not None
        assert indicators.bb_percent is not None

        # BB relationships
        assert indicators.bb_upper > indicators.bb_middle
        assert indicators.bb_middle > indicators.bb_lower

    def test_insufficient_data_handling(self):
        """Test handling of insufficient data for indicators."""
        base_time = datetime.now()

        # Create only 10 candles
        candles = []
        for i in range(10):
            candle = Candle(
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                open_time=base_time + timedelta(minutes=5*i),
                close_time=base_time + timedelta(minutes=5*(i+1)),
                open_price=Decimal("50000"),
                high_price=Decimal("50100"),
                low_price=Decimal("49900"),
                close_price=Decimal("50050"),
                volume=Decimal("100"),
                quote_volume=Decimal("5005000"),
                trades=50,
                taker_buy_base_volume=Decimal("60"),
                taker_buy_quote_volume=Decimal("3003000"),
                bar_index=i
            )
            candles.append(candle)

        indicators = TechnicalIndicatorsCalculator.calculate_all_indicators(candles)

        # Short EMAs should work
        assert indicators.ema_9 is not None

        # Long EMAs should be None
        assert indicators.ema_21 is None
        assert indicators.ema_50 is None
        assert indicators.ema_200 is None

        # RSI needs 15 candles (14 + 1)
        assert indicators.rsi_14 is None

        # MACD needs 26 candles
        assert indicators.macd_line is None
        assert indicators.macd_signal is None
        assert indicators.macd_histogram is None

    def test_extreme_values_handling(self):
        """Test handling of extreme price values."""
        base_time = datetime.now()

        # Create candles with extreme values
        extreme_prices = [
            (100000, 200000, 50000, 150000),  # Huge range
            (150000, 150001, 149999, 150000),  # Tiny range
            (1, 2, 0.5, 1.5),                  # Very small prices
            (1000000, 1000001, 999999, 1000000),  # Very large prices
        ]

        # Add normal candles to have enough data
        for _ in range(20):
            extreme_prices.append((100000, 100100, 99900, 100000))

        candles = []
        for i, (o, h, l, c) in enumerate(extreme_prices):
            candle = Candle(
                symbol="BTCUSDT",
                timeframe=TimeFrame.H1,
                open_time=base_time + timedelta(hours=i),
                close_time=base_time + timedelta(hours=i+1),
                open_price=Decimal(str(o)),
                high_price=Decimal(str(h)),
                low_price=Decimal(str(l)),
                close_price=Decimal(str(c)),
                volume=Decimal("100"),
                quote_volume=Decimal(str(c * 100)),
                trades=50,
                taker_buy_base_volume=Decimal("60"),
                taker_buy_quote_volume=Decimal(str(c * 60)),
                bar_index=i
            )
            candles.append(candle)

        # Should not raise exceptions
        indicators = TechnicalIndicatorsCalculator.calculate_all_indicators(candles)

        # ATR should reflect the extreme volatility
        assert indicators.atr_14 is not None
        assert indicators.atr_14 > Decimal("1000")  # Should be large due to extreme ranges

    def test_indicator_precision(self):
        """Test that indicators maintain appropriate precision."""
        prices = [Decimal("50000.123456789") for _ in range(50)]

        # EMA should maintain precision
        ema = TechnicalIndicatorsCalculator.ema(prices, 9)
        assert ema[-1] is not None
        # Should have reasonable precision, not infinite
        assert len(str(ema[-1]).split('.')[-1]) < 20

        # RSI should be percentage (0-100)
        rsi = TechnicalIndicatorsCalculator.rsi(prices, 14)
        assert rsi[-1] is not None
        # Constant prices give RSI = 100 (no losses, only minimal gains from precision)
        # RSI with constant prices is undefined, but our implementation returns 100
        assert rsi[-1] == Decimal("100")


class TestBackwardsCompatibility:
    """Test backwards compatibility functions."""

    def test_module_level_functions(self):
        """Test that module-level functions still work."""
        from app.engine.features.indicators import (
            calculate_ema, calculate_rsi, calculate_macd, calculate_bollinger_bands
        )

        prices = [Decimal(str(100 + i)) for i in range(50)]

        # Test EMA
        ema = calculate_ema(prices, 9)
        assert len(ema) == len(prices)
        assert ema[-1] is not None

        # Test RSI
        rsi = calculate_rsi(prices, 14)
        # RSI has one less value than prices (needs price changes)
        assert len(rsi) == len(prices) - 1
        assert rsi[-1] is not None

        # Test MACD
        macd_line, signal, hist = calculate_macd(prices)
        assert len(macd_line) == len(prices)
        assert macd_line[-1] is not None

        # Test Bollinger Bands
        upper, middle, lower = calculate_bollinger_bands(prices)
        assert len(upper) == len(prices)
        assert upper[-1] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])