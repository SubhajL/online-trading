from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from app.engine.models import Candle, TimeFrame
from app.engine.smc.engine import SMCEngine
from app.engine.smc.atr import atr
from app.engine.smc.numutils import to_float_ohlc_arrays


def _make_candle(ts: datetime, o: float, h: float, l: float, c: float, idx: int) -> Candle:
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


@pytest.mark.asyncio
async def test_engine_uses_vectorized_atr_for_state():
    # Build 15 candles so ATR(14) has one value at the end
    t0 = datetime.utcnow()
    series = []
    vals = [
        (10.0, 11.0, 9.8, 10.5),
        (10.6, 11.5, 10.2, 11.0),
        (11.0, 12.5, 10.9, 12.2),
        (12.2, 12.6, 11.8, 12.1),
        (12.1, 13.8, 12.0, 13.6),
        (13.6, 14.2, 13.5, 14.0),
        (14.0, 14.1, 13.9, 14.0),
        (14.0, 14.5, 13.7, 14.4),
        (14.4, 14.8, 14.0, 14.6),
        (14.6, 15.0, 14.4, 14.9),
        (14.9, 15.1, 14.7, 15.0),
        (15.0, 15.3, 14.8, 15.2),
        (15.2, 15.7, 15.0, 15.5),
        (15.5, 15.9, 15.1, 15.8),
        (15.8, 16.0, 15.6, 15.9),
    ]
    for i, (o, h, l, c) in enumerate(vals):
        series.append(_make_candle(t0 + timedelta(minutes=5 * i), o, h, l, c, i))

    engine = SMCEngine()
    for cndl in series:
        await engine.process_candle(cndl)

    key = ("BTCUSDT", TimeFrame.M5)
    # Compute expected ATR via vectorized function over last 14 bars
    recent = series[-14:]
    _o, h, l, c = to_float_ohlc_arrays(recent)
    expected = atr(h, l, c, period=14)[-1]

    got_dec = engine._atr_values[key]
    assert got_dec is not None
    got = float(got_dec)

    np.testing.assert_allclose(got, expected, rtol=1e-9, atol=1e-12)
