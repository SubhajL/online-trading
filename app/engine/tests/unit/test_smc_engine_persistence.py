"""Tests for SMC engine DB persistence via db_adapter.

Uses a real Protocol-compliant fake adapter (no mocks) to verify that
CHOCH/BOS events detected by SMCEngine are persisted through insert_smc_event_v1.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import logging

import pytest

from app.engine.bus import set_event_bus
from app.engine.core.event_bus_factory import EventBusConfig, EventBusFactory
from app.engine.models import Candle, TimeFrame
from app.engine.smc.engine import SMCEngine
from app.engine.smc_types import Pivot, StructureState

SYMBOL = "BTCUSDT"
TF = TimeFrame.M15
VENUE = "binance_spot"
BASE_TIME = datetime(2025, 1, 1, tzinfo=UTC)

# Candle filler values — realistic BTC/USDT magnitudes
CANDLE_VOLUME = Decimal("100")  # base asset volume per bar
CANDLE_QUOTE_VOLUME = Decimal("10000")  # ≈ CANDLE_VOLUME × price / 500
CANDLE_TRADES = 50  # trades per bar
TAKER_BUY_BASE = Decimal("50")  # ~50 % of volume
TAKER_BUY_QUOTE = Decimal("5000")  # ~50 % of quote volume
HIGH_LOW_OFFSET = Decimal("50")  # default wick size above/below body


class FakeSMCDBAdapter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def insert_smc_event_v1(self, payload: dict) -> None:
        self.events.append(payload)


class FailingSMCDBAdapter:
    async def insert_smc_event_v1(self, payload: dict) -> None:
        raise RuntimeError("DB connection lost")


def _make_candle(
    *,
    bar_index: int,
    open_price: Decimal,
    close_price: Decimal,
    high_price: Decimal | None = None,
    low_price: Decimal | None = None,
) -> Candle:
    return Candle(
        venue=VENUE,
        symbol=SYMBOL,
        timeframe=TF,
        open_time=BASE_TIME + timedelta(minutes=15 * bar_index),
        close_time=BASE_TIME + timedelta(minutes=15 * (bar_index + 1)),
        open_price=open_price,
        high_price=high_price or max(open_price, close_price) + HIGH_LOW_OFFSET,
        low_price=low_price or min(open_price, close_price) - HIGH_LOW_OFFSET,
        close_price=close_price,
        volume=CANDLE_VOLUME,
        quote_volume=CANDLE_QUOTE_VOLUME,
        trades=CANDLE_TRADES,
        taker_buy_base_volume=TAKER_BUY_BASE,
        taker_buy_quote_volume=TAKER_BUY_QUOTE,
        bar_index=bar_index,
    )


@pytest.fixture(autouse=True)
def _event_bus():
    cfg = EventBusConfig(
        use_priority_queue=False,
        dlq_on_any_failure=False,
        num_workers=1,
        max_queue_size=100,
        dead_letter_queue_size=10,
    )
    bus = EventBusFactory().create_with_config(cfg)
    set_event_bus(bus)
    yield
    set_event_bus(None)


def _seed_bullish_state(engine: SMCEngine) -> None:
    """Pre-seed the engine tracker into BULLISH state with known HL/HH pivots.

    This bypasses pivot detection (which requires bar_index alignment) and
    directly sets the structure state so CHOCH detection can fire.
    Does NOT reset candle history — call after feeding initial candles.
    """
    key = (SYMBOL, TF)
    tracker = engine._trackers[key]

    tracker.state = StructureState.BULLISH
    tracker.last_hl = Pivot(
        timestamp=BASE_TIME + timedelta(minutes=15 * 5),
        price=Decimal("49500"),
        is_high=False,
        strength=3,
        bar_index=5,
    )
    tracker.last_hh = Pivot(
        timestamp=BASE_TIME + timedelta(minutes=15 * 8),
        price=Decimal("51500"),
        is_high=True,
        strength=3,
        bar_index=8,
    )


class TestSMCEnginePersistence:

    @pytest.mark.asyncio
    async def test_process_candle_persists_choch_event_via_db_adapter(self) -> None:
        """Pre-seed BULLISH state, then feed a candle closing below HL to trigger
        a bearish CHOCH. Verify the adapter captured the event."""
        adapter = FakeSMCDBAdapter()
        engine = SMCEngine(db_adapter=adapter)

        # Seed enough candle history so process_candle doesn't early-return
        for i in range(10):
            c = _make_candle(
                bar_index=i,
                open_price=Decimal("50000") + Decimal(str(i * 100)),
                close_price=Decimal("50050") + Decimal(str(i * 100)),
            )
            await engine.process_candle(c, emit_events=False)

        # Now pre-seed BULLISH state with HL at 49500
        _seed_bullish_state(engine)

        # Feed a candle that closes below HL (49500) -> triggers bearish CHOCH
        choch_candle = _make_candle(
            bar_index=10,
            open_price=Decimal("49600"),
            close_price=Decimal("49000"),
            high_price=Decimal("49650"),
            low_price=Decimal("48950"),
        )
        await engine.process_candle(choch_candle, emit_events=True)

        assert len(adapter.events) >= 1, (
            "Expected at least one SMC event to be persisted via db_adapter"
        )

        event = adapter.events[0]
        assert event["symbol"] == SYMBOL
        assert event["venue"] == VENUE
        assert event["timeframe"] == TF.value
        assert event["event_type"] == "choch"
        assert event["direction"] == "bearish"
        assert event["price_level"] == "49000"
        assert event["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_process_candle_skips_persistence_when_no_db_adapter(self) -> None:
        """db_adapter=None should not cause any error when CHOCH fires."""
        engine = SMCEngine(db_adapter=None)

        for i in range(10):
            c = _make_candle(
                bar_index=i,
                open_price=Decimal("50000") + Decimal(str(i * 100)),
                close_price=Decimal("50050") + Decimal(str(i * 100)),
            )
            await engine.process_candle(c, emit_events=False)

        _seed_bullish_state(engine)

        choch_candle = _make_candle(
            bar_index=10,
            open_price=Decimal("49600"),
            close_price=Decimal("49000"),
        )
        await engine.process_candle(choch_candle, emit_events=True)

        # No crash means success
        assert engine._db_adapter is None

    @pytest.mark.asyncio
    async def test_process_candle_logs_and_continues_on_db_failure(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When adapter raises, the engine logs the exception and continues."""
        adapter = FailingSMCDBAdapter()
        engine = SMCEngine(db_adapter=adapter)

        for i in range(10):
            c = _make_candle(
                bar_index=i,
                open_price=Decimal("50000") + Decimal(str(i * 100)),
                close_price=Decimal("50050") + Decimal(str(i * 100)),
            )
            await engine.process_candle(c, emit_events=False)

        _seed_bullish_state(engine)

        choch_candle = _make_candle(
            bar_index=10,
            open_price=Decimal("49600"),
            close_price=Decimal("49000"),
        )

        with caplog.at_level(logging.ERROR):
            await engine.process_candle(choch_candle, emit_events=True)

        # Engine did not crash
        key = (SYMBOL, TF)
        assert engine._trackers.get(key) is not None

        # Verify the DB failure was logged
        error_messages = [r.message for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("persist SMC event" in m for m in error_messages)
