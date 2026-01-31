from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..bus import get_event_bus
from ..models import TimeFrame
from ..smc_types import SMCEvent, StructureBreakEvent, StructureState, Zone, ZoneEvent


def create_smc_event(
    venue: str,
    symbol: str,
    timeframe: TimeFrame | str,
    smc_event: SMCEvent,
    current_state: StructureState,
    key_levels: dict[str, Any],
) -> StructureBreakEvent:
    tf = TimeFrame(timeframe) if isinstance(timeframe, str) else timeframe
    return StructureBreakEvent(
        timestamp=smc_event.timestamp if smc_event.timestamp.tzinfo else smc_event.timestamp.replace(tzinfo=UTC),
        venue=venue,
        symbol=symbol,
        timeframe=tf,
        smc_event=smc_event,
        current_state=current_state,
        key_levels=key_levels,
    )


def create_zone_event(
    venue: str,
    zone: Zone,
    action: str,
) -> ZoneEvent:
    return ZoneEvent(
        timestamp=datetime.now(UTC),
        venue=venue,
        symbol=zone.symbol,
        timeframe=zone.timeframe,
        zone=zone,
        action=action,
    )


async def publish_events(events: list[Any], priority: int = 5) -> None:
    event_bus = get_event_bus()
    for event in events:
        await event_bus.publish(event, priority=priority)
