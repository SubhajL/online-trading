"""Unit tests for zone identity extraction."""

from __future__ import annotations

import pytest

from app.engine.core.zone_identity import ZoneIdentity, extract_zone_identity


class TestExtractZoneIdentity:
    """Tests for extract_zone_identity function."""

    def test_extracts_from_nested_zone(self) -> None:
        """Should extract zone_id from metadata['zone']['zone_id']."""
        metadata = {
            "zone": {
                "zone_id": "zone_123",
                "zone_type": "DEMAND",
            },
        }

        result = extract_zone_identity(metadata)

        assert result is not None
        assert result.zone_id == "zone_123"
        assert result.zone_type == "DEMAND"

    def test_extracts_from_direct_zone_id(self) -> None:
        """Should extract zone_id from metadata['zone_id'] (flat structure)."""
        metadata = {
            "zone_id": "zone_456",
        }

        result = extract_zone_identity(metadata)

        assert result is not None
        assert result.zone_id == "zone_456"
        assert result.zone_type is None

    def test_returns_none_for_missing_zone(self) -> None:
        """Should return None if no zone_id can be found."""
        metadata = {
            "signal_id": "sig_123",
            "timeframe": "15m",
        }

        result = extract_zone_identity(metadata)

        assert result is None

    def test_returns_none_for_empty_zone_id(self) -> None:
        """Should return None if zone_id is empty string."""
        metadata = {
            "zone": {
                "zone_id": "",
            },
        }

        result = extract_zone_identity(metadata)

        assert result is None

    def test_returns_none_for_non_dict_metadata(self) -> None:
        """Should return None for non-dict metadata."""
        assert extract_zone_identity(None) is None  # type: ignore[arg-type]
        assert extract_zone_identity("not a dict") is None  # type: ignore[arg-type]
        assert extract_zone_identity(123) is None  # type: ignore[arg-type]
        assert extract_zone_identity([]) is None  # type: ignore[arg-type]

    def test_includes_zone_type_if_present(self) -> None:
        """Should include zone_type in result if available."""
        metadata = {
            "zone": {
                "zone_id": "zone_789",
                "zone_type": "SUPPLY",
            },
        }

        result = extract_zone_identity(metadata)

        assert result is not None
        assert result.zone_type == "SUPPLY"

    def test_handles_none_zone_type(self) -> None:
        """Should handle missing zone_type gracefully."""
        metadata = {
            "zone": {
                "zone_id": "zone_abc",
            },
        }

        result = extract_zone_identity(metadata)

        assert result is not None
        assert result.zone_id == "zone_abc"
        assert result.zone_type is None

    def test_converts_integer_zone_id_to_string(self) -> None:
        """Should convert integer zone_id to string."""
        metadata = {
            "zone": {
                "zone_id": 12345,
            },
        }

        result = extract_zone_identity(metadata)

        assert result is not None
        assert result.zone_id == "12345"

    def test_converts_uuid_zone_id_to_string(self) -> None:
        """Should convert UUID zone_id to string."""
        import uuid

        zone_uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        metadata = {
            "zone": {
                "zone_id": zone_uuid,
            },
        }

        result = extract_zone_identity(metadata)

        assert result is not None
        assert result.zone_id == "12345678-1234-5678-1234-567812345678"

    def test_converts_flat_uuid_zone_id_to_string(self) -> None:
        """Should convert flat UUID zone_id to string."""
        import uuid

        zone_uuid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        metadata = {
            "zone_id": zone_uuid,
        }

        result = extract_zone_identity(metadata)

        assert result is not None
        assert result.zone_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def test_returns_none_for_non_dict_zone(self) -> None:
        """Should return None if zone is not a dict."""
        metadata = {
            "zone": "not a dict",
        }

        result = extract_zone_identity(metadata)

        assert result is None

    def test_prefers_nested_zone_over_direct(self) -> None:
        """Should prefer nested zone object over direct zone_id."""
        metadata = {
            "zone": {
                "zone_id": "nested_zone",
                "zone_type": "DEMAND",
            },
            "zone_id": "direct_zone",
        }

        result = extract_zone_identity(metadata)

        assert result is not None
        assert result.zone_id == "nested_zone"


class TestZoneIdentity:
    """Tests for ZoneIdentity dataclass."""

    def test_is_frozen(self) -> None:
        """ZoneIdentity should be immutable (frozen)."""
        identity = ZoneIdentity(zone_id="zone_123", zone_type="DEMAND")

        with pytest.raises(AttributeError):
            identity.zone_id = "new_id"  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two ZoneIdentity with same values should be equal."""
        identity1 = ZoneIdentity(zone_id="zone_123", zone_type="DEMAND")
        identity2 = ZoneIdentity(zone_id="zone_123", zone_type="DEMAND")

        assert identity1 == identity2

    def test_default_zone_type_is_none(self) -> None:
        """zone_type should default to None."""
        identity = ZoneIdentity(zone_id="zone_123")

        assert identity.zone_type is None
