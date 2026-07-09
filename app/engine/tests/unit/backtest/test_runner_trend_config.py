from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

from app.engine.backtest.runner import BacktestRunner
from app.engine.backtest.types import BacktestConfig, BacktestMetrics, BacktestResult


def _config_path(tmp_path: Path, text: str) -> str:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return str(path)


def test_yaml_loads_trend_knobs_into_config(tmp_path: Path) -> None:
    runner = BacktestRunner(
        _config_path(
            tmp_path,
            "backtest:\n"
            "  signal_source: price_sma\n"
            "  allow_short: true\n"
            "  atr_period: 20\n"
            "  atr_stop_mult: 2.5\n"
            "  sma_period: 65\n"
            "  tsmom_lookback: 14\n"
            "  tsmom_deadband_bps: 25\n"
            "  ema_fast: 5\n"
            "  ema_slow: 20\n"
            "  donchian_entry: 10\n"
            "  donchian_exit: 5\n"
            "  max_hold_bars: 30\n"
            "  trend_tp_r: 1.5\n",
        ),
    )

    config = runner.config
    loaded = (
        config.signal_source,
        config.allow_short,
        config.atr_period,
        config.atr_stop_mult,
        config.sma_period,
        config.tsmom_lookback,
        config.tsmom_deadband_bps,
        config.ema_fast,
        config.ema_slow,
        config.donchian_entry,
        config.donchian_exit,
        config.max_hold_bars,
        config.trend_tp_r,
    )
    assert loaded == (
        "price_sma",
        True,
        20,
        Decimal("2.5"),
        65,
        14,
        Decimal(25),
        5,
        20,
        10,
        5,
        30,
        Decimal("1.5"),
    )


def test_missing_trend_keys_default_to_smc_path(tmp_path: Path) -> None:
    runner = BacktestRunner(
        _config_path(tmp_path, "backtest:\n  warmup_bars: 50\n"),
    )

    defaults = BacktestConfig()
    config = runner.config
    assert (config.signal_source, config.allow_short) == ("smc_retest", False)
    assert (config.sma_period, config.tsmom_lookback, config.trend_tp_r) == (
        defaults.sma_period,
        defaults.tsmom_lookback,
        defaults.trend_tp_r,
    )


def test_report_json_includes_benchmark_and_signal_source(tmp_path: Path) -> None:
    runner = BacktestRunner(
        _config_path(tmp_path, "backtest:\n  signal_source: tsmom\n"),
    )
    result = BacktestResult(
        config=runner.config,
        metrics=BacktestMetrics(
            total_pnl_pct=Decimal(12),
            benchmark_return_pct=Decimal(30),
            benchmark_max_drawdown_pct=Decimal(25),
            benchmark_sharpe_ratio=Decimal("1.1"),
            excess_return_pct=Decimal(-18),
        ),
    )
    report_path = tmp_path / "report.json"

    runner._save_json_report(result, report_path)
    report = json.loads(report_path.read_text())

    assert report["config"]["signal_source"] == "tsmom"
    assert report["metrics"]["benchmark_return_pct"] == 30.0
    assert report["metrics"]["benchmark_max_drawdown_pct"] == 25.0
    assert report["metrics"]["benchmark_sharpe_ratio"] == 1.1
    assert report["metrics"]["excess_return_pct"] == -18.0
