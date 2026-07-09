from __future__ import annotations

import dataclasses
from decimal import Decimal
from pathlib import Path

import pytest

from app.engine.backtest.wfo import WFORunner


@pytest.fixture
def wfo_runner(tmp_path: Path) -> WFORunner:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "backtest:\n"
        "  fee_bps_spot: 10\n"
        "  slippage_bps: 2\n"
        "wfo:\n"
        "  train_days: 90\n"
        "  test_days: 30\n"
        "  step_days: 30\n",
    )
    return WFORunner(str(config_path))


def test_params_map_to_new_config_and_base_stays_unmutated(wfo_runner: WFORunner) -> None:
    base = wfo_runner.base_runner.config
    base_snapshot = dataclasses.replace(base)

    new_config = wfo_runner._update_config_with_params(
        {
            "slippage_bps": 3,
            "pivot_n": 5,
            "retest_max_wait_bars": 6,
            "cooldown_seconds": 900,
            "risk_per_trade": "0.01",
        },
    )

    assert new_config is not base
    assert (
        new_config.slippage_bps,
        new_config.pivot_n,
        new_config.retest_max_wait_bars,
        new_config.cooldown_seconds,
        new_config.risk_per_trade,
    ) == (Decimal(3), 5, 6, 900, Decimal("0.01"))
    assert base == base_snapshot


def test_trend_params_map_to_new_config(wfo_runner: WFORunner) -> None:
    base_snapshot = dataclasses.replace(wfo_runner.base_runner.config)

    new_config = wfo_runner._update_config_with_params(
        {
            "tsmom_lookback": 42,
            "sma_period": 30,
            "ema_fast": 5,
            "ema_slow": 20,
            "donchian_entry": 10,
            "donchian_exit": 5,
            "atr_stop_mult": "2.5",
            "max_hold_bars": 60,
        },
    )

    assert (
        new_config.tsmom_lookback,
        new_config.sma_period,
        new_config.ema_fast,
        new_config.ema_slow,
        new_config.donchian_entry,
        new_config.donchian_exit,
        new_config.atr_stop_mult,
        new_config.max_hold_bars,
    ) == (42, 30, 5, 20, 10, 5, Decimal("2.5"), 60)
    assert wfo_runner.base_runner.config == base_snapshot


def test_unknown_params_are_ignored(wfo_runner: WFORunner) -> None:
    base_snapshot = dataclasses.replace(wfo_runner.base_runner.config)

    new_config = wfo_runner._update_config_with_params({"not_a_param": 42})

    assert new_config == base_snapshot
