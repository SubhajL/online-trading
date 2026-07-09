from __future__ import annotations

from decimal import Decimal
import math

import pytest

from app.engine.backtest.metrics import MetricsCalculator, bars_per_year
from app.engine.backtest.types import BacktestMetrics
from app.engine.models import TimeFrame


def _closes(values: list[str]) -> list[Decimal]:
    return [Decimal(v) for v in values]


class TestApplyBenchmark:
    def test_benchmark_return_matches_first_to_last_close(self) -> None:
        metrics = MetricsCalculator(timeframe=TimeFrame.D1).apply_benchmark(
            BacktestMetrics(),
            _closes(["100", "104", "96", "130"]),
        )
        assert metrics.benchmark_return_pct == Decimal(30)

    def test_benchmark_max_drawdown_from_peak(self) -> None:
        # Peak 120 -> trough 90 is a 25% drawdown; the later recovery to 110
        # must not shrink it.
        metrics = MetricsCalculator(timeframe=TimeFrame.D1).apply_benchmark(
            BacktestMetrics(),
            _closes(["100", "120", "90", "110"]),
        )
        assert metrics.benchmark_max_drawdown_pct == Decimal(25)

    def test_benchmark_sharpe_uses_timeframe_annualization(self) -> None:
        # Bar returns +10%, -10%, +10%: Sharpe must scale by sqrt(bars/year)
        # of the DAILY crypto calendar (365), same as the strategy Sharpe.
        closes = _closes(["100", "110", "99", "108.9"])
        metrics = MetricsCalculator(timeframe=TimeFrame.D1).apply_benchmark(
            BacktestMetrics(),
            closes,
        )
        returns = [0.1, -0.1, 0.1]
        mean = sum(returns) / len(returns)
        std = math.sqrt(sum((r - mean) ** 2 for r in returns) / len(returns))
        expected = mean / std * math.sqrt(bars_per_year(TimeFrame.D1))
        assert metrics.benchmark_sharpe_ratio is not None
        assert float(metrics.benchmark_sharpe_ratio) == pytest.approx(expected)

    def test_excess_return_is_strategy_minus_benchmark(self) -> None:
        metrics = BacktestMetrics(total_pnl_pct=Decimal(12))
        MetricsCalculator(timeframe=TimeFrame.D1).apply_benchmark(
            metrics,
            _closes(["100", "130"]),
        )
        assert metrics.excess_return_pct == Decimal(-18)
