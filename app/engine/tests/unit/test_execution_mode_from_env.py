from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine.execution.order_update_correlation import OrderUpdateCorrelationStore
from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    RouterExecutionSubscriber,
    execution_mode_from_env,
)
from app.engine.models import EventType, RiskParameters, TradingDecision, TradingDecisionEvent


class _FakeDBAdapter:
    async def get_latest_equity_sample(self):
        return Decimal(10_000), datetime.now(UTC)

    async def get_equity_sample_at_or_after(self, _ts: datetime):
        return Decimal(10_000)

    async def get_peak_equity_since(self, _ts: datetime):
        return Decimal(10_000)

    async def get_active_positions(self, _venue: str):
        return []


def _default_risk() -> RiskParameters:
    return RiskParameters(
        max_position_size=Decimal("999999"),
        max_daily_loss=Decimal("1"),
        max_drawdown=Decimal("1"),
        risk_per_trade=Decimal("0.01"),
        max_correlation=Decimal("1"),
        max_open_positions=100,
        max_total_exposure_leverage=Decimal("100"),
        max_symbol_exposure_pct=Decimal("1"),
        max_position_notional_pct=Decimal("1"),
        risk_data_max_age_seconds=86400,
        drawdown_lookback_days=30,
    )


class TestExecutionModeFromEnv:
    def test_defaults_to_disabled(self) -> None:
        assert execution_mode_from_env({}) == ExecutionMode.DISABLED

    def test_rejects_unknown_value(self) -> None:
        with pytest.raises(RuntimeError, match="Unknown EXECUTION_MODE"):
            execution_mode_from_env({"EXECUTION_MODE": "nope"})

    def test_requires_ack_for_futures_mainnet(self) -> None:
        with pytest.raises(RuntimeError, match="I_UNDERSTAND_LIVE_TRADING"):
            execution_mode_from_env({"EXECUTION_MODE": "futures_mainnet"})

    def test_allows_futures_mainnet_with_ack(self) -> None:
        result = execution_mode_from_env(
            {
                "EXECUTION_MODE": "futures_mainnet",
                "I_UNDERSTAND_LIVE_TRADING": "1",
            }
        )
        assert result == ExecutionMode.FUTURES_MAINNET

    def test_allows_futures_testnet(self) -> None:
        result = execution_mode_from_env({"EXECUTION_MODE": "futures_testnet"})
        assert result == ExecutionMode.FUTURES_TESTNET

    def test_allows_spot_testnet(self) -> None:
        """Test that spot_testnet mode is accepted."""
        result = execution_mode_from_env({"EXECUTION_MODE": "spot_testnet"})
        assert result == ExecutionMode.SPOT_TESTNET

    def test_requires_ack_for_spot_mainnet(self) -> None:
        """Test that spot_mainnet requires I_UNDERSTAND_LIVE_TRADING=1."""
        with pytest.raises(RuntimeError, match="I_UNDERSTAND_LIVE_TRADING"):
            execution_mode_from_env({"EXECUTION_MODE": "spot_mainnet"})

    def test_allows_spot_mainnet_with_ack(self) -> None:
        """Test that spot_mainnet is accepted with safety flag."""
        result = execution_mode_from_env(
            {
                "EXECUTION_MODE": "spot_mainnet",
                "I_UNDERSTAND_LIVE_TRADING": "1",
            }
        )
        assert result == ExecutionMode.SPOT_MAINNET


class TestExecutionModeEnum:
    def test_spot_testnet_value(self) -> None:
        assert ExecutionMode.SPOT_TESTNET.value == "spot_testnet"

    def test_spot_mainnet_value(self) -> None:
        assert ExecutionMode.SPOT_MAINNET.value == "spot_mainnet"

    def test_all_modes_exist(self) -> None:
        """Verify all expected execution modes exist."""
        modes = {m.value for m in ExecutionMode}
        expected = {
            "disabled",
            "spot_testnet",
            "spot_mainnet",
            "futures_testnet",
            "futures_mainnet",
        }
        assert modes == expected


