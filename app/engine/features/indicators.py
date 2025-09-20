"""
Technical Indicators Module

Implements various technical analysis indicators including:
- EMA (Exponential Moving Average)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- ATR (Average True Range)
- Bollinger Bands
"""

import numpy as np
import pandas as pd
from decimal import Decimal
from typing import List, Optional, Tuple
import logging

from ..models import Candle, TechnicalIndicators


logger = logging.getLogger(__name__)


class TechnicalIndicatorsCalculator:
    """
    Calculator for technical analysis indicators.

    Uses pandas and numpy for efficient calculation of indicators
    on OHLCV data series.
    """

    @staticmethod
    def ema(values: List[Decimal], period: int) -> List[Optional[Decimal]]:
        """
        Calculate Exponential Moving Average

        Args:
            values: List of price values
            period: EMA period

        Returns:
            List of EMA values (None for insufficient data points)
        """
        if len(values) < period:
            return [None] * len(values)

        # Convert to numpy array for calculation
        prices = np.array([float(v) for v in values])

        # Calculate EMA
        ema_values = []
        multiplier = 2 / (period + 1)

        # Initialize with SMA for the first value
        sma = np.mean(prices[:period])
        ema_values.extend([None] * (period - 1))
        ema_values.append(Decimal(str(sma)))

        # Calculate remaining EMA values
        for i in range(period, len(prices)):
            ema = (prices[i] * multiplier) + (float(ema_values[-1]) * (1 - multiplier))
            ema_values.append(Decimal(str(ema)))

        return ema_values

    @staticmethod
    def sma(values: List[Decimal], period: int) -> List[Optional[Decimal]]:
        """
        Calculate Simple Moving Average

        Args:
            values: List of price values
            period: SMA period

        Returns:
            List of SMA values
        """
        if len(values) < period:
            return [None] * len(values)

        sma_values = [None] * (period - 1)

        for i in range(period - 1, len(values)):
            window = values[i - period + 1 : i + 1]
            avg = sum(window) / len(window)
            sma_values.append(avg)

        return sma_values

    @staticmethod
    def rsi(values: List[Decimal], period: int = 14) -> List[Optional[Decimal]]:
        """
        Calculate Relative Strength Index

        Args:
            values: List of price values (typically close prices)
            period: RSI period (default 14)

        Returns:
            List of RSI values (0-100)
        """
        if len(values) < period + 1:
            return [None] * len(values)

        # Calculate price changes
        deltas = []
        for i in range(1, len(values)):
            deltas.append(values[i] - values[i - 1])

        # Separate gains and losses
        gains = [max(delta, Decimal("0")) for delta in deltas]
        losses = [abs(min(delta, Decimal("0"))) for delta in deltas]

        # Calculate initial averages
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        rsi_values = [None] * period

        # Calculate RSI values
        for i in range(period, len(gains)):
            # Smoothed averages (Wilder's method)
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

            if avg_loss == 0:
                rsi = Decimal("100")
            else:
                rs = avg_gain / avg_loss
                rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

            rsi_values.append(rsi)

        return rsi_values

    @staticmethod
    def macd(
        values: List[Decimal],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> Tuple[
        List[Optional[Decimal]], List[Optional[Decimal]], List[Optional[Decimal]]
    ]:
        """
        Calculate MACD (Moving Average Convergence Divergence)

        Args:
            values: List of price values (typically close prices)
            fast_period: Fast EMA period (default 12)
            slow_period: Slow EMA period (default 26)
            signal_period: Signal line EMA period (default 9)

        Returns:
            Tuple of (MACD line, Signal line, Histogram)
        """
        if len(values) < slow_period:
            none_list = [None] * len(values)
            return none_list, none_list, none_list

        # Calculate fast and slow EMAs
        fast_ema = TechnicalIndicatorsCalculator.ema(values, fast_period)
        slow_ema = TechnicalIndicatorsCalculator.ema(values, slow_period)

        # Calculate MACD line
        macd_line = []
        for i in range(len(values)):
            if fast_ema[i] is not None and slow_ema[i] is not None:
                macd_line.append(fast_ema[i] - slow_ema[i])
            else:
                macd_line.append(None)

        # Calculate signal line (EMA of MACD line)
        macd_values_for_signal = [v for v in macd_line if v is not None]
        if len(macd_values_for_signal) < signal_period:
            signal_line = [None] * len(values)
            histogram = [None] * len(values)
        else:
            signal_ema = TechnicalIndicatorsCalculator.ema(
                macd_values_for_signal, signal_period
            )

            # Align signal line with MACD line
            signal_line = [None] * len(values)
            signal_start_idx = len(values) - len(signal_ema)
            for i, sig in enumerate(signal_ema):
                if signal_start_idx + i < len(signal_line):
                    signal_line[signal_start_idx + i] = sig

            # Calculate histogram
            histogram = []
            for i in range(len(values)):
                if macd_line[i] is not None and signal_line[i] is not None:
                    histogram.append(macd_line[i] - signal_line[i])
                else:
                    histogram.append(None)

        return macd_line, signal_line, histogram

    @staticmethod
    def atr(candles: List[Candle], period: int = 14) -> List[Optional[Decimal]]:
        """
        Calculate Average True Range

        Args:
            candles: List of Candle objects
            period: ATR period (default 14)

        Returns:
            List of ATR values
        """
        if len(candles) < period:
            return [None] * len(candles)

        # Calculate True Range for each candle
        true_ranges = []

        for i, candle in enumerate(candles):
            if i == 0:
                # First candle: TR = High - Low
                tr = candle.high_price - candle.low_price
            else:
                prev_close = candles[i - 1].close_price
                tr1 = candle.high_price - candle.low_price
                tr2 = abs(candle.high_price - prev_close)
                tr3 = abs(candle.low_price - prev_close)
                tr = max(tr1, tr2, tr3)

            true_ranges.append(tr)

        # Calculate ATR using smoothed moving average
        atr_values = [None] * (period - 1)

        # Initial ATR is simple average of first 'period' TRs
        initial_atr = sum(true_ranges[:period]) / period
        atr_values.append(initial_atr)

        # Subsequent ATRs use Wilder's smoothing method
        for i in range(period, len(true_ranges)):
            atr = (atr_values[-1] * (period - 1) + true_ranges[i]) / period
            atr_values.append(atr)

        return atr_values

    @staticmethod
    def bollinger_bands(
        values: List[Decimal], period: int = 20, std_dev: float = 2.0
    ) -> Tuple[
        List[Optional[Decimal]], List[Optional[Decimal]], List[Optional[Decimal]]
    ]:
        """
        Calculate Bollinger Bands

        Args:
            values: List of price values (typically close prices)
            period: Period for moving average and standard deviation (default 20)
            std_dev: Number of standard deviations (default 2.0)

        Returns:
            Tuple of (Upper band, Middle band/SMA, Lower band)
        """
        if len(values) < period:
            none_list = [None] * len(values)
            return none_list, none_list, none_list

        # Calculate middle band (SMA)
        middle_band = TechnicalIndicatorsCalculator.sma(values, period)

        upper_band = []
        lower_band = []

        for i in range(len(values)):
            if middle_band[i] is None:
                upper_band.append(None)
                lower_band.append(None)
            else:
                # Calculate standard deviation for the period
                start_idx = i - period + 1
                window = values[start_idx : i + 1]

                # Convert to float for std calculation
                window_float = [float(v) for v in window]
                mean_val = sum(window_float) / len(window_float)
                variance = sum((x - mean_val) ** 2 for x in window_float) / len(
                    window_float
                )
                std = variance**0.5

                upper_band.append(middle_band[i] + Decimal(str(std_dev * std)))
                lower_band.append(middle_band[i] - Decimal(str(std_dev * std)))

        return upper_band, middle_band, lower_band

    @staticmethod
    def bb_percent(
        price: Decimal, upper_band: Decimal, lower_band: Decimal
    ) -> Optional[Decimal]:
        """
        Calculate Bollinger Band Percent (%B)

        Args:
            price: Current price
            upper_band: Upper Bollinger Band value
            lower_band: Lower Bollinger Band value

        Returns:
            %B value (0-1, can exceed this range)
        """
        if upper_band == lower_band:
            return None

        return (price - lower_band) / (upper_band - lower_band)

    @staticmethod
    def bb_width(
        upper_band: Decimal, lower_band: Decimal, middle_band: Decimal
    ) -> Decimal:
        """
        Calculate Bollinger Band Width

        Args:
            upper_band: Upper Bollinger Band value
            lower_band: Lower Bollinger Band value
            middle_band: Middle Bollinger Band value (SMA)

        Returns:
            Band width as percentage of middle band
        """
        return (upper_band - lower_band) / middle_band

    @classmethod
    def calculate_all_indicators(
        cls,
        candles: List[Candle],
        ema_periods: List[int] = [9, 21, 50, 200],
        rsi_period: int = 14,
        macd_params: Tuple[int, int, int] = (12, 26, 9),
        atr_period: int = 14,
        bb_period: int = 20,
        bb_std_dev: float = 2.0,
    ) -> TechnicalIndicators:
        """
        Calculate all technical indicators for the latest candle

        Args:
            candles: List of Candle objects (should be in chronological order)
            ema_periods: List of EMA periods to calculate
            rsi_period: RSI period
            macd_params: MACD parameters (fast, slow, signal)
            atr_period: ATR period
            bb_period: Bollinger Bands period
            bb_std_dev: Bollinger Bands standard deviation multiplier

        Returns:
            TechnicalIndicators object with calculated values
        """
        if not candles:
            raise ValueError("No candles provided")

        latest_candle = candles[-1]
        close_prices = [candle.close_price for candle in candles]

        # Initialize result object
        indicators = TechnicalIndicators(
            symbol=latest_candle.symbol,
            timeframe=latest_candle.timeframe,
            timestamp=latest_candle.close_time,
        )

        try:
            # Calculate EMAs
            if 9 in ema_periods:
                ema_9_values = cls.ema(close_prices, 9)
                indicators.ema_9 = (
                    ema_9_values[-1] if ema_9_values[-1] is not None else None
                )

            if 21 in ema_periods:
                ema_21_values = cls.ema(close_prices, 21)
                indicators.ema_21 = (
                    ema_21_values[-1] if ema_21_values[-1] is not None else None
                )

            if 50 in ema_periods:
                ema_50_values = cls.ema(close_prices, 50)
                indicators.ema_50 = (
                    ema_50_values[-1] if ema_50_values[-1] is not None else None
                )

            if 200 in ema_periods:
                ema_200_values = cls.ema(close_prices, 200)
                indicators.ema_200 = (
                    ema_200_values[-1] if ema_200_values[-1] is not None else None
                )

            # Calculate RSI
            rsi_values = cls.rsi(close_prices, rsi_period)
            indicators.rsi_14 = rsi_values[-1] if rsi_values[-1] is not None else None

            # Calculate MACD
            macd_line, signal_line, histogram = cls.macd(
                close_prices, macd_params[0], macd_params[1], macd_params[2]
            )
            indicators.macd_line = macd_line[-1] if macd_line[-1] is not None else None
            indicators.macd_signal = (
                signal_line[-1] if signal_line[-1] is not None else None
            )
            indicators.macd_histogram = (
                histogram[-1] if histogram[-1] is not None else None
            )

            # Calculate ATR
            atr_values = cls.atr(candles, atr_period)
            indicators.atr_14 = atr_values[-1] if atr_values[-1] is not None else None

            # Calculate Bollinger Bands
            upper_band, middle_band, lower_band = cls.bollinger_bands(
                close_prices, bb_period, bb_std_dev
            )
            indicators.bb_upper = upper_band[-1] if upper_band[-1] is not None else None
            indicators.bb_middle = (
                middle_band[-1] if middle_band[-1] is not None else None
            )
            indicators.bb_lower = lower_band[-1] if lower_band[-1] is not None else None

            # Calculate BB width and percent
            if all(
                v is not None
                for v in [
                    indicators.bb_upper,
                    indicators.bb_middle,
                    indicators.bb_lower,
                ]
            ):
                indicators.bb_width = cls.bb_width(
                    indicators.bb_upper, indicators.bb_lower, indicators.bb_middle
                )
                indicators.bb_percent = cls.bb_percent(
                    latest_candle.close_price, indicators.bb_upper, indicators.bb_lower
                )

        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            # Return indicators object with None values

        return indicators
