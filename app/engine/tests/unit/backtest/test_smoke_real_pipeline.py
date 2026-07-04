"""End-to-end smoke: the real strategy pipeline produces a deterministic trade.

Drives synthetic candles through the fully real chain — SMCEngine structure
detection, zone creation, analyze_retest, shared sizing, pretrade risk,
cooldown, next-bar-open fills, OCO bracket exits — with no mocks. The series
is a 50-bar oscillating warmup, the proven bullish staircase from the SMC
pivot-registration tests (structure turns BULLISH, BOS fires), a pullback
into the demand zone, and a rally through TP1.

Staged asserts localize failures: structure -> BOS capture -> zone ->
order -> position -> completed trade.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.engine.backtest.simulator import BacktestSimulator
from app.engine.backtest.types import BacktestConfig, ExitReason
from app.engine.models import Candle, TimeFrame
from app.engine.smc_types import StructureState

from .series import make_candle

SYMBOL = "BTCUSDT"
TF = TimeFrame.M15
INITIAL_BALANCE = Decimal(10000)

# Pinned from the deterministic Decimal arithmetic of the pipeline:
# entry fills at bar-55 open (100.9) plus 2bps slippage and TP1 exits on the
# rally bar. A change to fills, sizing, or signal timing moves these values.
EXPECTED_ENTRY = Decimal("100.930270")
EXPECTED_EXIT_REASON = ExitReason.TP

SIGNAL_BAR = 54
ENTRY_BAR = 55
WARMUP_BARS = 50

STAIRCASE = [
    ("100", "101.0", "99.0", "100.2"),
    ("100.2", "102.0", "100.0", "101.5"),
    ("101.5", "101.4", "100.2", "100.6"),
    ("100.6", "100.5", "99.4", "99.8"),
    ("99.8", "101.2", "99.9", "100.9"),
    ("100.9", "104.0", "100.8", "103.6"),
    ("103.6", "103.0", "101.9", "102.2"),
    ("102.2", "102.6", "101.2", "101.6"),
    ("101.6", "103.2", "101.5", "102.9"),
]


def _smoke_series() -> list[Candle]:
    bars: list[Candle] = []
    index = 0
    for k in range(WARMUP_BARS):
        base = Decimal("100") + Decimal(k % 5) * Decimal("0.2")
        close = base + (Decimal("0.3") if k % 2 == 0 else Decimal("-0.2"))
        high = max(base, close) + Decimal("0.4")
        low = min(base, close) - Decimal("0.4")
        bars.append(make_candle(index, str(base), str(high), str(low), str(close)))
        index += 1
    for bar in STAIRCASE:
        bars.append(make_candle(index, *bar))
        index += 1
    bars.append(make_candle(index, "102.9", "105.2", "102.8", "105.0"))
    index += 1
    bars.append(make_candle(index, "105.0", "105.1", "103.2", "103.5"))
    index += 1
    bars.append(make_candle(index, "103.5", "103.6", "102.0", "102.3"))
    index += 1
    bars.append(make_candle(index, "102.3", "103.4", "102.1", "103.2"))
    index += 1
    for k in range(6):
        px = Decimal("103.5") + Decimal(k)
        bars.append(
            make_candle(
                index,
                str(px),
                str(px + Decimal("1.4")),
                str(px - Decimal("0.3")),
                str(px + Decimal("1.2")),
            ),
        )
        index += 1
    return bars


class TestSmokeRealPipeline:
    @pytest.mark.asyncio
    async def test_synthetic_trend_produces_one_deterministic_tp_trade(self) -> None:
        simulator = BacktestSimulator(BacktestConfig(), initial_balance=INITIAL_BALANCE)
        bars = _smoke_series()

        for candle in bars[:SIGNAL_BAR]:
            await simulator.process_candle(candle)

        # Stage 1: real structure detection turned BULLISH during the staircase.
        tracker = simulator.smc_engine._trackers[(SYMBOL, TF)]
        assert tracker.state == StructureState.BULLISH

        # Stage 2: structure breaks were captured off the bus.
        assert simulator._bos_events, "no BOS/CHOCH events captured"
        assert any(bos["type"].startswith("BULLISH_") for bos in simulator._bos_events)

        # Stage 3: real zones exist for the retest to trade against.
        zones = simulator.smc_engine.get_zones(SYMBOL, TF)
        assert any(zone.side.value == "LOW" for zone in zones)

        # Stage 4: the real analyze_retest produced a signal -> MARKET order.
        await simulator.process_candle(bars[SIGNAL_BAR])
        assert len(simulator.active_orders) == 1

        # Stage 5: entry fills at next bar open + slippage; OCO brackets rest.
        await simulator.process_candle(bars[ENTRY_BAR])
        assert len(simulator.positions) == 1
        position = next(iter(simulator.positions.values()))
        assert position.stop_loss is not None

        # Stage 6: the rally fills TP1, cancels the stop, completes the trade.
        for candle in bars[ENTRY_BAR + 1 :]:
            await simulator.process_candle(candle)

        assert len(simulator.completed_trades) == 1
        trade = simulator.completed_trades[0]
        assert trade.side == "long"
        assert trade.entry_price == EXPECTED_ENTRY
        assert trade.exit_reason == EXPECTED_EXIT_REASON
        assert trade.fees > 0
        assert trade.net_pnl is not None and trade.net_pnl > 0
        assert simulator.active_orders == []
        assert all(pos.quantity == 0 for pos in simulator.positions.values())
        assert simulator.current_balance > INITIAL_BALANCE
