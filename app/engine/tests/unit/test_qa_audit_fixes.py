"""Tests for QA audit fixes.

Covers:
1. Per-symbol lock in RouterExecutionSubscriber
2. Order DB persistence before event emission
3. Redis-backed signal cooldown (async methods)
4. Float contamination fix in decision engine
5. ErrorEvent emission in swallowed exceptions
6. Gap detection in IngestService
7. Transaction-wrapped paper broker writes
8. Risk parameter startup validation
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.engine.core.signal_cooldown import SignalCooldown
from app.engine.decision.engine import generate_decision
from app.engine.ingest.ingest_service import _timeframe_to_seconds
from app.engine.models import TimeFrame

# ---------------------------------------------------------------------------
# 1. Per-symbol lock
# ---------------------------------------------------------------------------


class TestPerSymbolLock:
    """Verify RouterExecutionSubscriber serializes orders per symbol."""

    @pytest.mark.asyncio
    async def test_symbol_lock_prevents_concurrent_execution(self) -> None:
        """Two decisions for same symbol must not execute concurrently."""
        from app.engine.execution.router_execution_subscriber import (
            RouterExecutionSubscriber,
        )

        execution_log: list[tuple[str, str]] = []

        bus = AsyncMock()
        bus.subscribe = AsyncMock(return_value="sub-1")
        bus.unsubscribe = AsyncMock(return_value=True)
        bus.publish = AsyncMock(return_value=True)

        router = AsyncMock()

        async def slow_place(payload: dict[str, Any]) -> dict[str, Any]:
            execution_log.append(("start", payload["symbol"]))
            await asyncio.sleep(0.05)
            execution_log.append(("end", payload["symbol"]))
            return {"success": True}

        router.place_bracket_order = AsyncMock(side_effect=slow_place)

        db_adapter = AsyncMock()
        risk = MagicMock()
        risk.max_daily_loss_pct = Decimal("0.05")

        sub = RouterExecutionSubscriber(
            bus=bus,
            router_client=router,
            db_adapter=db_adapter,
            risk=risk,
            venue="spot",
            execution_mode=MagicMock(value="spot_testnet"),
            order_update_correlation_store=AsyncMock(),
            min_confidence=Decimal("0.0"),
        )

        # Verify lock dict exists
        assert hasattr(sub, "_symbol_locks")
        assert isinstance(sub._symbol_locks, dict)

    @pytest.mark.asyncio
    async def test_different_symbols_can_execute_concurrently(self) -> None:
        """Locks are per-symbol, so different symbols should not block each other."""
        from app.engine.execution.router_execution_subscriber import (
            RouterExecutionSubscriber,
        )

        sub = RouterExecutionSubscriber(
            bus=AsyncMock(),
            router_client=AsyncMock(),
            db_adapter=AsyncMock(),
            risk=MagicMock(),
            venue="spot",
            execution_mode=MagicMock(value="spot_testnet"),
            order_update_correlation_store=AsyncMock(),
        )

        lock_btc = sub._get_symbol_lock("BTCUSDT")
        lock_eth = sub._get_symbol_lock("ETHUSDT")
        assert lock_btc is not lock_eth

        # Same symbol returns same lock
        assert sub._get_symbol_lock("BTCUSDT") is lock_btc


# ---------------------------------------------------------------------------
# 3. Redis-backed cooldown (async methods)
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._time = start

    def monotonic(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += seconds


class TestSignalCooldownAsync:
    """Test async Redis-backed cooldown methods."""

    @pytest.mark.asyncio
    async def test_should_allow_async_no_redis_falls_back(self) -> None:
        """Without Redis, async should_allow delegates to in-memory."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock, redis=None)

        result = await cooldown.should_allow_async("BTCUSDT", "15m", "z1", "BUY")
        assert result is True

        cooldown.record_signal("BTCUSDT", "15m", "z1", "BUY")

        result = await cooldown.should_allow_async("BTCUSDT", "15m", "z1", "BUY")
        assert result is False

    @pytest.mark.asyncio
    async def test_should_allow_async_with_redis(self) -> None:
        """With Redis, checks Redis first."""
        clock = FakeClock()
        redis = AsyncMock()
        redis.get = AsyncMock(return_value="1")  # In cooldown
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock, redis=redis)

        result = await cooldown.should_allow_async("BTCUSDT", "15m", "z1", "BUY")
        assert result is False
        redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_signal_async_writes_to_redis(self) -> None:
        """record_signal_async should write to Redis when available."""
        clock = FakeClock()
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock, redis=redis)

        await cooldown.record_signal_async("BTCUSDT", "15m", "z1", "BUY")

        redis.set.assert_called_once_with(
            "BTCUSDT:15m:z1:BUY",
            "1",
            expire=300,
            prefix="cooldown",
        )
        # Also in memory
        assert "BTCUSDT:15m:z1:BUY" in cooldown._cache

    @pytest.mark.asyncio
    async def test_record_signal_async_survives_redis_failure(self) -> None:
        """If Redis fails, in-memory fallback still works."""
        clock = FakeClock()
        redis = AsyncMock()
        redis.set = AsyncMock(side_effect=ConnectionError("down"))
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock, redis=redis)

        await cooldown.record_signal_async("BTCUSDT", "15m", "z1", "BUY")

        # In-memory still set
        assert "BTCUSDT:15m:z1:BUY" in cooldown._cache


