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


class TestFeaturesV1Schema:
    def test_valid_features_payload(self):
        schema = load_schema("features.v1")

        valid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2024-01-01T00:00:00Z",
            "close_time": "2024-01-01T01:00:00Z",
            "ema_short": 42150.50,
            "ema_long": 42000.00,
            "rsi": 65.5,
            "macd": 150.25,
            "macd_signal": 140.10,
            "macd_histogram": 10.15,
            "atr": 500.50,
            "bb_upper": 43000.00,
            "bb_middle": 42000.00,
            "bb_lower": 41000.00,
            "volume_ma": 1500.50,
        }

        # Should not raise
        validate(instance=valid_payload, schema=schema)

    def test_optional_fields_can_be_null(self):
        schema = load_schema("features.v1")

        # All indicator fields are optional and can be null
        minimal_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2024-01-01T00:00:00Z",
            "close_time": "2024-01-01T01:00:00Z",
            "ema_short": None,
            "ema_long": None,
            "rsi": None,
            "macd": None,
            "macd_signal": None,
            "macd_histogram": None,
            "atr": None,
            "bb_upper": None,
            "bb_middle": None,
            "bb_lower": None,
            "volume_ma": None,
        }

        # Should not raise
        validate(instance=minimal_payload, schema=schema)

    def test_indicators_must_be_numeric_when_present(self):
        schema = load_schema("features.v1")

        # RSI as string instead of number
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2024-01-01T00:00:00Z",
            "close_time": "2024-01-01T01:00:00Z",
            "ema_short": 42150.50,
            "ema_long": 42000.00,
            "rsi": "65.5",  # Should be number
            "macd": 150.25,
            "macd_signal": 140.10,
            "macd_histogram": 10.15,
            "atr": 500.50,
            "bb_upper": 43000.00,
            "bb_middle": 42000.00,
            "bb_lower": 41000.00,
            "volume_ma": 1500.50,
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert "'65.5' is not of type" in str(exc_info.value)

    def test_rsi_range_validation(self):
        schema = load_schema("features.v1")

        # RSI > 100
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2024-01-01T00:00:00Z",
            "close_time": "2024-01-01T01:00:00Z",
            "ema_short": 42150.50,
            "ema_long": 42000.00,
            "rsi": 150.0,  # Invalid: RSI must be 0-100
            "macd": 150.25,
            "macd_signal": 140.10,
            "macd_histogram": 10.15,
            "atr": 500.50,
            "bb_upper": 43000.00,
            "bb_middle": 42000.00,
            "bb_lower": 41000.00,
            "volume_ma": 1500.50,
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert "150.0 is greater than the maximum of 100" in str(exc_info.value)

    def test_atr_must_be_positive(self):
        schema = load_schema("features.v1")

        # Negative ATR
        invalid_payload = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2024-01-01T00:00:00Z",
            "close_time": "2024-01-01T01:00:00Z",
            "ema_short": 42150.50,
            "ema_long": 42000.00,
            "rsi": 65.5,
            "macd": 150.25,
            "macd_signal": 140.10,
            "macd_histogram": 10.15,
            "atr": -500.50,  # Invalid: ATR must be >= 0
            "bb_upper": 43000.00,
            "bb_middle": 42000.00,
            "bb_lower": 41000.00,
            "volume_ma": 1500.50,
        }

        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid_payload, schema=schema)
        assert "-500.5 is less than the minimum of 0" in str(exc_info.value)
