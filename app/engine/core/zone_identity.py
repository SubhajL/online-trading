"""Extract zone identity from event metadata safely."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ZoneIdentity:
    """Extracted zone identity for cooldown keying.

    Immutable dataclass to ensure consistent hashing.
    """

    zone_id: str
    zone_type: str | None = None


def extract_zone_identity(metadata: Any) -> ZoneIdentity | None:
    """Extract zone identity from event metadata.

    Returns None if zone_id cannot be determined (cooldown should be skipped).

    Handles variations in metadata structure:
    - metadata["zone"]["zone_id"] (nested zone object)
    - metadata["zone_id"] (flat structure)

    Args:
        metadata: Event metadata dict.

    Returns:
        ZoneIdentity if zone_id found, None otherwise.
    """
    if not isinstance(metadata, dict):
        return None

    # Try nested zone object first (preferred)
    zone = metadata.get("zone")
    if isinstance(zone, dict):
        zone_id = zone.get("zone_id")
        # Convert any truthy value to string (handles UUID, int, etc.)
        if zone_id is not None:
            zone_id_str = str(zone_id)
            if zone_id_str:
                return ZoneIdentity(
                    zone_id=zone_id_str,
                    zone_type=zone.get("zone_type"),
                )

    # Fall back to direct zone_id
    zone_id = metadata.get("zone_id")
    # Convert any truthy value to string (handles UUID, int, etc.)
    if zone_id is not None:
        zone_id_str = str(zone_id)
        if zone_id_str:
            return ZoneIdentity(zone_id=zone_id_str)

    return None
