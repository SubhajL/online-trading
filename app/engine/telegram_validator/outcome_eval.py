"""
Simplified outcome evaluation for external signals using candle high/low.

This module provides both:
1. Legacy simple evaluation (evaluate_trade_outcome) - for backward compatibility
2. Full fill model evaluation (evaluate_trade_outcome_with_fill_model) - with costs
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from ..models import Candle
from .fill_model import (
    BracketSpec,
    CostConfig,
    FillSimulationResult,
    simulate_bracket_fills,
)


TradeDirection = Literal["BUY", "SELL"]
TradeOutcomeLabel = Literal["TP1", "SL", "NONE"]


@dataclass(frozen=True)
class TradeOutcome:
    """Simple outcome result for backward compatibility."""

    outcome: TradeOutcomeLabel
    hit_timestamp: datetime | None


@dataclass(frozen=True)
class DetailedTradeOutcome:
    """Detailed outcome with PnL and cost breakdown from fill model."""

    outcome: TradeOutcomeLabel
    hit_timestamp: datetime | None
    gross_pnl: Decimal
    fees: Decimal
    slippage_cost: Decimal
    funding_cost: Decimal
    net_pnl: Decimal
    candles_held: int
    fill_result: FillSimulationResult


def evaluate_trade_outcome(
    *,
    direction: TradeDirection,
    stop_loss: Decimal,
    take_profit: Decimal,
    candles: list[Candle],
) -> TradeOutcome:
    """Evaluate which level (TP1/SL) is hit first using candle ranges.

    This is the legacy simple evaluation for backward compatibility.
    For detailed cost analysis, use evaluate_trade_outcome_with_fill_model().
    """
    for candle in candles:
        if direction == "BUY":
            tp_hit = candle.high_price >= take_profit
            sl_hit = candle.low_price <= stop_loss
        else:
            tp_hit = candle.low_price <= take_profit
            sl_hit = candle.high_price >= stop_loss

        if sl_hit and tp_hit:
            return TradeOutcome(outcome="SL", hit_timestamp=candle.open_time)
        if sl_hit:
            return TradeOutcome(outcome="SL", hit_timestamp=candle.open_time)
        if tp_hit:
            return TradeOutcome(outcome="TP1", hit_timestamp=candle.open_time)

    return TradeOutcome(outcome="NONE", hit_timestamp=None)


def evaluate_trade_outcome_with_fill_model(
    *,
    direction: TradeDirection,
    entry_price: Decimal,
    stop_loss: Decimal,
    take_profit: Decimal,
    candles: list[Candle],
    cost_config: CostConfig | None = None,
    intrabar_policy: Literal["worst_case", "best_case"] = "worst_case",
    max_bars: int = 1000,
) -> DetailedTradeOutcome:
    """Evaluate trade outcome using the full fill model with costs.

    This provides detailed PnL breakdown including:
    - Fees (configurable BPS)
    - Slippage (entry and exit)
    - Funding costs (8-hour intervals)

    Args:
        direction: Trade direction (BUY or SELL)
        entry_price: Entry price for the trade
        stop_loss: Stop loss price
        take_profit: Take profit price (single TP for simplicity)
        candles: List of candles to evaluate against
        cost_config: Cost configuration (fees, slippage, funding)
        intrabar_policy: How to resolve SL+TP in same bar
        max_bars: Maximum bars to simulate

    Returns:
        DetailedTradeOutcome with full PnL breakdown
    """
    # Build bracket spec with single TP (full position)
    bracket = BracketSpec(
        side=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profits=[take_profit],
        tp_sizes=[Decimal("1.0")],  # Full position at TP
    )

    # Run fill simulation
    result = simulate_bracket_fills(
        candles=candles,
        bracket=bracket,
        cost_config=cost_config,
        intrabar_policy=intrabar_policy,
        max_bars=max_bars,
    )

    # Map fill model outcome to legacy outcome label
    if result.outcome == "SL":
        label: TradeOutcomeLabel = "SL"
    elif result.outcome in ("TP_FULL", "TP_PARTIAL"):
        label = "TP1"
    else:
        label = "NONE"

    return DetailedTradeOutcome(
        outcome=label,
        hit_timestamp=result.exit_timestamp,
        gross_pnl=result.gross_pnl,
        fees=result.fees,
        slippage_cost=result.slippage_cost,
        funding_cost=result.funding_cost,
        net_pnl=result.net_pnl,
        candles_held=result.candles_held,
        fill_result=result,
    )

