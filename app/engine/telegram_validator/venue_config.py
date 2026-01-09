"""
Venue configuration for benchmark validation.

Loads per-source venue configs from environment variables.
Captain signals don't specify venue, so venue is resolved from config.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .benchmark_matcher import InternalSignalCandidate

_SOURCE_VENUE_PATTERN = re.compile(r"^BENCHMARK_SOURCE_([A-Z0-9_]+)_VENUE$")
_SOURCE_SYMBOL_OVERRIDE_PATTERN = re.compile(
    r"^BENCHMARK_SOURCE_([A-Z0-9_]+)_VENUE_([A-Z0-9]+)$"
)


@dataclass(frozen=True)
class SourceVenueConfig:
    source_id: str
    default_venue: str | None
    symbol_overrides: dict[str, str]


def load_source_venue_configs(
    environ: Mapping[str, str],
) -> dict[str, SourceVenueConfig]:
    sources: dict[str, dict[str, str | None | dict[str, str]]] = {}

    for key, value in environ.items():
        match = _SOURCE_VENUE_PATTERN.match(key)
        if match:
            source_id = match.group(1).lower()
            if source_id not in sources:
                sources[source_id] = {"default_venue": value, "symbol_overrides": {}}
            else:
                sources[source_id]["default_venue"] = value
            continue

        override_match = _SOURCE_SYMBOL_OVERRIDE_PATTERN.match(key)
        if override_match:
            source_id = override_match.group(1).lower()
            symbol = override_match.group(2)
            if source_id not in sources:
                sources[source_id] = {"default_venue": None, "symbol_overrides": {}}
            overrides = sources[source_id]["symbol_overrides"]
            if isinstance(overrides, dict):
                overrides[symbol] = value

    result: dict[str, SourceVenueConfig] = {}
    for source_id, data in sources.items():
        default_venue = data.get("default_venue")
        symbol_overrides = data.get("symbol_overrides", {})
        result[source_id] = SourceVenueConfig(
            source_id=source_id,
            default_venue=default_venue if isinstance(default_venue, str) else None,
            symbol_overrides=symbol_overrides if isinstance(symbol_overrides, dict) else {},
        )

    return result


def resolve_venue_for_signal(
    config: SourceVenueConfig | None,
    symbol: str,
) -> str | None:
    if config is None:
        return None
    if symbol in config.symbol_overrides:
        return config.symbol_overrides[symbol]
    return config.default_venue


def filter_candidates_by_venue(
    candidates: list[InternalSignalCandidate],
    venue: str | None,
) -> list[InternalSignalCandidate]:
    if venue is None:
        return candidates
    return [c for c in candidates if c.venue == venue]
