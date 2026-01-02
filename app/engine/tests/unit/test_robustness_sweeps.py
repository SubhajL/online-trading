"""
Unit tests for robustness sweeps module.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.models import Candle, TimeFrame
from app.engine.telegram_validator.fill_model import BracketSpec, CostConfig
from app.engine.telegram_validator.robustness_sweeps import (
    AGGRESSIVE_SWEEP,
    CONSERVATIVE_SWEEP,
    MODERATE_SWEEP,
    SweepResult,
    aggregate_sweep_metrics,
    build_sweep_grid,
    run_robustness_sweep,
)


def make_candle(
    *,
    open_time: datetime,
    open_p: Decimal,
    high_p: Decimal,
    low_p: Decimal,
    close_p: Decimal,
) -> Candle:
    """Helper to create test candles."""
    return Candle(
        symbol="BTCUSDT",
        timeframe=TimeFrame.H1,
        open_time=open_time,
        close_time=open_time + timedelta(hours=1),
        open_price=open_p,
        high_price=high_p,
        low_price=low_p,
        close_price=close_p,
        volume=Decimal("100"),
        quote_volume=Decimal("10000"),
        trades=50,
        taker_buy_base_volume=Decimal("50"),
        taker_buy_quote_volume=Decimal("5000"),
    )


class TestBuildSweepGrid:
    """Tests for build_sweep_grid function."""

    def test_single_value_ranges_produce_single_config(self) -> None:
        """Single values in each range produce one config."""
        base = CostConfig(
            fee_bps=Decimal("10"),
            slippage_bps=Decimal("5"),
            funding_rate_8h=Decimal("1"),
        )
        configs = build_sweep_grid(base)

        assert len(configs) == 1
        assert configs[0] == base

    def test_multiple_fee_values_produce_multiple_configs(self) -> None:
        """Multiple fee values expand the grid."""
        base = CostConfig()
        configs = build_sweep_grid(
            base,
            fee_range=(Decimal("5"), Decimal("10"), Decimal("15")),
        )

        assert len(configs) == 3
        assert configs[0].fee_bps == Decimal("5")
        assert configs[1].fee_bps == Decimal("10")
        assert configs[2].fee_bps == Decimal("15")

    def test_cartesian_product_of_all_ranges(self) -> None:
        """Grid is Cartesian product of all ranges."""
        base = CostConfig()
        configs = build_sweep_grid(
            base,
            fee_range=(Decimal("5"), Decimal("10")),
            slippage_range=(Decimal("0"), Decimal("10")),
            funding_range=(Decimal("0"), Decimal("5")),
        )

        # 2 * 2 * 2 = 8 configurations
        assert len(configs) == 8

    def test_preset_conservative_sweep_size(self) -> None:
        """Conservative preset produces expected grid size."""
        # 3 * 3 * 3 = 27
        assert len(CONSERVATIVE_SWEEP) == 27

    def test_preset_moderate_sweep_size(self) -> None:
        """Moderate preset produces expected grid size."""
        assert len(MODERATE_SWEEP) == 27

    def test_preset_aggressive_sweep_size(self) -> None:
        """Aggressive preset produces expected grid size."""
        assert len(AGGRESSIVE_SWEEP) == 27


class TestAggregateSweepMetrics:
    """Tests for aggregate_sweep_metrics function."""

    def test_empty_results_return_zeros(self) -> None:
        """Empty results return zeros."""
        pass_rate, p10, p50, p90 = aggregate_sweep_metrics([])

        assert pass_rate == 0.0
        assert p10 == Decimal("0")
        assert p50 == Decimal("0")
        assert p90 == Decimal("0")

    def test_all_positive_pnl_gives_100_percent_pass_rate(self) -> None:
        """All positive PnL means 100% pass rate."""
        from app.engine.telegram_validator.fill_model import FillSimulationResult

        results = [
            FillSimulationResult(
                outcome="TP_FULL",
                fills=(),
                gross_pnl=Decimal("10"),
                fees=Decimal("1"),
                slippage_cost=Decimal("0"),
                funding_cost=Decimal("0"),
                net_pnl=Decimal("9"),
                exit_timestamp=None,
                candles_held=1,
            )
            for _ in range(10)
        ]

        pass_rate, p10, p50, p90 = aggregate_sweep_metrics(results)

        assert pass_rate == 1.0

    def test_mixed_pnl_gives_partial_pass_rate(self) -> None:
        """Mixed positive/negative PnL gives partial pass rate."""
        from app.engine.telegram_validator.fill_model import FillSimulationResult

        results = [
            FillSimulationResult(
                outcome="TP_FULL",
                fills=(),
                gross_pnl=Decimal("10"),
                fees=Decimal("1"),
                slippage_cost=Decimal("0"),
                funding_cost=Decimal("0"),
                net_pnl=Decimal("5") if i % 2 == 0 else Decimal("-5"),
                exit_timestamp=None,
                candles_held=1,
            )
            for i in range(10)
        ]

        pass_rate, p10, p50, p90 = aggregate_sweep_metrics(results)

        assert pass_rate == 0.5

    def test_quantiles_are_ordered(self) -> None:
        """Quantiles should be in ascending order p10 <= p50 <= p90."""
        from app.engine.telegram_validator.fill_model import FillSimulationResult

        # Create varied PnL results
        results = [
            FillSimulationResult(
                outcome="TP_FULL",
                fills=(),
                gross_pnl=Decimal("10"),
                fees=Decimal("1"),
                slippage_cost=Decimal("0"),
                funding_cost=Decimal("0"),
                net_pnl=Decimal(str(i - 5)),  # -5 to +4
                exit_timestamp=None,
                candles_held=1,
            )
            for i in range(10)
        ]

        pass_rate, p10, p50, p90 = aggregate_sweep_metrics(results)

        assert p10 <= p50 <= p90


class TestRunRobustnessSweep:
    """Tests for run_robustness_sweep function."""

    def test_returns_sweep_result_with_baseline(self) -> None:
        """Sweep returns result with baseline from first config."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("110"),),
            tp_sizes=(Decimal("1.0"),),
        )
        candles = [
            make_candle(
                open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                open_p=Decimal("100"),
                high_p=Decimal("112"),
                low_p=Decimal("99"),
                close_p=Decimal("111"),
            ),
        ]
        configs = [
            CostConfig(fee_bps=Decimal("10")),
            CostConfig(fee_bps=Decimal("20")),
        ]

        result = run_robustness_sweep(candles, bracket, configs)

        assert isinstance(result, SweepResult)
        assert result.baseline is not None
        assert len(result.sweep_grid) == 2

    def test_higher_costs_reduce_pass_rate(self) -> None:
        """Higher costs should reduce or maintain pass rate."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("105"),),
            tp_sizes=(Decimal("1.0"),),
        )
        candles = [
            make_candle(
                open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                open_p=Decimal("100"),
                high_p=Decimal("106"),
                low_p=Decimal("99"),
                close_p=Decimal("105"),
            ),
        ]

        low_cost_configs = [
            CostConfig(fee_bps=Decimal("0"), slippage_bps=Decimal("0")),
        ]
        high_cost_configs = [
            CostConfig(fee_bps=Decimal("500"), slippage_bps=Decimal("500")),
        ]

        low_result = run_robustness_sweep(candles, bracket, low_cost_configs)
        high_result = run_robustness_sweep(candles, bracket, high_cost_configs)

        assert low_result.pass_rate >= high_result.pass_rate

    def test_raises_on_empty_configs(self) -> None:
        """Raises ValueError if sweep_configs is empty."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("110"),),
            tp_sizes=(Decimal("1.0"),),
        )

        with pytest.raises(ValueError, match="cannot be empty"):
            run_robustness_sweep([], bracket, [])

    def test_sweep_grid_contains_all_configs(self) -> None:
        """Sweep grid should have entry for each config."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("110"),),
            tp_sizes=(Decimal("1.0"),),
        )
        candles = [
            make_candle(
                open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                open_p=Decimal("100"),
                high_p=Decimal("112"),
                low_p=Decimal("99"),
                close_p=Decimal("111"),
            ),
        ]
        configs = build_sweep_grid(
            CostConfig(),
            fee_range=(Decimal("5"), Decimal("10")),
            slippage_range=(Decimal("0"), Decimal("5")),
        )

        result = run_robustness_sweep(candles, bracket, configs)

        assert len(result.sweep_grid) == len(configs)
        # Verify each config is in the grid
        grid_configs = [c for c, _ in result.sweep_grid]
        for config in configs:
            assert config in grid_configs
