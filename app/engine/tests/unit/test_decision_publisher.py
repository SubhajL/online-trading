from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.engine.bus import create_event_bus, set_event_bus
from app.engine.decision.decision_publisher import DecisionPublisher
from app.engine.models import (
    EventType,
    ErrorEvent,
    RiskParameters,
    RetestSignal,
    RetestSignalEvent,
    TimeFrame,
    TradingDecisionEvent,
)

class _FakeDBAdapter:
    async def insert_trading_decision(self, _decision) -> bool:
        return True

    async def get_latest_equity_sample(self):
        return Decimal(10_000), datetime.now(UTC)

    async def get_equity_sample_at_or_after(self, _ts: datetime):
        return Decimal(10_000)

    async def get_peak_equity_since(self, _ts: datetime):
        return Decimal(10_000)

    async def get_active_positions(self, _venue: str):
        return []


class _LossyDBAdapter(_FakeDBAdapter):
    async def get_latest_equity_sample(self):
        return Decimal(9000), datetime.now(UTC)

    async def get_equity_sample_at_or_after(self, _ts: datetime):
        return Decimal(10_000)


@pytest.mark.asyncio
async def test_decision_publisher_emits_buy_decision_from_retest_signal() -> None:
    bus = create_event_bus()
    set_event_bus(bus)
    await bus.start(num_workers=1)

    try:
        publisher = DecisionPublisher(
            db_adapter=_FakeDBAdapter(),  # type: ignore[arg-type]
            risk=RiskParameters(
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
            ),
            venue="SPOT",
        )
        await publisher.start()

        decisions: list[TradingDecisionEvent] = []
        got_event = asyncio.Event()

        async def on_decision(event: TradingDecisionEvent) -> None:
            decisions.append(event)
            got_event.set()

        await bus.subscribe(
            subscriber_id="test_decision_capture",
            handler=on_decision,
            event_types=[EventType.TRADING_DECISION],
        )

        signal = RetestSignal(
            venue="SPOT",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            level_price=Decimal(100),
            direction="BUY",
            stop_loss=Decimal(99),
            take_profit=Decimal("101.5"),
            retest_type="zone_retest",
            success_probability=Decimal("0.8"),
            volume_confirmation=True,
            confluence_factors=["bos_confirmation"],
        )
        await bus.publish(
            RetestSignalEvent(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                signal=signal,
            ),
        )

        await asyncio.wait_for(got_event.wait(), timeout=1.0)

        assert len(decisions) == 1
        decision_event = decisions[0]
        assert decision_event.symbol == "BTCUSDT"
        assert decision_event.timeframe == TimeFrame.M15
        assert decision_event.decision.action == "BUY"
        assert decision_event.decision.entry_price == Decimal(100)
        assert decision_event.decision.stop_loss == Decimal(99)
        assert decision_event.decision.take_profit == Decimal("101.5")
        assert decision_event.decision.quantity == Decimal(100)
        assert decision_event.metadata["signal_id"] == str(signal.signal_id)
        assert decision_event.metadata["decision_source"] == "retest_decision_publisher"
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_decision_publisher_caps_quantity_to_max_position_notional() -> None:
    bus = create_event_bus()
    set_event_bus(bus)
    await bus.start(num_workers=1)

    try:
        publisher = DecisionPublisher(
            db_adapter=_FakeDBAdapter(),  # type: ignore[arg-type]
            risk=RiskParameters(
                max_position_size=Decimal("999999"),
                max_daily_loss=Decimal("1"),
                max_drawdown=Decimal("1"),
                risk_per_trade=Decimal("0.02"),
                max_correlation=Decimal("1"),
                max_open_positions=100,
                max_total_exposure_leverage=Decimal("100"),
                max_symbol_exposure_pct=Decimal("1"),
                max_position_notional_pct=Decimal("0.10"),
                risk_data_max_age_seconds=86400,
                drawdown_lookback_days=30,
            ),
            venue="SPOT",
        )
        await publisher.start()

        decisions: list[TradingDecisionEvent] = []
        got_event = asyncio.Event()

        async def on_decision(event: TradingDecisionEvent) -> None:
            decisions.append(event)
            got_event.set()

        await bus.subscribe(
            subscriber_id="test_decision_capture",
            handler=on_decision,
            event_types=[EventType.TRADING_DECISION],
        )

        # Tight stop => huge risk-based size, should be capped by max_position_notional_pct=10%
        signal = RetestSignal(
            venue="SPOT",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            level_price=Decimal(100),
            direction="BUY",
            stop_loss=Decimal("99.99"),  # 0.01 stop distance
            take_profit=Decimal("101.5"),
            retest_type="zone_retest",
            success_probability=Decimal("0.8"),
            volume_confirmation=True,
            confluence_factors=["bos_confirmation"],
        )
        await bus.publish(
            RetestSignalEvent(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                signal=signal,
            ),
        )

        await asyncio.wait_for(got_event.wait(), timeout=1.0)

        assert len(decisions) == 1
        decision_event = decisions[0]
        # Equity=10,000 => max notional 1,000 at entry=100 => max qty 10
        assert decision_event.decision.quantity == Decimal(10)
        assert decision_event.metadata.get("sizing_capped") is True
        assert decision_event.metadata.get("sizing_original_quantity") == "20000"
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_decision_publisher_blocks_when_daily_loss_exceeded() -> None:
    bus = create_event_bus()
    set_event_bus(bus)
    await bus.start(num_workers=1)

    try:
        risk = RiskParameters(
            max_position_size=Decimal("999999"),
            max_daily_loss=Decimal("0.05"),
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

        publisher = DecisionPublisher(
            db_adapter=_LossyDBAdapter(),  # type: ignore[arg-type]
            risk=risk,
            venue="SPOT",
        )
        await publisher.start()

        errors: list[ErrorEvent] = []
        got_event = asyncio.Event()

        async def on_error(event: ErrorEvent) -> None:
            errors.append(event)
            got_event.set()

        await bus.subscribe(
            subscriber_id="test_error_capture",
            handler=on_error,
            event_types=[EventType.ERROR],
        )

        signal = RetestSignal(
            venue="SPOT",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            level_price=Decimal(100),
            direction="BUY",
            stop_loss=Decimal(99),
            take_profit=Decimal("101.5"),
            retest_type="zone_retest",
            success_probability=Decimal("0.8"),
            volume_confirmation=True,
            confluence_factors=["bos_confirmation"],
        )
        await bus.publish(
            RetestSignalEvent(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                signal=signal,
            ),
        )

        await asyncio.wait_for(got_event.wait(), timeout=1.0)
        assert len(errors) == 1
        assert errors[0].error_type == "risk_limit_exceeded"
        # Include debug metadata for operator visibility
        assert errors[0].metadata.get("equity_usd") is not None
        assert errors[0].metadata.get("start_of_day_equity_usd") is not None
        assert errors[0].metadata.get("daily_loss_ratio") is not None
        assert errors[0].metadata.get("max_daily_loss") is not None
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_decision_publisher_forwards_zone_metadata() -> None:
    """DecisionPublisher should forward zone metadata from RetestSignalEvent."""
    bus = create_event_bus()
    set_event_bus(bus)
    await bus.start(num_workers=1)

    try:
        publisher = DecisionPublisher(
            db_adapter=_FakeDBAdapter(),  # type: ignore[arg-type]
            risk=RiskParameters(
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
            ),
            venue="SPOT",
        )
        await publisher.start()

        decisions: list[TradingDecisionEvent] = []
        got_event = asyncio.Event()

        async def on_decision(event: TradingDecisionEvent) -> None:
            decisions.append(event)
            got_event.set()

        await bus.subscribe(
            subscriber_id="test_decision_capture",
            handler=on_decision,
            event_types=[EventType.TRADING_DECISION],
        )

        signal = RetestSignal(
            venue="SPOT",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            level_price=Decimal(100),
            direction="BUY",
            stop_loss=Decimal(99),
            take_profit=Decimal("101.5"),
            retest_type="zone_retest",
            success_probability=Decimal("0.8"),
            volume_confirmation=True,
            confluence_factors=["bos_confirmation"],
        )

        # Publish with zone metadata (as would come from RetestEngine)
        await bus.publish(
            RetestSignalEvent(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                signal=signal,
                metadata={
                    "zone": {
                        "zone_id": "zone-test-123",
                        "zone_type": "DEMAND",
                    },
                    "timeframe": "15m",
                },
            ),
        )

        await asyncio.wait_for(got_event.wait(), timeout=1.0)

        assert len(decisions) == 1
        decision_event = decisions[0]

        # Zone metadata should be forwarded
        assert "zone" in decision_event.metadata
        assert decision_event.metadata["zone"]["zone_id"] == "zone-test-123"
        assert decision_event.metadata["zone"]["zone_type"] == "DEMAND"
        assert decision_event.metadata.get("timeframe") == "15m"
        assert decision_event.metadata["signal_id"] == str(signal.signal_id)
        assert decision_event.metadata["decision_source"] == "retest_decision_publisher"
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_decision_publisher_handles_missing_zone_metadata() -> None:
    """DecisionPublisher should handle missing zone metadata gracefully."""
    bus = create_event_bus()
    set_event_bus(bus)
    await bus.start(num_workers=1)

    try:
        publisher = DecisionPublisher(
            db_adapter=_FakeDBAdapter(),  # type: ignore[arg-type]
            risk=RiskParameters(
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
            ),
            venue="SPOT",
        )
        await publisher.start()

        decisions: list[TradingDecisionEvent] = []
        got_event = asyncio.Event()

        async def on_decision(event: TradingDecisionEvent) -> None:
            decisions.append(event)
            got_event.set()

        await bus.subscribe(
            subscriber_id="test_decision_capture",
            handler=on_decision,
            event_types=[EventType.TRADING_DECISION],
        )

        signal = RetestSignal(
            venue="SPOT",
            symbol="ETHUSDT",
            timeframe=TimeFrame.H1,
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            level_price=Decimal(3000),
            direction="SELL",
            stop_loss=Decimal(3050),
            take_profit=Decimal(2900),
            retest_type="zone_retest",
            success_probability=Decimal("0.7"),
            volume_confirmation=True,
            confluence_factors=["macd_divergence"],
        )

        # Publish without zone metadata (legacy path)
        await bus.publish(
            RetestSignalEvent(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                signal=signal,
            ),
        )

        await asyncio.wait_for(got_event.wait(), timeout=1.0)

        assert len(decisions) == 1
        decision_event = decisions[0]

        # Should still work, zone is None
        assert decision_event.metadata.get("zone") is None
        assert decision_event.metadata["signal_id"] == str(signal.signal_id)
        assert decision_event.metadata["decision_source"] == "retest_decision_publisher"
    finally:
        await bus.stop()
