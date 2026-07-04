"""
Performance metrics calculation for backtesting.
Computes comprehensive trading performance statistics.
"""

from datetime import datetime
from decimal import Decimal
import math

import numpy as np

from ..models import TimeFrame
from .types import BacktestMetrics, BacktestTrade

_MINUTES_PER_YEAR = 365 * 24 * 60
_MINUTES_PER_BAR: dict[TimeFrame, int] = {
    TimeFrame.M1: 1,
    TimeFrame.M3: 3,
    TimeFrame.M5: 5,
    TimeFrame.M15: 15,
    TimeFrame.M30: 30,
    TimeFrame.H1: 60,
    TimeFrame.H2: 120,
    TimeFrame.H4: 240,
    TimeFrame.H6: 360,
    TimeFrame.H8: 480,
    TimeFrame.H12: 720,
    TimeFrame.D1: 1440,
    TimeFrame.D3: 4320,
    TimeFrame.W1: 10080,
    TimeFrame.MONTH1: 43200,
}
_LEGACY_TRADING_DAYS_PER_YEAR = 252


def bars_per_year(timeframe: TimeFrame) -> float:
    """
    Bars per year on the continuous crypto calendar (365 days, 24/7).
    """
    return _MINUTES_PER_YEAR / _MINUTES_PER_BAR[timeframe]


