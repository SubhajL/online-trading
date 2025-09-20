"""
Position tracker for managing trading positions.
Following C-4: Prefer simple, composable, testable functions.
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from app.engine.models import PositionSide

logger = logging.getLogger(__name__)


class CloseReason(Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TIME_STOP = "TIME_STOP"
    MANUAL = "MANUAL"


@dataclass
class Position:
    symbol: str
    side: PositionSide
    quantity: Decimal
    entry_price: Decimal
    realized_pnl: Decimal
    total_commission: Decimal
    open_time: datetime
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    max_hold_time: Optional[timedelta] = None
    is_closed: bool = False
    close_time: Optional[datetime] = None


@dataclass
class OrderFill:
    symbol: str
    side: PositionSide
    quantity: Decimal
    price: Decimal
    commission: Decimal
    timestamp: datetime


@dataclass
class MarketData:
    symbol: str
    current_price: Decimal
    bid: Decimal
    ask: Decimal
    timestamp: datetime


@dataclass
class CloseSignal:
    should_close: bool
    reason: Optional[CloseReason] = None
    close_price: Optional[Decimal] = None


def update_position(
    fill: OrderFill,
    existing_position: Optional[Position] = None
) -> Position:
    """
    Updates position state from order fills.
    Calculates average entry price, realized PnL, and commission costs accurately.
    """
    if existing_position is None:
        # Create new position
        return Position(
            symbol=fill.symbol,
            side=fill.side,
            quantity=fill.quantity,
            entry_price=fill.price,
            realized_pnl=-fill.commission,  # Start with negative commission
            total_commission=fill.commission,
            open_time=fill.timestamp
        )

    # Update existing position
    position = existing_position

    # Check if this is adding to position or closing
    is_same_side = fill.side == position.side

    if is_same_side:
        # Adding to position - update average entry price
        total_value = (position.quantity * position.entry_price) + (fill.quantity * fill.price)
        new_quantity = position.quantity + fill.quantity

        new_position = Position(
            symbol=position.symbol,
            side=position.side,
            quantity=new_quantity,
            entry_price=total_value / new_quantity if new_quantity > 0 else Decimal("0"),
            realized_pnl=position.realized_pnl - fill.commission,
            total_commission=position.total_commission + fill.commission,
            open_time=position.open_time,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            max_hold_time=position.max_hold_time
        )

    else:
        # Closing or reducing position
        close_quantity = min(fill.quantity, position.quantity)

        # Calculate PnL for the closed portion
        if position.side == PositionSide.LONG:
            # Long position: profit = (exit_price - entry_price) * quantity
            pnl = (fill.price - position.entry_price) * close_quantity
        else:
            # Short position: profit = (entry_price - exit_price) * quantity
            pnl = (position.entry_price - fill.price) * close_quantity

        # Update position
        new_quantity = position.quantity - close_quantity
        new_realized_pnl = position.realized_pnl + pnl - fill.commission

        new_position = Position(
            symbol=position.symbol,
            side=position.side,
            quantity=new_quantity,
            entry_price=position.entry_price,  # Keep same entry price
            realized_pnl=new_realized_pnl,
            total_commission=position.total_commission + fill.commission,
            open_time=position.open_time,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            max_hold_time=position.max_hold_time,
            is_closed=(new_quantity == 0),
            close_time=fill.timestamp if new_quantity == 0 else None
        )

    return new_position


def calculate_unrealized_pnl(
    position: Position,
    current_price: Decimal
) -> Decimal:
    """
    Calculates unrealized PnL considering position side, entry price,
    and current market price with proper decimal precision.
    """
    if position.quantity == 0:
        return Decimal("0")

    if position.side == PositionSide.LONG:
        # Long: profit when price goes up
        unrealized = (current_price - position.entry_price) * position.quantity
    else:
        # Short: profit when price goes down
        unrealized = (position.entry_price - current_price) * position.quantity

    return unrealized


def should_close_position(
    position: Position,
    market_data: MarketData
) -> CloseSignal:
    """
    Determines if position should be closed based on stop loss,
    take profit, or time-based exit rules.
    """
    # Check if position is already closed
    if position.is_closed or position.quantity == 0:
        return CloseSignal(should_close=False)

    current_price = market_data.current_price

    # Check stop loss
    if position.stop_loss is not None:
        if position.side == PositionSide.LONG:
            # Long position: close if price drops below stop loss
            if current_price <= position.stop_loss:
                return CloseSignal(
                    should_close=True,
                    reason=CloseReason.STOP_LOSS,
                    close_price=current_price
                )
        else:
            # Short position: close if price rises above stop loss
            if current_price >= position.stop_loss:
                return CloseSignal(
                    should_close=True,
                    reason=CloseReason.STOP_LOSS,
                    close_price=current_price
                )

    # Check take profit
    if position.take_profit is not None:
        if position.side == PositionSide.LONG:
            # Long position: close if price rises above take profit
            if current_price >= position.take_profit:
                return CloseSignal(
                    should_close=True,
                    reason=CloseReason.TAKE_PROFIT,
                    close_price=current_price
                )
        else:
            # Short position: close if price drops below take profit
            if current_price <= position.take_profit:
                return CloseSignal(
                    should_close=True,
                    reason=CloseReason.TAKE_PROFIT,
                    close_price=current_price
                )

    # Check time stop
    if position.max_hold_time is not None:
        time_held = market_data.timestamp - position.open_time
        if time_held >= position.max_hold_time:
            return CloseSignal(
                should_close=True,
                reason=CloseReason.TIME_STOP,
                close_price=current_price
            )

    # No close conditions met
    return CloseSignal(should_close=False)