"""Position sizing module for risk management"""

from decimal import Decimal


def calculate_position_size(
    account_balance: Decimal,
    risk_percentage: Decimal,
    entry_price: Decimal,
    stop_loss: Decimal,
) -> Decimal:
    """Calculate position size using fixed fractional method

    Args:
        account_balance: Total account balance
        risk_percentage: Risk per trade as decimal (e.g., 0.005 for 0.5%)
        entry_price: Entry price for the position
        stop_loss: Stop loss price for the position

    Returns:
        Position size in base currency
    """
    # Calculate stop distance (absolute value to handle both long and short)
    stop_distance = abs(entry_price - stop_loss)

    # Return zero if stop distance is zero (invalid placement)
    if stop_distance == 0:
        return Decimal(0)

    # Calculate risk amount in quote currency
    risk_amount = account_balance * risk_percentage

    # Calculate position size: Risk Amount / Stop Distance
    return risk_amount / stop_distance


def apply_leverage_constraints(
    position_size: Decimal,
    account_balance: Decimal,
    entry_price: Decimal,
    is_futures: bool,
    max_leverage: Decimal,
) -> Decimal:
    """Apply leverage constraints to position size

    Args:
        position_size: Calculated position size
        account_balance: Total account balance
        entry_price: Entry price for the position
        is_futures: Whether this is a futures position
        max_leverage: Maximum allowed leverage

    Returns:
        Adjusted position size respecting leverage limits
    """
    # Spot positions don't have leverage constraints
    if not is_futures:
        return position_size

    # Calculate position value
    position_value = position_size * entry_price

    # Calculate maximum allowed position value based on leverage
    max_position_value = account_balance * max_leverage

    # If position value exceeds max, reduce position size
    if position_value > max_position_value:
        return max_position_value / entry_price

    return position_size


def check_concurrent_positions(
    current_positions: list[str],
    max_concurrent: int,
) -> bool:
    """Check if new position is allowed based on concurrent limits

    Args:
        current_positions: List of current position IDs
        max_concurrent: Maximum allowed concurrent positions

    Returns:
        True if new position is allowed, False otherwise
    """
    return len(current_positions) < max_concurrent


def calculate_daily_drawdown(
    daily_pnl_history: list[Decimal],
    current_balance: Decimal,
    starting_balance: Decimal,
) -> Decimal:
    """Calculate current drawdown from daily high water mark

    Args:
        daily_pnl_history: List of daily PnL values
        current_balance: Current account balance
        starting_balance: Starting balance for the day

    Returns:
        Drawdown percentage as decimal (0.01 = 1%)
    """
    # Start with the starting balance as the initial high water mark
    high_water_mark = starting_balance

    # Calculate cumulative balance at each point to find HWM
    cumulative_balance = starting_balance
    for pnl in daily_pnl_history:
        cumulative_balance += pnl
        high_water_mark = max(high_water_mark, cumulative_balance)

    # If current balance equals or exceeds HWM, no drawdown
    if current_balance >= high_water_mark:
        return Decimal(0)

    # Calculate drawdown percentage
    return (high_water_mark - current_balance) / high_water_mark


def round_to_exchange_precision(value: Decimal, step_size: Decimal) -> Decimal:
    """Round value to exchange precision (step size)

    Args:
        value: Value to round
        step_size: Exchange step size (lot size)

    Returns:
        Value rounded down to nearest step size
    """
    # Return zero if value is below step size
    if value < step_size:
        return Decimal(0)

    # Calculate number of steps (round down)
    steps = value / step_size
    rounded_steps = int(steps)  # This rounds down

    # Return rounded value
    return Decimal(str(rounded_steps)) * step_size
