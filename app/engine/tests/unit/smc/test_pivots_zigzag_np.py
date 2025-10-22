from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.models import Candle, TimeFrame
from app.engine.smc.pivots import detect_zigzag_pivots, detect_zigzag_pivots_np


def _make_candle(ts, o, h, l, c, idx):
    return Candle(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        open_time=ts,
        close_time=ts + timedelta(minutes=5),
        open_price=Decimal(str(o)),
        high_price=Decimal(str(h)),
        low_price=Decimal(str(l)),
        close_price=Decimal(str(c)),
        volume=Decimal("1"),
        quote_volume=Decimal("1"),
        trades=1,
        taker_buy_base_volume=Decimal("0.5"),
        taker_buy_quote_volume=Decimal("0.5"),
        bar_index=idx,
    )


def _series():
    t0 = datetime.utcnow()
    vals = [
        (10.0, 10.5, 9.8, 10.2),
        (10.2, 10.8, 10.0, 10.7),
        (10.7, 11.2, 10.6, 11.0),  # up
        (11.0, 11.1, 10.3, 10.4),  # down
        (10.4, 10.6, 10.1, 10.2),
        (10.2, 10.9, 10.1, 10.8),  # up
        (10.8, 11.0, 10.2, 10.3),  # down
        (10.3, 10.5, 10.0, 10.4),
        (10.4, 11.0, 10.2, 10.9),  # up
        (10.9, 11.1, 10.7, 11.0),
    ]
    series = []
    for i, (o, h, l, c) in enumerate(vals):
        series.append(_make_candle(t0 + timedelta(minutes=5 * i), o, h, l, c, i))
    return series


def test_zigzag_np_matches_legacy_small_series():
    candles = _series()
    atr_value = Decimal("0.3")
    factor = 2.0

    legacy = detect_zigzag_pivots(candles, atr_value, factor)
    np_pivots = detect_zigzag_pivots_np(candles, float(atr_value), factor)

    assert len(np_pivots) == len(legacy)
    for a, b in zip(np_pivots, legacy):
        assert a.is_high == b.is_high
        assert a.bar_index == b.bar_index
        assert a.price == b.price


def test_zigzag_np_threshold_controls_pivot_density():
    candles = _series()
    low_thr = detect_zigzag_pivots_np(candles, 0.2, 1.0)
    high_thr = detect_zigzag_pivots_np(candles, 0.5, 2.0)
    assert len(high_thr) <= len(low_thr)


def test_zigzag_np_monotonic_series_no_pivots():
    t0 = datetime.utcnow()
    # strictly increasing tiny swings; threshold too large to trigger
    vals = [(10 + i * 0.1, 10 + i * 0.1, 10 + i * 0.1, 10 + i * 0.1) for i in range(10)]
    candles = [
        _make_candle(t0 + timedelta(minutes=5 * i), o, h + 0.01, l - 0.01, c, i)
        for i, (o, h, l, c) in enumerate(vals)
    ]
    piv = detect_zigzag_pivots_np(candles, 10.0, 2.0)
    assert len(piv) == 0