class TestBuildOrderPayload:
    @pytest.fixture
    def sample_decision(self) -> TradingDecision:
        return TradingDecision(
            venue="SPOT",
            symbol="BTCUSDT",
            action="BUY",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            entry_price=Decimal("50000.00"),
            stop_loss=Decimal("49500.00"),
            take_profit=Decimal("51000.00"),
            quantity=Decimal("0.001"),
            confidence=Decimal("0.8"),
            reasoning="Test signal",
        )

    @pytest.fixture
    def sample_event(self, sample_decision: TradingDecision) -> TradingDecisionEvent:
        return TradingDecisionEvent(
            event_type=EventType.TRADING_DECISION,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTCUSDT",
            timeframe=None,
            decision=sample_decision,
            metadata={
                "decision_source": "retest_decision_publisher",
                "signal_id": "sig-001",
            },
        )

    @pytest.mark.asyncio
    async def test_payload_includes_decision_ts(
        self,
        sample_event: TradingDecisionEvent,
    ) -> None:
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        mock_router = MagicMock()
        mock_router.place_bracket_order = AsyncMock(return_value={"success": True})

        subscriber = RouterExecutionSubscriber(
            bus=mock_bus,
            router_client=mock_router,
            db_adapter=_FakeDBAdapter(),  # type: ignore[arg-type]
            risk=_default_risk(),
            venue="SPOT",
            execution_mode=ExecutionMode.SPOT_TESTNET,
            order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
        )

        await subscriber._on_trading_decision(sample_event)

        mock_router.place_bracket_order.assert_called_once()
        payload = mock_router.place_bracket_order.call_args[0][0]

        assert "decision_ts" in payload
        assert payload["decision_ts"] == "2025-01-01T12:00:00+00:00"

    @pytest.mark.asyncio
    async def test_payload_includes_expected_price(
        self,
        sample_event: TradingDecisionEvent,
    ) -> None:
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        mock_router = MagicMock()
        mock_router.place_bracket_order = AsyncMock(return_value={"success": True})

        subscriber = RouterExecutionSubscriber(
            bus=mock_bus,
            router_client=mock_router,
            db_adapter=_FakeDBAdapter(),  # type: ignore[arg-type]
            risk=_default_risk(),
            venue="SPOT",
            execution_mode=ExecutionMode.SPOT_TESTNET,
            order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
        )

        await subscriber._on_trading_decision(sample_event)

        mock_router.place_bracket_order.assert_called_once()
        payload = mock_router.place_bracket_order.call_args[0][0]

        assert "expected_price" in payload
        assert payload["expected_price"] == "50000.00"

    @pytest.mark.asyncio
    async def test_expected_price_is_string_decimal(
        self,
        sample_decision: TradingDecision,
    ) -> None:
        sample_decision = TradingDecision(
            venue="SPOT",
            symbol="BTCUSDT",
            action="BUY",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            entry_price=Decimal("50123.45678901"),
            stop_loss=Decimal("49500.00"),
            take_profit=Decimal("51000.00"),
            quantity=Decimal("0.001"),
            confidence=Decimal("0.8"),
            reasoning="Test signal",
        )
        event = TradingDecisionEvent(
            event_type=EventType.TRADING_DECISION,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            symbol="BTCUSDT",
            timeframe=None,
            decision=sample_decision,
            metadata={"decision_source": "retest_decision_publisher"},
        )

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()
        mock_router = MagicMock()
        mock_router.place_bracket_order = AsyncMock(return_value={"success": True})

        subscriber = RouterExecutionSubscriber(
            bus=mock_bus,
            router_client=mock_router,
            db_adapter=_FakeDBAdapter(),  # type: ignore[arg-type]
            risk=_default_risk(),
            venue="SPOT",
            execution_mode=ExecutionMode.SPOT_TESTNET,
            order_update_correlation_store=OrderUpdateCorrelationStore(ttl_seconds=3600),
        )

        await subscriber._on_trading_decision(event)

        mock_router.place_bracket_order.assert_called_once()
        payload = mock_router.place_bracket_order.call_args[0][0]

        assert payload["expected_price"] == "50123.45678901"
        assert isinstance(payload["expected_price"], str)
