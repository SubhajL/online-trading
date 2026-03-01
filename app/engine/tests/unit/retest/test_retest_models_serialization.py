from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from uuid import uuid4

from app.engine.models import (
    RetestSignal,
    SupplyDemandZone,
    TimeFrame,
    ZoneType,
)


def test_retest_signal_serialization() -> None:
    rs = RetestSignal(
        venue="SPOT",
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        timestamp=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        level_price=Decimal("100.5"),
        direction="BUY",
        stop_loss=Decimal("99.0"),
        take_profit=Decimal("102.0"),
        retest_type="support_retest",
        success_probability=Decimal("0.65"),
        volume_confirmation=True,
    )
    d = json.loads(rs.model_dump_json())
    assert d["level_price"] == "100.5"
    assert d["direction"] == "BUY"
    assert d["stop_loss"] == "99.0"
    assert d["take_profit"] == "102.0"
    assert d["success_probability"] == "0.65"
    assert "Z" in d["timestamp"] or "+00:00" in d["timestamp"]


def test_supply_demand_zone_serialization() -> None:
    z = SupplyDemandZone(
        zone_id=uuid4(),
        symbol="ETHUSDT",
        timeframe=TimeFrame.M15,
        zone_type=ZoneType.SUPPLY,
        top_price=Decimal("120.0"),
        bottom_price=Decimal("115.0"),
        created_at=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        strength=5,
        volume_profile=Decimal("100.0"),
    )
    d = json.loads(z.model_dump_json())
    assert d["top_price"] == "120.0"
    assert d["bottom_price"] == "115.0"
    assert d["volume_profile"] == "100.0"
    assert "Z" in d["created_at"] or "+00:00" in d["created_at"]
