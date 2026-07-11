from __future__ import annotations

import numpy as np
import pytest

from app.engine.backtest.bootstrap import (
    SharpeGapCI,
    sharpe_gap_ci,
    stationary_bootstrap_indices,
)


class TestStationaryBootstrapIndices:
    def test_indices_cover_length_and_stay_in_range(self) -> None:
        rng = np.random.default_rng(7)

        indices = stationary_bootstrap_indices(500, mean_block=20.0, rng=rng)

        assert indices.shape == (500,)
        assert indices.min() >= 0
        assert indices.max() < 500

    def test_same_seed_reproduces_indices(self) -> None:
        first = stationary_bootstrap_indices(
            200,
            mean_block=10.0,
            rng=np.random.default_rng(11),
        )
        second = stationary_bootstrap_indices(
            200,
            mean_block=10.0,
            rng=np.random.default_rng(11),
        )

        assert np.array_equal(first, second)

    def test_blocks_are_consecutive_runs_modulo_wraparound(self) -> None:
        # Within a block each index advances by exactly 1 (mod n); block
        # restarts are the only discontinuities. With mean_block=50 over 100
        # samples some consecutive step must appear.
        rng = np.random.default_rng(3)

        indices = stationary_bootstrap_indices(100, mean_block=50.0, rng=rng)

        steps = (indices[1:] - indices[:-1]) % 100
        assert set(np.unique(steps)) <= set(range(100))
        assert (steps == 1).sum() > 0


class TestSharpeGapCI:
    def test_identical_series_give_zero_gap_and_degenerate_ci(self) -> None:
        returns = np.random.default_rng(5).normal(0.001, 0.02, 400)

        ci = sharpe_gap_ci(
            strategy_returns=returns,
            benchmark_returns=returns.copy(),
            bars_per_year=365.0,
            n_boot=200,
            mean_block=20,
            seed=1,
        )

        assert isinstance(ci, SharpeGapCI)
        assert ci.point == pytest.approx(0.0, abs=1e-12)
        assert ci.lower == pytest.approx(0.0, abs=1e-12)
        assert ci.upper == pytest.approx(0.0, abs=1e-12)

    def test_constant_positive_alpha_excludes_zero(self) -> None:
        # Same vol, strictly higher mean: every paired replicate must show a
        # positive gap, so the lower bound sits above zero.
        rng = np.random.default_rng(42)
        benchmark = rng.normal(0.0, 0.02, 500)
        strategy = benchmark + 0.002

        ci = sharpe_gap_ci(
            strategy_returns=strategy,
            benchmark_returns=benchmark,
            bars_per_year=365.0,
            n_boot=500,
            mean_block=20,
            seed=2,
        )

        assert ci.point > 0
        assert ci.lower > 0
        assert ci.lower <= ci.upper

    def test_same_seed_reproduces_interval(self) -> None:
        rng = np.random.default_rng(9)
        benchmark = rng.normal(0.001, 0.03, 300)
        strategy = rng.normal(0.001, 0.03, 300)

        first = sharpe_gap_ci(
            strategy_returns=strategy,
            benchmark_returns=benchmark,
            bars_per_year=365.0,
            n_boot=300,
            mean_block=15,
            seed=4,
        )
        second = sharpe_gap_ci(
            strategy_returns=strategy,
            benchmark_returns=benchmark,
            bars_per_year=365.0,
            n_boot=300,
            mean_block=15,
            seed=4,
        )

        assert (first.point, first.lower, first.upper) == (
            second.point,
            second.lower,
            second.upper,
        )

    def test_mismatched_lengths_raise(self) -> None:
        with pytest.raises(ValueError, match="length"):
            sharpe_gap_ci(
                strategy_returns=np.zeros(10),
                benchmark_returns=np.zeros(11),
                bars_per_year=365.0,
            )

    @pytest.mark.parametrize(
        ("n_boot", "mean_block"),
        [(0, 20), (100, 0)],
    )
    def test_non_positive_parameters_raise(self, n_boot: int, mean_block: int) -> None:
        returns = np.zeros(50)

        with pytest.raises(ValueError, match="n_boot|mean_block"):
            sharpe_gap_ci(
                strategy_returns=returns,
                benchmark_returns=returns,
                bars_per_year=365.0,
                n_boot=n_boot,
                mean_block=mean_block,
            )

    @pytest.mark.parametrize("n", [0, 1])
    def test_too_few_observations_raise(self, n: int) -> None:
        # Fewer than 2 returns cannot form a Sharpe; fail with a clear message
        # instead of an IndexError deep in the resampler.
        returns = np.zeros(n)

        with pytest.raises(ValueError, match="at least 2|observations"):
            sharpe_gap_ci(
                strategy_returns=returns,
                benchmark_returns=returns,
                bars_per_year=365.0,
            )
