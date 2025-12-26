"""
Simplified outcome evaluation for external signals using candle high/low.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from ..models import Candle


TradeDirection = Literal["BUY", "SELL"]
TradeOutcomeLabel = Literal["TP1", "SL", "NONE"]


@dataclass(frozen=True)
class TradeOutcome:
    outcome: TradeOutcomeLabel
    hit_timestamp: datetime | None


def evaluate_trade_outcome(
    *,
    direction: TradeDirection,
    stop_loss: Decimal,
    take_profit: Decimal,
    candles: list[Candle],
) -> TradeOutcome:
    """Evaluate which level (TP1/SL) is hit first using candle ranges."""
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

