"""Tests for risk-reward targets and bracket order construction"""

from decimal import Decimal
import pytest

from app.engine.decision.brackets import (
    calculate_risk_reward_levels,
    split_position_for_targets,
    create_bracket_orders,
    calculate_breakeven_adjustment,
    create_atr_trail_params,
)


def test_calculate_rr_levels_for_long_position():
    entry_price = Decimal('100')
    stop_loss = Decimal('95')
    risk = entry_price - stop_loss  # 5

    levels = calculate_risk_reward_levels(
        entry_price=entry_price,
        stop_loss=stop_loss,
        is_long=True
    )

    assert levels['tp1'] == Decimal('107.5')  # 1.5R = 100 + (1.5 * 5)
    assert levels['tp2'] == Decimal('110')    # 2R = 100 + (2 * 5)
    assert levels['tp3'] == Decimal('115')    # 3R = 100 + (3 * 5)


def test_calculate_rr_levels_for_short_position():
    entry_price = Decimal('100')
    stop_loss = Decimal('105')
    risk = stop_loss - entry_price  # 5

    levels = calculate_risk_reward_levels(
        entry_price=entry_price,
        stop_loss=stop_loss,
        is_long=False
    )

    assert levels['tp1'] == Decimal('92.5')  # 1.5R = 100 - (1.5 * 5)
    assert levels['tp2'] == Decimal('90')    # 2R = 100 - (2 * 5)
    assert levels['tp3'] == Decimal('85')    # 3R = 100 - (3 * 5)


def test_split_position_maintains_total_size():
    total_size = Decimal('1.0')

    splits = split_position_for_targets(total_size=total_size)

    assert splits['tp1'] == Decimal('0.4')  # 40%
    assert splits['tp2'] == Decimal('0.3')  # 30%
    assert splits['tp3'] == Decimal('0.3')  # 30%
    assert sum(splits.values()) == total_size


def test_split_position_rounds_to_step_size():
    total_size = Decimal('0.123')
    step_size = Decimal('0.01')

    splits = split_position_for_targets(
        total_size=total_size,
        step_size=step_size
    )

    # 40% = 0.0492 -> 0.04
    # 30% = 0.0369 -> 0.03
    # Remainder = 0.123 - 0.04 - 0.03 = 0.053 -> 0.05
    assert splits['tp1'] == Decimal('0.04')
    assert splits['tp2'] == Decimal('0.03')
    assert splits['tp3'] == Decimal('0.05')
    assert sum(splits.values()) == Decimal('0.12')  # Total after rounding


def test_create_bracket_orders_for_spot_long():
    entry_price = Decimal('100')
    stop_loss = Decimal('95')
    position_size = Decimal('1.0')

    orders = create_bracket_orders(
        symbol='BTCUSDT',
        side='BUY',
        entry_price=entry_price,
        stop_loss=stop_loss,
        position_size=position_size,
        is_futures=False
    )

    assert orders['entry']['type'] == 'MARKET'
    assert orders['entry']['side'] == 'BUY'
    assert orders['entry']['quantity'] == Decimal('1.0')

    assert orders['stop_loss']['type'] == 'STOP_LOSS_LIMIT'
    assert orders['stop_loss']['side'] == 'SELL'
    assert orders['stop_loss']['stopPrice'] == Decimal('95')

    assert len(orders['take_profits']) == 3
    assert orders['take_profits'][0]['side'] == 'SELL'
    assert orders['take_profits'][0]['quantity'] == Decimal('0.4')


def test_create_bracket_orders_for_futures_short():
    entry_price = Decimal('100')
    stop_loss = Decimal('105')
    position_size = Decimal('1.0')

    orders = create_bracket_orders(
        symbol='BTCUSDT',
        side='SELL',
        entry_price=entry_price,
        stop_loss=stop_loss,
        position_size=position_size,
        is_futures=True
    )

    assert orders['stop_loss']['type'] == 'STOP_MARKET'
    assert orders['stop_loss']['side'] == 'BUY'
    assert orders['stop_loss']['closePosition'] is True

    # Futures TPs should have reduceOnly
    for tp in orders['take_profits']:
        assert tp['reduceOnly'] == "true"  # API expects string


def test_calculate_breakeven_includes_fees():
    entry_price = Decimal('100')
    position_size = Decimal('1.0')
    fee_rate = Decimal('0.001')  # 0.1%

    breakeven = calculate_breakeven_adjustment(
        entry_price=entry_price,
        position_size=position_size,
        is_long=True,
        fee_rate=fee_rate
    )

    # For long: BE = entry * (1 + 2 * fee_rate)
    # 100 * (1 + 0.002) = 100.2
    assert breakeven == Decimal('100.2')


def test_calculate_breakeven_for_short():
    entry_price = Decimal('100')
    position_size = Decimal('1.0')
    fee_rate = Decimal('0.001')

    breakeven = calculate_breakeven_adjustment(
        entry_price=entry_price,
        position_size=position_size,
        is_long=False,
        fee_rate=fee_rate
    )

    # For short: BE = entry * (1 - 2 * fee_rate)
    # 100 * (1 - 0.002) = 99.8
    assert breakeven == Decimal('99.8')


def test_create_atr_trail_params():
    current_atr = Decimal('5.0')
    multiplier = Decimal('2.0')

    params = create_atr_trail_params(
        current_atr=current_atr,
        multiplier=multiplier
    )

    assert params['trail_distance'] == Decimal('10.0')  # 5 * 2
    assert params['activation_level'] == 'TP2'
    assert params['enabled'] is False  # Default disabled


def test_create_atr_trail_params_with_custom_activation():
    current_atr = Decimal('5.0')
    multiplier = Decimal('1.5')

    params = create_atr_trail_params(
        current_atr=current_atr,
        multiplier=multiplier,
        activation_level='TP1',
        enabled=True
    )

    assert params['trail_distance'] == Decimal('7.5')
    assert params['activation_level'] == 'TP1'
    assert params['enabled'] is True