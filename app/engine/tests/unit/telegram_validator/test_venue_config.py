"""Tests for venue configuration loading and resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.engine.telegram_validator.benchmark_matcher import InternalSignalCandidate
from app.engine.telegram_validator.venue_config import (
    SourceVenueConfig,
    filter_candidates_by_venue,
    load_source_venue_configs,
    resolve_venue_for_signal,
)


class TestLoadSourceVenueConfigs:
    def test_parses_default_venue(self) -> None:
        environ = {"BENCHMARK_SOURCE_CAPTAIN_VENUE": "spot"}
        result = load_source_venue_configs(environ)

        assert "captain" in result
        assert result["captain"].source_id == "captain"
        assert result["captain"].default_venue == "spot"
        assert result["captain"].symbol_overrides == {}

    def test_parses_symbol_overrides(self) -> None:
        environ = {
            "BENCHMARK_SOURCE_CAPTAIN_VENUE": "spot",
            "BENCHMARK_SOURCE_CAPTAIN_VENUE_BTCUSDTP": "usdm",
            "BENCHMARK_SOURCE_CAPTAIN_VENUE_ETHUSDTP": "usdm",
        }
        result = load_source_venue_configs(environ)

        assert result["captain"].default_venue == "spot"
        assert result["captain"].symbol_overrides == {
            "BTCUSDTP": "usdm",
            "ETHUSDTP": "usdm",
        }

    def test_returns_empty_when_unset(self) -> None:
        environ: dict[str, str] = {}
        result = load_source_venue_configs(environ)

        assert result == {}

    def test_parses_multiple_sources(self) -> None:
        environ = {
            "BENCHMARK_SOURCE_CAPTAIN_VENUE": "spot",
            "BENCHMARK_SOURCE_WHALE_VENUE": "usdm",
        }
        result = load_source_venue_configs(environ)

        assert "captain" in result
        assert "whale" in result
        assert result["captain"].default_venue == "spot"
        assert result["whale"].default_venue == "usdm"


class TestResolveVenueForSignal:
    def test_symbol_override_takes_precedence(self) -> None:
        config = SourceVenueConfig(
            source_id="captain",
            default_venue="spot",
            symbol_overrides={"BTCUSDTP": "usdm"},
        )
        result = resolve_venue_for_signal(config, "BTCUSDTP")
        assert result == "usdm"

    def test_returns_default_when_no_override(self) -> None:
        config = SourceVenueConfig(
            source_id="captain",
            default_venue="spot",
            symbol_overrides={"BTCUSDTP": "usdm"},
        )
        result = resolve_venue_for_signal(config, "ETHUSDT")
        assert result == "spot"

    def test_returns_none_when_no_config(self) -> None:
        result = resolve_venue_for_signal(None, "BTCUSDT")
        assert result is None

    def test_returns_none_when_no_default_and_no_override(self) -> None:
        config = SourceVenueConfig(
            source_id="captain",
            default_venue=None,
            symbol_overrides={},
        )
        result = resolve_venue_for_signal(config, "BTCUSDT")
        assert result is None


class TestFilterCandidatesByVenue:
    @pytest.fixture
    def sample_candidates(self) -> list[InternalSignalCandidate]:
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        return [
            InternalSignalCandidate(
                kind="trading_decision",
                id="td-001",
                timestamp=ts,
                symbol="BTCUSDT",
                timeframe="15m",
                direction="BUY",
                entry_price=Decimal(50000),
                venue="spot",
            ),
            InternalSignalCandidate(
                kind="trading_decision",
                id="td-002",
                timestamp=ts,
                symbol="BTCUSDT",
                timeframe="15m",
                direction="BUY",
                entry_price=Decimal(50100),
                venue="usdm",
            ),
            InternalSignalCandidate(
                kind="smc_signal",
                id="smc-001",
                timestamp=ts,
                symbol="BTCUSDT",
                timeframe="15m",
                direction="BUY",
                entry_price=Decimal(50050),
                venue="spot",
            ),
        ]

    def test_filters_correctly_for_spot(
        self, sample_candidates: list[InternalSignalCandidate],
    ) -> None:
        result = filter_candidates_by_venue(sample_candidates, "spot")

        assert len(result) == 2
        assert all(c.venue == "spot" for c in result)
        assert {c.id for c in result} == {"td-001", "smc-001"}

    def test_filters_correctly_for_usdm(
        self, sample_candidates: list[InternalSignalCandidate],
    ) -> None:
        result = filter_candidates_by_venue(sample_candidates, "usdm")

        assert len(result) == 1
        assert result[0].id == "td-002"
        assert result[0].venue == "usdm"

    def test_returns_all_when_venue_is_none(
        self, sample_candidates: list[InternalSignalCandidate],
    ) -> None:
        result = filter_candidates_by_venue(sample_candidates, None)

        assert len(result) == 3
        assert result == sample_candidates

    def test_returns_empty_when_no_matches(
        self, sample_candidates: list[InternalSignalCandidate],
    ) -> None:
        result = filter_candidates_by_venue(sample_candidates, "coinm")

        assert result == []

    def test_handles_empty_candidates(self) -> None:
        result = filter_candidates_by_venue([], "spot")
        assert result == []
