from __future__ import annotations

from decimal import Decimal
import logging
from typing import Any

from app.engine.ingest.bar_index import bar_index_from_open_time

from ..bus import get_event_bus
from ..contracts.mappers import SMCEventMapper
from ..models import Candle, CandleUpdateEvent, EventType, TimeFrame, is_realtime_candle_event
from ..smc_types import StructureState, StructureTracker, Zone
from .atr import atr
from .events import create_smc_event, create_zone_event, publish_events
from .numutils import to_float_ohlc_arrays
from .pivots import PivotMethod, detect_n_bar_pivots, detect_zigzag_pivots
from .structure import detect_bos, detect_choch, get_key_levels, register_new_pivots
from .zones import detect_fair_value_gap, detect_order_block, expire_old_zones

logger = logging.getLogger(__name__)


class SMCEngine:
    def __init__(
        self,
        pivot_method: PivotMethod = PivotMethod.N_BAR,
        pivot_n: int = 3,
        atr_reversal_factor: float = 2.0,
        zone_expiry_bars: int = 100,
        max_zones_per_symbol: int = 50,
        max_candle_history: int = 200,
        db_adapter: Any | None = None,
    ):
        self.pivot_method = pivot_method
        self.pivot_n = pivot_n
        self.atr_reversal_factor = atr_reversal_factor
        self.zone_expiry_bars = zone_expiry_bars
        self.max_zones_per_symbol = max_zones_per_symbol
        self.max_candle_history = max_candle_history
        self._db_adapter = db_adapter

        # State tracking per symbol/timeframe
        self._trackers: dict[tuple[str, TimeFrame], StructureTracker] = {}
        self._candle_history: dict[tuple[str, TimeFrame], list[Candle]] = {}
        self._zones: dict[tuple[str, TimeFrame], list[Zone]] = {}
        self._atr_values: dict[tuple[str, TimeFrame], Decimal] = {}

        self._event_bus = get_event_bus()
        self._subscription_id: str | None = None
        self._running = False

        logger.info(
            f"SMCEngine initialized with method={pivot_method.value}, n={pivot_n}",
        )

    async def start(self) -> None:
        if self._running:
            logger.warning("SMCEngine is already running")
            return

        self._running = True
        self._subscription_id = await self._event_bus.subscribe(
            subscriber_id="smc_engine",
            handler=self._handle_candle_update,
            event_types=[EventType.CANDLE_UPDATE],
            priority=4,
            serialize_by_key=True,
        )

        logger.info("SMCEngine started")

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        if self._subscription_id:
            await self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None

        logger.info("SMCEngine stopped")

    async def process_candle(self, candle: Candle, *, emit_events: bool) -> None:
        if candle.bar_index is None:
            candle.bar_index = bar_index_from_open_time(candle.open_time, candle.timeframe)
        if candle.bar_index is None:
            # Unsupported timeframe (e.g. month-based); skip SMC processing safely.
            return

        key = (candle.symbol, candle.timeframe)

        # Initialize state if needed
        if key not in self._trackers:
            self._initialize_state(key)

        # Store candle
        self._store_candle(key, candle)

        # Get current state
        tracker = self._trackers[key]
        candles = self._candle_history[key]

        if len(candles) < self.pivot_n:
            return  # Need minimum candles for pivot detection

        events_to_publish: list[Any] = []

        # 1. Detect pivots
        pivots = self._detect_pivots(candles)

        # 2. Register newly confirmed pivots (confirmation lags the pivot bar,
        # so matching against the current bar_index would register nothing).
        newly_registered = register_new_pivots(tracker, pivots)
        if newly_registered:
            logger.debug(
                "Registered %d new pivot(s) for %s",
                len(newly_registered),
                key,
            )

        # 3. Check for CHOCH/BOS
        close_price = candle.close_price
        close_bar_index = candle.bar_index
        timestamp = candle.close_time

        choch_event = detect_choch(tracker, close_price, close_bar_index, timestamp)
        if choch_event:
            tracker.state = choch_event.to_state  # Update state on CHOCH
            if emit_events:
                await self._persist_smc_event(
                    choch_event,
                    candle.venue,
                    candle.symbol,
                    candle.timeframe,
                )
                key_levels = get_key_levels(tracker)
                event = create_smc_event(
                    candle.venue,
                    candle.symbol,
                    candle.timeframe,
                    choch_event,
                    tracker.state,
                    key_levels,
                )
                events_to_publish.append(event)

            # Detect order block on CHOCH if we have previous candles
            if len(candles) >= 2 and choch_event.reference_pivot:
                # Find last opposite candle before the CHOCH
                for i in range(len(candles) - 2, -1, -1):
                    c = candles[i]
                    if choch_event.to_state == StructureState.BULLISH:
                        # Look for last bearish candle
                        if c.close_price < c.open_price:
                            ob_zone = detect_order_block(
                                c,
                                choch_event,
                                candle.timeframe,
                            )
                            if ob_zone:
                                self._add_zone(key, ob_zone)
                                if emit_events:
                                    zone_event = create_zone_event(
                                        candle.venue,
                                        ob_zone,
                                        "created",
                                    )
                                    events_to_publish.append(zone_event)
                                break
                    # Look for last bullish candle
                    elif c.close_price > c.open_price:
                        ob_zone = detect_order_block(
                            c,
                            choch_event,
                            candle.timeframe,
                        )
                        if ob_zone:
                            self._add_zone(key, ob_zone)
                            if emit_events:
                                zone_event = create_zone_event(
                                    candle.venue,
                                    ob_zone,
                                    "created",
                                )
                                events_to_publish.append(zone_event)
                            break

        bos_event = detect_bos(tracker, close_price, close_bar_index, timestamp)
        if bos_event:
            if emit_events:
                await self._persist_smc_event(
                    bos_event,
                    candle.venue,
                    candle.symbol,
                    candle.timeframe,
                )
                key_levels = get_key_levels(tracker)
                event = create_smc_event(
                    candle.venue,
                    candle.symbol,
                    candle.timeframe,
                    bos_event,
                    tracker.state,
                    key_levels,
                )
                events_to_publish.append(event)

            # Detect order block on BOS
            if len(candles) >= 2:
                last_opposite = candles[-2]
                ob_zone = detect_order_block(last_opposite, bos_event, candle.timeframe)
                if ob_zone:
                    self._add_zone(key, ob_zone)
                    if emit_events:
                        zone_event = create_zone_event(candle.venue, ob_zone, "created")
                        events_to_publish.append(zone_event)

        # 4. Detect FVG zones
        if len(candles) >= 3:
            recent_candles = candles[-3:]
            fvg_zone = detect_fair_value_gap(
                recent_candles,
                candle.symbol,
                candle.timeframe,
            )
            if fvg_zone:
                self._add_zone(key, fvg_zone)
                if emit_events:
                    zone_event = create_zone_event(candle.venue, fvg_zone, "created")
                    events_to_publish.append(zone_event)

        # 5. Update zone touches
        zones = self._zones.get(key, [])
        for zone in zones:
            if zone.bottom_price <= close_price <= zone.top_price:
                zone.touches += 1
                if zone.touches == 1:  # First touch
                    if emit_events:
                        zone_event = create_zone_event(candle.venue, zone, "touched")
                        events_to_publish.append(zone_event)

        # 6. Expire old zones
        if zones:
            active_zones = expire_old_zones(zones, candle.bar_index)
            expired_count = len(zones) - len(active_zones)
            if expired_count > 0:
                self._zones[key] = active_zones
                logger.debug(f"Expired {expired_count} zones for {key}")

        # 7. Publish all events
        if emit_events and events_to_publish:
            await publish_events(events_to_publish)

    async def _persist_smc_event(
        self,
        smc_event: Any,
        venue: str,
        symbol: str,
        timeframe: TimeFrame,
    ) -> None:
        if self._db_adapter is None:
            return
        try:
            payload = SMCEventMapper.to_schema(
                smc_event,
                venue,
                symbol,
                timeframe.value,
            )
            await self._db_adapter.insert_smc_event_v1(payload)
        except Exception:
            logger.exception("Failed to persist SMC event to DB (non-fatal)")

    async def _handle_candle_update(self, event: CandleUpdateEvent) -> None:
        try:
            await self.process_candle(
                event.candle,
                emit_events=is_realtime_candle_event(event.origin),
            )
        except Exception:
            logger.exception("Error processing candle in SMC engine")

    def _initialize_state(self, key: tuple[str, TimeFrame]) -> None:
        symbol, timeframe = key
        self._trackers[key] = StructureTracker(symbol=symbol, timeframe=timeframe)
        self._candle_history[key] = []
        self._zones[key] = []
        self._atr_values[key] = Decimal(0)

    def _store_candle(self, key: tuple[str, TimeFrame], candle: Candle) -> None:
        candles = self._candle_history[key]
        candles.append(candle)

        if len(candles) > self.max_candle_history:
            candles.pop(0)

        # Update ATR using vectorized numpy compute; store as Decimal with boundary conversion
        if len(candles) >= 14:
            recent = candles[-14:]
            _o, h, low, c = to_float_ohlc_arrays(recent)
            atr_series = atr(h, low, c, period=14)
            latest = atr_series[-1]
            # Convert back to Decimal with sufficient precision at boundary
            self._atr_values[key] = Decimal(str(latest))

    def _detect_pivots(self, candles: list[Candle]) -> list[Any]:
        if self.pivot_method == PivotMethod.N_BAR:
            return detect_n_bar_pivots(candles, n=self.pivot_n)
        # ZIGZAG
        atr = self._atr_values.get(
            (candles[0].symbol, candles[0].timeframe),
            Decimal("1.0"),
        )
        return detect_zigzag_pivots(
            candles,
            atr,
            min_reversal_factor=self.atr_reversal_factor,
        )

    def _add_zone(self, key: tuple[str, TimeFrame], zone: Zone) -> None:
        zones = self._zones[key]
        zones.append(zone)

        # Limit zones per symbol
        if len(zones) > self.max_zones_per_symbol:
            zones.sort(key=lambda z: z.created_bar_index)
            self._zones[key] = zones[-self.max_zones_per_symbol :]

    def get_structure_state(
        self,
        symbol: str,
        timeframe: TimeFrame,
    ) -> StructureState | None:
        key = (symbol, timeframe)
        tracker = self._trackers.get(key)
        return tracker.state if tracker else None

    def get_zones(
        self,
        symbol: str,
        timeframe: TimeFrame,
        zone_type: str | None = None,
    ) -> list[Zone]:
        key = (symbol, timeframe)
        zones = self._zones.get(key, [])

        if zone_type:
            zones = [z for z in zones if z.zone_type == zone_type]

        return zones

    def cleanup_expired_data(self) -> None:
        for key in list(self._trackers.keys()):
            tracker = self._trackers[key]
            if len(tracker.pivots) > tracker.max_pivots:
                tracker.pivots = tracker.pivots[-tracker.max_pivots :]
