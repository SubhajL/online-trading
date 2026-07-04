from __future__ import annotations

from decimal import Decimal
import logging
from pathlib import Path

import pytest

from app.engine.backtest.runner import BacktestRunner


def _config_path(tmp_path: Path, text: str) -> str:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return str(path)


def test_load_config_reads_backtest_section(tmp_path: Path) -> None:
    runner = BacktestRunner(
        _config_path(tmp_path, "backtest:\n  risk_per_trade: 0.007\n  warmup_bars: 60\n"),
    )

    assert (runner.config.risk_per_trade, runner.config.warmup_bars) == (
        Decimal("0.007"),
        60,
    )


def test_load_config_honors_backtesting_alias_with_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        runner = BacktestRunner(
            _config_path(tmp_path, "backtesting:\n  risk_per_trade: 0.007\n  warmup_bars: 60\n"),
        )

    assert (runner.config.risk_per_trade, runner.config.warmup_bars) == (
        Decimal("0.007"),
        60,
    )
    assert "backtesting" in caplog.text


def test_load_config_prefers_backtest_over_alias(tmp_path: Path) -> None:
    runner = BacktestRunner(
        _config_path(
            tmp_path,
            "backtest:\n  risk_per_trade: 0.009\nbacktesting:\n  risk_per_trade: 0.007\n",
        ),
    )

    assert runner.config.risk_per_trade == Decimal("0.009")


def test_load_config_warns_when_no_backtest_section(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        runner = BacktestRunner(_config_path(tmp_path, "smc:\n  pivot_n: 5\n"))

    assert runner.config.risk_per_trade == Decimal("0.005")
    assert "backtest" in caplog.text.lower()


def test_load_config_raises_when_file_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="missing.yaml"):
        BacktestRunner(str(tmp_path / "missing.yaml"))


def test_run_backtest_loads_downloader_csv_end_to_end(tmp_path: Path) -> None:
    from app.engine.backtest.dataset import export_candles_to_csv
    from app.engine.tests.unit.backtest.series import flat_candles

    candles = flat_candles(55)
    export_candles_to_csv(candles, str(tmp_path / "btcusdt_15m.csv"))
    runner = BacktestRunner(_config_path(tmp_path, "backtest:\n  warmup_bars: 50\n"))

    result = runner.run_backtest(
        symbol="BTCUSDT",
        timeframe="15m",
        start_date="2024-01-02",
        end_date="2024-01-02",
        data_source="csv",
        data_directory=str(tmp_path),
    )

    assert len(result.equity_curve) == 55
