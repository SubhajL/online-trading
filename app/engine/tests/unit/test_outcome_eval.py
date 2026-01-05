"""
Unit tests for simplified outcome evaluation of external signals.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.engine.models import Candle, TimeFrame
from app.engine.telegram_validator.outcome_eval import evaluate_trade_outcome


def _candle(*, t: datetime, high: str, low: str, close: str) -> Candle:
    return Candle(
        venue="spot",
        symbol="BTCUSDT",
        timeframe=TimeFrame.M30,
        open_time=t,
        close_time=t + timedelta(minutes=30),
        open_price=Decimal(close),
        high_price=Decimal(high),
        low_price=Decimal(low),
        close_price=Decimal(close),
        volume=Decimal("0"),
        quote_volume=Decimal("0"),
        trades=0,
        taker_buy_base_volume=Decimal("0"),
        taker_buy_quote_volume=Decimal("0"),
    )


def test_evaluate_trade_outcome_long_tp_first() -> None:
    t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
    candles = [
        _candle(t=t0, high="101", low="99", close="100"),
        _candle(t=t0 + timedelta(minutes=30), high="106", low="100", close="105"),
    ]

    outcome = evaluate_trade_outcome(
        direction="BUY",
        stop_loss=Decimal("98"),
        take_profit=Decimal("105"),
        candles=candles,
    )

    assert outcome.outcome == "TP1"
    assert outcome.hit_timestamp == candles[1].open_time


def test_evaluate_trade_outcome_short_both_hit_same_candle_is_conservative_sl() -> None:
    t0 = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
    candles = [
        _candle(t=t0, high="110", low="90", close="100"),
    ]

    outcome = evaluate_trade_outcome(
        direction="SELL",
        stop_loss=Decimal("105"),
        take_profit=Decimal("95"),
        candles=candles,
    )

    assert outcome.outcome == "SL"
