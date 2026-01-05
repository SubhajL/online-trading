"""
Tests for LivePaperTradingHarness.

Validates the harness that wires WebSocket → pipeline → paper broker
with decision persistence and Telegram alerts (decision only).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.engine.models import (
    Candle,
    CandleOrigin,
    EventType,
    TimeFrame,
    TradingDecision,
    TradingDecisionEvent,
)
from app.engine.paper.live_harness import LivePaperTradingHarness

# Accessing harness internals is intentional in these unit tests.
# ruff: noqa: SLF001

DB_PORT = 5433

if TYPE_CHECKING:
    from app.engine.paper.broker import PlaceBracketRequest


class TestLivePaperTradingHarnessInit:
    """Tests for harness initialization."""

    @pytest.mark.asyncio
    async def test_harness_init_creates_event_bus(self) -> None:
        """Harness creates an EventBus during initialization."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        assert harness.event_bus is not None

    @pytest.mark.asyncio
    async def test_harness_init_creates_ws_client_testnet(self) -> None:
        """Harness creates WebSocket client with testnet=True."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        assert harness.ws_client is not None
        # Testnet URL should be used
        assert "testnet" in harness.ws_client.base_url

    @pytest.mark.asyncio
    async def test_harness_init_creates_paper_broker(self) -> None:
        """Harness creates PaperBroker during initialization."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        assert harness.broker is not None

    @pytest.mark.asyncio
    async def test_harness_creates_db_adapter_from_config(self) -> None:
        """Harness creates TimescaleDBAdapter with parsed database URL."""
        config = _make_harness_config()
        config["database_url"] = f"postgresql://testuser:testpass@dbhost:{DB_PORT}/testdb"
        harness = LivePaperTradingHarness(config)

        assert harness.db_adapter is not None
        assert harness.db_adapter.host == "dbhost"
        assert harness.db_adapter.port == DB_PORT
        assert harness.db_adapter.database == "testdb"
        assert harness.db_adapter.username == "testuser"
        assert harness.db_adapter.password == "testpass"  # noqa: S105

    @pytest.mark.asyncio
    async def test_harness_has_unique_paper_session_id(self) -> None:
        """Harness has a unique UUID paper_session_id, different per instance."""
        config1 = _make_harness_config()
        config2 = _make_harness_config()
        harness1 = LivePaperTradingHarness(config1)
        harness2 = LivePaperTradingHarness(config2)

        assert isinstance(harness1.paper_session_id, UUID)
        assert isinstance(harness2.paper_session_id, UUID)
        assert harness1.paper_session_id != harness2.paper_session_id

    @pytest.mark.asyncio
    async def test_harness_accepts_custom_paper_session_id(self) -> None:
        """Harness uses provided paper_session_id from config."""
        custom_session_id = uuid4()
        config = _make_harness_config()
        config["paper_session_id"] = custom_session_id
        harness = LivePaperTradingHarness(config)

        assert harness.paper_session_id == custom_session_id

    @pytest.mark.asyncio
    async def test_harness_does_not_assign_run_id_to_broker(self) -> None:
        """Harness run session_id is not the broker bracket id."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        assert hasattr(harness, "paper_session_id")
        assert not hasattr(harness.broker, "paper_session_id")


class TestLivePaperTradingHarnessAlerts:
    """Tests for alert wiring."""

    @pytest.mark.asyncio
    async def test_wire_decision_only_alerts_creates_filtered_subscriber(
        self,
    ) -> None:
        """AlertSubscriber is created with event_types=[TRADING_DECISION] only."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        # Access the internal subscriber
        assert harness.alert_subscriber is not None
        assert harness.alert_subscriber._event_types == [EventType.TRADING_DECISION]


