from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import Any, TypeAlias

from ...smc_types import Pivot, SMCEvent, Zone

KyselyDatabase: TypeAlias = Any
Transaction: TypeAlias = Any

logger = logging.getLogger(__name__)


async def write_swing_points(
    db: KyselyDatabase | Transaction,
    symbol: str,
    timeframe: str,
    pivots: list[Pivot],
) -> None:
    if not pivots:
        return

    try:
        values = []
        for pivot in pivots:
            values.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": pivot.timestamp,
                    "price": str(pivot.price),
                    "is_high": pivot.is_high,
                    "strength": pivot.strength,
                    "bar_index": pivot.bar_index,
                },
            )

        await db.insert_into("swing_points").values(values).execute()
        logger.debug(f"Wrote {len(pivots)} swing points for {symbol} {timeframe}")

    except Exception as e:
        logger.error(f"Failed to write swing points: {e}")
        raise


async def write_smc_events(
    db: KyselyDatabase | Transaction,
    symbol: str,
    timeframe: str,
    events: list[SMCEvent],
) -> None:
    if not events:
        return

    try:
        values = []
        for event in events:
            values.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "event_type": event.kind.value,
                    "timestamp": event.timestamp,
                    "price": str(event.price),
                    "from_state": event.from_state,
                    "to_state": event.to_state,
                    "reference_price": str(event.reference_pivot.price)
                    if event.reference_pivot
                    else None,
                    "strength": str(event.strength),
                    "metadata": json.dumps(
                        {
                            "trigger_bar_index": event.trigger_pivot.bar_index
                            if event.trigger_pivot
                            else None,
                            "reference_bar_index": event.reference_pivot.bar_index
                            if event.reference_pivot
                            else None,
                        },
                    ),
                },
            )

        await db.insert_into("smc_events").values(values).execute()
        logger.debug(f"Wrote {len(events)} SMC events for {symbol} {timeframe}")

    except Exception as e:
        logger.error(f"Failed to write SMC events: {e}")
        raise


async def write_zones(
    db: KyselyDatabase | Transaction,
    zones: list[Zone],
) -> None:
    if not zones:
        return

    try:
        values = []
        for zone in zones:
            values.append(
                {
                    "zone_id": str(zone.zone_id),
                    "symbol": zone.symbol,
                    "timeframe": zone.timeframe.value,
                    "zone_type": zone.zone_type,
                    "side": zone.side.value,
                    "top_price": str(zone.top_price),
                    "bottom_price": str(zone.bottom_price),
                    "created_at": zone.created_at,
                    "created_bar_index": zone.created_bar_index,
                    "expiry_bars": zone.expiry_bars,
                    "touches": zone.touches,
                    "strength": str(zone.strength),
                    "is_active": zone.created_bar_index + zone.expiry_bars
                    > zone.created_bar_index,  # Simple active check
                },
            )

        await (
            db.insert_into("zones")
            .values(values)
            .on_conflict("zone_id")
            .do_update_set(
                {
                    "touches": lambda: "excluded.touches",
                    "is_active": lambda: "excluded.is_active",
                },
            )
            .execute()
        )

        logger.debug(f"Wrote {len(zones)} zones")

    except Exception as e:
        logger.error(f"Failed to write zones: {e}")
        raise


async def update_zone_touches(
    db: KyselyDatabase | Transaction,
    zone_id: str,
    touches: int,
) -> None:
    try:
        await (
            db.update("zones")
            .set(
                {
                    "touches": touches,
                    "last_touched_at": datetime.now(UTC),
                },
            )
            .where("zone_id", "=", zone_id)
            .execute()
        )

        logger.debug(f"Updated zone {zone_id} touches to {touches}")

    except Exception as e:
        logger.error(f"Failed to update zone touches: {e}")
        raise


async def expire_zones(
    db: KyselyDatabase | Transaction,
    symbol: str,
    timeframe: str,
    current_bar_index: int,
) -> int:
    try:
        result = (
            await db.update("zones")
            .set(
                {
                    "is_active": False,
                    "expired_at": datetime.now(UTC),
                },
            )
            .where("symbol", "=", symbol)
            .where("timeframe", "=", timeframe)
            .where(db.raw("created_bar_index + expiry_bars < ?", [current_bar_index]))
            .execute()
        )

        expired_count = result.num_updated_rows if hasattr(result, "num_updated_rows") else 0
        if expired_count > 0:
            logger.debug(f"Expired {expired_count} zones for {symbol} {timeframe}")

        return expired_count

    except Exception as e:
        logger.error(f"Failed to expire zones: {e}")
        raise


async def get_active_zones(
    db: KyselyDatabase | Transaction,
    symbol: str,
    timeframe: str,
    zone_type: str | None = None,
) -> list[dict[str, Any]]:
    try:
        query = (
            db.select_from("zones")
            .select_all()
            .where("symbol", "=", symbol)
            .where("timeframe", "=", timeframe)
            .where("is_active", "=", True)
        )

        if zone_type:
            query = query.where("zone_type", "=", zone_type)

        result = await query.execute()
        return list(result)

    except Exception as e:
        logger.error(f"Failed to get active zones: {e}")
        raise


async def get_recent_structure_state(
    db: KyselyDatabase | Transaction,
    symbol: str,
    timeframe: str,
) -> dict[str, Any] | None:
    try:
        # Get the most recent structure state from SMC events
        result = (
            await db.select_from("smc_events")
            .select("to_state", "timestamp", "price")
            .where("symbol", "=", symbol)
            .where("timeframe", "=", timeframe)
            .where("event_type", "in", ["CHOCH", "STRUCTURE_UPDATE"])
            .order_by("timestamp", "desc")
            .limit(1)
            .execute()
        )

        if result:
            return dict(result[0])

        return None

    except Exception as e:
        logger.error(f"Failed to get structure state: {e}")
        raise
