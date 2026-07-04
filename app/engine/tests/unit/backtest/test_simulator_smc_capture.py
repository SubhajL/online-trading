from __future__ import annotations

from decimal import Decimal

import pytest

from app.engine.backtest.simulator import BacktestSimulator
from app.engine.backtest.types import BacktestConfig
from app.engine.bus import get_event_bus
from app.engine.models import TimeFrame

from .series import impulse_bos_candles


@pytest.mark.asyncio
async def test_bullish_bos_captured_with_retest_engine_dict_shape() -> None:
    simulator = BacktestSimulator(BacktestConfig())
    candles = impulse_bos_candles()

    for candle in candles:
        await simulator.process_candle(candle)

    assert simulator._bos_events == [
        {
            "timestamp": candles[10].close_time,
            "type": "BULLISH_BOS",
            "level": Decimal("103.4"),
            "strength": Decimal("1.0"),
        },
    ]


@pytest.mark.asyncio
async def test_order_block_zone_mapped_with_retest_engine_dict_shape() -> None:
    simulator = BacktestSimulator(BacktestConfig())

    for candle in impulse_bos_candles():
        await simulator.process_candle(candle)

    zones = simulator._zones_as_dicts("BTCUSDT", TimeFrame.M15)
    ob_zones = [zone for zone in zones if zone["zone_type"] == "OB_BULL"]

    assert len(ob_zones) == 1
    ob_zone = ob_zones[0]
    assert set(ob_zone.keys()) == {
        "zone_id",
        "zone_type",
        "side",
        "top_price",
        "bottom_price",
        "created_at",
        "strength",
    }
    assert isinstance(ob_zone["zone_id"], str)
    assert (ob_zone["side"], ob_zone["top_price"], ob_zone["bottom_price"]) == (
        "LOW",
        Decimal("102.9"),
        Decimal("102"),
    )


def test_capture_bus_installed_as_global_bus_before_smc_engine() -> None:
    simulator = BacktestSimulator(BacktestConfig())

    assert simulator.smc_engine._event_bus is simulator._capture_bus
    assert get_event_bus() is simulator._capture_bus
