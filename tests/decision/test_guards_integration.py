"""Tests for guards integration in decision engine"""

from decimal import Decimal
from datetime import datetime, timezone, timedelta
import pytest

from app.engine.decision.engine import (
    fuse_signals,
    apply_trading_guards,
    evaluate_current_positions,
    generate_decision,
    format_decision_reasons,
)


def test_fuse_signals_combines_with_regime_context():
    signals_raw = [{
        'signal_id': 'sig-1',
        'signal_type': 'long',
        'entry_price': '100',
        'stop_loss': '95',
        'confidence': 0.8,
        'source': 'smc_retest'
    }]

    regime = {
        'regime_type': 'trending_up',
        'strength': 0.9,
        'volatility': 1.5
    }

    fused = fuse_signals(signals_raw=signals_raw, regime=regime)

    assert len(fused) == 1
    assert fused[0]['signal_id'] == 'sig-1'
    assert fused[0]['regime_alignment'] is True
    assert fused[0]['adjusted_confidence'] > 0.8  # Should boost confidence


def test_fuse_signals_filters_misaligned_regime():
    signals_raw = [{
        'signal_id': 'sig-1',
        'signal_type': 'long',
        'entry_price': '100',
        'stop_loss': '95',
        'confidence': 0.6,
        'source': 'trend_continuation'
    }]

    regime = {
        'regime_type': 'trending_down',  # Opposite of signal
        'strength': 0.9,
        'volatility': 1.5
    }

    fused = fuse_signals(signals_raw=signals_raw, regime=regime)

    assert len(fused) == 0  # Signal filtered out


def test_apply_trading_guards_blocks_news_events():
    signals = [{
        'signal_id': 'sig-1',
        'signal_type': 'long',
        'entry_price': '100',
        'stop_loss': '95'
    }]

    news_events = [{
        'event_time': datetime.now(timezone.utc) + timedelta(minutes=30),
        'impact': 'high',
        'currency': 'USD'
    }]

    funding_windows = []

    filtered = apply_trading_guards(
        signals=signals,
        news_events=news_events,
        funding_windows=funding_windows,
        news_buffer_minutes=60
    )

    assert isinstance(filtered, dict)  # Returns dict when all signals blocked
    assert filtered.get('blocked_reasons') == ['high_impact_news_event']


def test_apply_trading_guards_blocks_funding_window():
    signals = [{
        'signal_id': 'sig-1',
        'signal_type': 'long',
        'entry_price': '100',
        'stop_loss': '95'
    }]

    news_events = []
    funding_windows = [{
        'funding_time': datetime.now(timezone.utc) + timedelta(minutes=15),
        'predicted_rate': 0.05  # High positive rate
    }]

    filtered = apply_trading_guards(
        signals=signals,
        news_events=news_events,
        funding_windows=funding_windows,
        funding_buffer_minutes=30
    )

    assert isinstance(filtered, dict)  # Returns dict when all signals blocked
    assert filtered.get('blocked_reasons') == ['funding_window']


def test_apply_trading_guards_allows_safe_signals():
    signals = [{
        'signal_id': 'sig-1',
        'signal_type': 'long',
        'entry_price': '100',
        'stop_loss': '95'
    }]

    news_events = [{
        'event_time': datetime.now(timezone.utc) + timedelta(hours=2),
        'impact': 'low',
        'currency': 'EUR'  # Different currency
    }]

    funding_windows = [{
        'funding_time': datetime.now(timezone.utc) + timedelta(hours=5),
        'predicted_rate': 0.001  # Low rate
    }]

    filtered = apply_trading_guards(
        signals=signals,
        news_events=news_events,
        funding_windows=funding_windows
    )

    assert len(filtered) == 1  # Signal allowed through
    assert filtered[0]['signal_id'] == 'sig-1'


def test_evaluate_current_positions_blocks_at_limit():
    current_positions = [
        {'symbol': 'BTCUSDT', 'position_id': 'pos-1'},
        {'symbol': 'ETHUSDT', 'position_id': 'pos-2'},
        {'symbol': 'SOLUSDT', 'position_id': 'pos-3'}
    ]

    new_signal = {
        'symbol': 'ADAUSDT',
        'signal_id': 'sig-1'
    }

    max_concurrent = 3

    allowed = evaluate_current_positions(
        current_positions=current_positions,
        new_signal=new_signal,
        max_concurrent=max_concurrent
    )

    assert isinstance(allowed, dict)  # Returns dict when blocked
    assert allowed.get('reason') == 'max_concurrent_positions_reached'


def test_evaluate_current_positions_blocks_duplicate_symbol():
    current_positions = [
        {'symbol': 'BTCUSDT', 'position_id': 'pos-1'},
        {'symbol': 'ETHUSDT', 'position_id': 'pos-2'}
    ]

    new_signal = {
        'symbol': 'BTCUSDT',  # Already have position
        'signal_id': 'sig-1'
    }

    max_concurrent = 3

    allowed = evaluate_current_positions(
        current_positions=current_positions,
        new_signal=new_signal,
        max_concurrent=max_concurrent
    )

    assert isinstance(allowed, dict)  # Returns dict when blocked
    assert allowed.get('reason') == 'position_already_exists'


def test_generate_decision_creates_full_context():
    signal = {
        'signal_id': 'sig-1',
        'signal_type': 'long',
        'entry_price': Decimal('100'),
        'stop_loss': Decimal('95'),
        'confidence': 0.8,
        'source': 'smc_retest'
    }

    account_balance = Decimal('10000')
    risk_percentage = Decimal('0.005')

    decision = generate_decision(
        signal=signal,
        account_balance=account_balance,
        risk_percentage=risk_percentage,
        symbol='BTCUSDT',
        is_futures=False
    )

    assert decision['action'] == 'open_long'
    assert decision['entry_price'] == Decimal('100')
    assert decision['stop_loss'] == Decimal('95')
    assert decision['position_size'] is not None
    assert decision['risk_amount'] == Decimal('50')  # 10000 * 0.005
    assert decision['confidence'] == 0.8
    assert 'reasons' in decision
    assert 'risk_metadata' in decision


def test_generate_decision_respects_daily_drawdown():
    signal = {
        'signal_id': 'sig-1',
        'signal_type': 'long',
        'entry_price': Decimal('100'),
        'stop_loss': Decimal('95'),
        'confidence': 0.8
    }

    account_balance = Decimal('9750')
    risk_percentage = Decimal('0.005')
    daily_pnl = [Decimal('-200'), Decimal('-50')]  # Already down 2.5%

    decision = generate_decision(
        signal=signal,
        account_balance=account_balance,
        risk_percentage=risk_percentage,
        symbol='BTCUSDT',
        is_futures=False,
        daily_pnl_history=daily_pnl,
        max_daily_drawdown=Decimal('0.03')
    )

    assert decision['action'] == 'no_action'
    assert 'approaching_daily_drawdown_limit' in decision['reasons'][0]


def test_format_decision_reasons_provides_clear_explanation():
    reasons_data = {
        'signal_source': 'smc_retest',
        'regime_alignment': True,
        'confidence_factors': ['strong_volume', 'clean_structure'],
        'risk_factors': ['near_resistance'],
        'position_size_limited_by': 'leverage_constraint'
    }

    reasons = format_decision_reasons(reasons_data)

    assert len(reasons) >= 3
    assert any('SMC retest' in r for r in reasons)
    assert any('regime' in r.lower() for r in reasons)
    assert any('leverage constraint' in r for r in reasons)