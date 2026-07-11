from __future__ import annotations

import math

import numpy as np
import pytest

from app.engine.backtest.regime import (
    apply_regime_gate,
    label_trend_on_states,
    regime_features,
    sma_positions,
    strategy_net_metrics,
    tsmom_positions,
)


class TestRegimeFeatures:
    def test_returns_log_return_and_trailing_vol_aligned_to_bar(self) -> None:
        # closes -> log returns of ln(102/100), ln(102/102)=0, ln(104.04/102)
        closes = np.array([100.0, 102.0, 102.0, 104.04])

        feats = regime_features(closes, vol_window=2)

        assert feats.shape == (3, 2)
        expected_log = [math.log(1.02), 0.0, math.log(104.04 / 102.0)]
        assert feats[:, 0] == pytest.approx(expected_log)

    def test_trailing_vol_is_nan_during_warmup_then_population_std(self) -> None:
        closes = np.array([100.0, 110.0, 121.0, 133.1])  # +10% each -> constant log ret
        feats = regime_features(closes, vol_window=2)

        # log returns are constant (~0.0953) so trailing population std is 0
        # once the window fills; the first row lacks a full window -> nan.
        assert math.isnan(feats[0, 1])
        assert feats[1, 1] == pytest.approx(0.0, abs=1e-12)
        assert feats[2, 1] == pytest.approx(0.0, abs=1e-12)

    def test_too_few_closes_returns_empty(self) -> None:
        assert regime_features(np.array([100.0]), vol_window=2).shape == (0, 2)


class TestLabelTrendOnStates:
    def test_states_with_nonnegative_mean_return_are_trend_on(self) -> None:
        means = np.array([[0.01, 0.02], [-0.02, 0.05], [0.0, 0.01]])

        assert label_trend_on_states(means) == {0, 2}

    def test_all_negative_returns_empty_set(self) -> None:
        means = np.array([[-0.01, 0.02], [-0.02, 0.05]])

        assert label_trend_on_states(means) == set()


class TestApplyRegimeGate:
    def test_gate_zeros_positions_outside_regime(self) -> None:
        positions = np.array([1.0, 1.0, 1.0, 1.0])
        in_regime = np.array([True, False, True, False])

        gated = apply_regime_gate(positions, in_regime)

        assert gated.tolist() == [1.0, 0.0, 1.0, 0.0]

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="length"):
            apply_regime_gate(np.array([1.0, 1.0]), np.array([True]))


class TestPositionSignals:
    def test_tsmom_is_long_when_trailing_return_positive(self) -> None:
        # lookback 2: bar i long iff close[i] > close[i-2]. Warmup bars flat.
        closes = np.array([100.0, 100.0, 101.0, 99.0, 105.0])

        pos = tsmom_positions(closes, lookback=2)

        assert pos.tolist() == [0.0, 0.0, 1.0, 0.0, 1.0]

    def test_sma_is_long_when_close_above_trailing_mean(self) -> None:
        # period 2: SMA at bar i = mean(close[i-1], close[i]); long iff close>SMA.
        closes = np.array([100.0, 102.0, 101.0, 108.0])

        pos = sma_positions(closes, period=2)

        # bar1 SMA=101 close102>101 ->1; bar2 SMA=101.5 close101<->0; bar3 SMA=104.5 close108>->1
        assert pos.tolist() == [0.0, 1.0, 0.0, 1.0]


class TestStrategyNetMetrics:
    def test_flat_position_gives_zero_return_and_drawdown(self) -> None:
        closes = np.array([100.0, 110.0, 90.0, 100.0])
        positions = np.zeros(4)

        sharpe, max_dd, total_ret = strategy_net_metrics(
            closes, positions, cost_per_side=0.001, bars_per_year=365.0
        )

        assert (sharpe, max_dd, total_ret) == (0.0, 0.0, 0.0)

    def test_always_long_no_cost_matches_buy_and_hold(self) -> None:
        # held from bar 1 onward, single entry -> total return ~ buy&hold minus
        # the one-side entry cost. With zero cost it equals buy&hold exactly.
        closes = np.array([100.0, 110.0, 121.0])
        positions = np.ones(3)

        _, _, total_ret = strategy_net_metrics(
            closes, positions, cost_per_side=0.0, bars_per_year=365.0
        )

        assert total_ret == pytest.approx(21.0, abs=1e-9)

    def test_entry_cost_is_charged_once_per_side(self) -> None:
        closes = np.array([100.0, 100.0, 100.0])
        positions = np.array([0.0, 1.0, 1.0])  # one entry (0->1) at bar 1

        _, _, total_ret = strategy_net_metrics(
            closes, positions, cost_per_side=0.001, bars_per_year=365.0
        )

        # flat prices, one 0->1 turnover of 1.0 x 0.001 -> -0.1% total
        assert total_ret == pytest.approx(-0.1, abs=1e-9)