class TestLivePaperTradingHarnessPipeline:
    """Tests for pipeline wiring."""

    @pytest.mark.asyncio
    async def test_wire_pipeline_creates_and_starts_services(self) -> None:
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        await harness.event_bus.start(num_workers=1)
        try:
            await harness._wire_pipeline()

            assert harness.feature_service is not None
            assert harness.smc_service is not None
            assert harness.retest_engine is not None
            assert harness.decision_publisher is not None
        finally:
            if hasattr(harness, "decision_publisher") and harness.decision_publisher:
                await harness.decision_publisher.stop()
            if hasattr(harness, "retest_engine") and harness.retest_engine:
                await harness.retest_engine.stop()
            if hasattr(harness, "smc_service") and harness.smc_service:
                await harness.smc_service.stop()
            if hasattr(harness, "feature_service") and harness.feature_service:
                await harness.feature_service.stop()
            await harness.event_bus.stop()


class TestLivePaperTradingHarnessTelegramEnv:
    """Tests for Telegram adapter creation from env."""

    @pytest.mark.asyncio
    async def test_maybe_create_telegram_adapter_returns_none_without_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        adapter = await harness._maybe_create_telegram_adapter_from_env()
        assert adapter is None

    @pytest.mark.asyncio
    async def test_maybe_create_telegram_adapter_starts_adapter_with_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")

        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        with patch(
            "app.engine.paper.live_harness.TelegramAlertAdapter.start",
            new=AsyncMock(return_value=None),
        ) as start_mock:
            adapter = await harness._maybe_create_telegram_adapter_from_env()

        assert adapter is not None
        start_mock.assert_awaited_once()


class TestLivePaperTradingHarnessOnDecision:
    """Tests for decision handling."""

    @pytest.mark.asyncio
    async def test_on_decision_persists_before_broker_call(self) -> None:
        """Decision is persisted to DB before broker.place_bracket_order."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        # Mock dependencies
        call_order: list[str] = []

        async def mock_persist(_event: TradingDecisionEvent) -> None:
            call_order.append("persist")

        async def mock_place_bracket(_request: PlaceBracketRequest) -> object:
            call_order.append("place_bracket")
            return MagicMock()

        harness._persist_decision = mock_persist
        harness.broker.place_bracket_order = mock_place_bracket

        event = _make_trading_decision_event()
        await harness._on_decision(event)

        assert call_order == ["persist", "place_bracket"]

    @pytest.mark.asyncio
    async def test_on_decision_places_paper_order(self) -> None:
        """on_decision calls broker.place_bracket_order with correct params."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        harness._persist_decision = AsyncMock()
        harness.broker.place_bracket_order = AsyncMock(return_value=MagicMock())

        event = _make_trading_decision_event()
        await harness._on_decision(event)

        harness.broker.place_bracket_order.assert_called_once()
        call_args = harness.broker.place_bracket_order.call_args[0][0]
        assert call_args.symbol == "BTCUSDT"
        assert call_args.side == "BUY"

    @pytest.mark.asyncio
    async def test_on_decision_records_latency(self) -> None:
        """on_decision records processing latency in metrics."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        harness._persist_decision = AsyncMock()
        harness.broker.place_bracket_order = AsyncMock(return_value=MagicMock())

        event = _make_trading_decision_event()
        await harness._on_decision(event)

        metrics = harness.get_metrics()
        assert "decision_count" in metrics
        assert metrics["decision_count"] >= 1


class TestLivePaperTradingHarnessPersistDecision:
    """Tests for decision persistence via db_adapter."""

    @pytest.mark.asyncio
    async def test_persist_decision_calls_insert_trading_decision(self) -> None:
        """_persist_decision calls db_adapter.insert_trading_decision."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        # Mock db_adapter.insert_trading_decision
        harness.db_adapter.insert_trading_decision = AsyncMock(return_value=True)

        event = _make_trading_decision_event()
        await harness._persist_decision(event)

        harness.db_adapter.insert_trading_decision.assert_called_once_with(
            event.decision,
        )

    @pytest.mark.asyncio
    async def test_persist_decision_increments_error_on_failure(self) -> None:
        """_persist_decision increments error_count when insert returns False."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        # Mock db_adapter.insert_trading_decision to return False
        harness.db_adapter.insert_trading_decision = AsyncMock(return_value=False)

        initial_error_count = harness._metrics.error_count
        event = _make_trading_decision_event()
        await harness._persist_decision(event)

        assert harness._metrics.error_count == initial_error_count + 1

    @pytest.mark.asyncio
    async def test_persist_decision_increments_error_on_exception(self) -> None:
        """_persist_decision increments error_count on exception."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        # Mock db_adapter.insert_trading_decision to raise exception
        harness.db_adapter.insert_trading_decision = AsyncMock(
            side_effect=Exception("DB connection error"),
        )

        initial_error_count = harness._metrics.error_count
        event = _make_trading_decision_event()
        await harness._persist_decision(event)

        assert harness._metrics.error_count == initial_error_count + 1

    @pytest.mark.asyncio
    async def test_persist_decision_success_does_not_increment_error(self) -> None:
        """_persist_decision does not increment error_count on success."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        # Mock db_adapter.insert_trading_decision to return True
        harness.db_adapter.insert_trading_decision = AsyncMock(return_value=True)

        initial_error_count = harness._metrics.error_count
        event = _make_trading_decision_event()
        await harness._persist_decision(event)

        assert harness._metrics.error_count == initial_error_count


class TestLivePaperTradingHarnessOnCandle:
    """Tests for candle handling."""

    @pytest.mark.asyncio
    async def test_on_candle_updates_broker_market_data(self) -> None:
        """on_candle calls broker.update_market_data with candle."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        harness.broker.update_market_data = AsyncMock()

        candle = Candle(
            venue="spot",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M1,
            open_time=datetime.now(UTC),
            close_time=datetime.now(UTC),
            open_price=Decimal(50000),
            high_price=Decimal(50100),
            low_price=Decimal(49900),
            close_price=Decimal(50050),
            volume=Decimal(100),
            quote_volume=Decimal(5000000),
            trades=1000,
            taker_buy_base_volume=Decimal(50),
            taker_buy_quote_volume=Decimal(2500000),
        )

        await harness._on_candle(candle)

        harness.broker.update_market_data.assert_called_once_with(candle)


