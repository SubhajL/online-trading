"""
Unit tests for AlertSubscriber.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine.adapters.alert.alert_subscriber import (
    AlertSubscriber,
    _error_event_to_text,
)
from app.engine.models import (
    ErrorEvent,
    EventType,
    Order,
    OrderFilledEvent,
    OrderSide,
    OrderStatus,
    OrderType,
    OrderUpdate,
    OrderUpdateEvent,
    TimeFrame,
    TradingDecision,
    TradingDecisionEvent,
)


class _FakeBus:
    """Fake event bus for testing."""

    def __init__(self) -> None:
        self.subscriptions: list[dict[str, object]] = []
        self.unsubscribed: list[str] = []

    async def subscribe(
        self,
        subscriber_id: str,
        handler: object,
        event_types: list[EventType] | None = None,
        priority: int = 0,
    ) -> str:
        sub_id = f"sub-{len(self.subscriptions)}"
        self.subscriptions.append(
            {
                "subscriber_id": subscriber_id,
                "handler": handler,
                "event_types": event_types,
                "priority": priority,
                "sub_id": sub_id,
            },
        )
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        self.unsubscribed.append(subscription_id)
        return True


def _make_trading_decision_event(*, timestamp: datetime) -> TradingDecisionEvent:
    decision = TradingDecision(
        venue="SPOT",
        symbol="BTCUSDT",
        timestamp=timestamp,
        action="BUY",
        entry_price=Decimal(50000),
        stop_loss=Decimal(49000),
        take_profit=Decimal(52000),
        quantity=Decimal("0.01"),
        confidence=Decimal("0.85"),
        reasoning="SMC Break; Trend Alignment",
    )
    return TradingDecisionEvent(
        timestamp=timestamp,
        symbol="BTCUSDT",
        timeframe=TimeFrame.H1,
        metadata={
            "signal_id": "sig_123",
            "decision_source": "retest_decision_publisher",
        },
        decision=decision,
    )


def _make_order_filled_event(*, timestamp: datetime) -> OrderFilledEvent:
    order = Order(
        client_order_id="order-123",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        created_at=timestamp,
    )
    return OrderFilledEvent(
        timestamp=timestamp,
        symbol="BTCUSDT",
        order=order,
        fill_price=Decimal("50123.45"),
        fill_quantity=Decimal("0.01"),
        fill_timestamp=timestamp,
    )


def _make_error_event(*, timestamp: datetime) -> ErrorEvent:
    return ErrorEvent(
        timestamp=timestamp,
        symbol="BTCUSDT",
        component="ingest",
        error_type="ConnectionError",
        error_message="WebSocket disconnected",
    )


class TestAlertSubscriberRegister:
    @pytest.mark.asyncio
    async def test_registers_with_subscriber_id(self) -> None:
        bus = _FakeBus()
        subscriber = AlertSubscriber()

        await subscriber.register(bus)

        assert len(bus.subscriptions) == 1
        assert bus.subscriptions[0]["subscriber_id"] == "alert-subscriber"

    @pytest.mark.asyncio
    async def test_registers_with_correct_event_types(self) -> None:
        """Default mode (execution_enabled=False) subscribes to TRADING_DECISION and ERROR."""
        bus = _FakeBus()
        subscriber = AlertSubscriber()

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert event_types is not None
        # Default is execution_enabled=False, which subscribes to decision-only events
        assert EventType.TRADING_DECISION in event_types  # type: ignore[operator]
        assert EventType.ERROR in event_types  # type: ignore[operator]
        assert EventType.STARTUP_COMPLETE in event_types  # type: ignore[operator]
        assert len(event_types) == 3  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_registers_with_low_priority(self) -> None:
        bus = _FakeBus()
        subscriber = AlertSubscriber()

        await subscriber.register(bus)

        assert bus.subscriptions[0]["priority"] == 10


class TestAlertSubscriberUnregister:
    @pytest.mark.asyncio
    async def test_unregisters_from_bus(self) -> None:
        bus = _FakeBus()
        subscriber = AlertSubscriber()
        await subscriber.register(bus)

        await subscriber.unregister()

        assert "sub-0" in bus.unsubscribed


class TestAlertSubscriberHandleEvent:
    @pytest.mark.asyncio
    async def test_routes_trading_decision_to_telegram(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._handle_decision = AsyncMock()

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)

        await subscriber._handle_event(_make_trading_decision_event(timestamp=ts))

        mock_telegram._handle_decision.assert_called_once()
        payload = mock_telegram._handle_decision.call_args[0][0]
        assert payload["symbol"] == "BTCUSDT"
        assert payload["side"] == "long"
        assert payload["entry_price"] == Decimal(50000)
        assert payload["stop_loss"] == Decimal(49000)
        assert payload["take_profit"] == Decimal(52000)
        assert payload["quantity"] == Decimal("0.01")
        assert payload["signal_id"] == "sig_123"
        assert payload["timeframe"] == "1h"
        assert payload["venue"] is None
        assert payload["reasons"] == ["SMC Break", "Trend Alignment"]

    @pytest.mark.asyncio
    async def test_trade_alert_is_skipped_when_decision_source_missing(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._handle_decision = AsyncMock()

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)

        event = _make_trading_decision_event(timestamp=ts)
        event.metadata.pop("decision_source", None)

        await subscriber._handle_event(event)

        mock_telegram._handle_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_trade_alert_is_skipped_when_decision_source_is_bypass(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._handle_decision = AsyncMock()

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)

        event = _make_trading_decision_event(timestamp=ts)
        event.metadata["decision_source"] = "signal_emitter_bypass"

        await subscriber._handle_event(event)

        mock_telegram._handle_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_order_placed_alert_is_skipped_when_decision_source_missing(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._handle_order_update = AsyncMock()

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram, execution_enabled=True)
        ts = datetime.now(UTC)

        event = OrderUpdateEvent(
            timestamp=ts,
            symbol="BTCUSDT",
            metadata={"signal_id": "sig_123"},
            update=OrderUpdate(
                symbol="BTCUSDT",
                order_id=123,
                client_order_id="order-123",
                status="NEW",
                side="BUY",
                order_type="LIMIT",
                price=Decimal("50000.00"),
                quantity=Decimal("0.01"),
                executed_qty=Decimal("0"),
                update_time=ts,
            ),
        )

        await subscriber._handle_event(event)

        mock_telegram._handle_order_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_routes_zone_metadata_to_telegram_payload(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._handle_decision = AsyncMock()

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)

        decision = TradingDecision(
            venue="SPOT",
            symbol="ETHUSDT",
            timestamp=ts,
            action="SELL",
            entry_price=Decimal("3184.36"),
            stop_loss=Decimal("3187.16"),
            take_profit=Decimal("3152.52"),
            quantity=Decimal("0.01"),
            confidence=Decimal("0.65"),
            reasoning="FVG fill with bearish bias",
        )
        event = TradingDecisionEvent(
            timestamp=ts,
            symbol="ETHUSDT",
            timeframe=TimeFrame.M15,
            decision=decision,
            metadata={
                "signal_id": "sig_456",
                "decision_source": "retest_decision_publisher",
                "timeframe": "15m",
                "zone": {
                    "zone_type": "FAIR_VALUE_GAP",
                    "top_price": Decimal(3190),
                    "bottom_price": Decimal(3180),
                },
            },
        )

        await subscriber._handle_event(event)

        payload = mock_telegram._handle_decision.call_args[0][0]
        assert payload["zone"] == {
            "zone_type": "FAIR_VALUE_GAP",
            "top_price": Decimal(3190),
            "bottom_price": Decimal(3180),
        }

    @pytest.mark.asyncio
    async def test_routes_order_filled_to_telegram(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._handle_order_update = AsyncMock()

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)

        await subscriber._handle_event(_make_order_filled_event(timestamp=ts))

        mock_telegram._handle_order_update.assert_called_once()
        payload = mock_telegram._handle_order_update.call_args[0][0]
        assert payload["symbol"] == "BTCUSDT"
        assert payload["status"] == "filled"
        assert payload["side"] == "buy"
        assert payload["filled_price"] == Decimal("50123.45")

    @pytest.mark.asyncio
    async def test_routes_error_to_telegram(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._send_alert = AsyncMock(return_value=True)

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)

        await subscriber._handle_event(_make_error_event(timestamp=ts))

        mock_telegram._send_alert.assert_called_once()
        message = mock_telegram._send_alert.call_args[0][0]
        assert "Engine error" in message
        assert "ingest" in message

    @pytest.mark.asyncio
    async def test_handles_no_telegram_adapter(self) -> None:
        subscriber = AlertSubscriber(telegram_adapter=None)
        ts = datetime.now(UTC)
        await subscriber._handle_event(_make_trading_decision_event(timestamp=ts))

    @pytest.mark.asyncio
    async def test_handles_telegram_error_gracefully(self) -> None:
        mock_telegram = MagicMock()
        mock_telegram._handle_decision = AsyncMock(
            side_effect=Exception("Network error"),
        )

        subscriber = AlertSubscriber(telegram_adapter=mock_telegram)
        ts = datetime.now(UTC)
        await subscriber._handle_event(_make_trading_decision_event(timestamp=ts))


class TestAlertSubscriberStop:
    @pytest.mark.asyncio
    async def test_stop_calls_unregister(self) -> None:
        bus = _FakeBus()
        subscriber = AlertSubscriber()
        await subscriber.register(bus)

        await subscriber.stop()

        assert "sub-0" in bus.unsubscribed


class TestAlertSubscriberEventTypesParameter:
    """Tests for configurable event_types parameter."""

    @pytest.mark.asyncio
    async def test_default_event_types_when_none(self) -> None:
        """When event_types=None and execution_enabled=False (default), uses decision-only events."""
        bus = _FakeBus()
        subscriber = AlertSubscriber(event_types=None)

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert event_types is not None
        # Default is execution_enabled=False
        assert len(event_types) == 3  # type: ignore[arg-type]
        assert EventType.TRADING_DECISION in event_types  # type: ignore[operator]
        assert EventType.ERROR in event_types  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_execution_enabled_event_types(self) -> None:
        """When execution_enabled=True, subscribes to ORDER_UPDATE events."""
        bus = _FakeBus()
        subscriber = AlertSubscriber(execution_enabled=True)

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert event_types is not None
        assert len(event_types) == 3  # type: ignore[arg-type]
        assert EventType.ORDER_UPDATE in event_types  # type: ignore[operator]
        assert EventType.ERROR in event_types  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_execution_enabled_event_types_include_decision_when_flag_enabled(self) -> None:
        bus = _FakeBus()
        subscriber = AlertSubscriber(
            execution_enabled=True,
            execution_decision_alerts_enabled=True,
        )

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert event_types is not None
        assert EventType.ORDER_UPDATE in event_types  # type: ignore[operator]
        assert EventType.TRADING_DECISION in event_types  # type: ignore[operator]
        assert EventType.ERROR in event_types  # type: ignore[operator]
        assert EventType.STARTUP_COMPLETE in event_types  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_custom_event_types_override(self) -> None:
        """When event_types provided, uses only those types."""
        bus = _FakeBus()
        custom_types = [EventType.TRADING_DECISION]
        subscriber = AlertSubscriber(event_types=custom_types)

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert event_types == [EventType.TRADING_DECISION]

    @pytest.mark.asyncio
    async def test_decision_only_subscriber_ignores_order_filled(self) -> None:
        """Subscriber with only TRADING_DECISION doesn't receive ORDER_FILLED."""
        bus = _FakeBus()
        subscriber = AlertSubscriber(event_types=[EventType.TRADING_DECISION])

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert EventType.ORDER_FILLED not in event_types  # type: ignore[operator]
        assert EventType.ERROR not in event_types  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_multiple_custom_event_types(self) -> None:
        """Can specify multiple custom event types."""
        bus = _FakeBus()
        custom_types = [EventType.TRADING_DECISION, EventType.ERROR]
        subscriber = AlertSubscriber(event_types=custom_types)

        await subscriber.register(bus)

        event_types = bus.subscriptions[0]["event_types"]
        assert len(event_types) == 2  # type: ignore[arg-type]
        assert EventType.TRADING_DECISION in event_types  # type: ignore[operator]
        assert EventType.ERROR in event_types  # type: ignore[operator]
        assert EventType.ORDER_FILLED not in event_types  # type: ignore[operator]


