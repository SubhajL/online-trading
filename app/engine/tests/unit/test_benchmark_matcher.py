"""
Unit tests for external-vs-internal signal matching and scoring.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.engine.telegram_validator.benchmark_matcher import (
    ExternalSignal,
    InternalSignalCandidate,
    select_best_candidate,
    score_match,
)


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
