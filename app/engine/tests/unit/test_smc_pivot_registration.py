"""Tests for confirmation-lag-aware pivot registration and BOS re-fire suppression.

Pivot detection confirms an n-bar pivot only half_n bars after it forms, so
registration must accept lagged pivots exactly once (per-kind watermarks) and
detect_bos must not re-fire for the same broken reference pivot every bar.

Streaming tests drive SMCEngine.process_candle end-to-end (no tracker seeding)
using the FakeSMCDBAdapter seam from test_smc_engine_persistence.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.bus import set_event_bus
from app.engine.core.event_bus_factory import EventBusConfig, EventBusFactory
from app.engine.models import Candle, TimeFrame
from app.engine.smc.engine import SMCEngine
from app.engine.smc.structure import (
    detect_bos,
    register_new_pivots,
    update_structure_state,
)
from app.engine.smc_types import Pivot, PivotMethod, StructureState, StructureTracker

SYMBOL = "BTCUSDT"
TF = TimeFrame.M15
VENUE = "binance_spot"
BASE_TIME = datetime(2025, 1, 1, tzinfo=UTC)

CANDLE_VOLUME = Decimal("100")
CANDLE_QUOTE_VOLUME = Decimal("10000")
CANDLE_TRADES = 50
TAKER_BUY_BASE = Decimal("50")
TAKER_BUY_QUOTE = Decimal("5000")


class FakeSMCDBAdapter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def insert_smc_event_v1(self, payload: dict) -> None:
        self.events.append(payload)


def _make_pivot(*, bar_index: int, price: str, is_high: bool) -> Pivot:
    return Pivot(
        timestamp=BASE_TIME + timedelta(minutes=15 * bar_index),
        price=Decimal(price),
        is_high=is_high,
        strength=3,
        bar_index=bar_index,
    )


def _make_candle(
    *,
    bar_index: int,
    high: str,
    low: str,
    close: str | None = None,
) -> Candle:
    high_d = Decimal(high)
    low_d = Decimal(low)
    close_d = Decimal(close) if close is not None else (high_d + low_d) / 2
    return Candle(
        venue=VENUE,
        symbol=SYMBOL,
        timeframe=TF,
        open_time=BASE_TIME + timedelta(minutes=15 * bar_index),
        close_time=BASE_TIME + timedelta(minutes=15 * (bar_index + 1)),
        open_price=(high_d + low_d) / 2,
        high_price=high_d,
        low_price=low_d,
        close_price=close_d,
        volume=CANDLE_VOLUME,
        quote_volume=CANDLE_QUOTE_VOLUME,
        trades=CANDLE_TRADES,
        taker_buy_base_volume=TAKER_BUY_BASE,
        taker_buy_quote_volume=TAKER_BUY_QUOTE,
        bar_index=bar_index,
    )


# Staircase producing, with n=3 pivots: H@1 (110), L@3 (92), HH@5 (120), HL@7 (101).
# State becomes BULLISH once HL@7 registers (while processing bar 8).
BULLISH_STAIRCASE = [
    _make_candle(bar_index=0, high="100", low="90"),
    _make_candle(bar_index=1, high="110", low="100"),
    _make_candle(bar_index=2, high="105", low="95"),
    _make_candle(bar_index=3, high="98", low="92"),
    _make_candle(bar_index=4, high="104", low="96"),
    _make_candle(bar_index=5, high="120", low="103"),
    _make_candle(bar_index=6, high="112", low="104"),
    _make_candle(bar_index=7, high="110", low="101"),
    _make_candle(bar_index=8, high="115", low="106"),
]


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


def _tracker() -> StructureTracker:
    return StructureTracker(symbol=SYMBOL, timeframe=TF)


def _registered_pairs(tracker: StructureTracker) -> list[tuple[int, bool]]:
    return [(sp.pivot.bar_index, sp.pivot.is_high) for sp in tracker.pivots]


async def _stream(engine: SMCEngine, candles: list[Candle], *, emit_events: bool) -> None:
    for candle in candles:
        await engine.process_candle(candle, emit_events=emit_events)


class TestRegisterNewPivots:
    def test_batch_registers_all_chronologically_and_sets_state(self) -> None:
        tracker = _tracker()
        # Deliberately out of order: registration must sort by bar_index.
        detected = [
            _make_pivot(bar_index=6, price="101", is_high=False),
            _make_pivot(bar_index=2, price="92", is_high=False),
            _make_pivot(bar_index=8, price="120", is_high=True),
            _make_pivot(bar_index=4, price="110", is_high=True),
        ]

        registered = register_new_pivots(tracker, detected)

        assert [p.bar_index for p in registered] == [2, 4, 6, 8]
        assert _registered_pairs(tracker) == [
            (2, False),
            (4, True),
            (6, False),
            (8, True),
        ]
        assert tracker.state == StructureState.BULLISH
        assert tracker.last_registered_high_bar_index == 8
        assert tracker.last_registered_low_bar_index == 6

    def test_dedups_repeat_detection_across_calls(self) -> None:
        tracker = _tracker()
        detected = [
            _make_pivot(bar_index=2, price="92", is_high=False),
            _make_pivot(bar_index=4, price="110", is_high=True),
        ]
        register_new_pivots(tracker, detected)

        second = register_new_pivots(tracker, detected)

        assert second == []
        assert len(tracker.pivots) == 2

    def test_same_bar_high_and_low_across_calls_both_register_once(self) -> None:
        tracker = _tracker()
        register_new_pivots(
            tracker,
            [_make_pivot(bar_index=7, price="120", is_high=True)],
        )

        registered = register_new_pivots(
            tracker,
            [
                _make_pivot(bar_index=7, price="80", is_high=False),
                _make_pivot(bar_index=7, price="120", is_high=True),
            ],
        )

        assert [(p.bar_index, p.is_high) for p in registered] == [(7, False)]
        assert sorted(_registered_pairs(tracker)) == [(7, False), (7, True)]

    def test_tolerates_bar_index_gaps_and_skips_stale(self) -> None:
        tracker = _tracker()
        registered = register_new_pivots(
            tracker,
            [
                _make_pivot(bar_index=3, price="100", is_high=True),
                _make_pivot(bar_index=5, price="90", is_high=False),
                _make_pivot(bar_index=9, price="105", is_high=True),
                _make_pivot(bar_index=40, price="115", is_high=True),
            ],
        )
        assert [p.bar_index for p in registered] == [3, 5, 9, 40]

        stale = register_new_pivots(
            tracker,
            [_make_pivot(bar_index=8, price="103", is_high=True)],
        )

        assert stale == []
        assert len(tracker.pivots) == 4


class TestDetectBosSuppression:
    def test_bos_fires_once_per_reference_then_again_on_new_hh(self) -> None:
        tracker = _tracker()
        # Build BULLISH structure: L@1, H@2, HL@3, HH@4 (112).
        update_structure_state(tracker, _make_pivot(bar_index=1, price="90", is_high=False))
        update_structure_state(tracker, _make_pivot(bar_index=2, price="110", is_high=True))
        update_structure_state(tracker, _make_pivot(bar_index=3, price="95", is_high=False))
        update_structure_state(tracker, _make_pivot(bar_index=4, price="112", is_high=True))
        assert tracker.state == StructureState.BULLISH

        ts = BASE_TIME + timedelta(minutes=15 * 10)
        first = detect_bos(tracker, Decimal("115"), 10, ts)
        repeat = detect_bos(tracker, Decimal("116"), 11, ts + timedelta(minutes=15))

        assert first is not None
        assert first.reference_pivot is not None
        assert first.reference_pivot.bar_index == 4
        assert repeat is None

        # A newly registered higher HH re-arms BOS detection.
        update_structure_state(tracker, _make_pivot(bar_index=12, price="118", is_high=True))
        again = detect_bos(tracker, Decimal("120"), 13, ts + timedelta(minutes=45))

        assert again is not None
        assert again.reference_pivot is not None
        assert again.reference_pivot.bar_index == 12

    def test_bearish_bos_fires_once_per_reference_then_again_on_new_ll(self) -> None:
        tracker = _tracker()
        # Build BEARISH structure: H@1, L@2, LH@3, LL@4 (88).
        update_structure_state(tracker, _make_pivot(bar_index=1, price="110", is_high=True))
        update_structure_state(tracker, _make_pivot(bar_index=2, price="90", is_high=False))
        update_structure_state(tracker, _make_pivot(bar_index=3, price="105", is_high=True))
        update_structure_state(tracker, _make_pivot(bar_index=4, price="88", is_high=False))
        assert tracker.state == StructureState.BEARISH

        ts = BASE_TIME + timedelta(minutes=15 * 10)
        first = detect_bos(tracker, Decimal("85"), 10, ts)
        repeat = detect_bos(tracker, Decimal("84"), 11, ts + timedelta(minutes=15))

        assert first is not None
        assert first.reference_pivot is not None
        assert first.reference_pivot.bar_index == 4
        assert repeat is None

        # A newly registered lower LL re-arms bearish BOS detection.
        update_structure_state(tracker, _make_pivot(bar_index=12, price="82", is_high=False))
        again = detect_bos(tracker, Decimal("80"), 13, ts + timedelta(minutes=45))

        assert again is not None
        assert again.reference_pivot is not None
        assert again.reference_pivot.bar_index == 12


class TestStreamingPivotRegistration:
    @pytest.mark.asyncio
    async def test_pivots_register_and_state_leaves_neutral(self) -> None:
        engine = SMCEngine(pivot_n=3)
        await _stream(engine, BULLISH_STAIRCASE, emit_events=False)

        tracker = engine._trackers[(SYMBOL, TF)]
        pairs = _registered_pairs(tracker)

        assert pairs == [(1, True), (3, False), (5, True), (7, False)]
        assert engine.get_structure_state(SYMBOL, TF) == StructureState.BULLISH
        # Confirmation lag: every registered pivot is strictly older than the
        # newest candle (the old equality gate registered nothing at all).
        assert max(bar for bar, _ in pairs) < BULLISH_STAIRCASE[-1].bar_index

    @pytest.mark.asyncio
    async def test_choch_and_bos_persist_via_db_adapter(self) -> None:
        db = FakeSMCDBAdapter()
        engine = SMCEngine(pivot_n=3, db_adapter=db)
        await _stream(engine, BULLISH_STAIRCASE, emit_events=False)

        # Realtime: close above HH@5 (120) -> BOS; then close below HL@7 (101) -> CHOCH.
        await engine.process_candle(
            _make_candle(bar_index=9, high="126", low="118", close="125"),
            emit_events=True,
        )
        await engine.process_candle(
            _make_candle(bar_index=10, high="96", low="88", close="95"),
            emit_events=True,
        )

        event_types = [e["event_type"] for e in db.events]
        assert event_types == ["bos", "choch"]
        assert db.events[0]["direction"] == "bullish"
        assert db.events[1]["direction"] == "bearish"

    @pytest.mark.asyncio
    async def test_bos_does_not_refire_for_same_reference(self) -> None:
        db = FakeSMCDBAdapter()
        engine = SMCEngine(pivot_n=3, db_adapter=db)
        await _stream(engine, BULLISH_STAIRCASE, emit_events=False)

        # Three consecutive closes above the same stale HH@5 (120): one BOS only.
        await engine.process_candle(
            _make_candle(bar_index=9, high="126", low="118", close="125"),
            emit_events=True,
        )
        await engine.process_candle(
            _make_candle(bar_index=10, high="128", low="120", close="127"),
            emit_events=True,
        )
        await engine.process_candle(
            _make_candle(bar_index=11, high="130", low="122", close="129"),
            emit_events=True,
        )
        assert [e["event_type"] for e in db.events] == ["bos"]

        # Pullback confirms new HH@11 (130); breaking it re-arms BOS.
        await engine.process_candle(
            _make_candle(bar_index=12, high="124", low="116", close="118"),
            emit_events=True,
        )
        await engine.process_candle(
            _make_candle(bar_index=13, high="136", low="128", close="135"),
            emit_events=True,
        )

        assert [e["event_type"] for e in db.events] == ["bos", "bos"]

    @pytest.mark.asyncio
    async def test_backfill_consumes_bos_suppression_slot(self) -> None:
        db = FakeSMCDBAdapter()
        engine = SMCEngine(pivot_n=3, db_adapter=db)
        backfill = [
            *BULLISH_STAIRCASE,
            # Break above HH@5 already happened during backfill.
            _make_candle(bar_index=9, high="126", low="118", close="125"),
        ]
        await _stream(engine, backfill, emit_events=False)

        # First realtime candle re-closes above the same stale HH: no event.
        await engine.process_candle(
            _make_candle(bar_index=10, high="128", low="120", close="127"),
            emit_events=True,
        )

        assert db.events == []

    @pytest.mark.asyncio
    async def test_same_bar_high_low_pivot_registers_both(self) -> None:
        engine = SMCEngine(pivot_n=3)
        candles = [
            _make_candle(bar_index=0, high="100", low="90"),
            _make_candle(bar_index=1, high="105", low="95"),
            _make_candle(bar_index=2, high="120", low="80"),  # wide outside bar
            _make_candle(bar_index=3, high="110", low="92"),
            _make_candle(bar_index=4, high="108", low="94"),
            _make_candle(bar_index=5, high="112", low="96"),
            _make_candle(bar_index=6, high="114", low="98"),
        ]
        await _stream(engine, candles, emit_events=False)

        pairs = _registered_pairs(engine._trackers[(SYMBOL, TF)])

        assert pairs.count((2, True)) == 1
        assert pairs.count((2, False)) == 1

    @pytest.mark.asyncio
    async def test_bar_index_gap_does_not_block_registration(self) -> None:
        engine = SMCEngine(pivot_n=3)
        candles = [
            _make_candle(bar_index=0, high="100", low="90"),
            _make_candle(bar_index=1, high="110", low="100"),
            _make_candle(bar_index=2, high="105", low="95"),
            _make_candle(bar_index=3, high="98", low="88"),
            _make_candle(bar_index=4, high="104", low="94"),
            _make_candle(bar_index=5, high="106", low="96"),
            # Feed outage: bars 6-11 never arrive.
            _make_candle(bar_index=12, high="112", low="97"),
            _make_candle(bar_index=13, high="118", low="104"),
            _make_candle(bar_index=14, high="113", low="103"),
        ]
        await _stream(engine, candles, emit_events=False)

        pairs = _registered_pairs(engine._trackers[(SYMBOL, TF)])

        assert (13, True) in pairs

    @pytest.mark.asyncio
    async def test_window_rollover_registers_each_pivot_once(self) -> None:
        engine = SMCEngine(pivot_n=3, max_candle_history=10)
        # Repeating 4-bar zigzag: high pivot at every bar%4==1, low at bar%4==3.
        shape = [("100", "90"), ("110", "100"), ("105", "95"), ("98", "88")]
        candles = [
            _make_candle(bar_index=k, high=shape[k % 4][0], low=shape[k % 4][1]) for k in range(30)
        ]
        await _stream(engine, candles, emit_events=False)

        pairs = _registered_pairs(engine._trackers[(SYMBOL, TF)])

        assert len(pairs) == len(set(pairs))
        assert len(pairs) > 2  # registration kept working across rollover

    @pytest.mark.asyncio
    async def test_zigzag_late_confirmation_registers_once(self) -> None:
        engine = SMCEngine(pivot_method=PivotMethod.ZIGZAG, pivot_n=3)
        warmup = [
            _make_candle(bar_index=k, high="100.5", low="99.5", close="100")
            for k in range(14)  # ATR warmup; ATR ~= 1 afterwards
        ]
        rally = [
            _make_candle(bar_index=14 + i, high=str(102 + 2 * i), low=str(100 + 2 * i))
            for i in range(5)  # rises to high 110 at bar 18
        ]
        reversal = [
            _make_candle(bar_index=19, high="108", low="106", close="107"),
            _make_candle(bar_index=20, high="104", low="102", close="103"),
            _make_candle(bar_index=21, high="100", low="98", close="99"),
        ]
        await _stream(engine, [*warmup, *rally, *reversal], emit_events=False)

        pairs = _registered_pairs(engine._trackers[(SYMBOL, TF)])

        high_pivots = [bar for bar, is_high in pairs if is_high and bar >= 14]
        assert high_pivots, "rally high pivot should register despite late confirmation"
        assert len(pairs) == len(set(pairs))
        assert max(bar for bar, _ in pairs) < 21  # confirmation always lags