class TestAlertSubscriberSnapshotTiming:
    """Tests for snapshot timing in disabled mode (Gap 2 fix)."""

    @pytest.mark.asyncio
    async def test_snapshot_triggered_before_decision_alert(self) -> None:
        """In disabled mode, snapshot should be triggered BEFORE telegram call."""
        call_order: list[str] = []

        class _TrackingBffClient:
            async def post(self, endpoint: str, payload: dict) -> dict:
                call_order.append("notify_snapshot")
                return {"success": True}

        class _TrackingTelegram:
            async def _handle_decision(self, payload: dict) -> None:
                call_order.append("handle_decision")

        bff_client = _TrackingBffClient()
        mock_telegram = _TrackingTelegram()

        subscriber = AlertSubscriber(
            telegram_adapter=mock_telegram,  # type: ignore[arg-type]
            execution_enabled=False,
            bff_client=bff_client,
        )

        ts = datetime.now(UTC)
        event = _make_trading_decision_event(timestamp=ts)
        await subscriber._handle_event(event)

        # Snapshot should be triggered BEFORE telegram decision alert
        assert call_order == ["notify_snapshot", "handle_decision"]

    @pytest.mark.asyncio
    async def test_decision_alert_sent_even_without_bff_client(self) -> None:
        """Decision alert should still be sent when no BFF client configured."""
        call_order: list[str] = []

        class _TrackingTelegram:
            async def _handle_decision(self, payload: dict) -> None:
                call_order.append("handle_decision")

        mock_telegram = _TrackingTelegram()

        subscriber = AlertSubscriber(
            telegram_adapter=mock_telegram,  # type: ignore[arg-type]
            execution_enabled=False,
            bff_client=None,  # No BFF client
        )

        ts = datetime.now(UTC)
        event = _make_trading_decision_event(timestamp=ts)
        await subscriber._handle_event(event)

        # Telegram should still be called
        assert call_order == ["handle_decision"]