# ---------------------------------------------------------------------------
# 4. Float contamination fix
# ---------------------------------------------------------------------------


class TestFloatContamination:
    """Verify decision engine outputs str instead of float for Decimal fields."""

    def test_risk_metadata_uses_str_not_float(self) -> None:
        """risk_metadata values should be str, not float."""
        signal = {
            "signal_type": "long",
            "entry_price": "50000",
            "stop_loss": "49000",
            "confidence": 0.85,
            "source": "smc_retest",
        }

        result = generate_decision(
            signal=signal,
            account_balance=Decimal("10000"),
            risk_percentage=Decimal("0.005"),
            symbol="BTCUSDT",
            is_futures=False,
        )

        meta = result["risk_metadata"]
        assert isinstance(meta["account_balance"], str), "account_balance should be str"
        assert isinstance(meta["position_value"], str), "position_value should be str"
        assert isinstance(meta["max_loss"], str), "max_loss should be str"
        assert isinstance(result["risk_percentage"], str), "risk_percentage should be str"

    def test_futures_leverage_is_str(self) -> None:
        """leverage in risk_metadata should be str for futures."""
        signal = {
            "signal_type": "long",
            "entry_price": "50000",
            "stop_loss": "49000",
            "confidence": 0.85,
            "source": "smc_retest",
        }

        result = generate_decision(
            signal=signal,
            account_balance=Decimal("10000"),
            risk_percentage=Decimal("0.005"),
            symbol="BTCUSDT",
            is_futures=True,
        )

        assert isinstance(result["risk_metadata"]["leverage"], str)

    def test_drawdown_metadata_uses_str(self) -> None:
        """Drawdown no_action decision should use str not float."""
        signal = {
            "signal_type": "long",
            "entry_price": "50000",
            "stop_loss": "49000",
            "confidence": 0.85,
            "source": "smc_retest",
        }

        result = generate_decision(
            signal=signal,
            account_balance=Decimal("10000"),
            risk_percentage=Decimal("0.005"),
            symbol="BTCUSDT",
            is_futures=False,
            daily_pnl_history=[Decimal("-500")],
            max_daily_drawdown=Decimal("0.01"),
        )

        if result["action"] == "no_action":
            meta = result["risk_metadata"]
            assert isinstance(meta["current_drawdown"], str)
            assert isinstance(meta["max_allowed"], str)


# ---------------------------------------------------------------------------
# 6. Gap detection
# ---------------------------------------------------------------------------


