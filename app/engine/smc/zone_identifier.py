"""
Zone Identifier

Identifies supply/demand zones, order blocks, and fair value gaps for Smart Money Concepts.
Uses pivot points and price action analysis to detect institutional trading zones.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict
from uuid import uuid4

from .pivot_detector import PivotDetector
from ..types import (
    Candle, PivotPoint, SupplyDemandZone, ZoneType, TimeFrame
)


logger = logging.getLogger(__name__)


class ZoneIdentifier:
    """
    Identifies Smart Money Concepts zones including:
    - Supply and Demand zones
    - Order blocks (bullish/bearish)
    - Fair Value Gaps (FVG)
    - Liquidity zones
    """

    def __init__(
        self,
        min_zone_strength: int = 3,
        max_zones_per_type: int = 10,
        zone_invalidation_touches: int = 3,
        order_block_min_body_ratio: float = 0.6
    ):
        """
        Initialize zone identifier

        Args:
            min_zone_strength: Minimum strength required for zone creation
            max_zones_per_type: Maximum number of zones to track per type
            zone_invalidation_touches: Number of touches before zone becomes invalid
            order_block_min_body_ratio: Minimum body ratio for order block identification
        """
        self.min_zone_strength = min_zone_strength
        self.max_zones_per_type = max_zones_per_type
        self.zone_invalidation_touches = zone_invalidation_touches
        self.order_block_min_body_ratio = order_block_min_body_ratio

        # Active zones by type
        self._zones: Dict[ZoneType, List[SupplyDemandZone]] = {
            ZoneType.SUPPLY: [],
            ZoneType.DEMAND: [],
            ZoneType.ORDER_BLOCK_BULLISH: [],
            ZoneType.ORDER_BLOCK_BEARISH: [],
            ZoneType.FAIR_VALUE_GAP: []
        }

        # Historical zones (for analysis)
        self._historical_zones: List[SupplyDemandZone] = []

        logger.info(f"ZoneIdentifier initialized with min_strength={min_zone_strength}")

    def identify_supply_demand_zones(
        self,
        pivots: List[PivotPoint],
        recent_candles: List[Candle]
    ) -> List[SupplyDemandZone]:
        """
        Identify supply and demand zones based on pivot points

        Args:
            pivots: List of recent pivot points
            recent_candles: Recent candle data for volume analysis

        Returns:
            List of newly identified zones
        """
        new_zones = []

        try:
            # Group pivots by type
            swing_highs = [p for p in pivots if p.is_high]
            swing_lows = [p for p in pivots if not p.is_high]

            # Identify supply zones from swing highs
            for pivot in swing_highs:
                if pivot.strength >= self.min_zone_strength:
                    zone = self._create_supply_zone(pivot, recent_candles)
                    if zone and not self._zone_exists(zone):
                        new_zones.append(zone)
                        self._add_zone(zone)

            # Identify demand zones from swing lows
            for pivot in swing_lows:
                if pivot.strength >= self.min_zone_strength:
                    zone = self._create_demand_zone(pivot, recent_candles)
                    if zone and not self._zone_exists(zone):
                        new_zones.append(zone)
                        self._add_zone(zone)

        except Exception as e:
            logger.error(f"Error identifying supply/demand zones: {e}")

        return new_zones

    def identify_order_blocks(self, candles: List[Candle]) -> List[SupplyDemandZone]:
        """
        Identify order blocks from candle patterns

        Args:
            candles: List of recent candles

        Returns:
            List of identified order blocks
        """
        new_zones = []

        try:
            if len(candles) < 3:
                return new_zones

            for i in range(1, len(candles) - 1):
                current = candles[i]
                prev_candle = candles[i - 1]
                next_candle = candles[i + 1]

                # Check for bullish order block
                bullish_ob = self._identify_bullish_order_block(prev_candle, current, next_candle)
                if bullish_ob:
                    new_zones.append(bullish_ob)
                    self._add_zone(bullish_ob)

                # Check for bearish order block
                bearish_ob = self._identify_bearish_order_block(prev_candle, current, next_candle)
                if bearish_ob:
                    new_zones.append(bearish_ob)
                    self._add_zone(bearish_ob)

        except Exception as e:
            logger.error(f"Error identifying order blocks: {e}")

        return new_zones

    def identify_fair_value_gaps(self, candles: List[Candle]) -> List[SupplyDemandZone]:
        """
        Identify Fair Value Gaps (FVG) in price action

        Args:
            candles: List of recent candles

        Returns:
            List of identified FVGs
        """
        new_zones = []

        try:
            if len(candles) < 3:
                return new_zones

            for i in range(1, len(candles) - 1):
                prev_candle = candles[i - 1]
                current = candles[i]
                next_candle = candles[i + 1]

                # Check for bullish FVG (gap up)
                if (prev_candle.high_price < next_candle.low_price and
                    current.close_price > current.open_price):  # Current candle is bullish

                    fvg = SupplyDemandZone(
                        symbol=current.symbol,
                        timeframe=current.timeframe,
                        zone_type=ZoneType.FAIR_VALUE_GAP,
                        top_price=next_candle.low_price,
                        bottom_price=prev_candle.high_price,
                        created_at=current.open_time,
                        strength=self._calculate_fvg_strength(prev_candle, current, next_candle),
                        volume_profile=current.volume
                    )

                    if not self._zone_exists(fvg):
                        new_zones.append(fvg)
                        self._add_zone(fvg)

                # Check for bearish FVG (gap down)
                elif (prev_candle.low_price > next_candle.high_price and
                      current.close_price < current.open_price):  # Current candle is bearish

                    fvg = SupplyDemandZone(
                        symbol=current.symbol,
                        timeframe=current.timeframe,
                        zone_type=ZoneType.FAIR_VALUE_GAP,
                        top_price=prev_candle.low_price,
                        bottom_price=next_candle.high_price,
                        created_at=current.open_time,
                        strength=self._calculate_fvg_strength(prev_candle, current, next_candle),
                        volume_profile=current.volume
                    )

                    if not self._zone_exists(fvg):
                        new_zones.append(fvg)
                        self._add_zone(fvg)

        except Exception as e:
            logger.error(f"Error identifying fair value gaps: {e}")

        return new_zones

    def _create_supply_zone(
        self,
        pivot: PivotPoint,
        recent_candles: List[Candle]
    ) -> Optional[SupplyDemandZone]:
        """Create a supply zone from a swing high pivot"""
        try:
            # Find the candle that created this high
            pivot_candle = None
            for candle in recent_candles:
                if (candle.open_time <= pivot.timestamp and
                    abs(candle.high_price - pivot.price) / pivot.price < 0.001):
                    pivot_candle = candle
                    break

            if not pivot_candle:
                return None

            # Supply zone extends from the body to the high
            body_top = max(pivot_candle.open_price, pivot_candle.close_price)
            zone_top = pivot_candle.high_price
            zone_bottom = body_top

            # Calculate volume profile
            volume_profile = self._calculate_zone_volume_profile(
                pivot.timestamp, recent_candles, zone_bottom, zone_top
            )

            return SupplyDemandZone(
                symbol=pivot.symbol,
                timeframe=pivot.timeframe,
                zone_type=ZoneType.SUPPLY,
                top_price=zone_top,
                bottom_price=zone_bottom,
                created_at=pivot.timestamp,
                strength=pivot.strength,
                volume_profile=volume_profile
            )

        except Exception as e:
            logger.error(f"Error creating supply zone: {e}")
            return None

    def _create_demand_zone(
        self,
        pivot: PivotPoint,
        recent_candles: List[Candle]
    ) -> Optional[SupplyDemandZone]:
        """Create a demand zone from a swing low pivot"""
        try:
            # Find the candle that created this low
            pivot_candle = None
            for candle in recent_candles:
                if (candle.open_time <= pivot.timestamp and
                    abs(candle.low_price - pivot.price) / pivot.price < 0.001):
                    pivot_candle = candle
                    break

            if not pivot_candle:
                return None

            # Demand zone extends from the low to the body
            body_bottom = min(pivot_candle.open_price, pivot_candle.close_price)
            zone_top = body_bottom
            zone_bottom = pivot_candle.low_price

            # Calculate volume profile
            volume_profile = self._calculate_zone_volume_profile(
                pivot.timestamp, recent_candles, zone_bottom, zone_top
            )

            return SupplyDemandZone(
                symbol=pivot.symbol,
                timeframe=pivot.timeframe,
                zone_type=ZoneType.DEMAND,
                top_price=zone_top,
                bottom_price=zone_bottom,
                created_at=pivot.timestamp,
                strength=pivot.strength,
                volume_profile=volume_profile
            )

        except Exception as e:
            logger.error(f"Error creating demand zone: {e}")
            return None

    def _identify_bullish_order_block(
        self,
        prev_candle: Candle,
        current: Candle,
        next_candle: Candle
    ) -> Optional[SupplyDemandZone]:
        """Identify bullish order block pattern"""
        try:
            # Bullish order block criteria:
            # 1. Previous candle is bearish with significant body
            # 2. Current candle breaks structure upward
            # 3. Next candle confirms the move

            prev_body_ratio = abs(prev_candle.close_price - prev_candle.open_price) / (
                prev_candle.high_price - prev_candle.low_price
            )

            if (prev_candle.close_price < prev_candle.open_price and  # Bearish
                prev_body_ratio >= self.order_block_min_body_ratio and  # Significant body
                current.close_price > prev_candle.high_price and  # Break structure
                next_candle.close_price > current.close_price):  # Confirmation

                # Order block zone is the body of the bearish candle
                zone_top = prev_candle.open_price
                zone_bottom = prev_candle.close_price

                return SupplyDemandZone(
                    symbol=current.symbol,
                    timeframe=current.timeframe,
                    zone_type=ZoneType.ORDER_BLOCK_BULLISH,
                    top_price=zone_top,
                    bottom_price=zone_bottom,
                    created_at=current.open_time,
                    strength=5,  # Default strength for order blocks
                    volume_profile=current.volume
                )

        except Exception as e:
            logger.error(f"Error identifying bullish order block: {e}")

        return None

    def _identify_bearish_order_block(
        self,
        prev_candle: Candle,
        current: Candle,
        next_candle: Candle
    ) -> Optional[SupplyDemandZone]:
        """Identify bearish order block pattern"""
        try:
            # Bearish order block criteria:
            # 1. Previous candle is bullish with significant body
            # 2. Current candle breaks structure downward
            # 3. Next candle confirms the move

            prev_body_ratio = abs(prev_candle.close_price - prev_candle.open_price) / (
                prev_candle.high_price - prev_candle.low_price
            )

            if (prev_candle.close_price > prev_candle.open_price and  # Bullish
                prev_body_ratio >= self.order_block_min_body_ratio and  # Significant body
                current.close_price < prev_candle.low_price and  # Break structure
                next_candle.close_price < current.close_price):  # Confirmation

                # Order block zone is the body of the bullish candle
                zone_top = prev_candle.close_price
                zone_bottom = prev_candle.open_price

                return SupplyDemandZone(
                    symbol=current.symbol,
                    timeframe=current.timeframe,
                    zone_type=ZoneType.ORDER_BLOCK_BEARISH,
                    top_price=zone_top,
                    bottom_price=zone_bottom,
                    created_at=current.open_time,
                    strength=5,  # Default strength for order blocks
                    volume_profile=current.volume
                )

        except Exception as e:
            logger.error(f"Error identifying bearish order block: {e}")

        return None

    def _calculate_fvg_strength(
        self,
        prev_candle: Candle,
        current: Candle,
        next_candle: Candle
    ) -> int:
        """Calculate strength of a Fair Value Gap"""
        try:
            # Base strength on gap size and volume
            gap_size = abs(prev_candle.high_price - next_candle.low_price) if prev_candle.high_price < next_candle.low_price else abs(prev_candle.low_price - next_candle.high_price)
            avg_price = (prev_candle.close_price + current.close_price + next_candle.close_price) / 3
            gap_percentage = gap_size / avg_price

            # Volume strength
            avg_volume = (prev_candle.volume + current.volume + next_candle.volume) / 3
            volume_ratio = float(current.volume / avg_volume) if avg_volume > 0 else 1

            # Calculate strength (1-10)
            strength = min(10, max(1, int(gap_percentage * 1000) + int(volume_ratio)))
            return strength

        except Exception as e:
            logger.error(f"Error calculating FVG strength: {e}")
            return 3

    def _calculate_zone_volume_profile(
        self,
        zone_time: datetime,
        candles: List[Candle],
        bottom_price: Decimal,
        top_price: Decimal
    ) -> Decimal:
        """Calculate volume profile for a zone"""
        try:
            # Find candles within the zone time range
            zone_candles = [
                c for c in candles
                if abs((c.open_time - zone_time).total_seconds()) < 3600  # Within 1 hour
            ]

            if not zone_candles:
                return Decimal('0')

            # Calculate average volume for candles that interacted with the zone
            interacting_volumes = []
            for candle in zone_candles:
                if (candle.low_price <= top_price and candle.high_price >= bottom_price):
                    interacting_volumes.append(candle.volume)

            return sum(interacting_volumes) / len(interacting_volumes) if interacting_volumes else Decimal('0')

        except Exception as e:
            logger.error(f"Error calculating zone volume profile: {e}")
            return Decimal('0')

    def _zone_exists(self, new_zone: SupplyDemandZone) -> bool:
        """Check if a similar zone already exists"""
        existing_zones = self._zones[new_zone.zone_type]

        for zone in existing_zones:
            if (zone.symbol == new_zone.symbol and
                zone.timeframe == new_zone.timeframe):

                # Check for price overlap
                overlap_top = min(zone.top_price, new_zone.top_price)
                overlap_bottom = max(zone.bottom_price, new_zone.bottom_price)

                if overlap_top > overlap_bottom:  # There is overlap
                    overlap_ratio = (overlap_top - overlap_bottom) / min(
                        zone.top_price - zone.bottom_price,
                        new_zone.top_price - new_zone.bottom_price
                    )

                    if overlap_ratio > 0.5:  # 50% overlap threshold
                        return True

        return False

    def _add_zone(self, zone: SupplyDemandZone):
        """Add a zone to the appropriate collection"""
        zones = self._zones[zone.zone_type]
        zones.append(zone)

        # Keep only the most recent zones
        if len(zones) > self.max_zones_per_type:
            # Remove oldest zone
            oldest = min(zones, key=lambda z: z.created_at)
            zones.remove(oldest)
            self._historical_zones.append(oldest)

    def update_zone_tests(self, current_price: Decimal, symbol: str, timeframe: TimeFrame):
        """Update zone touch counts and invalidate if necessary"""
        try:
            for zone_type, zones in self._zones.items():
                zones_to_remove = []

                for zone in zones:
                    if zone.symbol != symbol or zone.timeframe != timeframe:
                        continue

                    # Check if price is testing the zone
                    if zone.bottom_price <= current_price <= zone.top_price:
                        zone.touches += 1
                        zone.tested_at = datetime.utcnow()

                        # Invalidate zone if touched too many times
                        if zone.touches >= self.zone_invalidation_touches:
                            zone.is_active = False
                            zones_to_remove.append(zone)

                # Remove invalidated zones
                for zone in zones_to_remove:
                    zones.remove(zone)
                    self._historical_zones.append(zone)

        except Exception as e:
            logger.error(f"Error updating zone tests: {e}")

    def get_active_zones(
        self,
        symbol: str,
        timeframe: TimeFrame,
        zone_type: Optional[ZoneType] = None
    ) -> List[SupplyDemandZone]:
        """Get active zones for a symbol and timeframe"""
        result = []

        zone_types = [zone_type] if zone_type else list(ZoneType)

        for zt in zone_types:
            zones = self._zones.get(zt, [])
            filtered_zones = [
                zone for zone in zones
                if (zone.symbol == symbol and
                    zone.timeframe == timeframe and
                    zone.is_active)
            ]
            result.extend(filtered_zones)

        return result

    def get_zones_near_price(
        self,
        symbol: str,
        timeframe: TimeFrame,
        price: Decimal,
        distance_pct: float = 0.02
    ) -> List[SupplyDemandZone]:
        """Get zones within a percentage distance of current price"""
        active_zones = self.get_active_zones(symbol, timeframe)
        nearby_zones = []

        for zone in active_zones:
            zone_center = (zone.top_price + zone.bottom_price) / 2
            distance = abs(price - zone_center) / price

            if distance <= distance_pct:
                nearby_zones.append(zone)

        return nearby_zones

    def clear_zones(self, symbol: Optional[str] = None, timeframe: Optional[TimeFrame] = None):
        """Clear zones for specific symbol/timeframe or all zones"""
        if symbol is None and timeframe is None:
            # Clear all zones
            for zone_type in self._zones:
                self._zones[zone_type].clear()
            self._historical_zones.clear()
        else:
            # Clear specific zones
            for zone_type in self._zones:
                zones_to_remove = []
                for zone in self._zones[zone_type]:
                    if ((symbol is None or zone.symbol == symbol) and
                        (timeframe is None or zone.timeframe == timeframe)):
                        zones_to_remove.append(zone)

                for zone in zones_to_remove:
                    self._zones[zone_type].remove(zone)

        logger.info(f"Cleared zones for {symbol or 'ALL'} {timeframe or 'ALL'}")

    def get_statistics(self) -> Dict:
        """Get zone identification statistics"""
        total_active = sum(len(zones) for zones in self._zones.values())

        return {
            "active_zones": {
                zone_type.value: len(zones)
                for zone_type, zones in self._zones.items()
            },
            "total_active": total_active,
            "historical_zones": len(self._historical_zones),
            "configuration": {
                "min_zone_strength": self.min_zone_strength,
                "max_zones_per_type": self.max_zones_per_type,
                "zone_invalidation_touches": self.zone_invalidation_touches,
                "order_block_min_body_ratio": self.order_block_min_body_ratio
            }
        }