class TestAlertSubscriberCooldown:
    """Tests for alert cooldown (Gap 3 fix)."""

    @pytest.mark.asyncio
    async def test_cooldown_blocks_duplicate_alert(self) -> None:
        """When cooldown active for zone, second alert should be blocked."""
        from app.engine.core.signal_cooldown import SignalCooldown

        call_count = 0

        class _TrackingTelegram:
            async def _handle_decision(self, payload: dict) -> None:
                nonlocal call_count
                call_count += 1

        mock_telegram = _TrackingTelegram()
        cooldown = SignalCooldown(cooldown_seconds=300)

        subscriber = AlertSubscriber(
            telegram_adapter=mock_telegram,  # type: ignore[arg-type]
            execution_enabled=False,
            cooldown=cooldown,
        )

        ts = datetime.now(UTC)
        decision = TradingDecision(
            venue="SPOT",
            symbol="BTCUSDT",
            timestamp=ts,
            action="BUY",
            entry_price=Decimal(50000),
            stop_loss=Decimal(49000),
            take_profit=Decimal(52000),
            quantity=Decimal("0.01"),
            confidence=Decimal("0.85"),
            reasoning="SMC Break",
        )
        event = TradingDecisionEvent(
            timestamp=ts,
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            metadata={
                "signal_id": "sig_123",
                "decision_source": "retest_decision_publisher",
                "zone": {"zone_id": "zone-abc", "zone_type": "DEMAND"},
            },
            decision=decision,
        )

        # First alert should go through
        await subscriber._handle_event(event)
        assert call_count == 1

        # Second alert on same zone should be blocked
        await subscriber._handle_event(event)
        assert call_count == 1  # Still 1, not 2

    @pytest.mark.asyncio
    async def test_cooldown_allows_different_zones(self) -> None:
        """Cooldown should not block alerts for different zones."""
        from app.engine.core.signal_cooldown import SignalCooldown

        call_count = 0

        class _TrackingTelegram:
            async def _handle_decision(self, payload: dict) -> None:
                nonlocal call_count
                call_count += 1

        mock_telegram = _TrackingTelegram()
        cooldown = SignalCooldown(cooldown_seconds=300)

        subscriber = AlertSubscriber(
            telegram_adapter=mock_telegram,  # type: ignore[arg-type]
            execution_enabled=False,
            cooldown=cooldown,
        )

        ts = datetime.now(UTC)

        # First zone
        event1 = TradingDecisionEvent(
            timestamp=ts,
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            metadata={
                "signal_id": "sig_1",
                "decision_source": "retest_decision_publisher",
                "zone": {"zone_id": "zone-1", "zone_type": "DEMAND"},
            },
            decision=TradingDecision(
                venue="SPOT",
                symbol="BTCUSDT",
                timestamp=ts,
                action="BUY",
                entry_price=Decimal(50000),
                stop_loss=Decimal(49000),
                take_profit=Decimal(52000),
                quantity=Decimal("0.01"),
                confidence=Decimal("0.85"),
                reasoning="SMC Break",
            ),
        )

        # Different zone
        event2 = TradingDecisionEvent(
            timestamp=ts,
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            metadata={
                "signal_id": "sig_2",
                "decision_source": "retest_decision_publisher",
                "zone": {"zone_id": "zone-2", "zone_type": "SUPPLY"},
            },
            decision=TradingDecision(
                venue="SPOT",
                symbol="BTCUSDT",
                timestamp=ts,
                action="SELL",
                entry_price=Decimal(51000),
                stop_loss=Decimal(52000),
                take_profit=Decimal(49000),
                quantity=Decimal("0.01"),
                confidence=Decimal("0.80"),
                reasoning="SMC Break",
            ),
        )

        await subscriber._handle_event(event1)
        assert call_count == 1

        await subscriber._handle_event(event2)
        assert call_count == 2  # Different zone, should go through

    @pytest.mark.asyncio
    async def test_no_cooldown_when_zone_missing(self) -> None:
        """When zone_id missing, cooldown should not block."""
        from app.engine.core.signal_cooldown import SignalCooldown

        call_count = 0

        class _TrackingTelegram:
            async def _handle_decision(self, payload: dict) -> None:
                nonlocal call_count
                call_count += 1

        mock_telegram = _TrackingTelegram()
        cooldown = SignalCooldown(cooldown_seconds=300)

        subscriber = AlertSubscriber(
            telegram_adapter=mock_telegram,  # type: ignore[arg-type]
            execution_enabled=False,
            cooldown=cooldown,
        )

        ts = datetime.now(UTC)
        event = TradingDecisionEvent(
            timestamp=ts,
            symbol="BTCUSDT",
            timeframe=TimeFrame.H1,
            metadata={
                "signal_id": "sig_123",
                "decision_source": "retest_decision_publisher",
            },  # No zone
            decision=TradingDecision(
                venue="SPOT",
                symbol="BTCUSDT",
                timestamp=ts,
                action="BUY",
                entry_price=Decimal(50000),
                stop_loss=Decimal(49000),
                take_profit=Decimal(52000),
                quantity=Decimal("0.01"),
                confidence=Decimal("0.85"),
                reasoning="SMC Break",
            ),
        )

        # Both alerts should go through (no zone to track)
        await subscriber._handle_event(event)
        assert call_count == 1

        await subscriber._handle_event(event)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_order_update_alert_is_not_cooldown_blocked(self) -> None:
        """ORDER_UPDATE alerts should never be suppressed by cooldown."""
        from app.engine.core.signal_cooldown import SignalCooldown

        call_count = 0

        class _TrackingTelegram:
            async def _handle_order_update(self, payload: dict) -> None:
                nonlocal call_count
                call_count += 1

        ts = datetime.now(UTC)
        cooldown = SignalCooldown(cooldown_seconds=300)
        subscriber = AlertSubscriber(
            telegram_adapter=_TrackingTelegram(),  # type: ignore[arg-type]
            execution_enabled=True,
            cooldown=cooldown,
        )

        event = OrderUpdateEvent(
            timestamp=ts,
            symbol="BTCUSDT",
            metadata={
                "signal_id": "sig_123",
                "decision_source": "retest_decision_publisher",
                "zone": {"zone_id": "zone-abc", "zone_type": "DEMAND"},
            },
            update=OrderUpdate(
                symbol="BTCUSDT",
                order_id=123,
                client_order_id="order-123",
                status="NEW",
                side="BUY",
                order_type="LIMIT",
                price=Decimal("50000.00"),
                quantity=Decimal("0.01"),
                executed_qty=Decimal("0"),
                update_time=ts,
            ),
        )

        await subscriber._handle_event(event)
        await subscriber._handle_event(event)

        assert call_count == 2


