import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.engine.smc_types import Pivot, Zone, ZoneSide, SMCEvent, SMCEventKind, StructureState
from app.engine.models import TimeFrame


def test_pivot_serializes_price_as_string():
    p = Pivot(
        timestamp=datetime.now(timezone.utc),
        price=Decimal("10.25"),
        is_high=True,
        strength=3,
        bar_index=5,
    )
    data = p.model_dump_json()
    d = json.loads(data)
    assert d["price"] == "10.25"


def test_zone_serializes_decimals_as_strings():
    z = Zone(
        zone_id=uuid4(),
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        zone_type="OB_BULL",
        side=ZoneSide.LOW,
        top_price=Decimal("12.0"),
        bottom_price=Decimal("11.2"),
        created_at=datetime.now(timezone.utc),
        created_bar_index=10,
        expiry_bars=20,
        touches=1,
        strength=Decimal("0.8"),
    )
    d = json.loads(z.model_dump_json())
    assert d["top_price"] == "12.0"
    assert d["bottom_price"] == "11.2"
    assert d["strength"] == "0.8"


def test_smc_event_serializes_decimals_as_strings():
    evt = SMCEvent(
        kind=SMCEventKind.CHOCH,
        timestamp=datetime.now(timezone.utc),
        price=Decimal("9.99"),
        from_state=StructureState.NEUTRAL,
        to_state=StructureState.BEARISH,
        trigger_pivot=Pivot(
            timestamp=datetime.now(timezone.utc),
            price=Decimal("10"),
            is_high=False,
            strength=1,
            bar_index=2,
        ),
    )
    d = json.loads(evt.model_dump_json())
    assert d["price"] == "9.99"
