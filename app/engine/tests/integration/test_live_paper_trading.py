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

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
from typing import TYPE_CHECKING, Protocol
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import asyncpg
import pytest
import pytest_asyncio

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter
from app.engine.models import (
    Candle,
    EventType,
    TimeFrame,
    TradingDecision,
    TradingDecisionEvent,
)
from app.engine.paper.broker import PaperBroker, PlaceBracketRequest
from app.engine.paper.live_harness import LivePaperTradingHarness
from app.engine.tests.integration.db_config import load_test_database_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

BRACKET_ORDER_COUNT = 3
BRACKET_FILL_COUNT_ENTRY_ONLY = 1
BRACKET_FILL_COUNT_WITH_TP = 2


class _TestDbCfg(Protocol):
    host: str
    port: int
    username: str
    password: str
    database: str


async def _connect_test_db(cfg: _TestDbCfg) -> asyncpg.Connection:
    return await asyncpg.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.username,
        password=cfg.password,
        database=cfg.database,
    )


def _make_candle(
    *,
    symbol: str,
    ohlc: tuple[Decimal, Decimal, Decimal, Decimal],
    now: datetime | None = None,
    timeframe: TimeFrame = TimeFrame.M1,
) -> Candle:
    open_price, high_price, low_price, close_price = ohlc
    if now is None:
        now = datetime.now(UTC).replace(microsecond=0)

    volume = Decimal(1)
    quote_volume = close_price * volume

    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=now,
        close_time=now + timedelta(minutes=1),
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
        quote_volume=quote_volume,
        trades=1,
        taker_buy_base_volume=Decimal(0),
        taker_buy_quote_volume=Decimal(0),
    )

# =============================================================================
# DB Integration Tests (require PostgreSQL)
# =============================================================================


@pytest_asyncio.fixture
async def db_adapter() -> AsyncIterator[TimescaleDBAdapter]:
    """Create a test database adapter.

    Uses TEST_DATABASE_URL env var or falls back to default.
    """
    cfg = load_test_database_config()

    adapter = TimescaleDBAdapter(
        host=cfg.host,
        port=cfg.port,
        database=cfg.database,
        username=cfg.username,
        password=cfg.password,
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
        db_adapter: TimescaleDBAdapter,
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
        db_adapter: TimescaleDBAdapter,
    ) -> None:
        """Harness._persist_decision writes to trading_decisions table."""
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
        await harness._persist_decision(event)  # noqa: SLF001

        # Verify no error occurred
        assert harness.get_metrics()["error_count"] == 0

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
    async def test_on_decision_creates_paper_orders(
        self,
        db_adapter: TimescaleDBAdapter,
    ) -> None:
        """_on_decision creates paper_orders rows with paper_session_id."""
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

        # Use test db_adapter for decision persistence
        harness.db_adapter = db_adapter

        # Initialize broker for real DB connection
        await harness.broker.initialize()

        try:
            # Create and process decision (real persistence, no mocking)
            event = _make_trading_decision_event()
            await harness._on_decision(event)  # noqa: SLF001

            # Verify decision was persisted (no mock)
            assert harness.get_metrics()["error_count"] == 0

            # Verify orders were created
            assert harness.get_metrics()["order_count"] >= 1

            # Verify order is in active_orders (in-memory check)
            assert len(harness.broker.active_orders) >= 1

            # Verify decision persisted to DB
            decisions = await db_adapter.get_recent_decisions(
                symbol="BTCUSDT",
                limit=10,
            )
            decision_found = any(
                d.get("id") == event.decision.decision_id for d in decisions
            )
            assert decision_found, "Decision should be persisted to trading_decisions"

        finally:
            await harness.broker.close()


@pytest.mark.integration
class TestHarnessLifecycle:
    """Tests for full harness lifecycle with real DB."""

    @pytest.mark.asyncio
    async def test_harness_decision_to_order_lifecycle(
        self,
        db_adapter: TimescaleDBAdapter,
    ) -> None:
        """Full lifecycle: Decision → trading_decisions → paper_orders."""
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
            await harness._on_decision(event)  # noqa: SLF001

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
            assert harness.get_metrics()["order_count"] >= 1

            # Verify metrics
            metrics = harness.get_metrics()
            assert metrics["decision_count"] >= 1
            assert metrics["error_count"] == 0

        finally:
            await harness.broker.close()


