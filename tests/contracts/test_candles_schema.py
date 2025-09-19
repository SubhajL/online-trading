import json
import pytest
from jsonschema import validate, ValidationError
from pathlib import Path


def load_schema(name: str) -> dict:
    schema_path = Path(__file__).parent.parent.parent / "contracts" / "jsonschema" / f"{name}.schema.json"
    with open(schema_path) as f:
        return json.load(f)


class TestCandlesV1Schema:
    def test_valid_candle_payload(self):
        schema = load_schema("candles.v1")

        valid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2024-01-01T00:00:00Z",
            "close_time": "2024-01-01T01:00:00Z",
            "open": 42000.50,
            "high": 42500.00,
            "low": 41800.00,
            "close": 42300.00,
            "volume": 1234.567,
            "quote_volume": 51234567.89,
            "trades": 12345,
            "taker_buy_volume": 600.123,
            "taker_buy_quote_volume": 25000000.00,
            "is_closed": True
        }

        # Should not raise
        validate(instance=valid_payload, schema=schema)

    def test_missing_required_fields(self):
        schema = load_schema("candles.v1")

        # Missing 'open' field
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2024-01-01T00:00:00Z",
            "close_time": "2024-01-01T01:00:00Z",
            "high": 42500.00,
            "low": 41800.00,
            "close": 42300.00,
            "volume": 1234.567,
            "quote_volume": 51234567.89,
            "trades": 12345,
            "taker_buy_volume": 600.123,
            "taker_buy_quote_volume": 25000000.00,
            "is_closed": True
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert "'open' is a required property" in str(exc_info.value)

    def test_invalid_numeric_types(self):
        schema = load_schema("candles.v1")

        # 'open' as string instead of number
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2024-01-01T00:00:00Z",
            "close_time": "2024-01-01T01:00:00Z",
            "open": "42000.50",  # Should be number
            "high": 42500.00,
            "low": 41800.00,
            "close": 42300.00,
            "volume": 1234.567,
            "quote_volume": 51234567.89,
            "trades": 12345,
            "taker_buy_volume": 600.123,
            "taker_buy_quote_volume": 25000000.00,
            "is_closed": True
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert "'42000.50' is not of type 'number'" in str(exc_info.value)

    def test_invalid_timestamp_format(self):
        schema = load_schema("candles.v1")

        # Invalid timestamp format
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2024-01-01 00:00:00",  # Not ISO8601
            "close_time": "2024-01-01T01:00:00Z",
            "open": 42000.50,
            "high": 42500.00,
            "low": 41800.00,
            "close": 42300.00,
            "volume": 1234.567,
            "quote_volume": 51234567.89,
            "trades": 12345,
            "taker_buy_volume": 600.123,
            "taker_buy_quote_volume": 25000000.00,
            "is_closed": True
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert "does not match" in str(exc_info.value)

    def test_no_additional_properties(self):
        schema = load_schema("candles.v1")

        # Extra field not allowed
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2024-01-01T00:00:00Z",
            "close_time": "2024-01-01T01:00:00Z",
            "open": 42000.50,
            "high": 42500.00,
            "low": 41800.00,
            "close": 42300.00,
            "volume": 1234.567,
            "quote_volume": 51234567.89,
            "trades": 12345,
            "taker_buy_volume": 600.123,
            "taker_buy_quote_volume": 25000000.00,
            "is_closed": True,
            "extra_field": "should not be here"
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert "Additional properties are not allowed" in str(exc_info.value)