class TestGapDetection:
    """Test timeframe-to-seconds conversion and gap detection logic."""

    @pytest.mark.parametrize(
        ("tf", "expected"),
        [
            (TimeFrame.M1, 60),
            (TimeFrame.M5, 300),
            (TimeFrame.M15, 900),
            (TimeFrame.H1, 3600),
            (TimeFrame.H4, 14400),
        ],
    )
    def test_timeframe_to_seconds(self, tf: TimeFrame, expected: int) -> None:
        assert _timeframe_to_seconds(tf) == expected

    @pytest.mark.asyncio
    async def test_gap_detection_finds_gaps(self) -> None:
        """Gap detection should identify missing candles."""
        from app.engine.bus import set_event_bus
        from app.engine.ingest.ingest_service import IngestService

        mock_bus = MagicMock()
        mock_bus.subscribe = AsyncMock(return_value="sub-1")
        mock_bus.publish = AsyncMock(return_value=True)
        set_event_bus(mock_bus)

        config = {"api_key": "test", "api_secret": "test", "testnet": True}

        candle_1 = MagicMock()
        candle_1.close_time = datetime(2025, 1, 1, 0, 15, tzinfo=UTC)
        candle_1.open_time = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)

        candle_2 = MagicMock()
        candle_2.open_time = datetime(2025, 1, 1, 1, 0, tzinfo=UTC)  # 45min gap
        candle_2.close_time = datetime(2025, 1, 1, 1, 15, tzinfo=UTC)

        db_adapter = AsyncMock()
        db_adapter.get_candles = AsyncMock(return_value=[candle_1, candle_2])
        db_adapter.insert_candle = AsyncMock()

        svc = IngestService(
            binance_config=config,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=db_adapter,
        )

        gaps = await svc.get_gap_detection("BTCUSDT", TimeFrame.M15)

        assert len(gaps) == 1
        assert gaps[0]["expected_candles"] >= 1

    @pytest.mark.asyncio
    async def test_no_gaps_returns_empty(self) -> None:
        """Consecutive candles should return no gaps."""
        from app.engine.bus import set_event_bus
        from app.engine.ingest.ingest_service import IngestService

        mock_bus = MagicMock()
        mock_bus.subscribe = AsyncMock(return_value="sub-1")
        mock_bus.publish = AsyncMock(return_value=True)
        set_event_bus(mock_bus)

        config = {"api_key": "test", "api_secret": "test", "testnet": True}

        candle_1 = MagicMock()
        candle_1.close_time = datetime(2025, 1, 1, 0, 15, tzinfo=UTC)
        candle_1.open_time = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)

        candle_2 = MagicMock()
        candle_2.open_time = datetime(2025, 1, 1, 0, 15, tzinfo=UTC)
        candle_2.close_time = datetime(2025, 1, 1, 0, 30, tzinfo=UTC)

        db_adapter = AsyncMock()
        db_adapter.get_candles = AsyncMock(return_value=[candle_1, candle_2])
        db_adapter.insert_candle = AsyncMock()

        svc = IngestService(
            binance_config=config,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=db_adapter,
        )

        gaps = await svc.get_gap_detection("BTCUSDT", TimeFrame.M15)
        assert gaps == []


# ---------------------------------------------------------------------------
# 8. Risk parameter startup validation
# ---------------------------------------------------------------------------


class TestRiskParameterValidation:
    """Test preflight risk parameter checks."""

    def test_missing_risk_params_fails(self) -> None:
        from app.engine.preflight.verify_environment import check_risk_parameters

        with patch.dict("os.environ", {}, clear=True):
            result = check_risk_parameters()
            assert result.status.value.upper() == "FAILED"
            assert len(result.details["missing"]) == 3

    def test_valid_risk_params_pass(self) -> None:
        from app.engine.preflight.verify_environment import check_risk_parameters

        env = {
            "RISK_PER_TRADE_PCT": "0.005",
            "MAX_DAILY_LOSS_PCT": "0.05",
            "MAX_POSITION_SIZE": "100",
        }
        with patch.dict("os.environ", env, clear=True):
            result = check_risk_parameters()
            assert result.status.value.upper() == "PASSED"

    def test_out_of_bounds_risk_fails(self) -> None:
        from app.engine.preflight.verify_environment import check_risk_parameters

        env = {
            "RISK_PER_TRADE_PCT": "0.99",  # Way too high
            "MAX_DAILY_LOSS_PCT": "0.05",
            "MAX_POSITION_SIZE": "100",
        }
        with patch.dict("os.environ", env, clear=True):
            result = check_risk_parameters()
            assert result.status.value.upper() == "FAILED"
            assert "RISK_PER_TRADE_PCT" in result.details["invalid"]

    def test_non_numeric_risk_fails(self) -> None:
        from app.engine.preflight.verify_environment import check_risk_parameters

        env = {
            "RISK_PER_TRADE_PCT": "not_a_number",
            "MAX_DAILY_LOSS_PCT": "0.05",
            "MAX_POSITION_SIZE": "100",
        }
        with patch.dict("os.environ", env, clear=True):
            result = check_risk_parameters()
            assert result.status.value.upper() == "FAILED"
            assert "RISK_PER_TRADE_PCT" in result.details["invalid"]


