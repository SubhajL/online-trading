"""Test the generated Python models."""

import pytest
from pathlib import Path
import sys

# Add parent directory to path to import contracts
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from contracts.gen.python.models import (
        CandlesV1,
        FeaturesV1,
        ZonesV1,
        SignalsRawV1,
        DecisionV1,
        OrderUpdateV1,
        SmcEventsV1,
        RegimeV1,
        NewsWindowV1,
        FundingWindowV1,
    )
except ImportError:
    pytest.skip("Generated models not available", allow_module_level=True)


class TestGeneratedModels:
    """Test that generated Python models work correctly."""

    def test_models_are_importable(self):
        """Test that all models can be imported."""
        assert CandlesV1 is not None
        assert FeaturesV1 is not None
        assert ZonesV1 is not None
        assert SignalsRawV1 is not None
        assert DecisionV1 is not None
        assert OrderUpdateV1 is not None
        assert SmcEventsV1 is not None
        assert RegimeV1 is not None
        assert NewsWindowV1 is not None
        assert FundingWindowV1 is not None

    def test_candle_model_basic(self):
        """Test basic candle model creation."""
        candle = CandlesV1(
            version="1.0.0",
            venue="binance",
            symbol="BTCUSDT",
            timeframe="1h",
            open_time="2024-01-15T10:00:00.000Z",
            close_time="2024-01-15T11:00:00.000Z",
            open="45000.0",
            high="45500.0",
            low="44800.0",
            close="45200.0",
            volume="100.5",
            quote_volume="4525000.0",
            trades=1500,
            taker_buy_volume="60.3",
            taker_buy_quote_volume="2715000.0",
            is_closed=True,
        )

        assert candle.symbol == "BTCUSDT"
        assert candle.open == "45000.0"
        assert candle.is_closed is True

    def test_decision_model_basic(self):
        """Test basic decision model creation."""
        decision = DecisionV1(
            version="1.0.0",
            venue="binance",
            symbol="BTCUSDT",
            decision_id="dec-123",
            decision_time="2024-01-15T11:00:00.000Z",
            action="open_long",
            signal_ids=["sig-001"],
            entry_price="45000.0",
            stop_loss="44500.0",
            take_profit="45500.0",
            position_size="0.1",
            risk_amount="50.0",
            risk_percentage=0.01,
            leverage="1.0",
            confidence=0.8,
            reason="Test decision",
        )

        assert decision.action == "open_long"
        assert decision.entry_price == "45000.0"
        assert len(decision.signal_ids) == 1
