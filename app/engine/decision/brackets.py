"""Bracket order construction module"""

from decimal import Decimal
from typing import TypedDict

from .sizing import round_to_exchange_precision


class TPSplits(TypedDict):
    tp1: Decimal
    tp2: Decimal
    tp3: Decimal


class RRLevels(TypedDict):
    tp1: Decimal
    tp2: Decimal
    tp3: Decimal


class ATRTrailParams(TypedDict):
    trail_distance: Decimal
    activation_level: str
    enabled: bool


def calculate_risk_reward_levels(
    entry_price: Decimal, stop_loss: Decimal, is_long: bool,
) -> RRLevels:
    """Calculate TP levels at 1.5R, 2R, 3R

    Args:
        entry_price: Entry price for the position
        stop_loss: Stop loss price
        is_long: True for long position, False for short

    Returns:
        Dictionary with tp1, tp2, tp3 levels
    """
    # Calculate risk (R) - distance from entry to stop
    risk = abs(entry_price - stop_loss)

    if is_long:
        # For longs, TPs are above entry
        tp1 = entry_price + (risk * Decimal("1.5"))
        tp2 = entry_price + (risk * Decimal("2.0"))
        tp3 = entry_price + (risk * Decimal("3.0"))
    else:
        # For shorts, TPs are below entry
        tp1 = entry_price - (risk * Decimal("1.5"))
        tp2 = entry_price - (risk * Decimal("2.0"))
        tp3 = entry_price - (risk * Decimal("3.0"))

    return RRLevels(tp1=tp1, tp2=tp2, tp3=tp3)


def split_position_for_targets(
    total_size: Decimal, step_size: Decimal | None = None,
) -> TPSplits:
    """Split position into 40%/30%/30% for TP1/TP2/TP3

    Args:
        total_size: Total position size to split
        step_size: Exchange step size for rounding (optional)

    Returns:
        Dictionary with tp1, tp2, tp3 position sizes
    """
    # Calculate raw splits
    tp1_size = total_size * Decimal("0.4")  # 40%
    tp2_size = total_size * Decimal("0.3")  # 30%

    # If step size provided, round down each split
    if step_size:
        tp1_size = round_to_exchange_precision(tp1_size, step_size)
        tp2_size = round_to_exchange_precision(tp2_size, step_size)

        # TP3 gets the remainder after rounding to ensure full position is used
        used_size = tp1_size + tp2_size
        tp3_size = round_to_exchange_precision(total_size - used_size, step_size)
    else:
        # Without step size, TP3 is simply 30%
        tp3_size = total_size * Decimal("0.3")

    return TPSplits(tp1=tp1_size, tp2=tp2_size, tp3=tp3_size)


def create_bracket_orders(
    symbol: str,
    side: str,
    entry_price: Decimal,
    stop_loss: Decimal,
    position_size: Decimal,
    is_futures: bool,
) -> dict:
    """Generate entry order + SL + multi-TP ladder

    Args:
        symbol: Trading symbol
        side: 'BUY' or 'SELL'
        entry_price: Entry price (used for limit orders)
        stop_loss: Stop loss price
        position_size: Total position size
        is_futures: Whether this is a futures position

    Returns:
        Dictionary with entry, stop_loss, and take_profits orders
    """
    is_long = side == "BUY"

    # Calculate TP levels
    tp_levels = calculate_risk_reward_levels(entry_price, stop_loss, is_long)

    # Split position for TPs
    tp_splits = split_position_for_targets(position_size)

    # Entry order
    entry_order = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": position_size,
    }

    # Stop loss order
    if is_futures:
        # Futures use STOP_MARKET and closePosition
        stop_loss_order = {
            "symbol": symbol,
            "side": "SELL" if is_long else "BUY",
            "type": "STOP_MARKET",
            "stopPrice": stop_loss,
            "closePosition": True,
        }
    else:
        # Spot uses STOP_LOSS_LIMIT
        stop_loss_order = {
            "symbol": symbol,
            "side": "SELL" if is_long else "BUY",
            "type": "STOP_LOSS_LIMIT",
            "stopPrice": stop_loss,
            "price": stop_loss,  # Limit price same as stop for simplicity
            "quantity": position_size,
        }

    # Take profit orders
    take_profits = []
    for _i, (level, size) in enumerate(
        [
            (tp_levels["tp1"], tp_splits["tp1"]),
            (tp_levels["tp2"], tp_splits["tp2"]),
            (tp_levels["tp3"], tp_splits["tp3"]),
        ],
        1,
    ):
        tp_order = {
            "symbol": symbol,
            "side": "SELL" if is_long else "BUY",
            "type": "LIMIT",
            "price": level,
            "quantity": size,
        }

        if is_futures:
            tp_order["reduceOnly"] = True

        take_profits.append(tp_order)

    return {
        "entry": entry_order,
        "stop_loss": stop_loss_order,
        "take_profits": take_profits,
    }


def calculate_breakeven_adjustment(
    entry_price: Decimal, position_size: Decimal, is_long: bool, fee_rate: Decimal,
) -> Decimal:
    """Calculate BE level after TP1 hit including fees

    Args:
        entry_price: Entry price of the position
        position_size: Position size (reserved for future use)
        is_long: True for long position, False for short
        fee_rate: Trading fee rate (e.g., 0.001 for 0.1%)

    Returns:
        Breakeven price including fees
    """
    # Keep position_size parameter for API compatibility
    _ = position_size
    # Account for entry fee + exit fee = 2 * fee_rate
    total_fee_rate = fee_rate * Decimal(2)

    if is_long:
        # For long: need price to rise to cover fees
        breakeven = entry_price * (Decimal(1) + total_fee_rate)
    else:
        # For short: need price to fall to cover fees
        breakeven = entry_price * (Decimal(1) - total_fee_rate)

    return breakeven


def create_atr_trail_params(
    current_atr: Decimal,
    multiplier: Decimal,
    activation_level: str = "TP2",
    enabled: bool = False,
) -> ATRTrailParams:
    """Create ATR-based trailing stop parameters

    Args:
        current_atr: Current ATR value
        multiplier: ATR multiplier for trail distance
        activation_level: When to activate trailing ('TP1', 'TP2', etc.)
        enabled: Whether trailing is enabled

    Returns:
        ATR trail parameters dictionary
    """
    trail_distance = current_atr * multiplier

    return ATRTrailParams(
        trail_distance=trail_distance,
        activation_level=activation_level,
        enabled=enabled,
    )
