"""
Live integration tests for paper trading.

These tests require RUN_LIVE_PAPER_TRADING=1 environment variable.
They connect to Binance testnet and may take several minutes.

For deterministic unit tests, see:
- app/engine/tests/unit/paper/test_paper_broker_schema.py
- app/engine/tests/unit/paper/test_paper_bracket_lifecycle.py
- app/engine/tests/unit/paper/test_live_harness.py
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine.models import EventType, TimeFrame, TradingDecision, TradingDecisionEvent

# Skip all tests in this module unless explicitly enabled
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_PAPER_TRADING") != "1",
    reason="Set RUN_LIVE_PAPER_TRADING=1 to run live tests",
)


class TestLiveTestnetConnection:
    """Live tests that connect to Binance testnet."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(180)  # 3 minute timeout
    async def test_live_testnet_receives_closed_candle(self):
        """Harness receives at least one closed candle (k.x==true) from testnet."""
        import asyncio

        from app.engine.paper.live_harness import LivePaperTradingHarness

        config = {
            "symbols": ["BTCUSDT"],
            "timeframes": [TimeFrame.M1],
            "database_url": "postgresql://localhost:5432/test",
            "testnet": True,
        }
        harness = LivePaperTradingHarness(config)

        # Mock broker to avoid DB connection
        harness.broker.initialize = AsyncMock()
        harness.broker.close = AsyncMock()
        harness.broker.update_market_data = AsyncMock()

        try:
            await harness.start()
            # Wait for at least one candle (up to 2 minutes for 1m candle)
            for _ in range(120):
                await asyncio.sleep(1)
                if harness._metrics.candle_count >= 1:
                    break

            assert harness._metrics.candle_count >= 1, "No closed candles received"
        finally:
            await harness.stop()


class TestLiveDecisionHandling:
    """Live tests for decision handling."""

    @pytest.mark.asyncio
    async def test_live_decision_routes_to_paper_broker(self):
        """Trading decision event routes to paper broker."""
        from app.engine.paper.live_harness import LivePaperTradingHarness

        config = {
            "symbols": ["BTCUSDT"],
            "timeframes": [TimeFrame.M1],
            "database_url": "postgresql://localhost:5432/test",
            "testnet": True,
        }
        harness = LivePaperTradingHarness(config)

        # Mock dependencies
        harness.broker.initialize = AsyncMock()
        harness.broker.close = AsyncMock()
        harness.broker.place_bracket_order = AsyncMock(return_value=MagicMock())
        harness._persist_decision = AsyncMock()

        # Create test decision event
        decision = TradingDecision(
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            action="BUY",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            take_profit=Decimal("52000"),
            quantity=Decimal("0.01"),
            confidence=Decimal("0.85"),
            reasoning="Test decision",
        )
        event = TradingDecisionEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            decision=decision,
        )

        # Process decision
        await harness._on_decision(event)

        # Verify broker was called
        harness.broker.place_bracket_order.assert_called_once()
        assert harness._metrics.decision_count == 1
        assert harness._metrics.order_count == 1


class TestLiveAlertFiltering:
    """Live tests for alert filtering."""

    @pytest.mark.asyncio
    async def test_live_alert_subscriber_filters_to_decision_only(self):
        """Alert subscriber only handles TRADING_DECISION events."""
        from app.engine.paper.live_harness import LivePaperTradingHarness

        config = {
            "symbols": ["BTCUSDT"],
            "timeframes": [TimeFrame.M1],
            "database_url": "postgresql://localhost:5432/test",
            "testnet": True,
        }
        harness = LivePaperTradingHarness(config)

        # Verify alert subscriber only subscribes to TRADING_DECISION
        assert harness.alert_subscriber._event_types == [EventType.TRADING_DECISION]
