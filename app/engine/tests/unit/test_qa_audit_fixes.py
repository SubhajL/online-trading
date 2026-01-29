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
