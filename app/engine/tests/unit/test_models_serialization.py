import json
from decimal import Decimal
from datetime import datetime, timezone

from app.engine.models import Candle, TimeFrame


def test_candle_json_serializes_decimals_as_strings():
    c = Candle(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        open_time=datetime.now(timezone.utc),
        close_time=datetime.now(timezone.utc),
        open_price=Decimal("10.1"),
        high_price=Decimal("10.5"),
        low_price=Decimal("9.9"),
        close_price=Decimal("10.3"),
        volume=Decimal("123.45"),
        quote_volume=Decimal("456.78"),
        trades=1,
        taker_buy_base_volume=Decimal("12.3"),
        taker_buy_quote_volume=Decimal("45.6"),
    )
    payload = c.model_dump_json()
    d = json.loads(payload)
    # Ensure decimals are serialized as strings
    assert isinstance(d["open_price"], str)
    assert d["open_price"] == "10.1"


def test_candle_json_roundtrip_preserves_values():
    c = Candle(
        symbol="ETHUSDT",
        timeframe=TimeFrame.M1,
        open_time=datetime.now(timezone.utc),
        close_time=datetime.now(timezone.utc),
        open_price=Decimal("100.0"),
        high_price=Decimal("110.0"),
        low_price=Decimal("90.0"),
        close_price=Decimal("105.0"),
        volume=Decimal("1000.0"),
        quote_volume=Decimal("10000.0"),
        trades=10,
        taker_buy_base_volume=Decimal("500.0"),
        taker_buy_quote_volume=Decimal("6000.0"),
    )
    s = c.model_dump_json()
    c2 = Candle.model_validate_json(s)
    assert c2.symbol == c.symbol
    assert c2.close_price == c.close_price
