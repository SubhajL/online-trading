"""Mappers for transforming internal models to schema-compliant contract formats.

These mappers ensure that internal Pydantic models are correctly transformed
to match the JSONSchema contracts defined in contracts/jsonschema/*.
"""

from datetime import UTC, datetime
from typing import Any, ClassVar

from app.engine.models import Candle
from app.engine.smc_types import SMCEvent, Zone


def _format_datetime_iso(dt: datetime) -> str:
    """Format datetime to ISO8601 with Z suffix for UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    # Ensure we get the Z suffix format
    iso_str = dt.isoformat()
    if iso_str.endswith("+00:00"):
        iso_str = iso_str.replace("+00:00", "Z")
    return iso_str


class CandleEventMapper:
    """Maps internal Candle model to candles.v1 schema format."""

    SCHEMA_VERSION = "1.0.0"

    @staticmethod
    def to_schema(candle: Candle, venue: str, is_closed: bool = True) -> dict[str, Any]:
        """Transform Candle to candles.v1 schema-compliant dict.

        Args:
            candle: Internal Candle model
            venue: Exchange/venue name (e.g., "binance")
            is_closed: Whether the candle is closed

        Returns:
            Dict matching candles.v1.schema.json required fields
        """
        return {
            "version": CandleEventMapper.SCHEMA_VERSION,
            "venue": venue,
            "symbol": candle.symbol,
            "timeframe": candle.timeframe.value,
            "open_time": _format_datetime_iso(candle.open_time),
            "close_time": _format_datetime_iso(candle.close_time),
            "open": str(candle.open_price),
            "high": str(candle.high_price),
            "low": str(candle.low_price),
            "close": str(candle.close_price),
            "volume": str(candle.volume),
            "quote_volume": str(candle.quote_volume),
            "trades": candle.trades,
            "taker_buy_volume": str(candle.taker_buy_base_volume),
            "taker_buy_quote_volume": str(candle.taker_buy_quote_volume),
            "is_closed": is_closed,
        }


class SMCEventMapper:
    """Maps internal SMCEvent model to smc_events.v1 schema format."""

    SCHEMA_VERSION = "1.0.0"

    # Internal enum value -> schema value (exhaustive for schema-valid types)
    KIND_TO_SCHEMA: ClassVar[dict[str, str]] = {
        "CHOCH": "choch",
        "BOS": "bos",
        # STRUCTURE_UPDATE is not a schema event type, defaults to bos
    }

    STATE_TO_DIRECTION: ClassVar[dict[str, str]] = {
        "BULLISH": "bullish",
        "BEARISH": "bearish",
        # NEUTRAL is not a schema direction, defaults to bullish
    }

    @staticmethod
    def to_schema(
        event: SMCEvent,
        venue: str,
        symbol: str,
        timeframe: str,
    ) -> dict[str, Any]:
        """Transform SMCEvent to smc_events.v1 schema-compliant dict.

        Args:
            event: Internal SMCEvent model
            venue: Exchange/venue name (e.g., "binance")
            symbol: Trading pair symbol
            timeframe: Candle timeframe

        Returns:
            Dict matching smc_events.v1.schema.json required fields
        """
        # Get trigger pivot (always present)
        trigger = event.trigger_pivot

        # Get reference pivot (for broken pivot data)
        reference = event.reference_pivot or trigger

        return {
            "version": SMCEventMapper.SCHEMA_VERSION,
            "venue": venue,
            "symbol": symbol,
            "timeframe": timeframe,
            "event_time": _format_datetime_iso(event.timestamp),
            "event_type": SMCEventMapper.KIND_TO_SCHEMA.get(
                event.kind.value,
                "bos",
            ),
            "direction": SMCEventMapper.STATE_TO_DIRECTION.get(
                event.to_state.value,
                "bullish",
            ),
            "price_level": str(event.price),
            "previous_pivot_price": str(reference.price),
            "previous_pivot_time": _format_datetime_iso(reference.timestamp),
            "broken_pivot_price": str(trigger.price),
            "broken_pivot_time": _format_datetime_iso(trigger.timestamp),
        }


class ZoneEventMapper:
    """Maps internal Zone model to zones.v1 schema format."""

    SCHEMA_VERSION = "1.0.0"

    # Internal zone_type -> schema zone_type
    ZONE_TYPE_MAP: ClassVar[dict[str, str]] = {
        "FVG": "fair_value_gap",
        "OB_BULL": "order_block",
        "OB_BEAR": "order_block",
    }

    # Internal ZoneSide -> schema direction
    SIDE_TO_DIRECTION: ClassVar[dict[str, str]] = {
        "HIGH": "supply",
        "LOW": "demand",
    }

    @staticmethod
    def to_schema(
        zone: Zone,
        venue: str,
        is_active: bool = True,
        candle_count: int = 1,
    ) -> dict[str, Any]:
        """Transform Zone to zones.v1 schema-compliant dict.

        Args:
            zone: Internal Zone model
            venue: Exchange/venue name (e.g., "binance")
            is_active: Whether the zone is still active
            candle_count: Number of candles forming the zone

        Returns:
            Dict matching zones.v1.schema.json required fields
        """
        return {
            "version": ZoneEventMapper.SCHEMA_VERSION,
            "venue": venue,
            "symbol": zone.symbol,
            "timeframe": zone.timeframe.value,
            "zone_id": str(zone.zone_id),
            "zone_type": ZoneEventMapper.ZONE_TYPE_MAP.get(
                zone.zone_type,
                "order_block",
            ),
            "direction": ZoneEventMapper.SIDE_TO_DIRECTION.get(
                zone.side.value,
                "demand",
            ),
            "upper_bound": str(zone.top_price),
            "lower_bound": str(zone.bottom_price),
            "created_time": _format_datetime_iso(zone.created_at),
            "candle_count": candle_count,
            "strength": float(zone.strength),
            "touches": zone.touches,
            "is_active": is_active,
        }
