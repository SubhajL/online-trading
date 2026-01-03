"""
Matching and scoring for external Telegram signals vs internal signals/decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


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


def score_match(
    external: ExternalSignal,
    candidate: InternalSignalCandidate,
    *,
    time_window_seconds: int,
    entry_tolerance: Decimal,
) -> ValidationScore:
    if (
        external.direction
        and candidate.direction
        and external.direction != candidate.direction
    ):
        # Still calculate timing_delta_seconds for analysis even on direction mismatch
        timing_delta = (candidate.timestamp - external.timestamp).total_seconds()
        return ValidationScore(
            score=0.0,
            breakdown={
                "direction": 0.0,
                "time": 0.0,
                "entry": 0.0,
                "symbol": 0.0,
                "timeframe": 0.0,
                "timing_delta_seconds": timing_delta,
            },
        )

    breakdown: dict[str, float] = {}

    breakdown["direction"] = (
        1.0
        if external.direction
        and candidate.direction
        and external.direction == candidate.direction
        else 0.0
        if external.direction and candidate.direction
        else 0.0
    )

    delta = abs((candidate.timestamp - external.timestamp).total_seconds())
    # Store raw timing delta for analysis (positive = internal after external)
    breakdown["timing_delta_seconds"] = (
        candidate.timestamp - external.timestamp
    ).total_seconds()

    if delta >= time_window_seconds:
        breakdown["time"] = 0.0
    else:
        breakdown["time"] = 1.0 - (delta / float(time_window_seconds))

    breakdown["symbol"] = (
        1.0 if external.symbol and external.symbol == candidate.symbol else 0.0
    )
    breakdown["timeframe"] = (
        1.0
        if external.timeframe
        and candidate.timeframe
        and external.timeframe == candidate.timeframe
        else 0.0
        if external.timeframe and candidate.timeframe
        else 0.0
    )

    entry_component: float | None = None
    if external.entry_price is not None and candidate.entry_price is not None:
        if external.entry_price == 0:
            entry_component = 0.0
        else:
            rel_err = (
                abs(candidate.entry_price - external.entry_price) / external.entry_price
            )
            if rel_err >= entry_tolerance:
                entry_component = 0.0
            else:
                entry_component = float(Decimal("1") - (rel_err / entry_tolerance))
    breakdown["entry"] = entry_component if entry_component is not None else 0.0

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
) -> InternalSignalCandidate | None:
    best: InternalSignalCandidate | None = None
    best_score = -1.0
    best_delta = float("inf")

    for candidate in candidates:
        if external.symbol and candidate.symbol != external.symbol:
            continue

        if external.direction:
            if candidate.direction != external.direction:
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
