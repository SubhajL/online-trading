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


class TestZonesV1Schema:
    def test_valid_order_block_zone(self):
        schema = load_schema("zones.v1")

        valid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "zone_id": "ob_1h_20240101_000000",
            "zone_type": "order_block",
            "direction": "demand",
            "upper_bound": 42500.00,
            "lower_bound": 42000.00,
            "created_time": "2024-01-01T00:00:00Z",
            "candle_count": 3,
            "strength": 0.85,
            "touches": 0,
            "is_active": True,
        }

        # Should not raise
        validate(instance=valid_payload, schema=schema)

    def test_valid_fair_value_gap_zone(self):
        schema = load_schema("zones.v1")

        valid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "4h",
            "zone_id": "fvg_4h_20240101_040000",
            "zone_type": "fair_value_gap",
            "direction": "supply",
            "upper_bound": 43000.00,
            "lower_bound": 42800.00,
            "created_time": "2024-01-01T04:00:00Z",
            "candle_count": 1,
            "strength": 0.70,
            "touches": 1,
            "is_active": False,
        }

        # Should not raise
        validate(instance=valid_payload, schema=schema)

    def test_zone_type_enum_validation(self):
        schema = load_schema("zones.v1")

        # Invalid zone type
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "zone_id": "invalid_1h_20240101_000000",
            "zone_type": "support_resistance",  # Must be order_block or fair_value_gap
            "direction": "demand",
            "upper_bound": 42500.00,
            "lower_bound": 42000.00,
            "created_time": "2024-01-01T00:00:00Z",
            "candle_count": 3,
            "strength": 0.85,
            "touches": 0,
            "is_active": True,
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert (
            "'support_resistance' is not one of ['order_block', 'fair_value_gap']"
            in str(exc_info.value)
        )

    def test_direction_enum_validation(self):
        schema = load_schema("zones.v1")

        # Invalid direction
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "zone_id": "ob_1h_20240101_000000",
            "zone_type": "order_block",
            "direction": "bullish",  # Must be demand or supply
            "upper_bound": 42500.00,
            "lower_bound": 42000.00,
            "created_time": "2024-01-01T00:00:00Z",
            "candle_count": 3,
            "strength": 0.85,
            "touches": 0,
            "is_active": True,
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert "'bullish' is not one of ['demand', 'supply']" in str(exc_info.value)

    def test_strength_range_validation(self):
        schema = load_schema("zones.v1")

        # Strength > 1
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "zone_id": "ob_1h_20240101_000000",
            "zone_type": "order_block",
            "direction": "demand",
            "upper_bound": 42500.00,
            "lower_bound": 42000.00,
            "created_time": "2024-01-01T00:00:00Z",
            "candle_count": 3,
            "strength": 1.5,  # Must be 0-1
            "touches": 0,
            "is_active": True,
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert "1.5 is greater than the maximum of 1" in str(exc_info.value)
