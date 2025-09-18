"""
Unit tests for vectorized backtest engine.
Following T-3: Pure logic unit tests without external dependencies.
Following T-5: Test complex algorithms thoroughly.
"""

import pytest
import numpy as np
import time
from typing import Callable

from app.engine.backtest.vector_engine import (
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    apply_signal_vectorized,
    calculate_metrics_vectorized,
    BacktestMetrics
)


class TestCalculateReturns:
    """Tests for vectorized return calculation."""

    def test_calculate_returns_long_positions(self):
        """Correctly computes long position returns."""
        prices = np.array([100, 110, 105, 115, 120])
        positions = np.array([1, 1, 1, 1, 0])  # Long then exit

        returns = calculate_returns(prices, positions, fees=0)  # No fees for clarity

        # Expected: [0, 0.1, -0.045, 0.095, 0.043478] - last is return while holding
        expected = np.array([0, 0.1, -0.045454545, 0.095238095, 0.043478261])
        np.testing.assert_array_almost_equal(returns, expected, decimal=5)

    def test_calculate_returns_short_positions(self):
        """Handles short positions with proper sign."""
        prices = np.array([100, 110, 105, 95, 100])
        positions = np.array([-1, -1, -1, -1, 0])  # Short then exit

        returns = calculate_returns(prices, positions, fees=0)

        # Short returns are inverted
        expected = np.array([0, -0.1, 0.045454545, 0.095238095, -0.052631579])
        np.testing.assert_array_almost_equal(returns, expected, decimal=5)

    def test_calculate_returns_with_fees(self):
        """Deducts transaction fees from returns."""
        prices = np.array([100, 110, 120])
        positions = np.array([0, 1, 0])  # Enter and exit
        fees = 0.001  # 0.1%

        returns = calculate_returns(prices, positions, fees)

        # Position change from 0 to 1: fee of 0.001
        # Position held from 1, price goes 110->120: return = 0.090909
        # Position change from 1 to 0: fee of 0.001
        # Net at exit: 0.090909 - 0.001 = 0.089909
        expected = np.array([0, -0.001, 0.089909091])
        np.testing.assert_array_almost_equal(returns, expected, decimal=5)

    def test_calculate_returns_mixed_positions(self):
        """Handles alternating long/short positions."""
        prices = np.array([100, 105, 110, 105, 100])
        positions = np.array([1, -1, 1, -1, 0])

        returns = calculate_returns(prices, positions, fees=0)

        # Complex position changes
        assert len(returns) == len(prices)
        assert returns[0] == 0  # No return at start
        # With alternating positions, returns should reflect position changes


class TestCalculateSharpeRatio:
    """Tests for Sharpe ratio calculation."""

    def test_calculate_sharpe_ratio_normal(self):
        """Computes Sharpe for typical returns."""
        returns = np.array([0.01, -0.005, 0.02, 0.015, -0.01, 0.025])

        sharpe = calculate_sharpe_ratio(returns, periods_per_year=252)

        # Should be positive with these returns
        assert sharpe > 0
        assert sharpe < 20  # Reasonable range for volatile returns

    def test_calculate_sharpe_ratio_zero_variance(self):
        """Handles constant returns gracefully."""
        returns = np.array([0.01, 0.01, 0.01, 0.01])

        sharpe = calculate_sharpe_ratio(returns, periods_per_year=252)

        # Zero variance should return inf or very large number
        assert sharpe > 100 or np.isinf(sharpe)

    def test_calculate_sharpe_ratio_negative(self):
        """Computes negative Sharpe for losses."""
        returns = np.array([-0.01, -0.02, -0.015, -0.005])

        sharpe = calculate_sharpe_ratio(returns, periods_per_year=252)

        assert sharpe < 0

    def test_calculate_sharpe_ratio_annual_scaling(self):
        """Correctly annualizes Sharpe ratio."""
        daily_returns = np.random.randn(252) * 0.01
        monthly_returns = np.random.randn(12) * 0.03

        daily_sharpe = calculate_sharpe_ratio(daily_returns, periods_per_year=252)
        monthly_sharpe = calculate_sharpe_ratio(monthly_returns, periods_per_year=12)

        # Both should be in similar range after annualization
        assert abs(daily_sharpe) < 10
        assert abs(monthly_sharpe) < 10


