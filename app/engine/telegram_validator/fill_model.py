"""
Bracket trade fill simulation with configurable costs.

Simulates bracket orders (entry + SL + TPs) against candle data
with realistic fee, slippage, and funding cost models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from ..models import Candle


# Type aliases
Side = Literal["BUY", "SELL"]
Outcome = Literal["TP_FULL", "TP_PARTIAL", "SL", "TIMEOUT", "NONE"]
IntrabarPolicy = Literal["worst_case", "best_case"]


@dataclass(frozen=True)
class BracketSpec:
    """Trade bracket specification."""

    side: Side
    entry_price: Decimal
    stop_loss: Decimal
    take_profits: tuple[Decimal, ...]  # Ordered TP levels
    tp_sizes: tuple[Decimal, ...]  # Fraction at each TP (sum=1.0)

    def __post_init__(self) -> None:
        if len(self.take_profits) != len(self.tp_sizes):
            raise ValueError("take_profits and tp_sizes must have same length")
        if self.take_profits and abs(sum(self.tp_sizes) - Decimal("1")) > Decimal("0.001"):
            raise ValueError("tp_sizes must sum to 1.0")


@dataclass(frozen=True)
class CostConfig:
    """Trading cost configuration."""

    fee_bps: Decimal = Decimal("10")  # 0.1% = 10 bps
    slippage_bps: Decimal = Decimal("5")  # 0.05% = 5 bps
    funding_rate_8h: Decimal = Decimal("1")  # 0.01% = 1 bp per 8h


@dataclass(frozen=True)
class Fill:
    """Record of a single fill event."""

    timestamp: datetime
    price: Decimal
    size_fraction: Decimal  # Fraction of original position
    fill_type: Literal["TP", "SL"]
    level_index: int | None  # TP level index (0, 1, 2...) or None for SL


@dataclass(frozen=True)
class FillSimulationResult:
    """Result of bracket fill simulation."""

    outcome: Outcome
    fills: tuple[Fill, ...]
    gross_pnl: Decimal
    fees: Decimal
    slippage_cost: Decimal
    funding_cost: Decimal
    net_pnl: Decimal
    exit_timestamp: datetime | None
    candles_held: int


def check_level_touch(
    candle: Candle,
    level: Decimal,
    side: Side,
    is_stop: bool,
) -> bool:
    """Check if candle touches a price level.

    For BUY:
      - TP touched when high >= level
      - SL touched when low <= level
    For SELL:
      - TP touched when low <= level
      - SL touched when high >= level

    Pure function.
    """
    if side == "BUY":
        if is_stop:
            return candle.low_price <= level
        else:
            return candle.high_price >= level
    else:  # SELL
        if is_stop:
            return candle.high_price >= level
        else:
            return candle.low_price <= level


def resolve_intrabar_conflict(
    sl_touched: bool,
    tp_touched: bool,
    policy: IntrabarPolicy,
) -> Literal["SL", "TP"]:
    """Resolve conflict when both SL and TP touched in same candle.

    worst_case: SL wins (conservative)
    best_case: TP wins (optimistic)

    Pure function.
    """
    if policy == "worst_case":
        return "SL"
    else:  # best_case
        return "TP"


def apply_slippage(
    price: Decimal,
    side: Side,
    slippage_bps: Decimal,
    is_entry: bool,
) -> Decimal:
    """Adjust fill price by slippage in adverse direction.

    Entry slippage:
      - BUY: price goes UP (worse entry)
      - SELL: price goes DOWN (worse entry)
    Exit slippage:
      - BUY closing (sell): price goes DOWN (worse exit)
      - SELL closing (buy): price goes UP (worse exit)

    Pure function.
    """
    if slippage_bps == Decimal("0"):
        return price

    slip_factor = slippage_bps / Decimal("10000")
    slip_amount = price * slip_factor

    if side == "BUY":
        if is_entry:
            return price + slip_amount  # Worse entry (higher)
        else:
            return price - slip_amount  # Worse exit (lower)
    else:  # SELL
        if is_entry:
            return price - slip_amount  # Worse entry (lower)
        else:
            return price + slip_amount  # Worse exit (higher)


def compute_fees(notional: Decimal, fee_bps: Decimal) -> Decimal:
    """Compute trading fees.

    Fee = notional * (fee_bps / 10000)

    Pure function.
    """
    return notional * fee_bps / Decimal("10000")


def compute_funding_cost(
    entry_ts: datetime,
    exit_ts: datetime,
    notional: Decimal,
    funding_rate_8h: Decimal,
) -> Decimal:
    """Compute funding cost for position hold period.

    Funding intervals: 00:00, 08:00, 16:00 UTC
    Cost = notional * (funding_rate_8h / 10000) * num_funding_periods

    Pure function.
    """
    funding_hours = [0, 8, 16]  # 00:00, 08:00, 16:00 UTC
    num_periods = 0

    # Normalize to same day base for iteration
    current = entry_ts
    while current < exit_ts:
        hour = current.hour
        # Find next funding time
        next_funding_hour = None
        for fh in funding_hours:
            if fh > hour:
                next_funding_hour = fh
                break

        if next_funding_hour is None:
            # Next funding is 00:00 next day
            next_day = (current + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            if next_day <= exit_ts:
                num_periods += 1
            current = next_day
        else:
            # Next funding is same day
            next_funding = current.replace(
                hour=next_funding_hour, minute=0, second=0, microsecond=0
            )
            if next_funding <= exit_ts:
                num_periods += 1
            current = next_funding

        # Safety: prevent infinite loop
        if current == entry_ts:
            break

    return notional * funding_rate_8h / Decimal("10000") * num_periods


def simulate_bracket_fills(
    candles: list[Candle],
    bracket: BracketSpec,
    *,
    intrabar_policy: IntrabarPolicy = "worst_case",
    cost_config: CostConfig | None = None,
    max_bars: int = 500,
) -> FillSimulationResult:
    """Simulate bracket order execution against candle data.

    Iterates through candles, checks for SL/TP touches,
    applies intrabar conflict policy, computes fills and costs.

    Returns FillSimulationResult with outcome, fills, and all costs.

    Pure function.
    """
    config = cost_config or CostConfig()

    if not candles:
        return FillSimulationResult(
            outcome="NONE",
            fills=(),
            gross_pnl=Decimal("0"),
            fees=Decimal("0"),
            slippage_cost=Decimal("0"),
            funding_cost=Decimal("0"),
            net_pnl=Decimal("0"),
            exit_timestamp=None,
            candles_held=0,
        )

    # Track which TPs have been filled
    tp_filled = [False] * len(bracket.take_profits)
    fills: list[Fill] = []
    remaining_position = Decimal("1.0")  # Fraction of position remaining
    entry_ts = candles[0].open_time

    # Apply entry slippage
    actual_entry = apply_slippage(
        bracket.entry_price, bracket.side, config.slippage_bps, is_entry=True
    )
    entry_slippage_cost = abs(actual_entry - bracket.entry_price)

    bars_processed = 0
    exit_ts: datetime | None = None

    for candle in candles[:max_bars]:
        bars_processed += 1

        # Check SL touch
        sl_touched = check_level_touch(candle, bracket.stop_loss, bracket.side, is_stop=True)

        # Check each unfilled TP
        tp_touched_indices: list[int] = []
        for i, tp_level in enumerate(bracket.take_profits):
            if not tp_filled[i]:
                if check_level_touch(candle, tp_level, bracket.side, is_stop=False):
                    tp_touched_indices.append(i)

        any_tp_touched = len(tp_touched_indices) > 0

        # Handle intrabar conflict
        if sl_touched and any_tp_touched:
            winner = resolve_intrabar_conflict(sl_touched, any_tp_touched, intrabar_policy)
            if winner == "SL":
                # SL wins - close entire remaining position
                fills.append(
                    Fill(
                        timestamp=candle.open_time,
                        price=bracket.stop_loss,
                        size_fraction=remaining_position,
                        fill_type="SL",
                        level_index=None,
                    )
                )
                exit_ts = candle.open_time
                break
            else:
                # TP wins - fill available TPs
                for i in tp_touched_indices:
                    tp_filled[i] = True
                    fills.append(
                        Fill(
                            timestamp=candle.open_time,
                            price=bracket.take_profits[i],
                            size_fraction=bracket.tp_sizes[i],
                            fill_type="TP",
                            level_index=i,
                        )
                    )
                    remaining_position -= bracket.tp_sizes[i]

                if remaining_position <= Decimal("0.001"):
                    exit_ts = candle.open_time
                    break

        elif sl_touched:
            # SL hit - close remaining position
            fills.append(
                Fill(
                    timestamp=candle.open_time,
                    price=bracket.stop_loss,
                    size_fraction=remaining_position,
                    fill_type="SL",
                    level_index=None,
                )
            )
            exit_ts = candle.open_time
            break

        elif any_tp_touched:
            # TPs hit - fill them
            for i in tp_touched_indices:
                tp_filled[i] = True
                fills.append(
                    Fill(
                        timestamp=candle.open_time,
                        price=bracket.take_profits[i],
                        size_fraction=bracket.tp_sizes[i],
                        fill_type="TP",
                        level_index=i,
                    )
                )
                remaining_position -= bracket.tp_sizes[i]

            if remaining_position <= Decimal("0.001"):
                exit_ts = candle.open_time
                break

    # Determine outcome
    if not fills:
        if bars_processed >= max_bars:
            outcome: Outcome = "TIMEOUT"
        else:
            outcome = "NONE"
    else:
        has_sl = any(f.fill_type == "SL" for f in fills)
        if has_sl:
            outcome = "SL"
        elif remaining_position <= Decimal("0.001"):
            outcome = "TP_FULL"
        else:
            outcome = "TP_PARTIAL"

    # Compute PnL and costs
    gross_pnl = Decimal("0")
    exit_slippage_cost = Decimal("0")

    for fill in fills:
        # Apply exit slippage
        actual_exit = apply_slippage(
            fill.price, bracket.side, config.slippage_bps, is_entry=False
        )
        exit_slippage_cost += abs(actual_exit - fill.price) * fill.size_fraction

        # Compute PnL for this fill
        if bracket.side == "BUY":
            pnl = (actual_exit - actual_entry) * fill.size_fraction
        else:  # SELL
            pnl = (actual_entry - actual_exit) * fill.size_fraction
        gross_pnl += pnl

    total_slippage = entry_slippage_cost + exit_slippage_cost

    # Compute fees (on notional, approximated as entry price)
    # Fee on entry + fee on exit
    total_notional = bracket.entry_price * Decimal("2")  # Entry + exit
    fees = compute_fees(total_notional, config.fee_bps)

    # Compute funding cost
    if exit_ts:
        funding_cost = compute_funding_cost(
            entry_ts, exit_ts, bracket.entry_price, config.funding_rate_8h
        )
    else:
        funding_cost = Decimal("0")

    net_pnl = gross_pnl - fees - total_slippage - funding_cost

    return FillSimulationResult(
        outcome=outcome,
        fills=tuple(fills),
        gross_pnl=gross_pnl,
        fees=fees,
        slippage_cost=total_slippage,
        funding_cost=funding_cost,
        net_pnl=net_pnl,
        exit_timestamp=exit_ts,
        candles_held=bars_processed,
    )
