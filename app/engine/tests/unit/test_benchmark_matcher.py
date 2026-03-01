"""
Unit tests for external-vs-internal signal matching and scoring.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.engine.telegram_validator.benchmark_matcher import (
    ExternalSignal,
    InternalSignalCandidate,
    score_match,
    select_best_candidate,
)
from app.engine.telegram_validator.benchmark_validator import _empty_score

ENTRY_DELTA_BPS = 20.0
TIMING_DELTA_POSITIVE = 30.0
TIMING_DELTA_NEGATIVE = -45.0
TIMING_DELTA_ON_MISMATCH = 15.0


def test_select_best_candidate_prefers_direction_match_over_closer_time() -> None:
    t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
    external = ExternalSignal(
        source="captain",
        chat_id=1,
        message_id=1,
        timestamp=t0,
        symbol="BTCUSDT",
        timeframe="30m",
        direction="SELL",
        entry_price=Decimal("100.00"),
    )

    buy_close = InternalSignalCandidate(
        kind="trading_decision",
        id="buy",
        timestamp=t0 + timedelta(seconds=1),
        symbol="BTCUSDT",
        timeframe=None,
        direction="BUY",
        entry_price=Decimal("100.00"),
    )
    sell_farther = InternalSignalCandidate(
        kind="trading_decision",
        id="sell",
        timestamp=t0 + timedelta(seconds=30),
        symbol="BTCUSDT",
        timeframe=None,
        direction="SELL",
        entry_price=Decimal("100.00"),
    )

    match = select_best_candidate(
        external,
        [buy_close, sell_farther],
        time_window_seconds=60,
        entry_tolerance=Decimal("0.002"),
    )

    assert match is not None
    assert match.id == "sell"


def test_score_match_entry_proximity_respects_tolerance() -> None:
    t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
    external = ExternalSignal(
        source="captain",
        chat_id=1,
        message_id=1,
        timestamp=t0,
        symbol="BTCUSDT",
        timeframe="30m",
        direction="SELL",
        entry_price=Decimal("100.00"),
    )
    candidate_good = InternalSignalCandidate(
        kind="trading_decision",
        id="good",
        timestamp=t0,
        symbol="BTCUSDT",
        timeframe=None,
        direction="SELL",
        entry_price=Decimal("100.10"),  # 0.1%
    )
    candidate_bad = InternalSignalCandidate(
        kind="trading_decision",
        id="bad",
        timestamp=t0,
        symbol="BTCUSDT",
        timeframe=None,
        direction="SELL",
        entry_price=Decimal("101.00"),  # 1%
    )

    good = score_match(
        external,
        candidate_good,
        time_window_seconds=300,
        entry_tolerance=Decimal("0.002"),
    )
    bad = score_match(
        external,
        candidate_bad,
        time_window_seconds=300,
        entry_tolerance=Decimal("0.002"),
    )

    assert good.score > bad.score
    assert bad.breakdown["entry"] == 0.0


def test_score_match_reweights_when_entry_missing() -> None:
    t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
    external = ExternalSignal(
        source="captain",
        chat_id=1,
        message_id=1,
        timestamp=t0,
        symbol="EURUSD",
        timeframe="1h",
        direction="BUY",
        entry_price=None,
    )
    candidate = InternalSignalCandidate(
        kind="smc_signal",
        id="x",
        timestamp=t0 + timedelta(seconds=60),
        symbol="EURUSD",
        timeframe="1h",
        direction="BUY",
        entry_price=None,
    )

    result = score_match(
        external,
        candidate,
        time_window_seconds=300,
        entry_tolerance=Decimal("0.002"),
    )

    assert 0.0 <= result.score <= 1.0
    assert result.breakdown["direction"] == 1.0


class TestTimingDeltaSeconds:
    """Tests for timing_delta_seconds in breakdown."""

    def test_timing_delta_seconds_positive_when_internal_after_external(self) -> None:
        """timing_delta_seconds positive when internal after external."""
        t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
        external = ExternalSignal(
            source="captain",
            chat_id=1,
            message_id=1,
            timestamp=t0,
            symbol="BTCUSDT",
            timeframe="30m",
            direction="BUY",
            entry_price=Decimal("100.00"),
        )
        candidate = InternalSignalCandidate(
            kind="trading_decision",
            id="internal",
            timestamp=t0 + timedelta(seconds=30),
            symbol="BTCUSDT",
            timeframe=None,
            direction="BUY",
            entry_price=Decimal("100.00"),
        )

        result = score_match(
            external,
            candidate,
            time_window_seconds=60,
            entry_tolerance=Decimal("0.002"),
        )

        assert "timing_delta_seconds" in result.breakdown
        assert result.breakdown["timing_delta_seconds"] == TIMING_DELTA_POSITIVE

    def test_timing_delta_seconds_negative_when_internal_before_external(self) -> None:
        """timing_delta_seconds negative when internal before external."""
        t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
        external = ExternalSignal(
            source="captain",
            chat_id=1,
            message_id=1,
            timestamp=t0,
            symbol="BTCUSDT",
            timeframe="30m",
            direction="SELL",
            entry_price=Decimal("100.00"),
        )
        candidate = InternalSignalCandidate(
            kind="trading_decision",
            id="internal",
            timestamp=t0 - timedelta(seconds=45),
            symbol="BTCUSDT",
            timeframe=None,
            direction="SELL",
            entry_price=Decimal("100.00"),
        )

        result = score_match(
            external,
            candidate,
            time_window_seconds=60,
            entry_tolerance=Decimal("0.002"),
        )

        assert result.breakdown["timing_delta_seconds"] == TIMING_DELTA_NEGATIVE

    def test_timing_delta_seconds_zero_when_timestamps_match(self) -> None:
        """timing_delta_seconds is zero when timestamps are identical."""
        t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
        external = ExternalSignal(
            source="captain",
            chat_id=1,
            message_id=1,
            timestamp=t0,
            symbol="BTCUSDT",
            timeframe="30m",
            direction="BUY",
            entry_price=Decimal("100.00"),
        )
        candidate = InternalSignalCandidate(
            kind="trading_decision",
            id="internal",
            timestamp=t0,
            symbol="BTCUSDT",
            timeframe=None,
            direction="BUY",
            entry_price=Decimal("100.00"),
        )

        result = score_match(
            external,
            candidate,
            time_window_seconds=60,
            entry_tolerance=Decimal("0.002"),
        )

        assert result.breakdown["timing_delta_seconds"] == 0.0

    def test_timing_delta_seconds_present_on_direction_mismatch(self) -> None:
        """timing_delta_seconds is still calculated even when directions don't match."""
        t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
        external = ExternalSignal(
            source="captain",
            chat_id=1,
            message_id=1,
            timestamp=t0,
            symbol="BTCUSDT",
            timeframe="30m",
            direction="BUY",
            entry_price=Decimal("100.00"),
        )
        candidate = InternalSignalCandidate(
            kind="trading_decision",
            id="internal",
            timestamp=t0 + timedelta(seconds=15),
            symbol="BTCUSDT",
            timeframe=None,
            direction="SELL",  # Mismatch
            entry_price=Decimal("100.00"),
        )

        result = score_match(
            external,
            candidate,
            time_window_seconds=60,
            entry_tolerance=Decimal("0.002"),
        )

        # Score is 0 due to direction mismatch, but timing_delta is still present
        assert result.score == 0.0
        assert result.breakdown["timing_delta_seconds"] == TIMING_DELTA_ON_MISMATCH