class TestLivePaperTradingHarnessWarmBuffers:
    """Tests for buffer warming."""

    @pytest.mark.asyncio
    async def test_warm_buffers_marks_candles_as_backfill(self) -> None:
        """warm_buffers fetches candles with CandleOrigin.BACKFILL."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        backfill_origins: list[CandleOrigin] = []

        async def mock_fetch_and_publish(origin: CandleOrigin) -> None:
            backfill_origins.append(origin)

        harness._fetch_historical_candles = mock_fetch_and_publish

        await harness.warm_buffers()

        assert CandleOrigin.BACKFILL in backfill_origins


class TestLivePaperTradingHarnessMetrics:
    """Tests for metrics collection."""

    def test_get_metrics_includes_all_keys(self) -> None:
        """get_metrics returns all expected metric keys."""
        config = _make_harness_config()
        harness = LivePaperTradingHarness(config)

        metrics = harness.get_metrics()

        expected_keys = [
            "decision_count",
            "candle_count",
            "order_count",
            "error_count",
            "latency_sum_ms",
        ]
        for key in expected_keys:
            assert key in metrics, f"Missing metric key: {key}"


# =============================================================================
# Test Helpers
# =============================================================================


def _make_harness_config() -> dict:
    """Create a minimal harness configuration for testing."""
    return {
        "symbols": ["BTCUSDT"],
        "timeframes": [TimeFrame.M1],
        "database_url": "postgresql://test:test@localhost:5432/test",
        "testnet": True,
    }


def _make_trading_decision_event() -> TradingDecisionEvent:
    """Create a sample trading decision event."""
    decision = TradingDecision(
        symbol="BTCUSDT",
        timestamp=datetime.now(UTC),
        action="BUY",
        entry_price=Decimal(50000),
        stop_loss=Decimal(49000),
        take_profit=Decimal(52000),
        quantity=Decimal("0.01"),
        confidence=Decimal("0.85"),
        reasoning="SMC Break; Trend Alignment",
    )
    return TradingDecisionEvent(
        timestamp=datetime.now(UTC),
        symbol="BTCUSDT",
        timeframe=TimeFrame.H1,
        metadata={"signal_id": "sig_123"},
        decision=decision,
    )
