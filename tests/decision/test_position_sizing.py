"""Tests for position sizing module"""

from decimal import Decimal
import pytest

from app.engine.decision.sizing import (
    calculate_position_size,
    apply_leverage_constraints,
    check_concurrent_positions,
    calculate_daily_drawdown,
    round_to_exchange_precision,
)


def test_calculates_position_size_using_fixed_fractional_method():
    account_balance = Decimal('10000')
    risk_percentage = Decimal('0.005')  # 0.5%
    entry_price = Decimal('50000')
    stop_loss = Decimal('49000')

    size = calculate_position_size(
        account_balance=account_balance,
        risk_percentage=risk_percentage,
        entry_price=entry_price,
        stop_loss=stop_loss
    )

    # Risk amount = 10000 * 0.005 = 50
    # Stop distance = 50000 - 49000 = 1000
    # Position size = 50 / 1000 = 0.05
    assert size == Decimal('0.05')


def test_handles_short_positions_with_stop_loss_above_entry():
    account_balance = Decimal('10000')
    risk_percentage = Decimal('0.005')
    entry_price = Decimal('50000')
    stop_loss = Decimal('51000')  # Stop above entry for short

    size = calculate_position_size(
        account_balance=account_balance,
        risk_percentage=risk_percentage,
        entry_price=entry_price,
        stop_loss=stop_loss
    )

    # Risk amount = 10000 * 0.005 = 50
    # Stop distance = 51000 - 50000 = 1000
    # Position size = 50 / 1000 = 0.05
    assert size == Decimal('0.05')


def test_returns_zero_for_invalid_stop_loss_placement():
    account_balance = Decimal('10000')
    risk_percentage = Decimal('0.005')
    entry_price = Decimal('50000')
    stop_loss = Decimal('50000')  # Invalid: same as entry

    size = calculate_position_size(
        account_balance=account_balance,
        risk_percentage=risk_percentage,
        entry_price=entry_price,
        stop_loss=stop_loss
    )

    assert size == Decimal('0')




def test_allows_spot_positions_without_leverage_adjustment():
    position_size = Decimal('0.1')
    account_balance = Decimal('10000')
    entry_price = Decimal('50000')
    is_futures = False
    max_leverage = Decimal('3')

    adjusted = apply_leverage_constraints(
        position_size=position_size,
        account_balance=account_balance,
        entry_price=entry_price,
        is_futures=is_futures,
        max_leverage=max_leverage
    )

    assert adjusted == position_size


def test_reduces_futures_position_to_respect_max_leverage():
    position_size = Decimal('1')
    account_balance = Decimal('10000')
    entry_price = Decimal('50000')
    is_futures = True
    max_leverage = Decimal('3')

    adjusted = apply_leverage_constraints(
        position_size=position_size,
        account_balance=account_balance,
        entry_price=entry_price,
        is_futures=is_futures,
        max_leverage=max_leverage
    )

    # Position value = 1 * 50000 = 50000
    # Max allowed = 10000 * 3 = 30000
    # Adjusted size = 30000 / 50000 = 0.6
    assert adjusted == Decimal('0.6')


def test_allows_futures_position_within_leverage_limits():
    position_size = Decimal('0.5')
    account_balance = Decimal('10000')
    entry_price = Decimal('50000')
    is_futures = True
    max_leverage = Decimal('3')

    adjusted = apply_leverage_constraints(
        position_size=position_size,
        account_balance=account_balance,
        entry_price=entry_price,
        is_futures=is_futures,
        max_leverage=max_leverage
    )

    # Position value = 0.5 * 50000 = 25000
    # Max allowed = 10000 * 3 = 30000
    # Within limits, no adjustment
    assert adjusted == position_size




def test_allows_new_position_when_below_limit():
    current_positions = ['BTC-123', 'ETH-456']
    max_concurrent = 3

    allowed = check_concurrent_positions(
        current_positions=current_positions,
        max_concurrent=max_concurrent
    )

    assert allowed is True


def test_blocks_new_position_at_limit():
    current_positions = ['BTC-123', 'ETH-456', 'SOL-789']
    max_concurrent = 3

    allowed = check_concurrent_positions(
        current_positions=current_positions,
        max_concurrent=max_concurrent
    )

    assert allowed is False


def test_handles_empty_positions_list():
    current_positions = []
    max_concurrent = 3

    allowed = check_concurrent_positions(
        current_positions=current_positions,
        max_concurrent=max_concurrent
    )

    assert allowed is True




def test_calculates_drawdown_from_daily_high_water_mark():
    daily_pnl_history = [
        Decimal('100'),   # +100
        Decimal('-50'),   # +50 total
        Decimal('200'),   # +250 total (high water mark)
        Decimal('-150'),  # +100 total
        Decimal('-50'),   # +50 total
    ]
    current_balance = Decimal('10050')
    starting_balance = Decimal('10000')

    dd_pct = calculate_daily_drawdown(
        daily_pnl_history=daily_pnl_history,
        current_balance=current_balance,
        starting_balance=starting_balance
    )

    # HWM = 10000 + 250 = 10250
    # Current = 10050
    # DD = (10250 - 10050) / 10250 = 0.0195
    assert abs(dd_pct - Decimal('0.0195121951')) < Decimal('0.0001')


def test_returns_zero_when_at_high_water_mark():
    daily_pnl_history = [Decimal('100'), Decimal('50')]
    current_balance = Decimal('10150')
    starting_balance = Decimal('10000')

    dd_pct = calculate_daily_drawdown(
        daily_pnl_history=daily_pnl_history,
        current_balance=current_balance,
        starting_balance=starting_balance
    )

    assert dd_pct == Decimal('0')


def test_handles_empty_pnl_history():
    daily_pnl_history = []
    current_balance = Decimal('9950')
    starting_balance = Decimal('10000')

    dd_pct = calculate_daily_drawdown(
        daily_pnl_history=daily_pnl_history,
        current_balance=current_balance,
        starting_balance=starting_balance
    )

    # DD from starting balance = (10000 - 9950) / 10000 = 0.005
    assert dd_pct == Decimal('0.005')




def test_rounds_down_to_lot_size_precision():
    value = Decimal('0.12345')
    step_size = Decimal('0.001')

    rounded = round_to_exchange_precision(
        value=value,
        step_size=step_size
    )

    assert rounded == Decimal('0.123')


def test_handles_whole_number_step_sizes():
    value = Decimal('123.456')
    step_size = Decimal('10')

    rounded = round_to_exchange_precision(
        value=value,
        step_size=step_size
    )

    assert rounded == Decimal('120')


def test_returns_zero_for_values_below_step_size():
    value = Decimal('0.0009')
    step_size = Decimal('0.001')

    rounded = round_to_exchange_precision(
        value=value,
        step_size=step_size
    )

    assert rounded == Decimal('0')


def test_preserves_exact_multiples():
    value = Decimal('0.5')
    step_size = Decimal('0.1')

    rounded = round_to_exchange_precision(
        value=value,
        step_size=step_size
    )

    assert rounded == Decimal('0.5')