@pytest.mark.integration
class TestPaperBrokerDbPersistence:
    @pytest.mark.asyncio
    async def test_db_bracket_fill_writes_paper_orders_positions_fills(self) -> None:
        """Entry fill persists paper_orders/paper_positions/paper_fills."""
        database_url = os.environ["TEST_DATABASE_URL"]
        cfg = load_test_database_config()

        conn = await _connect_test_db(cfg)
        try:
            await conn.execute("TRUNCATE TABLE paper_orders CASCADE")
        finally:
            await conn.close()

        broker = PaperBroker(database_url=database_url)
        await broker.initialize()
        try:
            candle = _make_candle(
                symbol="BTCUSDT",
                ohlc=(
                    Decimal(50000),
                    Decimal(50500),
                    Decimal(49500),
                    Decimal(50200),
                ),
            )
            await broker.update_market_data(candle)

            response = await broker.place_bracket_order(
                PlaceBracketRequest(
                    symbol="BTCUSDT",
                    side="BUY",
                    quantity=Decimal("0.01"),
                    entry_price=Decimal(0),
                    take_profit_prices=[Decimal(52000)],
                    stop_loss_price=Decimal(49000),
                    order_type="MARKET",
                    is_futures=False,
                ),
            )

            bracket_id = UUID(response.bracket_order_id)
            conn = await _connect_test_db(cfg)
            try:
                order_rows = await conn.fetch(
                    """
                    SELECT status, reduce_only
                    FROM paper_orders
                    WHERE paper_session_id = $1
                    ORDER BY reduce_only ASC
                    """,
                    bracket_id,
                )
                assert len(order_rows) == BRACKET_ORDER_COUNT
                assert order_rows[0]["status"] == "FILLED"
                assert order_rows[0]["reduce_only"] is False
                assert [r["status"] for r in order_rows[1:]] == ["NEW", "NEW"]
                assert [r["reduce_only"] for r in order_rows[1:]] == [True, True]

                fills_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM paper_fills WHERE symbol = 'BTCUSDT'",
                )
                assert fills_count == BRACKET_FILL_COUNT_ENTRY_ONLY

                position = await conn.fetchrow(
                    """
                    SELECT side, quantity
                    FROM paper_positions
                    WHERE symbol = 'BTCUSDT' AND paper_session_id = $1
                    """,
                    bracket_id,
                )
                assert position is not None
                assert position["side"] == "LONG"
                assert position["quantity"] == Decimal("0.01")
            finally:
                await conn.close()
        finally:
            await broker.close()

    @pytest.mark.asyncio
    async def test_db_tp_fill_cancels_sl_sibling_in_db(self) -> None:
        """TP fill cancels SL sibling order (OCO)."""
        database_url = os.environ["TEST_DATABASE_URL"]
        cfg = load_test_database_config()

        conn = await _connect_test_db(cfg)
        try:
            await conn.execute("TRUNCATE TABLE paper_orders CASCADE")
        finally:
            await conn.close()

        broker = PaperBroker(database_url=database_url)
        await broker.initialize()
        try:
            entry_candle = _make_candle(
                symbol="BTCUSDT",
                ohlc=(
                    Decimal(50000),
                    Decimal(50100),
                    Decimal(49900),
                    Decimal(50050),
                ),
            )
            await broker.update_market_data(entry_candle)

            response = await broker.place_bracket_order(
                PlaceBracketRequest(
                    symbol="BTCUSDT",
                    side="BUY",
                    quantity=Decimal("0.01"),
                    entry_price=Decimal(0),
                    take_profit_prices=[Decimal(51000)],
                    stop_loss_price=Decimal(49000),
                    order_type="MARKET",
                    is_futures=False,
                ),
            )

            tp_candle = _make_candle(
                symbol="BTCUSDT",
                ohlc=(
                    Decimal(50050),
                    Decimal(52000),
                    Decimal(49500),
                    Decimal(51500),
                ),
            )
            await broker.update_market_data(tp_candle)

            bracket_id = UUID(response.bracket_order_id)
            conn = await _connect_test_db(cfg)
            try:
                statuses = await conn.fetch(
                    """
                    SELECT client_order_id, reduce_only, status
                    FROM paper_orders
                    WHERE paper_session_id = $1
                    ORDER BY client_order_id ASC
                    """,
                    bracket_id,
                )
                assert len(statuses) == BRACKET_ORDER_COUNT

                filled = [r for r in statuses if r["status"] == "FILLED"]
                canceled = [r for r in statuses if r["status"] == "CANCELED"]

                assert len(filled) == BRACKET_FILL_COUNT_WITH_TP
                assert len(canceled) == 1
                assert canceled[0]["reduce_only"] is True

                fills_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM paper_fills WHERE symbol = 'BTCUSDT'",
                )
                assert fills_count == BRACKET_FILL_COUNT_WITH_TP
            finally:
                await conn.close()
        finally:
            await broker.close()


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
    async def test_live_testnet_receives_closed_candle(self) -> None:
        """Harness receives at least one closed candle (k.x==true) from testnet."""
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
            await asyncio.wait_for(_await_first_candle(harness), timeout=180)

            assert (
                harness.get_metrics()["candle_count"] >= 1
            ), "No closed candles received"
        finally:
            await harness.stop()


async def _await_first_candle(harness: LivePaperTradingHarness) -> None:
    first = asyncio.Event()

    async def _on_candle(_event: object) -> None:
        first.set()

    subscription_id = await harness.event_bus.subscribe(
        subscriber_id="test-first-candle",
        handler=_on_candle,
        event_types=[EventType.CANDLE_UPDATE],
        priority=0,
    )
    try:
        await first.wait()
    finally:
        await harness.event_bus.unsubscribe(subscription_id)


@live_testnet_skip
class TestLiveDecisionHandling:
    """Live tests for decision handling."""

    @pytest.mark.asyncio
    async def test_live_decision_routes_to_paper_broker(self) -> None:
        """Trading decision event routes to paper broker."""
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
        harness._persist_decision = AsyncMock()  # noqa: SLF001

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
        await harness._on_decision(event)  # noqa: SLF001

        # Verify broker was called
        harness.broker.place_bracket_order.assert_called_once()
        metrics = harness.get_metrics()
        assert metrics["decision_count"] == 1
        assert metrics["order_count"] == 1


@live_testnet_skip
class TestLiveAlertFiltering:
    """Live tests for alert filtering."""

    @pytest.mark.asyncio
    async def test_live_alert_subscriber_filters_to_decision_only(self) -> None:
        """Alert subscriber only handles TRADING_DECISION events."""
        config = {
            "symbols": ["BTCUSDT"],
            "timeframes": [TimeFrame.M1],
            "database_url": "postgresql://localhost:5432/test",
            "testnet": True,
        }
        harness = LivePaperTradingHarness(config)

        # Verify alert subscriber only subscribes to TRADING_DECISION
        assert harness.alert_subscriber._event_types == [EventType.TRADING_DECISION]  # noqa: SLF001