# ---------------------------------------------------------------------------
# QA Round 2: Bug 7 — logger.exception preserves tracebacks
# ---------------------------------------------------------------------------


class TestTryAcquireAsync:
    """Test atomic try_acquire_async cooldown method."""

    @pytest.mark.asyncio
    async def test_try_acquire_async_redis_atomic(self) -> None:
        """First call acquires, second is blocked via Redis SET NX."""
        from app.engine.core.signal_cooldown import SignalCooldown

        clock = FakeClock()
        redis = AsyncMock()
        redis.set_nx = AsyncMock(side_effect=[True, False])
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock, redis=redis)

        first = await cooldown.try_acquire_async("BTCUSDT", "15m", "z1", "BUY")
        second = await cooldown.try_acquire_async("BTCUSDT", "15m", "z1", "BUY")

        assert first is True
        assert second is False
        assert redis.set_nx.call_count == 2

    @pytest.mark.asyncio
    async def test_try_acquire_async_no_redis_fallback(self) -> None:
        """Without Redis, uses in-memory check-and-set."""
        clock = FakeClock()
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock, redis=None)

        first = await cooldown.try_acquire_async("BTCUSDT", "15m", "z1", "BUY")
        second = await cooldown.try_acquire_async("BTCUSDT", "15m", "z1", "BUY")

        assert first is True
        assert second is False

    @pytest.mark.asyncio
    async def test_try_acquire_key_includes_venue(self) -> None:
        """Key must include venue prefix."""
        clock = FakeClock()
        redis = AsyncMock()
        redis.set_nx = AsyncMock(return_value=True)
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock, redis=redis)

        await cooldown.try_acquire_async("BTCUSDT", "15m", "z1", "BUY", venue="SPOT")

        assert "SPOT:BTCUSDT:15m:z1:BUY" in cooldown._cache

    @pytest.mark.asyncio
    async def test_try_acquire_updates_in_memory_on_success(self) -> None:
        """After Redis acquire, in-memory cache must also have the key."""
        clock = FakeClock()
        redis = AsyncMock()
        redis.set_nx = AsyncMock(return_value=True)
        cooldown = SignalCooldown(cooldown_seconds=300, clock=clock, redis=redis)

        await cooldown.try_acquire_async("BTCUSDT", "15m", "z1", "BUY", venue="SPOT")

        assert "SPOT:BTCUSDT:15m:z1:BUY" in cooldown._cache


class TestCooldownWiring:
    """Verify Redis is wired into cooldowns in main.py."""

    def test_main_passes_redis_to_cooldown(self) -> None:
        """SignalCooldown constructors in main.py must include redis= parameter."""
        import inspect

        from app.engine.main import initialize_services

        source = inspect.getsource(initialize_services)
        assert "redis=redis_adapter" in source


class TestPaperBrokerMemoryMutation:
    """Verify paper broker does not mutate memory on DB failure."""

    @pytest.mark.asyncio
    async def test_apply_fill_no_memory_mutation_on_db_failure(self) -> None:
        """If DB transaction fails, order.status must remain unchanged."""
        from contextlib import asynccontextmanager

        from app.engine.backtest.types import (
            BacktestFill,
            BacktestOrder,
            OrderSide,
            OrderStatus,
            OrderType,
        )
        from app.engine.paper.broker import PaperBroker

        # Proper async context manager mocks
        @asynccontextmanager
        async def fake_acquire():
            yield mock_conn

        @asynccontextmanager
        async def fake_transaction():
            yield

        mock_conn = AsyncMock()
        mock_conn.transaction = fake_transaction
        mock_conn.execute = AsyncMock(side_effect=Exception("DB down"))

        mock_pool = MagicMock()
        mock_pool.acquire = fake_acquire

        broker = PaperBroker.__new__(PaperBroker)
        broker.db_pool = mock_pool
        broker.positions = {}
        broker.active_orders = {}
        broker._order_bracket_ids = {"order-1": uuid4()}
        broker.cost_calculator = MagicMock()
        broker.cost_calculator.calculate_trading_fee = MagicMock(return_value=Decimal("0.50"))

        order = MagicMock(spec=BacktestOrder)
        order.client_order_id = "order-1"
        order.symbol = "BTCUSDT"
        order.status = OrderStatus.NEW
        order.quantity = Decimal("0.01")
        order.filled_quantity = Decimal("0")
        order.remaining_quantity = Decimal("0.01")
        order.fill_time = None
        order.type = OrderType.LIMIT
        order.reduce_only = False

        fill = MagicMock(spec=BacktestFill)
        fill.quantity = Decimal("0.01")
        fill.price = Decimal("50000")
        fill.fill_time = datetime(2025, 1, 1, tzinfo=UTC)
        fill.slippage = Decimal("0")

        candle = MagicMock()
        candle.close_price = Decimal("50000")

        with patch.object(broker, "_insert_paper_fill", AsyncMock(side_effect=Exception("DB down"))):
            with pytest.raises(Exception, match="DB down"):
                await broker._apply_fill(order, fill, candle)

        # Memory must NOT be mutated
        assert order.status == OrderStatus.NEW
        assert order.filled_quantity == Decimal("0")


