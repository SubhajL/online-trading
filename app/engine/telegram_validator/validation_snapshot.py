"""
Validation snapshot models and builder for benchmark reproducibility.

Captures engine state (zones, structures, guards, regime) at validation time
to enable reproducible benchmark reruns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID


SNAPSHOT_VERSION = 1
DEFAULT_ZONE_LOOKBACK_BARS = 100
DEFAULT_STRUCTURE_LOOKBACK_BARS = 50


@dataclass(frozen=True)
class ZoneSnapshot:
    """Compact zone representation for snapshot payload."""

    zone_id: str
    zone_type: str
    top_price: str
    bottom_price: str
    strength: int
    is_active: bool
    created_at: str


@dataclass(frozen=True)
class StructureSnapshot:
    """Compact SMC structure event for snapshot payload."""

    event_id: str
    event_type: str
    timestamp: str
    direction: str | None
    price: str | None


@dataclass(frozen=True)
class GuardStateSnapshot:
    """Guard status at validation time."""

    news_guard_active: bool
    funding_guard_active: bool
    drawdown_guard_active: bool
    guards_evaluated_at: str | None


@dataclass(frozen=True)
class RegimeSnapshot:
    """Market regime at validation time."""

    regime: str
    confidence: float | None
    evaluated_at: str | None


@dataclass(frozen=True)
class InternalMatchSnapshot:
    """Matched internal signal/decision info."""

    kind: Literal["trading_decision", "smc_signal"]
    internal_id: str
    timestamp: str
    direction: str | None
    entry_price: str | None


@dataclass(frozen=True)
class ValidationSnapshotPayload:
    """Complete snapshot payload for persistence."""

    zones: list[ZoneSnapshot]
    structures: list[StructureSnapshot]
    guards: GuardStateSnapshot
    regime: RegimeSnapshot
    internal_match: InternalMatchSnapshot | None


@dataclass(frozen=True)
class ValidationSnapshot:
    """Full validation snapshot with metadata."""

    snapshot_id: UUID | None
    source: str
    chat_id: int
    message_id: int
    validated_at: datetime
    symbol: str
    timeframe: str | None
    snapshot_version: int
    payload: ValidationSnapshotPayload


def serialize_snapshot_payload(payload: ValidationSnapshotPayload) -> dict[str, Any]:
    """Convert snapshot payload to JSON-serializable dict.

    Handles Decimal→str and datetime→ISO8601 conversion.
    Pure function with no side effects.
    """
    return {
        "version": SNAPSHOT_VERSION,
        "zones": [
            {
                "zone_id": z.zone_id,
                "zone_type": z.zone_type,
                "top_price": z.top_price,
                "bottom_price": z.bottom_price,
                "strength": z.strength,
                "is_active": z.is_active,
                "created_at": z.created_at,
            }
            for z in payload.zones
        ],
        "structures": [
            {
                "event_id": s.event_id,
                "event_type": s.event_type,
                "timestamp": s.timestamp,
                "direction": s.direction,
                "price": s.price,
            }
            for s in payload.structures
        ],
        "guards": {
            "news_guard_active": payload.guards.news_guard_active,
            "funding_guard_active": payload.guards.funding_guard_active,
            "drawdown_guard_active": payload.guards.drawdown_guard_active,
            "guards_evaluated_at": payload.guards.guards_evaluated_at,
        },
        "regime": {
            "regime": payload.regime.regime,
            "confidence": payload.regime.confidence,
            "evaluated_at": payload.regime.evaluated_at,
        },
        "internal_match": (
            {
                "kind": payload.internal_match.kind,
                "internal_id": payload.internal_match.internal_id,
                "timestamp": payload.internal_match.timestamp,
                "direction": payload.internal_match.direction,
                "entry_price": payload.internal_match.entry_price,
            }
            if payload.internal_match
            else None
        ),
    }


def deserialize_snapshot_payload(data: dict[str, Any]) -> ValidationSnapshotPayload:
    """Parse JSON payload back to typed model.

    Validates version compatibility.
    Pure function with no side effects.
    """
    version = data.get("version", 1)
    if version > SNAPSHOT_VERSION:
        raise ValueError(f"Unsupported snapshot version: {version} (max: {SNAPSHOT_VERSION})")

    zones = [
        ZoneSnapshot(
            zone_id=z["zone_id"],
            zone_type=z["zone_type"],
            top_price=z["top_price"],
            bottom_price=z["bottom_price"],
            strength=z["strength"],
            is_active=z["is_active"],
            created_at=z["created_at"],
        )
        for z in data.get("zones", [])
    ]

    structures = [
        StructureSnapshot(
            event_id=s["event_id"],
            event_type=s["event_type"],
            timestamp=s["timestamp"],
            direction=s.get("direction"),
            price=s.get("price"),
        )
        for s in data.get("structures", [])
    ]

    guards_data = data.get("guards", {})
    guards = GuardStateSnapshot(
        news_guard_active=guards_data.get("news_guard_active", False),
        funding_guard_active=guards_data.get("funding_guard_active", False),
        drawdown_guard_active=guards_data.get("drawdown_guard_active", False),
        guards_evaluated_at=guards_data.get("guards_evaluated_at"),
    )

    regime_data = data.get("regime", {})
    regime = RegimeSnapshot(
        regime=regime_data.get("regime", "UNKNOWN"),
        confidence=regime_data.get("confidence"),
        evaluated_at=regime_data.get("evaluated_at"),
    )

    internal_match_data = data.get("internal_match")
    internal_match = (
        InternalMatchSnapshot(
            kind=internal_match_data["kind"],
            internal_id=internal_match_data["internal_id"],
            timestamp=internal_match_data["timestamp"],
            direction=internal_match_data.get("direction"),
            entry_price=internal_match_data.get("entry_price"),
        )
        if internal_match_data
        else None
    )

    return ValidationSnapshotPayload(
        zones=zones,
        structures=structures,
        guards=guards,
        regime=regime,
        internal_match=internal_match,
    )


async def build_validation_snapshot(
    adapter: Any,
    *,
    source: str,
    chat_id: int,
    message_id: int,
    symbol: str,
    timeframe: str | None,
    validated_at: datetime,
    internal_match: InternalMatchSnapshot | None,
    zone_lookback_bars: int = DEFAULT_ZONE_LOOKBACK_BARS,
    structure_lookback_bars: int = DEFAULT_STRUCTURE_LOOKBACK_BARS,
) -> ValidationSnapshot:
    """Build a bounded, versioned snapshot for a validation timestamp.

    Queries zones, structures, guards, and regime within lookback window.
    Returns a ValidationSnapshot ready for persistence.
    """
    # Query active zones at validation time
    zone_rows = await adapter.get_active_zones_at_time(
        symbol=symbol,
        timestamp=validated_at,
        lookback_bars=zone_lookback_bars,
        max_zones=20,
    )
    zones = _zones_to_snapshots(zone_rows, max_zones=20)

    # Query structure events (CHOCH/BOS) near validation time
    event_rows = await adapter.get_structure_events_at_time(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=validated_at,
        lookback_bars=structure_lookback_bars,
        max_events=30,
    )
    structures = _structures_to_snapshots(event_rows, max_events=30)

    # Build guard state (currently computed on-the-fly, so defaults)
    # In future, could query a guards_history table
    guards = _build_guard_state(evaluated_at=validated_at)

    # Build regime state (currently defaults to UNKNOWN)
    # In future, could query regime_history table
    regime = _build_regime_state(evaluated_at=validated_at)

    # Build payload
    payload = ValidationSnapshotPayload(
        zones=zones,
        structures=structures,
        guards=guards,
        regime=regime,
        internal_match=internal_match,
    )

    return ValidationSnapshot(
        snapshot_id=None,  # Will be set after DB insert
        source=source,
        chat_id=chat_id,
        message_id=message_id,
        validated_at=validated_at,
        symbol=symbol,
        timeframe=timeframe,
        snapshot_version=SNAPSHOT_VERSION,
        payload=payload,
    )


def _zones_to_snapshots(
    zone_rows: list[dict[str, Any]],
    *,
    max_zones: int = 20,
) -> list[ZoneSnapshot]:
    """Convert zone DB rows to compact snapshot format.

    Limits to max_zones, orders by strength descending.
    Pure function.
    """
    if not zone_rows:
        return []

    # Sort by strength descending
    sorted_rows = sorted(zone_rows, key=lambda z: z.get("strength", 0), reverse=True)

    # Limit to max_zones
    limited_rows = sorted_rows[:max_zones]

    result = []
    for z in limited_rows:
        # Handle datetime or string for created_at
        created_at = z.get("created_at")
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat()
        else:
            created_at_str = str(created_at) if created_at else ""

        # Handle Decimal or numeric for prices
        top_price = z.get("top_price")
        if isinstance(top_price, Decimal):
            top_price_str = str(top_price)
        else:
            top_price_str = str(top_price) if top_price else "0"

        bottom_price = z.get("bottom_price")
        if isinstance(bottom_price, Decimal):
            bottom_price_str = str(bottom_price)
        else:
            bottom_price_str = str(bottom_price) if bottom_price else "0"

        result.append(
            ZoneSnapshot(
                zone_id=str(z.get("zone_id", z.get("id", ""))),
                zone_type=z.get("zone_type", "UNKNOWN"),
                top_price=top_price_str,
                bottom_price=bottom_price_str,
                strength=int(z.get("strength", 0)),
                is_active=bool(z.get("is_active", True)),
                created_at=created_at_str,
            ),
        )

    return result


def _structures_to_snapshots(
    event_rows: list[dict[str, Any]],
    *,
    max_events: int = 30,
) -> list[StructureSnapshot]:
    """Convert SMC event DB rows to compact snapshot format.

    Limits to max_events, orders by timestamp descending (most recent first).
    Pure function.
    """
    if not event_rows:
        return []

    # Sort by timestamp descending (most recent first)
    def get_timestamp(row: dict[str, Any]) -> datetime:
        ts = row.get("timestamp")
        if isinstance(ts, datetime):
            return ts
        # If string, try to parse
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return datetime.min
        return datetime.min

    sorted_rows = sorted(event_rows, key=get_timestamp, reverse=True)

    # Limit to max_events
    limited_rows = sorted_rows[:max_events]

    result = []
    for e in limited_rows:
        # Handle timestamp
        ts = e.get("timestamp")
        if isinstance(ts, datetime):
            ts_str = ts.isoformat()
        else:
            ts_str = str(ts) if ts else ""

        # Handle price (may be Decimal, float, or None)
        price = e.get("price")
        if price is not None:
            price_str = str(price)
        else:
            price_str = None

        result.append(
            StructureSnapshot(
                event_id=str(e.get("event_id", e.get("id", ""))),
                event_type=e.get("event_type", "UNKNOWN"),
                timestamp=ts_str,
                direction=e.get("direction"),
                price=price_str,
            ),
        )

    return result


def _build_guard_state(
    *,
    news_active: bool = False,
    funding_active: bool = False,
    drawdown_active: bool = False,
    evaluated_at: datetime | None = None,
) -> GuardStateSnapshot:
    """Build guard state snapshot.

    In current implementation, guards are computed on-the-fly.
    This captures the resolved state at validation time.
    """
    return GuardStateSnapshot(
        news_guard_active=news_active,
        funding_guard_active=funding_active,
        drawdown_guard_active=drawdown_active,
        guards_evaluated_at=evaluated_at.isoformat() if evaluated_at else None,
    )


def _build_regime_state(
    *,
    regime: str = "UNKNOWN",
    confidence: float | None = None,
    evaluated_at: datetime | None = None,
) -> RegimeSnapshot:
    """Build regime state snapshot.

    Defaults to UNKNOWN if no regime data available.
    """
    return RegimeSnapshot(
        regime=regime,
        confidence=confidence,
        evaluated_at=evaluated_at.isoformat() if evaluated_at else None,
    )
