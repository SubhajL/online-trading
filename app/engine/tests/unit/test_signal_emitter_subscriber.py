"""Unit tests for SignalEmitterSubscriber."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.engine.adapters.alert.signal_emitter_subscriber import SignalEmitterSubscriber
from app.engine.models import (
    OrderSide,
    SMCSignal,
    SMCSignalEvent,
    SupplyDemandZone,
    TimeFrame,
    ZoneType,
)


@pytest.mark.asyncio
async def test_handle_smc_signal_passes_zone_evidence_to_emitter() -> None:
    bus = Mock()
    mock_emitter = Mock()
    mock_emitter.emit_signal = AsyncMock(return_value="sig_test")

    subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=mock_emitter, venue="SPOT")

    now = datetime(2025, 7, 1, 9, 0, 0, tzinfo=UTC)
    zone = SupplyDemandZone(
        symbol="ETHUSDT",
        timeframe=TimeFrame.M15,
        zone_type=ZoneType.FAIR_VALUE_GAP,
        top_price=Decimal(3190),
        bottom_price=Decimal(3180),
        created_at=now,
        strength=5,
        volume_profile=Decimal(1),
    )
    signal = SMCSignal(
        symbol="ETHUSDT",
        timeframe=TimeFrame.M15,
        timestamp=now,
        signal_type="fair_value_gap",
        direction=OrderSide.SELL,
        entry_price=Decimal("3184.36"),
        stop_loss=Decimal("3187.16"),
        take_profit=Decimal("3152.52"),
        confidence=Decimal("0.65"),
        zone=zone,
        reasoning="FVG fill with bearish bias",
    )
    event = SMCSignalEvent(
        timestamp=now,
        symbol="ETHUSDT",
        timeframe=TimeFrame.M15,
        signal=signal,
    )

    await subscriber._handle_smc_signal(event)

    mock_emitter.emit_signal.assert_awaited_once()
    kwargs = mock_emitter.emit_signal.call_args.kwargs
    assert kwargs["zone"] == {
        "zone_id": str(zone.zone_id),
        "zone_type": ZoneType.FAIR_VALUE_GAP.value,
        "top_price": zone.top_price,
        "bottom_price": zone.bottom_price,
    }
