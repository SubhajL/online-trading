import json
import pytest
from jsonschema import validate, ValidationError
from pathlib import Path


def load_schema(name: str) -> dict:
    schema_path = (
        Path(__file__).parent.parent.parent
        / "contracts"
        / "jsonschema"
        / f"{name}.schema.json"
    )
    with open(schema_path) as f:
        return json.load(f)


class TestSmcEventsV1Schema:
    def test_valid_choch_event(self):
        schema = load_schema("smc_events.v1")

        valid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "event_time": "2024-01-01T00:00:00Z",
            "event_type": "choch",
            "direction": "bullish",
            "price_level": 42000.50,
            "previous_pivot_price": 41500.00,
            "previous_pivot_time": "2024-01-01T00:00:00Z",
            "broken_pivot_price": 41800.00,
            "broken_pivot_time": "2023-12-31T23:00:00Z",
        }

        # Should not raise
        validate(instance=valid_payload, schema=schema)

    def test_valid_bos_event(self):
        schema = load_schema("smc_events.v1")

        valid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "4h",
            "event_time": "2024-01-01T04:00:00Z",
            "event_type": "bos",
            "direction": "bearish",
            "price_level": 41000.00,
            "previous_pivot_price": 41500.00,
            "previous_pivot_time": "2024-01-01T00:00:00Z",
            "broken_pivot_price": 41200.00,
            "broken_pivot_time": "2023-12-31T20:00:00Z",
        }

        # Should not raise
        validate(instance=valid_payload, schema=schema)

    def test_event_type_enum_validation(self):
        schema = load_schema("smc_events.v1")

        # Invalid event type
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "event_time": "2024-01-01T00:00:00Z",
            "event_type": "INVALID",  # Must be CHOCH or BOS
            "direction": "bullish",
            "price_level": 42000.50,
            "previous_pivot_price": 41500.00,
            "previous_pivot_time": "2024-01-01T00:00:00Z",
            "broken_pivot_price": 41800.00,
            "broken_pivot_time": "2023-12-31T23:00:00Z",
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert "'INVALID' is not one of ['choch', 'bos']" in str(exc_info.value)

    def test_direction_enum_validation(self):
        schema = load_schema("smc_events.v1")

        # Invalid direction
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "event_time": "2024-01-01T00:00:00Z",
            "event_type": "choch",
            "direction": "sideways",  # Must be bullish or bearish
            "price_level": 42000.50,
            "previous_pivot_price": 41500.00,
            "previous_pivot_time": "2024-01-01T00:00:00Z",
            "broken_pivot_price": 41800.00,
            "broken_pivot_time": "2023-12-31T23:00:00Z",
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert "'sideways' is not one of ['bullish', 'bearish']" in str(exc_info.value)