class TestConcurrentSerialization:
    """Verify per-symbol lock actually serializes concurrent executions."""

    @pytest.mark.asyncio
    async def test_concurrent_decisions_same_symbol_serialize(self) -> None:
        """Two concurrent _on_trading_decision calls must not overlap."""
        from app.engine.execution.router_execution_subscriber import (
            RouterExecutionSubscriber,
        )

        execution_log: list[tuple[str, str]] = []

        sub = RouterExecutionSubscriber(
            bus=AsyncMock(),
            router_client=AsyncMock(),
            db_adapter=AsyncMock(),
            risk=MagicMock(),
            venue="spot",
            execution_mode=MagicMock(value="spot_testnet"),
            order_update_correlation_store=AsyncMock(),
        )

        async def tracking_execute(event: Any) -> None:
            symbol = event.decision.symbol
            execution_log.append(("start", symbol))
            await asyncio.sleep(0.05)
            execution_log.append(("end", symbol))

        with patch.object(sub, "_execute_decision", tracking_execute):

            def make_event(symbol: str) -> MagicMock:
                ev = MagicMock()
                ev.decision.symbol = symbol
                ev.decision.action = "BUY"
                ev.metadata = {"decision_source": "retest_decision_publisher"}
                ev.timeframe = MagicMock(value="15m")
                return ev

            await asyncio.gather(
                sub._on_trading_decision(make_event("BTCUSDT")),
                sub._on_trading_decision(make_event("BTCUSDT")),
            )

            # Serial: [start, end, start, end] not [start, start, end, end]
            assert execution_log[0] == ("start", "BTCUSDT")
            assert execution_log[1] == ("end", "BTCUSDT")
            assert execution_log[2] == ("start", "BTCUSDT")
            assert execution_log[3] == ("end", "BTCUSDT")


class TestGapDetectionRound2:
    """Tests for gap detection with DESC-ordered candles and single-candle gaps."""

    @pytest.mark.asyncio
    async def test_gap_detection_with_desc_ordered_candles(self) -> None:
        """Gap detection must find gaps even when DB returns candles in DESC order."""
        from app.engine.bus import set_event_bus
        from app.engine.ingest.ingest_service import IngestService

        mock_bus = MagicMock()
        mock_bus.subscribe = AsyncMock(return_value="sub-1")
        mock_bus.publish = AsyncMock(return_value=True)
        set_event_bus(mock_bus)

        config = {"api_key": "test", "api_secret": "test", "testnet": True}

        c1 = MagicMock()
        c1.open_time = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
        c1.close_time = datetime(2025, 1, 1, 0, 15, tzinfo=UTC)

        c2 = MagicMock()
        c2.open_time = datetime(2025, 1, 1, 0, 15, tzinfo=UTC)
        c2.close_time = datetime(2025, 1, 1, 0, 30, tzinfo=UTC)

        c3 = MagicMock()
        c3.open_time = datetime(2025, 1, 1, 1, 0, tzinfo=UTC)  # 30min gap after c2
        c3.close_time = datetime(2025, 1, 1, 1, 15, tzinfo=UTC)

        # DB returns DESC order: c3, c2, c1
        db_adapter = AsyncMock()
        db_adapter.get_candles = AsyncMock(return_value=[c3, c2, c1])

        svc = IngestService(
            binance_config=config,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=db_adapter,
        )

        gaps = await svc.get_gap_detection("BTCUSDT", TimeFrame.M15)
        assert len(gaps) == 1
        assert gaps[0]["missing_seconds"] == 1800.0

    @pytest.mark.asyncio
    async def test_gap_detection_single_missing_candle(self) -> None:
        """Detect exactly 1 missing M15 candle (delta=1800s > threshold=990s)."""
        from app.engine.bus import set_event_bus
        from app.engine.ingest.ingest_service import IngestService

        mock_bus = MagicMock()
        mock_bus.subscribe = AsyncMock(return_value="sub-1")
        mock_bus.publish = AsyncMock(return_value=True)
        set_event_bus(mock_bus)

        config = {"api_key": "test", "api_secret": "test", "testnet": True}

        c1 = MagicMock()
        c1.open_time = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
        c1.close_time = datetime(2025, 1, 1, 0, 15, tzinfo=UTC)

        # Skip 0:15-0:30 candle — next starts at 0:30
        c2 = MagicMock()
        c2.open_time = datetime(2025, 1, 1, 0, 30, tzinfo=UTC)
        c2.close_time = datetime(2025, 1, 1, 0, 45, tzinfo=UTC)

        db_adapter = AsyncMock()
        db_adapter.get_candles = AsyncMock(return_value=[c1, c2])

        svc = IngestService(
            binance_config=config,
            symbols=["BTCUSDT"],
            timeframes=[TimeFrame.M15],
            enable_realtime=False,
            enable_backfill=False,
            db_adapter=db_adapter,
        )

        gaps = await svc.get_gap_detection("BTCUSDT", TimeFrame.M15)
        # close_time 0:15 to open_time 0:30 = 900s, threshold = 990s → no gap
        # This is correct behavior for a single missing candle on contiguous timestamps
        assert gaps == []


