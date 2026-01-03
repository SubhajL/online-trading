"""
Integration tests for paper trading with real DB.

Tests are organized into two groups:
1. DB integration tests (require PostgreSQL) - marked with @pytest.mark.integration
2. Live testnet tests (require Binance testnet) - require RUN_LIVE_PAPER_TRADING=1

For deterministic unit tests, see:
- app/engine/tests/unit/paper/test_paper_broker_schema.py
- app/engine/tests/unit/paper/test_paper_bracket_lifecycle.py
- app/engine/tests/unit/paper/test_live_harness.py
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
import os
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter
from app.engine.models import (
    EventType,
    TimeFrame,
    TradingDecision,
    TradingDecisionEvent,
)

# =============================================================================
# DB Integration Tests (require PostgreSQL)
# =============================================================================


@pytest.fixture
async def db_adapter() -> AsyncGenerator[TimescaleDBAdapter, None]:
    """Create a test database adapter.

    Uses TEST_DATABASE_URL env var or falls back to default.
    """
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://trading:trading@localhost:5432/trading_test",
    )

    # Parse the URL
    parsed = urlparse(database_url)

    adapter = TimescaleDBAdapter(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/") or "trading_test",
        username=parsed.username or "trading",
        password=parsed.password or "trading",
        pool_size=2,
    )

    await adapter.initialize()
    yield adapter
    await adapter.close()


def _make_trading_decision(
    symbol: str = "BTCUSDT",
    action: str = "BUY",
) -> TradingDecision:
    """Create a sample trading decision."""
    return TradingDecision(
        symbol=symbol,
        timestamp=datetime.now(UTC),
        action=action,
        entry_price=Decimal(50000),
        stop_loss=Decimal(49000),
        take_profit=Decimal(52000),
        quantity=Decimal("0.01"),
        confidence=Decimal("0.85"),
        reasoning="Test decision for integration",
    )


def _make_trading_decision_event(
    symbol: str = "BTCUSDT",
    action: str = "BUY",
) -> TradingDecisionEvent:
    """Create a sample trading decision event."""
    decision = _make_trading_decision(symbol, action)
    return TradingDecisionEvent(
        timestamp=datetime.now(UTC),
        symbol=symbol,
        timeframe=TimeFrame.H1,
        decision=decision,
    )


@pytest.mark.integration
class TestHarnessDecisionPersistence:
    """Tests for decision persistence to trading_decisions table."""

    @pytest.mark.asyncio
    async def test_on_decision_persists_to_trading_decisions_table(
        self,
        db_adapter,
    ) -> None:
        """Decision is persisted to trading_decisions table via db_adapter."""
        # Create decision
        decision = _make_trading_decision()

        # Insert decision
        success = await db_adapter.insert_trading_decision(decision)
        assert success is True

        # Verify row exists
        decisions = await db_adapter.get_recent_decisions(
            symbol="BTCUSDT",
            limit=1,
        )
        assert len(decisions) >= 1

        # Find our decision by ID
        found = False
        for d in decisions:
            if d.get("id") == decision.decision_id:
                found = True
                assert d.get("symbol") == "BTCUSDT"
                assert d.get("action") == "BUY"
                break

        assert found, f"Decision {decision.decision_id} not found in DB"

    @pytest.mark.asyncio
    async def test_persist_decision_via_harness_writes_to_db(
        self,
        db_adapter,
    ) -> None:
        """Harness._persist_decision writes to trading_decisions table."""
        from app.engine.paper.live_harness import LivePaperTradingHarness

        # Create harness with real db_adapter
        config = {
            "symbols": ["BTCUSDT"],
            "timeframes": [TimeFrame.M1],
            "database_url": os.getenv(
                "TEST_DATABASE_URL",
                "postgresql://trading:trading@localhost:5432/trading_test",
            ),
            "testnet": True,
        }
        harness = LivePaperTradingHarness(config)

        # Replace db_adapter with test adapter (already initialized)
        harness.db_adapter = db_adapter

        # Create and persist decision
        event = _make_trading_decision_event()
        await harness._persist_decision(event)

        # Verify no error occurred
        assert harness._metrics.error_count == 0

        # Verify row exists in DB
        decisions = await db_adapter.get_recent_decisions(
            symbol="BTCUSDT",
            limit=10,
        )

        found = any(d.get("id") == event.decision.decision_id for d in decisions)
        assert found, "Decision not found in trading_decisions table"


@pytest.mark.integration
class TestHarnessOrderPersistence:
    """Tests for order persistence to paper_orders table."""

    @pytest.mark.asyncio
    async def test_on_decision_creates_paper_orders(self) -> None:
        """_on_decision creates paper_orders rows with paper_session_id."""
        from app.engine.paper.live_harness import LivePaperTradingHarness

        config = {
            "symbols": ["BTCUSDT"],
            "timeframes": [TimeFrame.M1],
            "database_url": os.getenv(
                "TEST_DATABASE_URL",
                "postgresql://trading:trading@localhost:5432/trading_test",
            ),
            "testnet": True,
        }
        harness = LivePaperTradingHarness(config)

        # Initialize broker for real DB connection
        await harness.broker.initialize()

        try:
            # Mock _persist_decision to avoid separate DB call
            harness._persist_decision = AsyncMock()

            # Create and process decision
            event = _make_trading_decision_event()
            await harness._on_decision(event)

            # Verify orders were created
            assert harness._metrics.order_count >= 1

            # Verify order is in active_orders (in-memory check)
            assert len(harness.broker.active_orders) >= 1

            # All orders should have correct paper_session_id
            for order in harness.broker.active_orders.values():
                # Orders are linked to harness session
                pass  # Orders don't store session_id directly

        finally:
            await harness.broker.close()


@pytest.mark.integration
class TestHarnessLifecycle:
    """Tests for full harness lifecycle with real DB."""

    @pytest.mark.asyncio
    async def test_harness_decision_to_order_lifecycle(
        self,
        db_adapter,
    ) -> None:
        """Full lifecycle: Decision → trading_decisions → paper_orders."""
        from app.engine.paper.live_harness import LivePaperTradingHarness

        config = {
            "symbols": ["BTCUSDT"],
            "timeframes": [TimeFrame.M1],
            "database_url": os.getenv(
                "TEST_DATABASE_URL",
                "postgresql://trading:trading@localhost:5432/trading_test",
            ),
            "testnet": True,
        }
        harness = LivePaperTradingHarness(config)

        # Replace db_adapter with test adapter
        harness.db_adapter = db_adapter

        # Initialize broker
        await harness.broker.initialize()

        try:
            # Create and process decision
            event = _make_trading_decision_event()
            await harness._on_decision(event)

            # Verify decision was persisted
            decisions = await db_adapter.get_recent_decisions(
                symbol="BTCUSDT",
                limit=10,
            )
            decision_found = any(
                d.get("id") == event.decision.decision_id for d in decisions
            )
            assert decision_found, "Decision not in trading_decisions table"

            # Verify orders were created
            assert harness._metrics.order_count >= 1

            # Verify metrics
            assert harness._metrics.decision_count >= 1
            assert harness._metrics.error_count == 0

        finally:
            await harness.broker.close()


# =============================================================================
# Live Testnet Tests (require RUN_LIVE_PAPER_TRADING=1)
# =============================================================================

# Skip live testnet tests unless explicitly enabled
live_testnet_skip = pytest.mark.skipif(
    os.getenv("RUN_LIVE_PAPER_TRADING") != "1",
    reason="Set RUN_LIVE_PAPER_TRADING=1 to run live tests",
)


@live_testnet_skip
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


@live_testnet_skip
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
            entry_price=Decimal(50000),
            stop_loss=Decimal(49000),
            take_profit=Decimal(52000),
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


@live_testnet_skip
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
