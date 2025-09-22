"""
Golden Vector Tests for Technical Indicators

Tests indicator calculations against pre-computed expected values to ensure
consistency and correctness across changes.
"""

import os
import json
import pytest
import pandas as pd
import numpy as np
from decimal import Decimal

from app.engine.shared.math import (
    calculate_ema,
    calculate_rsi,
    calculate_macd,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_vwap,
    calculate_vwma,
)


class TestIndicatorsGolden:
    """Test technical indicators against golden vectors"""

    @pytest.fixture
    def fixture_data(self):
        """Load fixture CSV data"""
        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixture_btcusdt_15m.csv"
        )
        df = pd.read_csv(fixture_path, parse_dates=["timestamp"])
        return df

    @pytest.fixture
    def golden_values(self):
        """Load pre-computed golden values"""
        golden_path = os.path.join(
            os.path.dirname(__file__), "golden_vectors.json"
        )

        if os.path.exists(golden_path):
            with open(golden_path, "r") as f:
                return json.load(f)
        else:
            # Return empty dict if golden vectors not yet generated
            return {}

    def test_ema_golden(self, fixture_data, golden_values):
        """Test EMA calculation against golden values"""
        close_prices = fixture_data["close"].values

        # Test different periods
        for period in [20, 50]:
            ema_result = calculate_ema(close_prices, period)

            if f"ema_{period}" in golden_values:
                expected = np.array(golden_values[f"ema_{period}"])

                # Compare non-NaN values
                valid_mask = ~np.isnan(ema_result) & ~np.isnan(expected)
                np.testing.assert_allclose(
                    ema_result[valid_mask],
                    expected[valid_mask],
                    rtol=1e-8,
                    err_msg=f"EMA({period}) mismatch"
                )

    def test_rsi_golden(self, fixture_data, golden_values):
        """Test RSI calculation against golden values"""
        close_prices = fixture_data["close"].values

        rsi_result = calculate_rsi(close_prices, period=14)

        if "rsi_14" in golden_values:
            expected = np.array(golden_values["rsi_14"])

            # Compare non-NaN values
            valid_mask = ~np.isnan(rsi_result) & ~np.isnan(expected)
            np.testing.assert_allclose(
                rsi_result[valid_mask],
                expected[valid_mask],
                rtol=1e-8,
                err_msg="RSI(14) mismatch"
            )

    def test_macd_golden(self, fixture_data, golden_values):
        """Test MACD calculation against golden values"""
        close_prices = fixture_data["close"].values

        macd_line, signal_line, histogram = calculate_macd(close_prices, 12, 26, 9)

        if "macd_line" in golden_values:
            expected_line = np.array(golden_values["macd_line"])
            expected_signal = np.array(golden_values["macd_signal"])
            expected_hist = np.array(golden_values["macd_histogram"])

            # Compare non-NaN values
            for result, expected, name in [
                (macd_line, expected_line, "MACD line"),
                (signal_line, expected_signal, "MACD signal"),
                (histogram, expected_hist, "MACD histogram")
            ]:
                valid_mask = ~np.isnan(result) & ~np.isnan(expected)
                np.testing.assert_allclose(
                    result[valid_mask],
                    expected[valid_mask],
                    rtol=1e-8,
                    err_msg=f"{name} mismatch"
                )

    def test_atr_golden(self, fixture_data, golden_values):
        """Test ATR calculation against golden values"""
        high_prices = fixture_data["high"].values
        low_prices = fixture_data["low"].values
        close_prices = fixture_data["close"].values

        atr_result = calculate_atr(high_prices, low_prices, close_prices, period=14)

        if "atr_14" in golden_values:
            expected = np.array(golden_values["atr_14"])

            # Compare non-NaN values
            valid_mask = ~np.isnan(atr_result) & ~np.isnan(expected)
            np.testing.assert_allclose(
                atr_result[valid_mask],
                expected[valid_mask],
                rtol=1e-8,
                err_msg="ATR(14) mismatch"
            )

    def test_bollinger_bands_golden(self, fixture_data, golden_values):
        """Test Bollinger Bands calculation against golden values"""
        close_prices = fixture_data["close"].values

        upper, middle, lower = calculate_bollinger_bands(close_prices, period=20, std_dev=2.0)

        if "bb_upper" in golden_values:
            expected_upper = np.array(golden_values["bb_upper"])
            expected_middle = np.array(golden_values["bb_middle"])
            expected_lower = np.array(golden_values["bb_lower"])

            # Compare non-NaN values
            for result, expected, name in [
                (upper, expected_upper, "BB upper"),
                (middle, expected_middle, "BB middle"),
                (lower, expected_lower, "BB lower")
            ]:
                valid_mask = ~np.isnan(result) & ~np.isnan(expected)
                np.testing.assert_allclose(
                    result[valid_mask],
                    expected[valid_mask],
                    rtol=1e-8,
                    err_msg=f"{name} mismatch"
                )

    def test_vwap_golden(self, fixture_data, golden_values):
        """Test VWAP calculation against golden values"""
        high_prices = fixture_data["high"].values
        low_prices = fixture_data["low"].values
        close_prices = fixture_data["close"].values
        volumes = fixture_data["volume"].values

        vwap_result = calculate_vwap(
            high_prices, low_prices, close_prices, volumes, reset_daily=False
        )

        if "vwap" in golden_values:
            expected = np.array(golden_values["vwap"])

            # Compare non-NaN values
            valid_mask = ~np.isnan(vwap_result) & ~np.isnan(expected)
            np.testing.assert_allclose(
                vwap_result[valid_mask],
                expected[valid_mask],
                rtol=1e-8,
                err_msg="VWAP mismatch"
            )

    def test_vwma_golden(self, fixture_data, golden_values):
        """Test VWMA calculation against golden values"""
        close_prices = fixture_data["close"].values
        volumes = fixture_data["volume"].values

        vwma_result = calculate_vwma(close_prices, volumes, period=20)

        if "vwma_20" in golden_values:
            expected = np.array(golden_values["vwma_20"])

            # Compare non-NaN values
            valid_mask = ~np.isnan(vwma_result) & ~np.isnan(expected)
            np.testing.assert_allclose(
                vwma_result[valid_mask],
                expected[valid_mask],
                rtol=1e-8,
                err_msg="VWMA(20) mismatch"
            )

    def test_all_indicators_deterministic(self, fixture_data):
        """Test that all indicators produce deterministic results"""
        close_prices = fixture_data["close"].values
        high_prices = fixture_data["high"].values
        low_prices = fixture_data["low"].values
        volumes = fixture_data["volume"].values

        # Run each indicator twice and ensure results are identical
        indicators = [
            ("EMA", lambda: calculate_ema(close_prices, 20)),
            ("RSI", lambda: calculate_rsi(close_prices, 14)),
            ("MACD", lambda: calculate_macd(close_prices, 12, 26, 9)),
            ("ATR", lambda: calculate_atr(high_prices, low_prices, close_prices, 14)),
            ("BB", lambda: calculate_bollinger_bands(close_prices, 20, 2.0)),
            ("VWAP", lambda: calculate_vwap(high_prices, low_prices, close_prices, volumes, False)),
            ("VWMA", lambda: calculate_vwma(close_prices, volumes, 20)),
        ]

        for name, calc_func in indicators:
            result1 = calc_func()
            result2 = calc_func()

            # Handle both single arrays and tuples of arrays
            if isinstance(result1, tuple):
                for arr1, arr2 in zip(result1, result2):
                    np.testing.assert_array_equal(
                        arr1, arr2,
                        err_msg=f"{name} not deterministic"
                    )
            else:
                np.testing.assert_array_equal(
                    result1, result2,
                    err_msg=f"{name} not deterministic"
                )

    def test_indicator_output_shapes(self, fixture_data):
        """Test that all indicators return arrays of correct shape"""
        n_candles = len(fixture_data)
        close_prices = fixture_data["close"].values
        high_prices = fixture_data["high"].values
        low_prices = fixture_data["low"].values
        volumes = fixture_data["volume"].values

        # Single array outputs
        assert len(calculate_ema(close_prices, 20)) == n_candles
        assert len(calculate_rsi(close_prices, 14)) == n_candles
        assert len(calculate_atr(high_prices, low_prices, close_prices, 14)) == n_candles
        assert len(calculate_vwap(high_prices, low_prices, close_prices, volumes, False)) == n_candles
        assert len(calculate_vwma(close_prices, volumes, 20)) == n_candles

        # Tuple outputs
        macd_line, signal_line, histogram = calculate_macd(close_prices, 12, 26, 9)
        assert len(macd_line) == n_candles
        assert len(signal_line) == n_candles
        assert len(histogram) == n_candles

        upper, middle, lower = calculate_bollinger_bands(close_prices, 20, 2.0)
        assert len(upper) == n_candles
        assert len(middle) == n_candles
        assert len(lower) == n_candles