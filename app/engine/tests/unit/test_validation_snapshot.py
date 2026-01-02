"""
Unit tests for validation snapshot builder and serialization.

Tests pure logic without DB dependencies.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.engine.telegram_validator.validation_snapshot import (
    GuardStateSnapshot,
    InternalMatchSnapshot,
    RegimeSnapshot,
    StructureSnapshot,
    ValidationSnapshotPayload,
    ZoneSnapshot,
    _build_guard_state,
    _build_regime_state,
    _structures_to_snapshots,
    _zones_to_snapshots,
    deserialize_snapshot_payload,
    serialize_snapshot_payload,
)


class TestZonesToSnapshots:
    """Tests for _zones_to_snapshots conversion."""

    def test_converts_zone_rows_to_snapshots(self) -> None:
        """Zone rows are converted to ZoneSnapshot with correct fields."""
        zone_rows = [
            {
                "zone_id": "zone-1",
                "zone_type": "DEMAND",
                "top_price": Decimal("100.50"),
                "bottom_price": Decimal("99.50"),
                "strength": 8,
                "is_active": True,
                "created_at": datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
            },
        ]

        result = _zones_to_snapshots(zone_rows)

        assert len(result) == 1
        assert result[0].zone_id == "zone-1"
        assert result[0].zone_type == "DEMAND"
        assert result[0].top_price == "100.50"
        assert result[0].bottom_price == "99.50"
        assert result[0].strength == 8
        assert result[0].is_active is True

    def test_limits_to_max_zones(self) -> None:
        """Zones are limited to max_zones parameter."""
        zone_rows = [
            {
                "zone_id": f"zone-{i}",
                "zone_type": "SUPPLY",
                "top_price": Decimal("100"),
                "bottom_price": Decimal("99"),
                "strength": i,
                "is_active": True,
                "created_at": datetime(2025, 1, 1, tzinfo=UTC),
            }
            for i in range(30)
        ]

        result = _zones_to_snapshots(zone_rows, max_zones=5)

        assert len(result) == 5

    def test_orders_by_strength_descending(self) -> None:
        """Zones are ordered by strength descending (highest first)."""
        zone_rows = [
            {
                "zone_id": "weak",
                "zone_type": "DEMAND",
                "top_price": Decimal("100"),
                "bottom_price": Decimal("99"),
                "strength": 2,
                "is_active": True,
                "created_at": datetime(2025, 1, 1, tzinfo=UTC),
            },
            {
                "zone_id": "strong",
                "zone_type": "DEMAND",
                "top_price": Decimal("100"),
                "bottom_price": Decimal("99"),
                "strength": 9,
                "is_active": True,
                "created_at": datetime(2025, 1, 1, tzinfo=UTC),
            },
        ]

        result = _zones_to_snapshots(zone_rows, max_zones=10)

        assert result[0].zone_id == "strong"
        assert result[1].zone_id == "weak"

    def test_returns_empty_list_for_no_zones(self) -> None:
        """Empty input returns empty list."""
        result = _zones_to_snapshots([])
        assert result == []


class TestStructuresToSnapshots:
    """Tests for _structures_to_snapshots conversion."""

    def test_converts_event_rows_to_snapshots(self) -> None:
        """SMC event rows are converted to StructureSnapshot."""
        event_rows = [
            {
                "id": "event-1",
                "event_type": "CHOCH",
                "timestamp": datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
                "direction": "BUY",
                "price": Decimal("95000.00"),
            },
        ]

        result = _structures_to_snapshots(event_rows)

        assert len(result) == 1
        assert result[0].event_id == "event-1"
        assert result[0].event_type == "CHOCH"
        assert result[0].direction == "BUY"
        assert result[0].price == "95000.00"

    def test_limits_to_max_events(self) -> None:
        """Events are limited to max_events parameter."""
        event_rows = [
            {
                "id": f"event-{i}",
                "event_type": "BOS",
                "timestamp": datetime(2025, 1, 1 + (i // 24), i % 24, 0, tzinfo=UTC),
                "direction": "SELL",
                "price": Decimal("100"),
            }
            for i in range(50)
        ]

        result = _structures_to_snapshots(event_rows, max_events=10)

        assert len(result) == 10

    def test_orders_by_timestamp_descending(self) -> None:
        """Events are ordered by timestamp descending (most recent first)."""
        event_rows = [
            {
                "id": "old",
                "event_type": "CHOCH",
                "timestamp": datetime(2025, 1, 1, 8, 0, tzinfo=UTC),
                "direction": "BUY",
                "price": Decimal("100"),
            },
            {
                "id": "new",
                "event_type": "BOS",
                "timestamp": datetime(2025, 1, 1, 12, 0, tzinfo=UTC),
                "direction": "SELL",
                "price": Decimal("101"),
            },
        ]

        result = _structures_to_snapshots(event_rows)

        assert result[0].event_id == "new"
        assert result[1].event_id == "old"

    def test_handles_missing_optional_fields(self) -> None:
        """Handles events with missing direction or price."""
        event_rows = [
            {
                "id": "event-1",
                "event_type": "BOS",
                "timestamp": datetime(2025, 1, 1, tzinfo=UTC),
                "direction": None,
                "price": None,
            },
        ]

        result = _structures_to_snapshots(event_rows)

        assert result[0].direction is None
        assert result[0].price is None


class TestBuildGuardState:
    """Tests for _build_guard_state helper."""

    def test_builds_guard_state_with_defaults(self) -> None:
        """Default guard state has all guards inactive."""
        result = _build_guard_state()

        assert result.news_guard_active is False
        assert result.funding_guard_active is False
        assert result.drawdown_guard_active is False
        assert result.guards_evaluated_at is None

    def test_builds_guard_state_with_active_guards(self) -> None:
        """Guard state reflects active guards."""
        eval_time = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)

        result = _build_guard_state(
            news_active=True,
            funding_active=False,
            drawdown_active=True,
            evaluated_at=eval_time,
        )

        assert result.news_guard_active is True
        assert result.funding_guard_active is False
        assert result.drawdown_guard_active is True
        assert result.guards_evaluated_at == "2025-01-01T12:00:00+00:00"


class TestBuildRegimeState:
    """Tests for _build_regime_state helper."""

    def test_builds_regime_state_with_defaults(self) -> None:
        """Default regime is UNKNOWN."""
        result = _build_regime_state()

        assert result.regime == "UNKNOWN"
        assert result.confidence is None
        assert result.evaluated_at is None

    def test_builds_regime_state_with_values(self) -> None:
        """Regime state captures provided values."""
        eval_time = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)

        result = _build_regime_state(
            regime="TRENDING_UP",
            confidence=0.85,
            evaluated_at=eval_time,
        )

        assert result.regime == "TRENDING_UP"
        assert result.confidence == 0.85
        assert result.evaluated_at == "2025-01-01T12:00:00+00:00"


class TestSerializeSnapshotPayload:
    """Tests for serialize_snapshot_payload function."""

    def test_serializes_complete_payload(self) -> None:
        """Complete payload serializes to JSON-compatible dict."""
        payload = ValidationSnapshotPayload(
            zones=[
                ZoneSnapshot(
                    zone_id="z1",
                    zone_type="DEMAND",
                    top_price="100.50",
                    bottom_price="99.50",
                    strength=8,
                    is_active=True,
                    created_at="2025-01-01T12:00:00+00:00",
                ),
            ],
            structures=[
                StructureSnapshot(
                    event_id="e1",
                    event_type="CHOCH",
                    timestamp="2025-01-01T12:00:00+00:00",
                    direction="BUY",
                    price="95000.00",
                ),
            ],
            guards=GuardStateSnapshot(
                news_guard_active=True,
                funding_guard_active=False,
                drawdown_guard_active=False,
                guards_evaluated_at="2025-01-01T12:00:00+00:00",
            ),
            regime=RegimeSnapshot(
                regime="TRENDING_UP",
                confidence=0.85,
                evaluated_at="2025-01-01T12:00:00+00:00",
            ),
            internal_match=InternalMatchSnapshot(
                kind="trading_decision",
                internal_id="dec-123",
                timestamp="2025-01-01T12:00:00+00:00",
                direction="BUY",
                entry_price="95000.00",
            ),
        )

        result = serialize_snapshot_payload(payload)

        assert isinstance(result, dict)
        assert len(result["zones"]) == 1
        assert result["zones"][0]["zone_id"] == "z1"
        assert result["guards"]["news_guard_active"] is True
        assert result["regime"]["regime"] == "TRENDING_UP"
        assert result["internal_match"]["kind"] == "trading_decision"

    def test_serializes_payload_without_internal_match(self) -> None:
        """Payload without internal match serializes correctly."""
        payload = ValidationSnapshotPayload(
            zones=[],
            structures=[],
            guards=_build_guard_state(),
            regime=_build_regime_state(),
            internal_match=None,
        )

        result = serialize_snapshot_payload(payload)

        assert result["internal_match"] is None


class TestDeserializeSnapshotPayload:
    """Tests for deserialize_snapshot_payload function."""

    def test_deserializes_complete_payload(self) -> None:
        """JSON dict deserializes to typed payload."""
        data = {
            "zones": [
                {
                    "zone_id": "z1",
                    "zone_type": "DEMAND",
                    "top_price": "100.50",
                    "bottom_price": "99.50",
                    "strength": 8,
                    "is_active": True,
                    "created_at": "2025-01-01T12:00:00+00:00",
                },
            ],
            "structures": [
                {
                    "event_id": "e1",
                    "event_type": "CHOCH",
                    "timestamp": "2025-01-01T12:00:00+00:00",
                    "direction": "BUY",
                    "price": "95000.00",
                },
            ],
            "guards": {
                "news_guard_active": True,
                "funding_guard_active": False,
                "drawdown_guard_active": False,
                "guards_evaluated_at": "2025-01-01T12:00:00+00:00",
            },
            "regime": {
                "regime": "TRENDING_UP",
                "confidence": 0.85,
                "evaluated_at": "2025-01-01T12:00:00+00:00",
            },
            "internal_match": {
                "kind": "trading_decision",
                "internal_id": "dec-123",
                "timestamp": "2025-01-01T12:00:00+00:00",
                "direction": "BUY",
                "entry_price": "95000.00",
            },
        }

        result = deserialize_snapshot_payload(data)

        assert isinstance(result, ValidationSnapshotPayload)
        assert len(result.zones) == 1
        assert result.zones[0].zone_id == "z1"
        assert result.guards.news_guard_active is True
        assert result.regime.regime == "TRENDING_UP"
        assert result.internal_match is not None
        assert result.internal_match.kind == "trading_decision"

    def test_deserializes_payload_without_internal_match(self) -> None:
        """Payload with null internal_match deserializes correctly."""
        data = {
            "zones": [],
            "structures": [],
            "guards": {
                "news_guard_active": False,
                "funding_guard_active": False,
                "drawdown_guard_active": False,
                "guards_evaluated_at": None,
            },
            "regime": {
                "regime": "UNKNOWN",
                "confidence": None,
                "evaluated_at": None,
            },
            "internal_match": None,
        }

        result = deserialize_snapshot_payload(data)

        assert result.internal_match is None

    def test_roundtrip_serialize_deserialize(self) -> None:
        """Serialize→deserialize produces equivalent payload."""
        original = ValidationSnapshotPayload(
            zones=[
                ZoneSnapshot(
                    zone_id="z1",
                    zone_type="SUPPLY",
                    top_price="200.00",
                    bottom_price="195.00",
                    strength=7,
                    is_active=True,
                    created_at="2025-01-01T08:00:00+00:00",
                ),
            ],
            structures=[],
            guards=_build_guard_state(news_active=True),
            regime=_build_regime_state(regime="VOLATILE", confidence=0.72),
            internal_match=None,
        )

        serialized = serialize_snapshot_payload(original)
        restored = deserialize_snapshot_payload(serialized)

        assert restored.zones[0].zone_id == original.zones[0].zone_id
        assert restored.zones[0].strength == original.zones[0].strength
        assert restored.guards.news_guard_active == original.guards.news_guard_active
        assert restored.regime.regime == original.regime.regime
        assert restored.regime.confidence == original.regime.confidence


class _FakeSnapshotAdapter:
    """Fake adapter for testing build_validation_snapshot."""

    def __init__(
        self,
        zones: list[dict] | None = None,
        events: list[dict] | None = None,
    ) -> None:
        self.zones = zones or []
        self.events = events or []

    async def get_active_zones_at_time(self, **kwargs) -> list[dict]:  # noqa: ANN001
        return self.zones

    async def get_structure_events_at_time(self, **kwargs) -> list[dict]:  # noqa: ANN001
        return self.events


class TestBuildValidationSnapshot:
    """Tests for build_validation_snapshot async function."""

    @pytest.mark.asyncio
    async def test_builds_snapshot_with_zones_and_events(self) -> None:
        """Snapshot includes zones and events from adapter."""
        from app.engine.telegram_validator.validation_snapshot import (
            build_validation_snapshot,
        )

        adapter = _FakeSnapshotAdapter(
            zones=[
                {
                    "zone_id": "zone-1",
                    "zone_type": "DEMAND",
                    "top_price": Decimal("100.00"),
                    "bottom_price": Decimal("95.00"),
                    "strength": 8,
                    "is_active": True,
                    "created_at": datetime(2025, 1, 1, 8, 0, tzinfo=UTC),
                },
            ],
            events=[
                {
                    "event_id": "event-1",
                    "event_type": "CHOCH",
                    "timestamp": datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
                    "direction": "BUY",
                    "price": Decimal("98.00"),
                },
            ],
        )

        snapshot = await build_validation_snapshot(
            adapter,
            source="captain",
            chat_id=123,
            message_id=456,
            symbol="BTCUSDT",
            timeframe="H1",
            validated_at=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            internal_match=None,
        )

        assert snapshot.source == "captain"
        assert snapshot.chat_id == 123
        assert snapshot.message_id == 456
        assert snapshot.symbol == "BTCUSDT"
        assert snapshot.timeframe == "H1"
        assert len(snapshot.payload.zones) == 1
        assert snapshot.payload.zones[0].zone_id == "zone-1"
        assert len(snapshot.payload.structures) == 1
        assert snapshot.payload.structures[0].event_type == "CHOCH"

    @pytest.mark.asyncio
    async def test_builds_snapshot_with_internal_match(self) -> None:
        """Snapshot includes internal match when provided."""
        from app.engine.telegram_validator.validation_snapshot import (
            build_validation_snapshot,
        )

        adapter = _FakeSnapshotAdapter()

        internal_match = InternalMatchSnapshot(
            kind="trading_decision",
            internal_id="decision-123",
            timestamp="2025-01-01T10:00:00+00:00",
            direction="SELL",
            entry_price="50000.00",
        )

        snapshot = await build_validation_snapshot(
            adapter,
            source="captain",
            chat_id=123,
            message_id=456,
            symbol="BTCUSDT",
            timeframe=None,
            validated_at=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            internal_match=internal_match,
        )

        assert snapshot.payload.internal_match is not None
        assert snapshot.payload.internal_match.kind == "trading_decision"
        assert snapshot.payload.internal_match.internal_id == "decision-123"
        assert snapshot.payload.internal_match.direction == "SELL"

    @pytest.mark.asyncio
    async def test_builds_snapshot_with_empty_zones_and_events(self) -> None:
        """Snapshot handles empty zones and events gracefully."""
        from app.engine.telegram_validator.validation_snapshot import (
            build_validation_snapshot,
        )

        adapter = _FakeSnapshotAdapter()

        snapshot = await build_validation_snapshot(
            adapter,
            source="captain",
            chat_id=1,
            message_id=1,
            symbol="XAUUSD",
            timeframe="M15",
            validated_at=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            internal_match=None,
        )

        assert snapshot.payload.zones == []
        assert snapshot.payload.structures == []
        assert snapshot.payload.guards.news_guard_active is False
        assert snapshot.payload.regime.regime == "UNKNOWN"