class TestEmptyScoreTimingDelta:
    """Tests for _empty_score() timing_delta_seconds handling."""

    def test_empty_score_omits_timing_delta_seconds(self) -> None:
        """_empty_score() omits timing delta and metrics."""
        empty = _empty_score()

        # timing_delta_seconds should NOT be present in empty breakdown
        # to avoid polluting latency analysis with artificial zeros
        assert "timing_delta_seconds" not in empty.breakdown
        assert "entry_delta_bps" not in empty.breakdown
        assert "direction_match" not in empty.breakdown
        assert empty.score == 0.0
        assert empty.breakdown["direction"] == 0.0
        assert empty.breakdown["time"] == 0.0


class TestMatchBreakdownMetrics:
    """Tests for additional breakdown metrics."""

    def test_breakdown_includes_entry_delta_bps(self) -> None:
        """Adds entry_delta_bps when both entries exist."""
        t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
        external = ExternalSignal(
            source="captain",
            chat_id=1,
            message_id=1,
            timestamp=t0,
            symbol="BTCUSDT",
            timeframe="30m",
            direction="BUY",
            entry_price=Decimal(50_000),
        )
        candidate = InternalSignalCandidate(
            kind="trading_decision",
            id="internal",
            timestamp=t0,
            symbol="BTCUSDT",
            timeframe=None,
            direction="BUY",
            entry_price=Decimal(50_100),
        )

        result = score_match(
            external,
            candidate,
            time_window_seconds=300,
            entry_tolerance=Decimal("0.002"),
        )

        assert result.breakdown["entry_delta_bps"] == ENTRY_DELTA_BPS

    def test_breakdown_includes_direction_match(self) -> None:
        """Adds direction_match when both directions exist."""
        t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
        external = ExternalSignal(
            source="captain",
            chat_id=1,
            message_id=1,
            timestamp=t0,
            symbol="BTCUSDT",
            timeframe="30m",
            direction="BUY",
            entry_price=Decimal(50_000),
        )
        candidate = InternalSignalCandidate(
            kind="trading_decision",
            id="internal",
            timestamp=t0,
            symbol="BTCUSDT",
            timeframe=None,
            direction="BUY",
            entry_price=Decimal(50_000),
        )

        result = score_match(
            external,
            candidate,
            time_window_seconds=300,
            entry_tolerance=Decimal("0.002"),
        )

        assert result.breakdown["direction_match"] == 1.0

    def test_direction_mismatch_includes_direction_match_zero(self) -> None:
        """Direction mismatch includes direction_match=0.0."""
        t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
        external = ExternalSignal(
            source="captain",
            chat_id=1,
            message_id=1,
            timestamp=t0,
            symbol="BTCUSDT",
            timeframe="30m",
            direction="BUY",
            entry_price=Decimal(50_000),
        )
        candidate = InternalSignalCandidate(
            kind="trading_decision",
            id="internal",
            timestamp=t0,
            symbol="BTCUSDT",
            timeframe=None,
            direction="SELL",
            entry_price=Decimal(50_000),
        )

        result = score_match(
            external,
            candidate,
            time_window_seconds=300,
            entry_tolerance=Decimal("0.002"),
        )

        assert result.breakdown["direction_match"] == 0.0
