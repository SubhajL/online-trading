"""
Matching and scoring for external Telegram signals vs internal signals/decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class ExternalSignal:
    source: str
    chat_id: int
    message_id: int
    timestamp: datetime
    symbol: str | None
    timeframe: str | None
    direction: Literal["BUY", "SELL"] | None
    entry_price: Decimal | None


@dataclass(frozen=True)
class InternalSignalCandidate:
    kind: Literal["trading_decision", "smc_signal"]
    id: str
    timestamp: datetime
    symbol: str
    timeframe: str | None
    direction: Literal["BUY", "SELL"] | None
    entry_price: Decimal | None
    venue: str | None = None


@dataclass(frozen=True)
class ValidationScore:
    score: float
    breakdown: dict[str, float]


_WEIGHTS: dict[str, float] = {
    "direction": 0.4,
    "time": 0.3,
    "entry": 0.2,
    "symbol": 0.05,
    "timeframe": 0.05,
}


def _compute_direction_match(
    external_direction: Literal["BUY", "SELL"] | None,
    candidate_direction: Literal["BUY", "SELL"] | None,
) -> float | None:
    if external_direction is None or candidate_direction is None:
        return None
    return 1.0 if external_direction == candidate_direction else 0.0


def _compute_entry_delta_bps(
    external_entry: Decimal | None,
    candidate_entry: Decimal | None,
) -> float | None:
    if external_entry is None or candidate_entry is None:
        return None
    if external_entry == 0:
        return None
    rel_err = abs(candidate_entry - external_entry) / external_entry
    return float(rel_err * Decimal(10_000))


def _compute_entry_component(
    external_entry: Decimal | None,
    candidate_entry: Decimal | None,
    entry_tolerance: Decimal,
) -> float | None:
    if external_entry is None or candidate_entry is None:
        return None
    if external_entry == 0:
        return 0.0
    rel_err = abs(candidate_entry - external_entry) / external_entry
    if rel_err >= entry_tolerance:
        return 0.0
    return float(Decimal(1) - (rel_err / entry_tolerance))


def score_match(
    external: ExternalSignal,
    candidate: InternalSignalCandidate,
    *,
    time_window_seconds: int,
    entry_tolerance: Decimal,
) -> ValidationScore:
    direction_match = _compute_direction_match(external.direction, candidate.direction)
    entry_delta_bps = _compute_entry_delta_bps(
        external.entry_price,
        candidate.entry_price,
    )
    entry_component = _compute_entry_component(
        external.entry_price,
        candidate.entry_price,
        entry_tolerance,
    )

    timing_delta = (candidate.timestamp - external.timestamp).total_seconds()
    delta = abs(timing_delta)

    is_direction_mismatch = direction_match == 0.0 and (
        external.direction is not None and candidate.direction is not None
    )
    if is_direction_mismatch:
        breakdown: dict[str, float] = {
            "direction": 0.0,
            "time": 0.0,
            "entry": 0.0,
            "symbol": 0.0,
            "timeframe": 0.0,
            "timing_delta_seconds": timing_delta,
        }
        if direction_match is not None:
            breakdown["direction_match"] = direction_match
        if entry_delta_bps is not None:
            breakdown["entry_delta_bps"] = entry_delta_bps
        return ValidationScore(score=0.0, breakdown=breakdown)

    breakdown: dict[str, float] = {
        "direction": direction_match if direction_match is not None else 0.0,
        "time": max(0.0, 1.0 - (delta / float(time_window_seconds))),
        "entry": entry_component if entry_component is not None else 0.0,
        "symbol": (
            1.0
            if external.symbol and external.symbol == candidate.symbol
            else 0.0
        ),
        "timeframe": 1.0
        if external.timeframe
        and candidate.timeframe
        and external.timeframe == candidate.timeframe
        else 0.0,
        "timing_delta_seconds": timing_delta,
    }
    if direction_match is not None:
        breakdown["direction_match"] = direction_match
    if entry_delta_bps is not None:
        breakdown["entry_delta_bps"] = entry_delta_bps

    available = {
        "direction": breakdown["direction"],
        "time": breakdown["time"],
        "symbol": breakdown["symbol"],
        "timeframe": breakdown["timeframe"],
    }
    if external.entry_price is not None and candidate.entry_price is not None:
        available["entry"] = breakdown["entry"]

    denom = sum(_WEIGHTS[k] for k in available)
    score = sum(available[k] * _WEIGHTS[k] for k in available) / denom if denom else 0.0
    return ValidationScore(score=score, breakdown=breakdown)


def select_best_candidate(
    external: ExternalSignal,
    candidates: list[InternalSignalCandidate],
    *,
    time_window_seconds: int,
    entry_tolerance: Decimal,
    venue: str | None = None,
) -> InternalSignalCandidate | None:
    best: InternalSignalCandidate | None = None
    best_score = -1.0
    best_delta = float("inf")

    for candidate in candidates:
        if venue is not None and candidate.venue != venue:
            continue

        if external.symbol and candidate.symbol != external.symbol:
            continue

        if external.direction and candidate.direction != external.direction:
            continue

        delta = abs((candidate.timestamp - external.timestamp).total_seconds())
        if delta > time_window_seconds:
            continue

        scored = score_match(
            external,
            candidate,
            time_window_seconds=time_window_seconds,
            entry_tolerance=entry_tolerance,
        )
        if scored.score > best_score or (
            scored.score == best_score and delta < best_delta
        ):
            best = candidate
            best_score = scored.score
            best_delta = delta

    return best
