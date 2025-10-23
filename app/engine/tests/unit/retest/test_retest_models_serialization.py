import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.engine.models import RetestSignal, SupplyDemandZone, TimeFrame, ZoneType


def test_retest_signal_serialization():
    rs = RetestSignal(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        timestamp=datetime.now(timezone.utc),
        level_price=Decimal("100.5"),
        retest_type="support_retest",
        success_probability=Decimal("0.65"),
        volume_confirmation=True,
    )
    d = json.loads(rs.model_dump_json())
    assert d["level_price"] == "100.5"
    assert d["success_probability"] == "0.65"
    assert "Z" in d["timestamp"] or "+00:00" in d["timestamp"]


def test_supply_demand_zone_serialization():
    z = SupplyDemandZone(
        zone_id=uuid4(),
        symbol="ETHUSDT",
        timeframe=TimeFrame.M15,
        zone_type=ZoneType.SUPPLY,
        top_price=Decimal("120.0"),
        bottom_price=Decimal("115.0"),
        created_at=datetime.now(timezone.utc),
        strength=5,
        volume_profile=Decimal("100.0"),
    )
    d = json.loads(z.model_dump_json())
    assert d["top_price"] == "120.0"
    assert d["bottom_price"] == "115.0"
    assert d["volume_profile"] == "100.0"
    assert "Z" in d["created_at"] or "+00:00" in d["created_at"]
