from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import math

import pytest

from app.engine.backtest.metrics import MetricsCalculator, bars_per_year
from app.engine.backtest.types import BacktestTrade
from app.engine.models import TimeFrame

CURVE_START = datetime(2024, 1, 2, tzinfo=UTC)
INITIAL_BALANCE = Decimal(10000)


def _equity_curve(
    balances: list[str],
    bar_duration: timedelta,
) -> list[tuple[datetime, Decimal]]:
    return [
        (CURVE_START + i * bar_duration, Decimal(balance)) for i, balance in enumerate(balances)
    ]


def _trades() -> list[BacktestTrade]:
    return [
        BacktestTrade(net_pnl=Decimal(100), net_pnl_r=Decimal(1)),
        BacktestTrade(net_pnl=Decimal(-50), net_pnl_r=Decimal("-0.5")),
    ]


def _flat_drawdown(curve: list[tuple[datetime, Decimal]]) -> list[tuple[datetime, Decimal]]:
    return [(timestamp, Decimal(0)) for timestamp, _ in curve]


def test_bars_per_year_matches_continuous_crypto_calendar() -> None:
    assert (
        bars_per_year(TimeFrame.M15),
        bars_per_year(TimeFrame.H1),
        bars_per_year(TimeFrame.D1),
    ) == (35040, 8760, 365)


def test_bars_per_year_covers_every_timeframe() -> None:
    assert all(bars_per_year(timeframe) > 0 for timeframe in TimeFrame)


@pytest.mark.parametrize(
    ("timeframe", "bar_duration"),
    [
        (TimeFrame.M15, timedelta(minutes=15)),
        (TimeFrame.H1, timedelta(hours=1)),
    ],
)
def test_sharpe_annualizes_by_timeframe(timeframe: TimeFrame, bar_duration: timedelta) -> None:
    curve = _equity_curve(["10000", "10100", "10302"], bar_duration)
    calculator = MetricsCalculator(INITIAL_BALANCE, timeframe=timeframe)

    metrics = calculator.calculate_metrics(_trades(), curve, _flat_drawdown(curve))

    # returns are +1%, +2% → mean 0.015 / population std 0.005 = 3.0
    per_bar_sharpe = 3.0
    assert float(metrics.sharpe_ratio) == pytest.approx(
        per_bar_sharpe * math.sqrt(bars_per_year(timeframe)),
        rel=1e-9,
    )


def test_sharpe_defaults_to_daily_trading_year_without_timeframe() -> None:
    curve = _equity_curve(["10000", "10100", "10302"], timedelta(minutes=15))
    calculator = MetricsCalculator(INITIAL_BALANCE)

    metrics = calculator.calculate_metrics(_trades(), curve, _flat_drawdown(curve))

    # returns are +1%, +2% → mean 0.015 / population std 0.005 = 3.0
    per_bar_sharpe = 3.0
    assert float(metrics.sharpe_ratio) == pytest.approx(
        per_bar_sharpe * math.sqrt(252),
        rel=1e-9,
    )


def test_sortino_uses_same_timeframe_annualization() -> None:
    curve = _equity_curve(["10000", "10200", "10098", "9896.04"], timedelta(hours=1))
    calculator = MetricsCalculator(INITIAL_BALANCE, timeframe=TimeFrame.H1)

    metrics = calculator.calculate_metrics(_trades(), curve, _flat_drawdown(curve))

    returns = [0.02, -0.01, -0.02]
    mean_return = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    downside_mean = sum(downside) / len(downside)
    downside_std = math.sqrt(
        sum((r - downside_mean) ** 2 for r in downside) / len(downside),
    )
    assert float(metrics.sortino_ratio) == pytest.approx(
        mean_return / downside_std * math.sqrt(bars_per_year(TimeFrame.H1)),
        rel=1e-6,
    )
