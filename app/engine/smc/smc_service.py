"""
Smart Money Concepts Service

Main service that orchestrates pivot detection, zone identification, and signal generation
for Smart Money Concepts analysis. Integrates with the event bus for real-time processing.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .pivot_detector import PivotDetector
from .zone_identifier import ZoneIdentifier
from ..types import (
    BaseEvent,
    Candle,
    CandleUpdateEvent,
    SMCSignal,
    SMCSignalEvent,
    TimeFrame,
    OrderSide,
    SupplyDemandZone,
    ZoneType,
    PivotPoint,
)
from ..bus import get_event_bus


logger = logging.getLogger(__name__)


class SMCService:
    """
    Smart Money Concepts service that provides:
    - Real-time pivot detection
    - Supply/demand zone identification
    - Order block detection
    - Fair value gap identification
    - SMC signal generation
    """

    def __init__(
        self,
        pivot_config: Dict = None,
        zone_config: Dict = None,
        signal_config: Dict = None,
    ):
        """
        Initialize SMC service

        Args:
            pivot_config: Configuration for pivot detector
            zone_config: Configuration for zone identifier
            signal_config: Configuration for signal generation
        """
        # Default configurations
        pivot_config = pivot_config or {
            "left_bars": 5,
            "right_bars": 5,
            "min_strength": 3,
            "max_strength": 10,
        }

        zone_config = zone_config or {
            "min_zone_strength": 3,
            "max_zones_per_type": 10,
            "zone_invalidation_touches": 3,
            "order_block_min_body_ratio": 0.6,
        }

        signal_config = signal_config or {
            "min_signal_confidence": 0.6,
            "max_signals_per_symbol": 5,
            "signal_timeout_hours": 24,
        }

        # Initialize components
        self.pivot_detector = PivotDetector(**pivot_config)
        self.zone_identifier = ZoneIdentifier(**zone_config)

        # Signal configuration
        self.min_signal_confidence = signal_config["min_signal_confidence"]
        self.max_signals_per_symbol = signal_config["max_signals_per_symbol"]
        self.signal_timeout_hours = signal_config["signal_timeout_hours"]

        # Candle storage for analysis (symbol -> timeframe -> candles)
        self._candle_history: Dict[str, Dict[TimeFrame, List[Candle]]] = {}
        self._max_candle_history = 200

        # Active signals
        self._active_signals: List[SMCSignal] = []

        self._event_bus = get_event_bus()
        self._running = False
        self._subscription_id: Optional[str] = None

        # Statistics
        self._signals_generated = 0
        self._zones_identified = 0
        self._pivots_detected = 0

        logger.info("SMCService initialized")

    async def start(self):
        """Start the SMC service"""
        if self._running:
            logger.warning("SMCService is already running")
            return

        self._running = True

        # Subscribe to candle update events
        self._subscription_id = await self._event_bus.subscribe(
            subscriber_id="smc_service",
            handler=self._handle_candle_update,
            event_types=[BaseEvent.EventType.CANDLE_UPDATE],
            priority=4,  # Lower priority than features, higher than decisions
        )

        logger.info("SMCService started and subscribed to candle updates")

    async def stop(self):
        """Stop the SMC service"""
        if not self._running:
            return

        self._running = False

        # Unsubscribe from events
        if self._subscription_id:
            await self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None

        logger.info("SMCService stopped")

    async def _handle_candle_update(self, event: CandleUpdateEvent):
        """Handle candle update events"""
        try:
            candle = event.candle
            symbol = candle.symbol
            timeframe = candle.timeframe

            # Store candle in history
            self._store_candle(candle)

            # Get recent candles for analysis
            recent_candles = self._get_recent_candles(symbol, timeframe, 50)

            if len(recent_candles) < 10:  # Need minimum data for analysis
                return

            # Detect pivots
            new_pivots = self.pivot_detector.add_candle(candle)
            if new_pivots:
                self._pivots_detected += len(new_pivots)
                logger.debug(
                    f"Detected {len(new_pivots)} new pivots for {symbol} {timeframe.value}"
                )

            # Update zone tests with current price
            self.zone_identifier.update_zone_tests(
                candle.close_price, symbol, timeframe
            )

            # Identify new zones if we have recent pivots
            recent_pivots = self.pivot_detector.get_recent_pivots(20)
            if recent_pivots:
                # Identify supply/demand zones
                new_sd_zones = self.zone_identifier.identify_supply_demand_zones(
                    recent_pivots, recent_candles
                )

                # Identify order blocks
                new_ob_zones = self.zone_identifier.identify_order_blocks(
                    recent_candles[-10:]
                )

                # Identify fair value gaps
                new_fvg_zones = self.zone_identifier.identify_fair_value_gaps(
                    recent_candles[-10:]
                )

                total_new_zones = (
                    len(new_sd_zones) + len(new_ob_zones) + len(new_fvg_zones)
                )
                if total_new_zones > 0:
                    self._zones_identified += total_new_zones
                    logger.debug(
                        f"Identified {total_new_zones} new zones for {symbol} {timeframe.value}"
                    )

            # Generate signals based on current price action and zones
            await self._generate_signals(symbol, timeframe, candle, recent_candles)

            # Clean up old signals
            self._cleanup_old_signals()

        except Exception as e:
            logger.error(f"Error handling candle update in SMC service: {e}")

    def _store_candle(self, candle: Candle):
        """Store candle in history for analysis"""
        symbol = candle.symbol
        timeframe = candle.timeframe

        if symbol not in self._candle_history:
            self._candle_history[symbol] = {}

        if timeframe not in self._candle_history[symbol]:
            self._candle_history[symbol][timeframe] = []

        candles = self._candle_history[symbol][timeframe]
        candles.append(candle)

        # Keep only recent candles
        if len(candles) > self._max_candle_history:
            candles.pop(0)

    def _get_recent_candles(
        self, symbol: str, timeframe: TimeFrame, count: int
    ) -> List[Candle]:
        """Get recent candles for a symbol and timeframe"""
        if symbol not in self._candle_history:
            return []

        if timeframe not in self._candle_history[symbol]:
            return []

        candles = self._candle_history[symbol][timeframe]
        return candles[-count:] if candles else []

    async def _generate_signals(
        self,
        symbol: str,
        timeframe: TimeFrame,
        current_candle: Candle,
        recent_candles: List[Candle],
    ):
        """Generate SMC signals based on current market conditions"""
        try:
            # Get nearby zones
            nearby_zones = self.zone_identifier.get_zones_near_price(
                symbol,
                timeframe,
                current_candle.close_price,
                distance_pct=0.005,  # 0.5%
            )

            for zone in nearby_zones:
                signal = await self._analyze_zone_for_signal(
                    zone, current_candle, recent_candles
                )
                if signal:
                    await self._publish_signal(signal)

            # Check for order block entries
            order_block_signal = await self._check_order_block_entry(
                symbol, timeframe, current_candle, recent_candles
            )
            if order_block_signal:
                await self._publish_signal(order_block_signal)

            # Check for fair value gap entries
            fvg_signal = await self._check_fvg_entry(
                symbol, timeframe, current_candle, recent_candles
            )
            if fvg_signal:
                await self._publish_signal(fvg_signal)

        except Exception as e:
            logger.error(f"Error generating SMC signals: {e}")

    async def _analyze_zone_for_signal(
        self,
        zone: SupplyDemandZone,
        current_candle: Candle,
        recent_candles: List[Candle],
    ) -> Optional[SMCSignal]:
        """Analyze a zone for potential trading signals"""
        try:
            # Check if price is entering the zone
            price = current_candle.close_price

            if not (zone.bottom_price <= price <= zone.top_price):
                return None

            # Determine signal direction based on zone type
            if zone.zone_type == ZoneType.DEMAND:
                direction = OrderSide.BUY
                entry_price = price
                stop_loss = zone.bottom_price * 0.998  # Slightly below zone
                take_profit = price * 1.02  # 2% profit target
                signal_type = "demand_zone_entry"

            elif zone.zone_type == ZoneType.SUPPLY:
                direction = OrderSide.SELL
                entry_price = price
                stop_loss = zone.top_price * 1.002  # Slightly above zone
                take_profit = price * 0.98  # 2% profit target
                signal_type = "supply_zone_entry"

            else:
                return None

            # Calculate confidence based on zone strength and market conditions
            confidence = self._calculate_zone_signal_confidence(
                zone, current_candle, recent_candles
            )

            if confidence < self.min_signal_confidence:
                return None

            # Create signal
            signal = SMCSignal(
                symbol=current_candle.symbol,
                timeframe=current_candle.timeframe,
                timestamp=current_candle.close_time,
                signal_type=signal_type,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=confidence,
                zone=zone,
                reasoning=f"{signal_type} at {zone.zone_type.value} zone with strength {zone.strength}",
            )

            return signal

        except Exception as e:
            logger.error(f"Error analyzing zone for signal: {e}")
            return None

    async def _check_order_block_entry(
        self,
        symbol: str,
        timeframe: TimeFrame,
        current_candle: Candle,
        recent_candles: List[Candle],
    ) -> Optional[SMCSignal]:
        """Check for order block entry opportunities"""
        try:
            # Get order block zones
            ob_zones = self.zone_identifier.get_active_zones(
                symbol, timeframe, ZoneType.ORDER_BLOCK_BULLISH
            ) + self.zone_identifier.get_active_zones(
                symbol, timeframe, ZoneType.ORDER_BLOCK_BEARISH
            )

            for zone in ob_zones:
                # Check if price is testing the order block
                if zone.bottom_price <= current_candle.low_price <= zone.top_price:
                    # Bullish order block - look for bounce
                    if zone.zone_type == ZoneType.ORDER_BLOCK_BULLISH:
                        if (
                            current_candle.close_price > current_candle.open_price
                        ):  # Bullish reaction
                            confidence = 0.75  # High confidence for order block

                            signal = SMCSignal(
                                symbol=symbol,
                                timeframe=timeframe,
                                timestamp=current_candle.close_time,
                                signal_type="order_block_entry",
                                direction=OrderSide.BUY,
                                entry_price=current_candle.close_price,
                                stop_loss=zone.bottom_price * 0.998,
                                take_profit=current_candle.close_price * 1.015,
                                confidence=confidence,
                                zone=zone,
                                reasoning="Bullish reaction at bullish order block",
                            )

                            return signal

                    # Bearish order block - look for rejection
                    elif zone.zone_type == ZoneType.ORDER_BLOCK_BEARISH:
                        if (
                            current_candle.close_price < current_candle.open_price
                        ):  # Bearish reaction
                            confidence = 0.75  # High confidence for order block

                            signal = SMCSignal(
                                symbol=symbol,
                                timeframe=timeframe,
                                timestamp=current_candle.close_time,
                                signal_type="order_block_entry",
                                direction=OrderSide.SELL,
                                entry_price=current_candle.close_price,
                                stop_loss=zone.top_price * 1.002,
                                take_profit=current_candle.close_price * 0.985,
                                confidence=confidence,
                                zone=zone,
                                reasoning="Bearish reaction at bearish order block",
                            )

                            return signal

        except Exception as e:
            logger.error(f"Error checking order block entry: {e}")

        return None

    async def _check_fvg_entry(
        self,
        symbol: str,
        timeframe: TimeFrame,
        current_candle: Candle,
        recent_candles: List[Candle],
    ) -> Optional[SMCSignal]:
        """Check for fair value gap entry opportunities"""
        try:
            # Get FVG zones
            fvg_zones = self.zone_identifier.get_active_zones(
                symbol, timeframe, ZoneType.FAIR_VALUE_GAP
            )

            for zone in fvg_zones:
                # Check if price is filling the gap
                if zone.bottom_price <= current_candle.close_price <= zone.top_price:
                    # Determine signal based on gap direction and current reaction
                    zone_mid = (zone.top_price + zone.bottom_price) / 2

                    if current_candle.close_price > zone_mid:
                        # Upper half of gap - potential continuation up
                        signal = SMCSignal(
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=current_candle.close_time,
                            signal_type="fair_value_gap",
                            direction=OrderSide.BUY,
                            entry_price=current_candle.close_price,
                            stop_loss=zone.bottom_price,
                            take_profit=current_candle.close_price * 1.01,
                            confidence=0.65,
                            zone=zone,
                            reasoning="FVG fill with bullish bias",
                        )

                        return signal

                    else:
                        # Lower half of gap - potential continuation down
                        signal = SMCSignal(
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=current_candle.close_time,
                            signal_type="fair_value_gap",
                            direction=OrderSide.SELL,
                            entry_price=current_candle.close_price,
                            stop_loss=zone.top_price,
                            take_profit=current_candle.close_price * 0.99,
                            confidence=0.65,
                            zone=zone,
                            reasoning="FVG fill with bearish bias",
                        )

                        return signal

        except Exception as e:
            logger.error(f"Error checking FVG entry: {e}")

        return None

    def _calculate_zone_signal_confidence(
        self,
        zone: SupplyDemandZone,
        current_candle: Candle,
        recent_candles: List[Candle],
    ) -> float:
        """Calculate confidence for a zone-based signal"""
        try:
            confidence = 0.5  # Base confidence

            # Zone strength factor
            strength_factor = min(zone.strength / 10.0, 0.3)
            confidence += strength_factor

            # Touch count factor (fewer touches = higher confidence)
            touch_factor = max(0, 0.2 - (zone.touches * 0.05))
            confidence += touch_factor

            # Volume factor
            if len(recent_candles) >= 5:
                avg_volume = sum(c.volume for c in recent_candles[-5:]) / 5
                volume_ratio = (
                    float(current_candle.volume / avg_volume) if avg_volume > 0 else 1
                )
                volume_factor = min(volume_ratio * 0.1, 0.15)
                confidence += volume_factor

            # Zone age factor (newer zones might be more relevant)
            age_hours = (
                current_candle.close_time - zone.created_at
            ).total_seconds() / 3600
            age_factor = max(0, 0.1 - (age_hours * 0.001))
            confidence += age_factor

            return min(1.0, confidence)

        except Exception as e:
            logger.error(f"Error calculating zone signal confidence: {e}")
            return 0.5

    async def _publish_signal(self, signal: SMCSignal):
        """Publish an SMC signal event"""
        try:
            # Check if we already have too many signals for this symbol
            symbol_signals = [
                s for s in self._active_signals if s.symbol == signal.symbol
            ]
            if len(symbol_signals) >= self.max_signals_per_symbol:
                return

            # Add to active signals
            self._active_signals.append(signal)

            # Create and publish event
            event = SMCSignalEvent(
                timestamp=datetime.utcnow(),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                signal=signal,
            )

            await self._event_bus.publish(event, priority=6)

            self._signals_generated += 1
            logger.info(
                f"Published SMC signal: {signal.signal_type} {signal.direction.value} "
                f"for {signal.symbol} at {signal.entry_price}"
            )

        except Exception as e:
            logger.error(f"Error publishing SMC signal: {e}")

    def _cleanup_old_signals(self):
        """Remove old signals that have expired"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=self.signal_timeout_hours)
            self._active_signals = [
                signal
                for signal in self._active_signals
                if signal.timestamp > cutoff_time
            ]

        except Exception as e:
            logger.error(f"Error cleaning up old signals: {e}")

    def get_active_signals(
        self, symbol: Optional[str] = None, timeframe: Optional[TimeFrame] = None
    ) -> List[SMCSignal]:
        """Get active SMC signals"""
        signals = self._active_signals

        if symbol:
            signals = [s for s in signals if s.symbol == symbol]

        if timeframe:
            signals = [s for s in signals if s.timeframe == timeframe]

        return signals

    def get_zones(
        self, symbol: str, timeframe: TimeFrame, zone_type: Optional[ZoneType] = None
    ) -> List[SupplyDemandZone]:
        """Get zones for a symbol and timeframe"""
        return self.zone_identifier.get_active_zones(symbol, timeframe, zone_type)

    def get_pivots(self, count: int = 20) -> List[PivotPoint]:
        """Get recent pivot points"""
        return self.pivot_detector.get_recent_pivots(count)

    async def health_check(self) -> Dict:
        """Get health status of the SMC service"""
        pivot_stats = self.pivot_detector.get_statistics()
        zone_stats = self.zone_identifier.get_statistics()

        return {
            "running": self._running,
            "subscription_active": self._subscription_id is not None,
            "signals_generated": self._signals_generated,
            "zones_identified": self._zones_identified,
            "pivots_detected": self._pivots_detected,
            "active_signals": len(self._active_signals),
            "pivot_statistics": pivot_stats,
            "zone_statistics": zone_stats,
            "tracked_symbols": len(self._candle_history),
        }