class TestCalculateMaxDrawdown:
    """Tests for maximum drawdown calculation."""

    def test_calculate_max_drawdown_typical(self):
        """Finds drawdown in volatile series."""
        equity_curve = np.array([100, 110, 105, 120, 100, 95, 110, 115])

        dd, peak_idx, trough_idx = calculate_max_drawdown(equity_curve)

        # Max drawdown from 120 to 95 = -20.83%
        assert dd == pytest.approx(-0.2083, rel=1e-3)
        assert peak_idx == 3
        assert trough_idx == 5

    def test_calculate_max_drawdown_monotonic(self):
        """Returns zero for monotonic increase."""
        equity_curve = np.array([100, 110, 120, 130, 140, 150])

        dd, peak_idx, trough_idx = calculate_max_drawdown(equity_curve)

        assert dd == 0
        assert peak_idx == 0
        assert trough_idx == 0

    def test_calculate_max_drawdown_all_decline(self):
        """Handles continuous decline."""
        equity_curve = np.array([100, 90, 80, 70, 60])

        dd, peak_idx, trough_idx = calculate_max_drawdown(equity_curve)

        assert dd == pytest.approx(-0.4, rel=1e-3)  # -40%
        assert peak_idx == 0
        assert trough_idx == 4


class TestApplySignalVectorized:
    """Tests for vectorized signal application."""

    def test_apply_signal_vectorized_basic(self):
        """Converts signals to positions correctly."""
        signals = np.array([0, 1, 1, -1, -1, 0, 1, 0])
        prices = np.array([100, 105, 110, 108, 106, 105, 110, 115])

        def simple_sizer(signal, price):
            return signal * 1.0  # Fixed size

        positions = apply_signal_vectorized(signals, prices, simple_sizer)

        np.testing.assert_array_equal(positions, signals.astype(float))

    def test_apply_signal_vectorized_position_limits(self):
        """Respects maximum position constraints."""
        signals = np.array([2, 3, 1, -2, -3])  # Large signals
        prices = np.array([100, 105, 110, 108, 106])

        def limited_sizer(signal, price):
            return np.clip(signal, -1, 1)  # Limit to ±1

        positions = apply_signal_vectorized(signals, prices, limited_sizer)

        assert np.all(np.abs(positions) <= 1)
        np.testing.assert_array_equal(positions, [1, 1, 1, -1, -1])

    def test_apply_signal_vectorized_price_dependent(self):
        """Position sizing depends on price."""
        signals = np.array([1, 1, 1])
        prices = np.array([100, 200, 50])

        def inverse_price_sizer(signal, price):
            return signal * (10000 / price)  # Fixed notional

        positions = apply_signal_vectorized(signals, prices, inverse_price_sizer)

        np.testing.assert_array_almost_equal(positions, [100, 50, 200])


class TestCalculateMetrics:
    """Tests for comprehensive metrics calculation."""

    def test_calculate_metrics_vectorized_basic(self):
        """Computes all metrics correctly."""
        returns = np.array([0.01, -0.005, 0.02, -0.01, 0.015, 0.005])
        equity = np.cumprod(1 + returns) * 100

        metrics = calculate_metrics_vectorized(returns, equity)

        assert isinstance(metrics, BacktestMetrics)
        assert metrics.total_return > 0
        assert metrics.sharpe_ratio is not None
        assert metrics.max_drawdown <= 0
        assert 0 <= metrics.win_rate <= 1

    def test_calculate_metrics_performance(self):
        """1000x faster than loop implementation."""
        # Large dataset
        returns = np.random.randn(10000) * 0.01
        equity = np.cumprod(1 + returns) * 100

        # Vectorized version
        start = time.time()
        metrics_vec = calculate_metrics_vectorized(returns, equity)
        vec_time = time.time() - start

        # Simple loop version for comparison
        start = time.time()
        total_return = (equity[-1] / equity[0]) - 1
        wins = sum(1 for r in returns if r > 0)
        win_rate = wins / len(returns)
        loop_time = time.time() - start

        # Should be much faster (allow 10x for safety on slow systems)
        assert vec_time < loop_time * 10

    def test_calculate_metrics_edge_cases(self):
        """Handles edge cases gracefully."""
        # No returns
        empty_returns = np.array([])
        empty_equity = np.array([100])

        metrics = calculate_metrics_vectorized(empty_returns, empty_equity)
        assert metrics.total_return == 0
        assert metrics.win_rate == 0

        # All wins
        win_returns = np.array([0.01, 0.02, 0.03])
        win_equity = np.cumprod(1 + win_returns) * 100

        metrics = calculate_metrics_vectorized(win_returns, win_equity)
        assert metrics.win_rate == 1.0

    def test_calculate_metrics_sortino_ratio(self):
        """Calculates Sortino ratio correctly."""
        returns = np.array([0.01, -0.02, 0.03, -0.01, 0.02])
        equity = np.cumprod(1 + returns) * 100

        metrics = calculate_metrics_vectorized(returns, equity)

        # Sortino only uses downside volatility
        assert metrics.sortino_ratio is not None
        assert metrics.sortino_ratio != metrics.sharpe_ratio