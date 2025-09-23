from __future__ import annotations

from datetime import datetime
from typing import Any

from ..bus import get_event_bus
from ..models import BaseEvent, EventType
from ..types import SMCEvent, StructureState, Zone


def create_smc_event(
    symbol: str,
    timeframe: str,
    smc_event: SMCEvent,
    current_state: StructureState,
    key_levels: dict[str, Any],
) -> BaseEvent:
    return BaseEvent(
        event_type=EventType.SMC_SIGNAL,
        timestamp=datetime.utcnow(),
        symbol=symbol,
        timeframe=timeframe,
        metadata={
            "kind": smc_event.kind.value,
            "price": str(smc_event.price),
            "from_state": smc_event.from_state,
            "to_state": smc_event.to_state,
            "current_state": current_state.value,
            "key_levels": {k: str(v) if isinstance(v, (int, float)) else v for k, v in key_levels.items()},
            "strength": str(smc_event.strength),
            "reference_pivot": {
                "price": str(smc_event.reference_pivot.price),
                "is_high": smc_event.reference_pivot.is_high,
                "bar_index": smc_event.reference_pivot.bar_index,
            } if smc_event.reference_pivot else None,
        },
    )


def create_zone_event(
    zone: Zone,
    action: str,
) -> BaseEvent:
    return BaseEvent(
        event_type=EventType.SMC_SIGNAL,
        timestamp=datetime.utcnow(),
        symbol=zone.symbol,
        timeframe=zone.timeframe,
        metadata={
            "event_type": "zone",
            "action": action,
            "zone": {
                "zone_id": str(zone.zone_id),
                "zone_type": zone.zone_type,
                "side": zone.side.value,
                "top_price": str(zone.top_price),
                "bottom_price": str(zone.bottom_price),
                "created_bar_index": zone.created_bar_index,
                "expiry_bars": zone.expiry_bars,
                "touches": zone.touches,
                "strength": str(zone.strength),
            },
        },
    )


async def publish_events(events: list[BaseEvent], priority: int = 5) -> None:
    event_bus = get_event_bus()
    for event in events:
        await event_bus.publish(event, priority=priority)