"""
Side-by-side comparison of Captain vs Internal outcomes.
Uses existing external_telegram_signal_validations to find matched pairs,
then evaluates both through the same fill model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from ..models import Candle
from .fill_model import (
    BracketSpec,
    CostConfig,
    FillSimulationResult,
    simulate_bracket_fills,
)


@dataclass(frozen=True)
class OutcomeResult:
    """Single outcome evaluation result."""

    direction: str
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    outcome: str  # TP_FULL, TP_PARTIAL, SL, TIMEOUT, NONE
    net_pnl: Decimal
    fees: Decimal
    slippage_cost: Decimal
    funding_cost: Decimal
    candles_held: int


@dataclass(frozen=True)
class MatchedComparison:
    """Comparison result for a single matched pair."""

    external_id: str
    internal_id: str | None
    symbol: str
    timestamp: datetime
    captain_outcome: OutcomeResult | None
    internal_outcome: OutcomeResult | None
    outcome_match: bool  # Same outcome (TP vs SL)
    pnl_delta: Decimal | None  # Internal PnL - Captain PnL


@dataclass(frozen=True)
class StreamComparisonResult:
    """Aggregated comparison result for a stream of signals."""

    captain_count: int
    internal_count: int
    matched_count: int
    captain_win_rate: Decimal
    internal_win_rate: Decimal
    avg_pnl_delta: Decimal
    timing_delta_seconds: float
    comparisons: tuple[MatchedComparison, ...]


def evaluate_bracket_outcome(
    *,
    direction: str,
    entry_price: Decimal,
    stop_loss: Decimal,
    take_profit: Decimal,
    candles: list[Candle],
    cost_config: CostConfig | None = None,
) -> OutcomeResult | None:
    """
    Evaluate a bracket trade using the fill model.

    Returns None if required fields are missing.
    """
    if not all([direction, entry_price, stop_loss, take_profit, candles]):
        return None

    bracket = BracketSpec(
        side=direction,  # type: ignore[arg-type]
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profits=[take_profit],  # type: ignore[arg-type]
        tp_sizes=[Decimal("1.0")],  # type: ignore[arg-type]
    )

    result = simulate_bracket_fills(
        candles=candles,
        bracket=bracket,
        cost_config=cost_config,
    )

    return OutcomeResult(
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        outcome=result.outcome,
        net_pnl=result.net_pnl,
        fees=result.fees,
        slippage_cost=result.slippage_cost,
        funding_cost=result.funding_cost,
        candles_held=result.candles_held,
    )


def _is_winning_outcome(outcome: str) -> bool:
    """Check if outcome is a win (TP hit)."""
    return outcome in ("TP_FULL", "TP_PARTIAL")


def compute_win_rate(outcomes: list[OutcomeResult]) -> Decimal:
    """Compute win rate from list of outcomes."""
    if not outcomes:
        return Decimal(0)

    decided = [o for o in outcomes if o.outcome in ("TP_FULL", "TP_PARTIAL", "SL")]
    if not decided:
        return Decimal(0)

    wins = sum(1 for o in decided if _is_winning_outcome(o.outcome))
    return Decimal(str(wins)) / Decimal(str(len(decided)))


async def compare_captain_vs_internal_outcomes(
    adapter: Any,
    *,
    source: str,
    start_time: datetime,
    end_time: datetime,
    cost_config: CostConfig | None = None,
    candle_lookback_bars: int = 100,
) -> StreamComparisonResult:
    """
    Compare Captain outcomes vs Internal outcomes using existing validation matches.

    Uses external_telegram_signal_validations to find matched pairs,
    then evaluates both through same fill model.

    Args:
        adapter: TimescaleDBAdapter instance
        source: Signal source (e.g., "captain")
        start_time: Start of time window
        end_time: End of time window
        cost_config: Cost configuration for fill model
        candle_lookback_bars: Number of candles to fetch for evaluation

    Returns:
        StreamComparisonResult with aggregated metrics
    """
    # 1. Get validations with matches (internal_kind IS NOT NULL)
    validations = await adapter.get_external_telegram_signal_validations(
        source=source,
        start_time=start_time,
        end_time=end_time,
    )

    # 2. Get corresponding external signals for full details
    signals = await adapter.get_external_telegram_signals(
        source=source,
        start_time=start_time,
        end_time=end_time,
    )

    # Build signal lookup by (chat_id, message_id)
    signal_lookup: dict[tuple[int, int], dict[str, Any]] = {
        (s["chat_id"], s["message_id"]): s for s in signals
    }

    comparisons: list[MatchedComparison] = []
    captain_outcomes: list[OutcomeResult] = []
    internal_outcomes: list[OutcomeResult] = []
    timing_deltas: list[float] = []

    for v in validations:
        chat_id = v["chat_id"]
        message_id = v["message_id"]
        internal_kind = v.get("internal_kind")
        internal_id = v.get("internal_id")
        internal_timestamp = v.get("internal_timestamp")

        # Get the external signal
        signal = signal_lookup.get((chat_id, message_id))
        if not signal:
            continue

        symbol = signal.get("symbol")
        direction = signal.get("direction")
        entry_price = signal.get("entry_price")
        stop_loss = signal.get("stop_loss")
        take_profits = signal.get("take_profits")
        timestamp = signal.get("timestamp")

        if not all([symbol, direction, entry_price, stop_loss, take_profits]):
            continue

        tp1 = take_profits[0] if isinstance(take_profits, list) else take_profits

        # Get candles for evaluation
        candle_end = timestamp + timedelta(hours=72)  # Look ahead for outcome
        candles = await adapter.get_candles(
            symbol=symbol,
            timeframe=signal.get("timeframe", "1h"),
            start_time=timestamp,
            end_time=candle_end,
            limit=candle_lookback_bars,
        )

        if not candles:
            continue

        # Evaluate Captain signal
        captain_result = evaluate_bracket_outcome(
            direction=direction,
            entry_price=Decimal(str(entry_price)),
            stop_loss=Decimal(str(stop_loss)),
            take_profit=Decimal(str(tp1)),
            candles=candles,
            cost_config=cost_config,
        )

        if captain_result:
            captain_outcomes.append(captain_result)

        # Evaluate matched internal decision if exists
        internal_result: OutcomeResult | None = None
        if internal_kind and internal_id:
            internal = await adapter.get_trading_decision_by_id(str(internal_id))
            if internal:
                internal_entry = internal.get("entry_price")
                internal_sl = internal.get("stop_loss")
                internal_tp = internal.get("take_profit")
                internal_dir = internal.get("action", internal.get("direction"))

                if all([internal_entry, internal_sl, internal_tp, internal_dir]):
                    internal_result = evaluate_bracket_outcome(
                        direction=str(internal_dir).upper(),
                        entry_price=Decimal(str(internal_entry)),
                        stop_loss=Decimal(str(internal_sl)),
                        take_profit=Decimal(str(internal_tp)),
                        candles=candles,
                        cost_config=cost_config,
                    )
                    if internal_result:
                        internal_outcomes.append(internal_result)

        # Compute timing delta if we have internal timestamp
        if internal_timestamp and timestamp:
            delta = (internal_timestamp - timestamp).total_seconds()
            timing_deltas.append(delta)

        # Build comparison
        pnl_delta: Decimal | None = None
        outcome_match = False
        if captain_result and internal_result:
            pnl_delta = internal_result.net_pnl - captain_result.net_pnl
            captain_won = _is_winning_outcome(captain_result.outcome)
            internal_won = _is_winning_outcome(internal_result.outcome)
            outcome_match = captain_won == internal_won

        comparisons.append(
            MatchedComparison(
                external_id=f"{chat_id}_{message_id}",
                internal_id=str(internal_id) if internal_id else None,
                symbol=symbol,
                timestamp=timestamp,
                captain_outcome=captain_result,
                internal_outcome=internal_result,
                outcome_match=outcome_match,
                pnl_delta=pnl_delta,
            ),
        )

    # Compute aggregate metrics
    captain_win_rate = compute_win_rate(captain_outcomes)
    internal_win_rate = compute_win_rate(internal_outcomes)

    pnl_deltas = [c.pnl_delta for c in comparisons if c.pnl_delta is not None]
    avg_pnl_delta = sum(pnl_deltas) / len(pnl_deltas) if pnl_deltas else Decimal(0)

    avg_timing_delta = sum(timing_deltas) / len(timing_deltas) if timing_deltas else 0.0

    return StreamComparisonResult(
        captain_count=len(captain_outcomes),
        internal_count=len(internal_outcomes),
        matched_count=len([c for c in comparisons if c.internal_outcome]),
        captain_win_rate=captain_win_rate,
        internal_win_rate=internal_win_rate,
        avg_pnl_delta=avg_pnl_delta,  # type: ignore[arg-type]
        timing_delta_seconds=avg_timing_delta,
        comparisons=tuple(comparisons),
    )
