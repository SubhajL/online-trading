"""
Tests for FeatureService candle buffers pre-allocation and eviction behavior.
"""

from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal

from app.engine.bus import set_event_bus
from app.engine.features.feature_service import FeatureService
from app.engine.models import Candle, TimeFrame


def make_candle(symbol: str, t: datetime) -> Candle:
    return Candle(
        venue="spot",
        symbol=symbol,
        timeframe=TimeFrame.M15,
        open_time=t,
        close_time=t + timedelta(minutes=15),
        open_price=Decimal("100"),
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        close_price=Decimal("100.5"),
        volume=Decimal("10"),
        quote_volume=Decimal("1000"),
        trades=5,
        taker_buy_base_volume=Decimal("6"),
        taker_buy_quote_volume=Decimal("600"),
    )


def test_deque_respects_maxlen_and_evicts_oldest() -> None:
    # Inject a dummy event bus to satisfy constructor
    class _DummyBus:
        async def subscribe(self, *args, **kwargs):  # noqa: D401, ANN001
            return "sub-id"

    set_event_bus(_DummyBus())  # type: ignore[arg-type]
    svc = FeatureService(buffer_size=5)
    symbol = "BTCUSDT"
    tf = TimeFrame.M15

    # Append 7 candles to a deque with maxlen=5
    for i in range(7):
        c = make_candle(symbol, datetime.utcnow() + timedelta(minutes=i * 15))
        svc._candle_buffers[symbol][tf].append(c)

    buf = svc._candle_buffers[symbol][tf]
    assert isinstance(buf, deque)
    assert buf.maxlen == 5
    assert len(buf) == 5


def test_buffers_are_isolated_per_symbol_and_timeframe() -> None:
    class _DummyBus:
        async def subscribe(self, *args, **kwargs):  # noqa: D401, ANN001
            return "sub-id"

    set_event_bus(_DummyBus())  # type: ignore[arg-type]
    svc = FeatureService(buffer_size=3)
    sym1, sym2 = "BTCUSDT", "ETHUSDT"
    tf1, tf2 = TimeFrame.M15, TimeFrame.H1

    svc._candle_buffers[sym1][tf1].append(make_candle(sym1, datetime.utcnow()))
    svc._candle_buffers[sym2][tf1].append(make_candle(sym2, datetime.utcnow()))
    svc._candle_buffers[sym1][tf2].append(make_candle(sym1, datetime.utcnow()))

    assert len(svc._candle_buffers[sym1][tf1]) == 1
    assert len(svc._candle_buffers[sym2][tf1]) == 1
    assert len(svc._candle_buffers[sym1][tf2]) == 1


def test_upsert_replaces_duplicate_open_time_in_place() -> None:
    class _DummyBus:
        async def subscribe(self, *args, **kwargs):  # noqa: D401, ANN001
            return "sub-id"

    set_event_bus(_DummyBus())  # type: ignore[arg-type]
    svc = FeatureService(buffer_size=5)
    symbol = "BTCUSDT"
    tf = TimeFrame.M15

    t0 = datetime(2026, 1, 5, 12, 0)
    first = make_candle(symbol, t0)
    second = make_candle(symbol, t0).model_copy(update={"close_price": Decimal("999")})

    svc._upsert_candle_into_buffer(symbol=symbol, timeframe=tf, candle=first)
    svc._upsert_candle_into_buffer(symbol=symbol, timeframe=tf, candle=second)

    buf = svc._candle_buffers[symbol][tf]
    assert len(buf) == 1
    assert buf[0].close_price == Decimal("999")


def test_upsert_inserts_out_of_order_candles_sorted_by_open_time() -> None:
    class _DummyBus:
        async def subscribe(self, *args, **kwargs):  # noqa: D401, ANN001
            return "sub-id"

    set_event_bus(_DummyBus())  # type: ignore[arg-type]
    svc = FeatureService(buffer_size=10)
    symbol = "BTCUSDT"
    tf = TimeFrame.M15

    t0 = datetime(2026, 1, 5, 12, 0)
    t1 = datetime(2026, 1, 5, 12, 15)
    t2 = datetime(2026, 1, 5, 12, 30)

    svc._upsert_candle_into_buffer(symbol=symbol, timeframe=tf, candle=make_candle(symbol, t1))
    svc._upsert_candle_into_buffer(symbol=symbol, timeframe=tf, candle=make_candle(symbol, t2))
    svc._upsert_candle_into_buffer(symbol=symbol, timeframe=tf, candle=make_candle(symbol, t0))

    buf = svc._candle_buffers[symbol][tf]
    assert [c.open_time for c in buf] == [t0, t1, t2]


def test_upsert_ignores_too_old_candle_when_buffer_full() -> None:
    class _DummyBus:
        async def subscribe(self, *args, **kwargs):  # noqa: D401, ANN001
            return "sub-id"

    set_event_bus(_DummyBus())  # type: ignore[arg-type]
    svc = FeatureService(buffer_size=3)
    symbol = "BTCUSDT"
    tf = TimeFrame.M15

    t0 = datetime(2026, 1, 5, 12, 0)
    t1 = datetime(2026, 1, 5, 12, 15)
    t2 = datetime(2026, 1, 5, 12, 30)

    svc._upsert_candle_into_buffer(symbol=symbol, timeframe=tf, candle=make_candle(symbol, t0))
    svc._upsert_candle_into_buffer(symbol=symbol, timeframe=tf, candle=make_candle(symbol, t1))
    svc._upsert_candle_into_buffer(symbol=symbol, timeframe=tf, candle=make_candle(symbol, t2))

    buf = svc._candle_buffers[symbol][tf]
    assert [c.open_time for c in buf] == [t0, t1, t2]

    too_old = datetime(2026, 1, 5, 11, 45)
    svc._upsert_candle_into_buffer(symbol=symbol, timeframe=tf, candle=make_candle(symbol, too_old))

    buf2 = svc._candle_buffers[symbol][tf]
    assert [c.open_time for c in buf2] == [t0, t1, t2]
