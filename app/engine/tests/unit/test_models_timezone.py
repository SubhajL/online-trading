from datetime import timezone

from app.engine.smc.events import create_smc_event, create_zone_event
from app.engine.smc_types import SMCEvent, SMCEventKind, StructureState, Zone, ZoneSide, Pivot
from app.engine.models import TimeFrame
from uuid import uuid4
from decimal import Decimal
from datetime import datetime


def test_smc_event_timestamp_timezone_aware():
    pivot = Pivot(
        timestamp=datetime.now(timezone.utc),
        price=Decimal("10"),
        is_high=True,
        strength=1,
        bar_index=1,
    )
    smc = SMCEvent(
        kind=SMCEventKind.BOS,
        timestamp=datetime.now(timezone.utc),
        price=Decimal("10"),
        from_state=StructureState.NEUTRAL,
        to_state=StructureState.BULLISH,
        trigger_pivot=pivot,
    )
    evt = create_smc_event("SPOT", "BTCUSDT", TimeFrame.M5, smc, StructureState.BULLISH, {})
    assert evt.timestamp.tzinfo is not None
    assert evt.timestamp.tzname() in ("UTC", "UTC+00:00", "Coordinated Universal Time")


def test_zone_event_timestamp_timezone_aware():
    zone = Zone(
        zone_id=uuid4(),
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        zone_type="OB_BULL",
        side=ZoneSide.LOW,
        top_price=Decimal("11"),
        bottom_price=Decimal("10"),
        created_at=datetime.now(timezone.utc),
        created_bar_index=1,
        expiry_bars=10,
    )
    evt = create_zone_event("SPOT", zone, "created")
    assert evt.timestamp.tzinfo is not None
    assert evt.timestamp.tzname() in ("UTC", "UTC+00:00", "Coordinated Universal Time")
