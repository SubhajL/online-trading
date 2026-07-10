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


def test_yaml_loads_sizing_knobs_into_config(tmp_path: Path) -> None:
    runner = BacktestRunner(
        _config_path(
            tmp_path,
            "backtest:\n"
            "  sizing_mode: notional\n"
            "  notional_pct: 0.5\n"
            "  vol_target_annual_pct: 40\n"
            "  vol_lookback_bars: 30\n"
            "  max_position_notional_pct: 1.0\n"
            "  max_symbol_exposure_pct: 1.0\n"
            "  max_total_exposure_leverage: 2\n",
        ),
    )

    config = runner.config
    loaded = (
        config.sizing_mode,
        config.notional_pct,
        config.vol_target_annual_pct,
        config.vol_lookback_bars,
        config.max_position_notional_pct,
        config.max_symbol_exposure_pct,
        config.max_total_exposure_leverage,
    )
    assert loaded == (
        "notional",
        Decimal("0.5"),
        Decimal(40),
        30,
        Decimal("1.0"),
        Decimal("1.0"),
        Decimal(2),
    )


def test_missing_sizing_keys_default_to_risk_mode_and_live_caps(tmp_path: Path) -> None:
    runner = BacktestRunner(
        _config_path(tmp_path, "backtest:\n  warmup_bars: 50\n"),
    )

    defaults = BacktestConfig()
    config = runner.config
    assert (config.sizing_mode, config.notional_pct) == ("risk", defaults.notional_pct)
    assert (
        config.vol_target_annual_pct,
        config.vol_lookback_bars,
        config.max_position_notional_pct,
        config.max_symbol_exposure_pct,
        config.max_total_exposure_leverage,
    ) == (
        defaults.vol_target_annual_pct,
        defaults.vol_lookback_bars,
        Decimal("0.10"),
        Decimal("0.25"),
        Decimal(3),
    )


def test_report_json_includes_sizing_fields(tmp_path: Path) -> None:
    runner = BacktestRunner(
        _config_path(
            tmp_path,
            "backtest:\n"
            "  signal_source: tsmom\n"
            "  sizing_mode: notional\n"
            "  notional_pct: 0.25\n"
            "  max_position_notional_pct: 1.0\n",
        ),
    )
    result = BacktestResult(
        config=runner.config,
        metrics=BacktestMetrics(),
    )
    report_path = tmp_path / "report.json"

    runner._save_json_report(result, report_path)
    report = json.loads(report_path.read_text())

    assert report["config"]["sizing_mode"] == "notional"
    assert report["config"]["notional_pct"] == 0.25
    assert report["config"]["vol_target_annual_pct"] == 0.0
    assert report["config"]["max_position_notional_pct"] == 1.0
    assert report["config"]["max_symbol_exposure_pct"] == 0.25
    assert report["config"]["max_total_exposure_leverage"] == 3.0