class TestErrorEventToText:
    """Tests for _error_event_to_text metadata rendering."""

    def test_error_event_text_includes_metadata_fields(self) -> None:
        """Timeframe + age should appear in alert text when present in metadata."""
        ts = datetime(2026, 2, 5, 12, 0, tzinfo=UTC)
        event = ErrorEvent(
            timestamp=ts,
            symbol="BTCUSDT",
            component="pipeline_health",
            error_type="candle_stale",
            error_message="No recent closed candle for symbol/timeframe",
        )
        event.metadata.update(
            {
                "timeframe": "5m",
                "latest_candle_ago_seconds": 1200.5,
                "max_allowed_candle_age_seconds": 720.0,
            },
        )

        text = _error_event_to_text(event)

        assert "BTCUSDT" in text
        assert "candle_stale" in text
        assert "5m" in text
        assert "1200" in text
        assert "720" in text

    def test_error_event_text_without_metadata(self) -> None:
        """Empty metadata should render clean basic format without extras."""
        ts = datetime(2026, 2, 5, 12, 0, tzinfo=UTC)
        event = ErrorEvent(
            timestamp=ts,
            symbol="BTCUSDT",
            component="ingest",
            error_type="ConnectionError",
            error_message="WebSocket disconnected",
        )
        # No metadata set

        text = _error_event_to_text(event)

        assert "Engine error" in text
        assert "ingest" in text
        assert "ConnectionError" in text
        assert "WebSocket disconnected" in text
        # Should NOT have a "Details:" section
        assert "Timeframe:" not in text

    def test_error_event_text_includes_kline_stream_stale_metadata(self) -> None:
        ts = datetime(2026, 2, 6, 12, 0, tzinfo=UTC)
        event = ErrorEvent(
            timestamp=ts,
            symbol="SYSTEM",
            component="pipeline_health",
            error_type="kline_stream_stale",
            error_message="WebSocket connected but klines not arriving",
        )
        event.metadata.update(
            {
                "last_kline_ago_seconds": None,
                "last_closed_kline_ago_seconds": None,
                "last_message_ago_seconds": 0.07,
                "stale_threshold_seconds": 120,
            },
        )

        text = _error_event_to_text(event)

        assert "kline_stream_stale" in text
        assert "WS Kline Age: null" in text
        assert "WS Closed Kline Age: null" in text
        assert "WS Last Msg Age: 0s" in text
        assert "Stale Threshold: 120s" in text

    def test_error_event_text_includes_recovery_context_metadata(self) -> None:
        ts = datetime(2026, 2, 6, 12, 0, tzinfo=UTC)
        event = ErrorEvent(
            timestamp=ts,
            symbol="SYSTEM",
            component="pipeline_health",
            error_type="websocket_disconnected",
            error_message="WebSocket is disconnected",
        )
        event.metadata.update(
            {
                "recovery_stage": "dns_recovery",
                "backoff_attempt": 4,
                "max_reconnect_attempts": 50,
                "dispatch_queue_size": 80,
                "dispatch_queue_max": 200,
                "last_subscribe_ok_ago_seconds": 120.0,
                "last_subscribe_error_ago_seconds": 30.0,
                "last_subscribe_error": "subscribe timeout",
            },
        )

        text = _error_event_to_text(event)

        assert "Recovery Stage: dns_recovery" in text
        assert "WS Backoff Attempt: 4" in text
        assert "WS Max Reconnect Attempts: 50" in text
        assert "WS Dispatch Queue: 80/200" in text
        assert "WS Last Subscribe OK Age: 120s" in text
        assert "WS Last Subscribe Error Age: 30s" in text
        assert "WS Last Subscribe Error: subscribe timeout" in text

    def test_error_event_text_includes_risk_debug_metadata(self) -> None:
        ts = datetime(2026, 2, 6, 12, 0, tzinfo=UTC)
        event = ErrorEvent(
            timestamp=ts,
            symbol="BTCUSDT",
            component="decision_publisher",
            error_type="risk_limit_exceeded",
            error_message="max_position_notional_exceeded:4.79",
        )
        event.metadata.update(
            {
                "equity_usd": "10000",
                "start_of_day_equity_usd": "10000",
                "peak_equity_usd": "11000",
                "daily_loss_ratio": "0.01",
                "max_daily_loss": "0.05",
                "drawdown_ratio": "0.0909",
                "max_drawdown": "0.15",
                "symbol_exposure_usd": "1500",
                "max_symbol_exposure_pct": "0.25",
                "total_exposure_usd": "2500",
                "max_total_exposure_leverage": "3",
                "entry_price": "66500",
                "stop_loss": "66750",
                "stop_distance": "250",
                "quantity": "0.5",
                "new_notional_usd": "33250",
                "max_position_notional_ratio": "3.325",
                "max_position_notional_pct": "0.10",
            },
        )

        text = _error_event_to_text(event)

        assert "Equity:" in text
        assert "Daily Loss:" in text
        assert "Drawdown:" in text
        assert "Symbol Exposure:" in text
        assert "Total Exposure:" in text
        assert "New Notional:" in text
        assert "Entry:" in text