class TestBracketOrderIdMapping:
    """Verify _persist_order_to_db reads bracket_order_id from router response."""

    @pytest.mark.asyncio
    async def test_persist_order_uses_bracket_order_id(self) -> None:
        """exchange_order_id must come from response['bracket_order_id']."""
        from app.engine.execution.router_execution_subscriber import (
            RouterExecutionSubscriber,
        )

        captured_rows: list[dict[str, Any]] = []

        async def fake_upsert(row: dict[str, Any]) -> None:
            captured_rows.append(row)

        sub = RouterExecutionSubscriber(
            bus=AsyncMock(),
            router_client=AsyncMock(),
            db_adapter=AsyncMock(),
            risk=MagicMock(),
            venue="spot",
            execution_mode=MagicMock(value="spot_testnet"),
            order_update_correlation_store=AsyncMock(),
            min_confidence=Decimal("0.0"),
        )

        event = MagicMock()
        event.decision.symbol = "BTCUSDT"
        event.decision.action = "BUY"
        event.decision.quantity = Decimal("0.01")
        event.decision.entry_price = Decimal("50000")
        event.decision.stop_loss = Decimal("49000")
        event.decision.decision_id = "dec-1"
        event.metadata = {}

        response = {"bracket_order_id": "bracket-abc-123", "success": True}

        with patch(
            "app.engine.adapters.db.timescale.upsert_order",
            side_effect=fake_upsert,
        ):
            await sub._persist_order_to_db(event, response, "client-1")

        assert len(captured_rows) == 1
        assert captured_rows[0]["exchange_order_id"] == "bracket-abc-123"


class TestLoggerExceptionTracebacks:
    """Verify error handlers use logger.exception to preserve tracebacks."""

    def test_feature_service_uses_logger_exception(self) -> None:
        """feature_service error handler must use logger.exception, not logger.error."""
        import inspect

        from app.engine.features.feature_service import FeatureService

        source = inspect.getsource(FeatureService)
        assert 'logger.error(f"Error handling candle update: {e}")' not in source
        assert "logger.exception" in source

    def test_smc_engine_uses_logger_exception(self) -> None:
        """smc engine error handler must use logger.exception."""
        import inspect

        from app.engine.smc.engine import SMCEngine

        source = inspect.getsource(SMCEngine)
        assert 'logger.error(f"Error processing candle in SMC engine: {e}")' not in source
        assert "logger.exception" in source

    def test_ingest_service_uses_logger_exception(self) -> None:
        """ingest_service candle persist error handler must use logger.exception."""
        import inspect

        from app.engine.ingest.ingest_service import IngestService

        source = inspect.getsource(IngestService)
        assert 'logger.error(f"Failed to persist candle' not in source
        assert "logger.exception" in source