class MetricsCalculator:
    """
    Calculates comprehensive backtesting performance metrics.
    """

    def __init__(
        self,
        initial_balance: Decimal = Decimal(10000),
        timeframe: TimeFrame | None = None,
    ):
        """
        Initialize metrics calculator.

        Args:
            initial_balance: Starting account balance
            timeframe: Bar timeframe of the equity curve; annualization
                falls back to 252 daily periods when omitted
        """
        self.initial_balance = initial_balance
        if timeframe is not None:
            self._annualization_factor = math.sqrt(bars_per_year(timeframe))
        else:
            self._annualization_factor = math.sqrt(_LEGACY_TRADING_DAYS_PER_YEAR)

    def calculate_metrics(
        self,
        trades: list[BacktestTrade],
        equity_curve: list[tuple[datetime, Decimal]],
        drawdown_curve: list[tuple[datetime, Decimal]],
        runtime_ms: int = 0,
    ) -> BacktestMetrics:
        """
        Calculate comprehensive performance metrics.

        Args:
            trades: List of completed trades
            equity_curve: Time series of equity values
            drawdown_curve: Time series of drawdown values
            runtime_ms: Runtime in milliseconds

        Returns:
            Complete metrics object
        """
        metrics = BacktestMetrics()
        metrics.runtime_ms = runtime_ms

        if not trades or not equity_curve:
            return metrics

        # Basic trade statistics
        self._calculate_trade_stats(trades, metrics)

        # PnL and returns
        self._calculate_pnl_metrics(trades, equity_curve, metrics)

        # Risk metrics
        self._calculate_risk_metrics(equity_curve, drawdown_curve, metrics)

        # Advanced ratios
        self._calculate_advanced_ratios(equity_curve, trades, metrics)

        return metrics

    def _calculate_trade_stats(
        self,
        trades: list[BacktestTrade],
        metrics: BacktestMetrics,
    ) -> None:
        """
        Calculate basic trade statistics.

        Args:
            trades: List of trades
            metrics: Metrics object to update
        """
        if not trades:
            return

        metrics.total_trades = len(trades)

        # Categorize trades
        winning_trades = [t for t in trades if t.net_pnl and t.net_pnl > 0]
        losing_trades = [t for t in trades if t.net_pnl and t.net_pnl <= 0]

        metrics.winning_trades = len(winning_trades)
        metrics.losing_trades = len(losing_trades)

        # Hit rate
        if metrics.total_trades > 0:
            metrics.hit_rate_pct = (
                Decimal(metrics.winning_trades) / Decimal(metrics.total_trades)
            ) * Decimal(100)

        # R multiples
        if winning_trades:
            metrics.avg_win_r = sum(t.net_pnl_r for t in winning_trades if t.net_pnl_r) / Decimal(
                len(winning_trades)
            )
            metrics.largest_win_r = max(t.net_pnl_r for t in winning_trades if t.net_pnl_r)

        if losing_trades:
            metrics.avg_loss_r = sum(t.net_pnl_r for t in losing_trades if t.net_pnl_r) / Decimal(
                len(losing_trades)
            )
            metrics.largest_loss_r = min(t.net_pnl_r for t in losing_trades if t.net_pnl_r)

        # Overall average R
        r_values = [t.net_pnl_r for t in trades if t.net_pnl_r]
        if r_values:
            metrics.avg_r = sum(r_values) / Decimal(len(r_values))

        # Cost breakdown
        metrics.total_fees = sum(t.fees for t in trades)  # type: ignore[assignment]
        metrics.total_slippage = sum(t.slippage for t in trades)  # type: ignore[assignment]
        metrics.total_funding = sum(t.funding for t in trades)  # type: ignore[assignment]

    def _calculate_pnl_metrics(
        self,
        trades: list[BacktestTrade],
        equity_curve: list[tuple[datetime, Decimal]],
        metrics: BacktestMetrics,
    ) -> None:
        """
        Calculate PnL and return metrics.

        Args:
            trades: List of trades
            equity_curve: Equity time series
            metrics: Metrics object to update
        """
        if not equity_curve:
            return

        # Total PnL
        final_equity = equity_curve[-1][1]
        metrics.total_pnl = final_equity - self.initial_balance
        metrics.total_pnl_pct = (metrics.total_pnl / self.initial_balance) * Decimal(
            100,
        )

        # Profit factor
        gross_wins = sum(t.net_pnl for t in trades if t.net_pnl and t.net_pnl > 0)
        gross_losses = abs(
            sum(t.net_pnl for t in trades if t.net_pnl and t.net_pnl <= 0),
        )

        if gross_losses > 0:  # type: ignore[operator]
            metrics.profit_factor = gross_wins / gross_losses  # type: ignore[assignment, operator]

    def _calculate_risk_metrics(
        self,
        equity_curve: list[tuple[datetime, Decimal]],
        drawdown_curve: list[tuple[datetime, Decimal]],
        metrics: BacktestMetrics,
    ) -> None:
        """
        Calculate risk-related metrics.

        Args:
            equity_curve: Equity time series
            drawdown_curve: Drawdown time series
            metrics: Metrics object to update
        """
        if not drawdown_curve:
            return

        # Maximum drawdown
        max_dd = max(dd for _, dd in drawdown_curve)
        metrics.max_drawdown_pct = max_dd * Decimal(100)

        # Maximum drawdown duration
        metrics.max_drawdown_duration_hours = self._calculate_max_dd_duration(
            drawdown_curve,
        )

        # Exposure calculation (time in market)
        if equity_curve and len(equity_curve) > 1:
            total_time = equity_curve[-1][0] - equity_curve[0][0]
            # Simplified: assume always in market for now
            metrics.exposure_pct = Decimal(100)  # TODO: Calculate actual exposure

    def _calculate_advanced_ratios(
        self,
        equity_curve: list[tuple[datetime, Decimal]],
        trades: list[BacktestTrade],
        metrics: BacktestMetrics,
    ) -> None:
        """
        Calculate advanced performance ratios.

        Args:
            equity_curve: Equity time series
            trades: List of trades
            metrics: Metrics object to update
        """
        if len(equity_curve) < 2:
            return

        # Calculate returns
        returns = self._calculate_returns(equity_curve)
        if not returns:
            return

        # Convert to numpy for calculations
        returns_array = np.array([float(r) for r in returns])

        # Sharpe ratio (assuming 0% risk-free rate)
        if returns_array.std() > 0:
            metrics.sharpe_ratio = Decimal(
                str(returns_array.mean() / returns_array.std() * self._annualization_factor),
            )

        # Sortino ratio (downside deviation)
        downside_returns = returns_array[returns_array < 0]
        if len(downside_returns) > 0:
            downside_std = downside_returns.std()
            if downside_std > 0:
                metrics.sortino_ratio = Decimal(
                    str(returns_array.mean() / downside_std * self._annualization_factor),
                )

        # Calmar ratio (return / max drawdown)
        if metrics.max_drawdown_pct > 0:
            annual_return = metrics.total_pnl_pct  # Simplified
            metrics.calmar_ratio = annual_return / metrics.max_drawdown_pct

    def _calculate_returns(
        self,
        equity_curve: list[tuple[datetime, Decimal]],
    ) -> list[Decimal]:
        """
        Calculate period returns from equity curve.

        Args:
            equity_curve: Time series of equity values

        Returns:
            List of period returns
        """
        if len(equity_curve) < 2:
            return []

        returns = []
        for i in range(1, len(equity_curve)):
            prev_equity = equity_curve[i - 1][1]
            curr_equity = equity_curve[i][1]

            if prev_equity > 0:
                period_return = (curr_equity - prev_equity) / prev_equity
                returns.append(period_return)

        return returns

    def _calculate_max_dd_duration(
        self,
        drawdown_curve: list[tuple[datetime, Decimal]],
    ) -> int:
        """
        Calculate maximum drawdown duration in hours.

        Args:
            drawdown_curve: Time series of drawdown values

        Returns:
            Maximum drawdown duration in hours
        """
        if not drawdown_curve:
            return 0

        max_duration = 0
        current_duration = 0
        dd_start = None

        for timestamp, drawdown in drawdown_curve:
            if drawdown > Decimal("0.001"):  # In drawdown (>0.1%)
                if dd_start is None:
                    dd_start = timestamp
                current_duration = int((timestamp - dd_start).total_seconds() / 3600)
            # Out of drawdown
            elif dd_start is not None:
                max_duration = max(max_duration, current_duration)
                dd_start = None
                current_duration = 0

        # Check if still in drawdown at end
        if dd_start is not None:
            max_duration = max(max_duration, current_duration)

        return max_duration

    def calculate_trade_distribution(
        self,
        trades: list[BacktestTrade],
    ) -> dict:
        """
        Calculate trade distribution statistics.

        Args:
            trades: List of trades

        Returns:
            Dictionary with distribution statistics
        """
        if not trades:
            return {}

        pnls = [float(t.net_pnl) for t in trades if t.net_pnl]
        r_values = [float(t.net_pnl_r) for t in trades if t.net_pnl_r]

        if not pnls:
            return {}

        pnl_array = np.array(pnls)
        r_array = np.array(r_values) if r_values else np.array([])

        distribution = {
            # PnL statistics
            "pnl_mean": float(pnl_array.mean()),
            "pnl_std": float(pnl_array.std()),
            "pnl_skew": float(self._calculate_skewness(pnl_array)),
            "pnl_kurtosis": float(self._calculate_kurtosis(pnl_array)),
            "pnl_percentiles": {
                "5th": float(np.percentile(pnl_array, 5)),
                "25th": float(np.percentile(pnl_array, 25)),
                "50th": float(np.percentile(pnl_array, 50)),
                "75th": float(np.percentile(pnl_array, 75)),
                "95th": float(np.percentile(pnl_array, 95)),
            },
        }

        if len(r_array) > 0:
            distribution.update(
                {
                    # R multiple statistics
                    "r_mean": float(r_array.mean()),
                    "r_std": float(r_array.std()),
                    "r_percentiles": {
                        "5th": float(np.percentile(r_array, 5)),
                        "25th": float(np.percentile(r_array, 25)),
                        "50th": float(np.percentile(r_array, 50)),
                        "75th": float(np.percentile(r_array, 75)),
                        "95th": float(np.percentile(r_array, 95)),
                    },
                },
            )

        return distribution

    def _calculate_skewness(self, data: np.ndarray) -> float:
        """Calculate skewness of data."""
        if len(data) < 3:
            return 0.0

        mean = data.mean()
        std = data.std()
        if std == 0:
            return 0.0

        return ((data - mean) ** 3).mean() / (std**3)

    def _calculate_kurtosis(self, data: np.ndarray) -> float:
        """Calculate kurtosis of data."""
        if len(data) < 4:
            return 0.0

        mean = data.mean()
        std = data.std()
        if std == 0:
            return 0.0

        return ((data - mean) ** 4).mean() / (std**4) - 3  # Excess kurtosis

    def calculate_monthly_returns(
        self,
        equity_curve: list[tuple[datetime, Decimal]],
    ) -> list[tuple[str, Decimal]]:
        """
        Calculate monthly returns.

        Args:
            equity_curve: Time series of equity values

        Returns:
            List of (month_str, return) tuples
        """
        if len(equity_curve) < 2:
            return []

        monthly_returns = []
        current_month = None
        month_start_equity = None

        for timestamp, equity in equity_curve:
            month_key = timestamp.strftime("%Y-%m")

            if month_key != current_month:
                # New month
                if current_month is not None and month_start_equity is not None:
                    # Calculate previous month return
                    prev_equity = month_start_equity
                    month_return = (equity - prev_equity) / prev_equity * Decimal(100)
                    monthly_returns.append((current_month, month_return))

                current_month = month_key
                month_start_equity = equity

        return monthly_returns
