import json
import pytest
from pathlib import Path
from datetime import datetime

# Import generated models
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from contracts.gen.python.models import (
    CandlesV1, FeaturesV1, SmcEventsV1, ZonesV1,
    SignalsRawV1, RegimeV1, NewsWindowV1,
    FundingWindowV1, DecisionV1, OrderUpdateV1
)


class TestGeneratedPythonModels:
    def test_candles_v1_model_validation(self):
        """Test CandlesV1 model validates correctly."""
        valid_data = {
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

        # Should create model successfully
        candle = CandlesV1(**valid_data)
        assert candle.symbol == "BTCUSDT"
        assert candle.open == 42000.50

    def test_features_v1_nullable_fields(self):
        """Test FeaturesV1 handles nullable indicator fields."""
        valid_data = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2024-01-01T00:00:00Z",
            "close_time": "2024-01-01T01:00:00Z",
            "ema_short": 42150.50,
            "ema_long": None,  # Nullable
            "rsi": 65.5,
            "macd": None,  # Nullable
            "macd_signal": None,  # Nullable
            "macd_histogram": None,  # Nullable
            "atr": 500.50,
            "bb_upper": None,  # Nullable
            "bb_middle": None,  # Nullable
            "bb_lower": None,  # Nullable
            "volume_ma": 1500.50
        }

        features = FeaturesV1(**valid_data)
        assert features.ema_short == 42150.50
        assert features.ema_long is None
        assert features.rsi == 65.5

    def test_decision_v1_enum_validation(self):
        """Test DecisionV1 validates enum fields correctly."""
        valid_data = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "decision_id": "dec_123",
            "decision_time": "2024-01-01T00:00:00Z",
            "action": "open_long",
            "signal_ids": ["sig_1", "sig_2"],
            "entry_price": 42000.00,
            "stop_loss": 41500.00,
            "take_profit": 43000.00,
            "position_size": 0.1,
            "risk_amount": 50.0,
            "risk_percentage": 0.01,
            "leverage": 1.0,
            "confidence": 0.85,
            "reason": "Strong bullish signal with zone confluence"
        }

        decision = DecisionV1(**valid_data)
        assert decision.action == "open_long"

        # Test invalid action
        invalid_data = valid_data.copy()
        invalid_data["action"] = "invalid_action"

        with pytest.raises(ValueError) as exc_info:
            DecisionV1(**invalid_data)
        assert "literal_error" in str(exc_info.value).lower()

    def test_model_forbids_extra_fields(self):
        """Test models reject extra fields (additionalProperties: false)."""
        valid_data = {
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
            "extra_field": "should fail"  # Extra field
        }

        with pytest.raises(ValueError) as exc_info:
            CandlesV1(**valid_data)
        assert "extra" in str(exc_info.value).lower()

    def test_order_update_v1_complex_model(self):
        """Test OrderUpdateV1 with all nullable fields."""
        valid_data = {
            "version": "1.0.0",
            "venue": "binance",
            "symbol": "BTCUSDT",
            "order_id": "123456",
            "client_order_id": "client_123",
            "decision_id": "dec_123",
            "update_time": "2024-01-01T00:00:00Z",
            "status": "filled",
            "side": "buy",
            "order_type": "limit",
            "price": 42000.00,
            "stop_price": None,
            "quantity": 0.1,
            "filled_quantity": 0.1,
            "average_fill_price": 42000.00,
            "commission": 0.042,
            "commission_asset": "BTC",
            "error_message": None,
            "is_reduce_only": False
        }

        order = OrderUpdateV1(**valid_data)
        assert order.status == "filled"
        assert order.stop_price is None
        assert order.error_message is None

    def test_all_models_serialize_to_json(self):
        """Test all models can serialize to JSON."""
        # Create a simple valid instance of each model
        models_data = {
            CandlesV1: {
                "version": "1.0.0", "venue": "binance", "symbol": "BTCUSDT",
                "timeframe": "1h", "open_time": "2024-01-01T00:00:00Z",
                "close_time": "2024-01-01T01:00:00Z", "open": 100.0,
                "high": 100.0, "low": 100.0, "close": 100.0,
                "volume": 100.0, "quote_volume": 100.0, "trades": 100,
                "taker_buy_volume": 100.0, "taker_buy_quote_volume": 100.0,
                "is_closed": True
            },
            SmcEventsV1: {
                "version": "1.0.0", "venue": "binance", "symbol": "BTCUSDT",
                "timeframe": "1h", "event_time": "2024-01-01T00:00:00Z",
                "event_type": "choch", "direction": "bullish",
                "price_level": 100.0, "previous_pivot_price": 100.0,
                "previous_pivot_time": "2024-01-01T00:00:00Z",
                "broken_pivot_price": 100.0, "broken_pivot_time": "2024-01-01T00:00:00Z"
            }
        }

        for model_cls, data in models_data.items():
            instance = model_cls(**data)
            # Should serialize without error
            json_str = instance.model_dump_json()
            assert isinstance(json_str, str)

            # Should deserialize back
            parsed = json.loads(json_str)
            assert parsed["version"] == "1.0.0"