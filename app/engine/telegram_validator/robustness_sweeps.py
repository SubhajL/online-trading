"""
Robustness sweeps for bracket fill simulation.

Runs fill simulation across a grid of cost configurations
to evaluate signal robustness under varying assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import product
from statistics import quantiles

from ..models import Candle
from .fill_model import (
    BracketSpec,
    CostConfig,
    FillSimulationResult,
    IntrabarPolicy,
    simulate_bracket_fills,
)


@dataclass(frozen=True)
class SweepResult:
    """Result of a robustness sweep across cost configurations."""

    baseline: FillSimulationResult
    sweep_grid: tuple[tuple[CostConfig, FillSimulationResult], ...]
    pass_rate: float  # % of grid with positive net_pnl
    pnl_p10: Decimal  # 10th percentile net_pnl
    pnl_p50: Decimal  # Median net_pnl
    pnl_p90: Decimal  # 90th percentile net_pnl


def build_sweep_grid(
    base_config: CostConfig,
    *,
    fee_range: tuple[Decimal, ...] | None = None,
    slippage_range: tuple[Decimal, ...] | None = None,
    funding_range: tuple[Decimal, ...] | None = None,
) -> list[CostConfig]:
    """Generate Cartesian product of cost configurations for sweep.

    If a range is None, uses only the base config value for that dimension.

    Returns list of CostConfig instances.
    """
    fees = fee_range if fee_range else (base_config.fee_bps,)
    slips = slippage_range if slippage_range else (base_config.slippage_bps,)
    fundings = funding_range if funding_range else (base_config.funding_rate_8h,)

    configs = []
    for fee, slip, funding in product(fees, slips, fundings):
        configs.append(
            CostConfig(
                fee_bps=fee,
                slippage_bps=slip,
                funding_rate_8h=funding,
            )
        )

    return configs


def aggregate_sweep_metrics(
    results: list[FillSimulationResult],
) -> tuple[float, Decimal, Decimal, Decimal]:
    """Compute aggregate metrics from sweep results.

    Returns (pass_rate, pnl_p10, pnl_p50, pnl_p90).
    """
    if not results:
        return 0.0, Decimal("0"), Decimal("0"), Decimal("0")

    pnls = [r.net_pnl for r in results]
    positive_count = sum(1 for p in pnls if p > Decimal("0"))
    pass_rate = positive_count / len(pnls)

    # Convert to float for quantile calculation
    pnl_floats = sorted(float(p) for p in pnls)

    if len(pnl_floats) < 4:
        # Not enough data for proper quantiles
        p10 = Decimal(str(pnl_floats[0]))
        p50 = Decimal(str(pnl_floats[len(pnl_floats) // 2]))
        p90 = Decimal(str(pnl_floats[-1]))
    else:
        qs = quantiles(pnl_floats, n=10)  # Returns 9 cut points for 10 quantiles
        p10 = Decimal(str(qs[0]))  # 10th percentile
        p50 = Decimal(str(qs[4]))  # 50th percentile (median)
        p90 = Decimal(str(qs[8]))  # 90th percentile

    return pass_rate, p10, p50, p90


def run_robustness_sweep(
    candles: list[Candle],
    bracket: BracketSpec,
    sweep_configs: list[CostConfig],
    *,
    intrabar_policy: IntrabarPolicy = "worst_case",
    max_bars: int = 500,
) -> SweepResult:
    """Run fill simulation for each config and aggregate into SweepResult.

    The baseline is computed with the first config in sweep_configs.
    """
    if not sweep_configs:
        raise ValueError("sweep_configs cannot be empty")

    # Run baseline with first config
    baseline_config = sweep_configs[0]
    baseline = simulate_bracket_fills(
        candles,
        bracket,
        intrabar_policy=intrabar_policy,
        cost_config=baseline_config,
        max_bars=max_bars,
    )

    # Run sweep for all configs
    grid_results: list[tuple[CostConfig, FillSimulationResult]] = []
    all_results: list[FillSimulationResult] = []

    for config in sweep_configs:
        result = simulate_bracket_fills(
            candles,
            bracket,
            intrabar_policy=intrabar_policy,
            cost_config=config,
            max_bars=max_bars,
        )
        grid_results.append((config, result))
        all_results.append(result)

    # Aggregate metrics
    pass_rate, pnl_p10, pnl_p50, pnl_p90 = aggregate_sweep_metrics(all_results)

    return SweepResult(
        baseline=baseline,
        sweep_grid=tuple(grid_results),
        pass_rate=pass_rate,
        pnl_p10=pnl_p10,
        pnl_p50=pnl_p50,
        pnl_p90=pnl_p90,
    )


# Preset sweep configurations
CONSERVATIVE_SWEEP = build_sweep_grid(
    CostConfig(),
    fee_range=(Decimal("5"), Decimal("10"), Decimal("15")),
    slippage_range=(Decimal("0"), Decimal("5"), Decimal("10")),
    funding_range=(Decimal("0"), Decimal("5"), Decimal("10")),
)

MODERATE_SWEEP = build_sweep_grid(
    CostConfig(),
    fee_range=(Decimal("10"), Decimal("20"), Decimal("30")),
    slippage_range=(Decimal("5"), Decimal("15"), Decimal("25")),
    funding_range=(Decimal("5"), Decimal("15"), Decimal("25")),
)

AGGRESSIVE_SWEEP = build_sweep_grid(
    CostConfig(),
    fee_range=(Decimal("20"), Decimal("40"), Decimal("60")),
    slippage_range=(Decimal("20"), Decimal("50"), Decimal("100")),
    funding_range=(Decimal("20"), Decimal("50"), Decimal("100")),
)

# Dictionary mapping preset names to sweep configurations
SWEEP_PRESETS: dict[str, list[CostConfig]] = {
    "conservative": CONSERVATIVE_SWEEP,
    "moderate": MODERATE_SWEEP,
    "aggressive": AGGRESSIVE_SWEEP,
}
