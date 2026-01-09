"""Tests for benchmark matcher venue filtering integration."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.engine.telegram_validator.benchmark_matcher import (
    ExternalSignal,
    InternalSignalCandidate,
    score_match,
    select_best_candidate,
)


class TestSelectBestCandidateWithVenueFilter:
    @pytest.fixture
    def external_signal(self) -> ExternalSignal:
        return ExternalSignal(
            source="captain",
            chat_id=123,
            message_id=456,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            symbol="BTCUSDT",
            timeframe="15m",
            direction="BUY",
            entry_price=Decimal("50000"),
        )

    @pytest.fixture
    def mixed_venue_candidates(self) -> list[InternalSignalCandidate]:
        ts = datetime(2025, 1, 1, 12, 0, 30, tzinfo=timezone.utc)
        return [
            InternalSignalCandidate(
                kind="trading_decision",
                id="td-spot-001",
                timestamp=ts,
                symbol="BTCUSDT",
                timeframe="15m",
                direction="BUY",
                entry_price=Decimal("50010"),
                venue="spot",
            ),
            InternalSignalCandidate(
                kind="trading_decision",
                id="td-usdm-001",
                timestamp=ts,
                symbol="BTCUSDT",
                timeframe="15m",
                direction="BUY",
                entry_price=Decimal("50005"),
                venue="usdm",
            ),
            InternalSignalCandidate(
                kind="smc_signal",
                id="smc-spot-001",
                timestamp=ts,
                symbol="BTCUSDT",
                timeframe="15m",
                direction="BUY",
                entry_price=Decimal("50020"),
                venue="spot",
            ),
        ]

    def test_with_venue_filter_spot(
        self,
        external_signal: ExternalSignal,
        mixed_venue_candidates: list[InternalSignalCandidate],
    ) -> None:
        result = select_best_candidate(
            external_signal,
            mixed_venue_candidates,
            time_window_seconds=300,
            entry_tolerance=Decimal("0.002"),
            venue="spot",
        )

        assert result is not None
        assert result.venue == "spot"
        assert result.id in {"td-spot-001", "smc-spot-001"}

    def test_with_venue_filter_usdm(
        self,
        external_signal: ExternalSignal,
        mixed_venue_candidates: list[InternalSignalCandidate],
    ) -> None:
        result = select_best_candidate(
            external_signal,
            mixed_venue_candidates,
            time_window_seconds=300,
            entry_tolerance=Decimal("0.002"),
            venue="usdm",
        )

        assert result is not None
        assert result.venue == "usdm"
        assert result.id == "td-usdm-001"

    def test_returns_none_when_venue_has_no_matches(
        self,
        external_signal: ExternalSignal,
        mixed_venue_candidates: list[InternalSignalCandidate],
    ) -> None:
        result = select_best_candidate(
            external_signal,
            mixed_venue_candidates,
            time_window_seconds=300,
            entry_tolerance=Decimal("0.002"),
            venue="coinm",
        )

        assert result is None

    def test_no_venue_filter_returns_best_match(
        self,
        external_signal: ExternalSignal,
        mixed_venue_candidates: list[InternalSignalCandidate],
    ) -> None:
        result = select_best_candidate(
            external_signal,
            mixed_venue_candidates,
            time_window_seconds=300,
            entry_tolerance=Decimal("0.002"),
        )

        assert result is not None


class TestScoreMatchUnchangedByVenueFilter:
    def test_score_match_unchanged_by_venue_field(self) -> None:
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        external = ExternalSignal(
            source="captain",
            chat_id=123,
            message_id=456,
            timestamp=ts,
            symbol="BTCUSDT",
            timeframe="15m",
            direction="BUY",
            entry_price=Decimal("50000"),
        )

        candidate_no_venue = InternalSignalCandidate(
            kind="trading_decision",
            id="td-001",
            timestamp=ts,
            symbol="BTCUSDT",
            timeframe="15m",
            direction="BUY",
            entry_price=Decimal("50000"),
            venue=None,
        )

        candidate_with_venue = InternalSignalCandidate(
            kind="trading_decision",
            id="td-001",
            timestamp=ts,
            symbol="BTCUSDT",
            timeframe="15m",
            direction="BUY",
            entry_price=Decimal("50000"),
            venue="spot",
        )

        score_no_venue = score_match(
            external,
            candidate_no_venue,
            time_window_seconds=300,
            entry_tolerance=Decimal("0.002"),
        )

        score_with_venue = score_match(
            external,
            candidate_with_venue,
            time_window_seconds=300,
            entry_tolerance=Decimal("0.002"),
        )

        assert score_no_venue.score == score_with_venue.score
        assert score_no_venue.breakdown["direction"] == score_with_venue.breakdown["direction"]
        assert score_no_venue.breakdown["time"] == score_with_venue.breakdown["time"]
        assert score_no_venue.breakdown["entry"] == score_with_venue.breakdown["entry"]
