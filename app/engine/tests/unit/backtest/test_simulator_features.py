from __future__ import annotations

from typing import Any

import pytest

import app.engine.backtest.simulator as simulator_module
from app.engine.backtest.simulator import BacktestSimulator
from app.engine.backtest.types import BacktestConfig
from app.engine.features.indicators import TechnicalIndicatorsCalculator

from .series import flat_candles


def _install_analyze_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def spy(**kwargs: Any) -> None:
        calls.append(kwargs)
        return None

    monkeypatch.setattr(simulator_module, "analyze_retest", spy)
    return calls


@pytest.mark.asyncio
async def test_no_signal_attempt_before_warmup_plus_one_bar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_analyze_spy(monkeypatch)
    simulator = BacktestSimulator(BacktestConfig())
    candles = flat_candles(51)

    for candle in candles[:50]:
        await simulator.process_candle(candle)

    assert calls == []

    await simulator.process_candle(candles[50])

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_macd_hist_prev_is_real_previous_bar_histogram(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_analyze_spy(monkeypatch)
    simulator = BacktestSimulator(BacktestConfig())
    candles = flat_candles(51)

    for candle in candles:
        await simulator.process_candle(candle)

    closes = [candle.close_price for candle in candles]
    expected_prev = TechnicalIndicatorsCalculator.macd(closes[:50], 12, 26, 9)[2][-1]
    expected_curr = TechnicalIndicatorsCalculator.macd(closes, 12, 26, 9)[2][-1]

    assert len(calls) == 1
    features = calls[0]["features"]
    assert (features["macd_hist_prev"], features["macd_hist"]) == (expected_prev, expected_curr)
    assert features["atr"] > 0
    assert features["rsi"] is not None
