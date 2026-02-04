"""
AlertSubscriber - Routes trading events to alert adapters.
Subscribes to the event bus and dispatches events to configured alert channels.

Mode-aware behavior:
- When execution_enabled=True: Subscribes to ORDER_UPDATE (alerts on router/exchange updates)
- When execution_enabled=False: Subscribes to TRADING_DECISION (alerts on signal, with snapshots)
"""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import TYPE_CHECKING, Any, Protocol

from app.engine.models import (
    BaseEvent,
    ErrorEvent,
    EventType,
    OrderFilledEvent,
    OrderUpdateEvent,
    StartupCompleteEvent,
    TradingDecisionEvent,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.engine.core.signal_cooldown import SignalCooldown

    from .telegram import TelegramAlertAdapter

logger = logging.getLogger(__name__)


class _BffClient(Protocol):
    async def post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class _EventBus(Protocol):
    async def subscribe(
        self,
        subscriber_id: str,
        handler: Callable[[BaseEvent], Awaitable[None]],
        event_types: list[EventType] | None = None,
        priority: int = 0,
    ) -> str: ...

    async def unsubscribe(self, subscription_id: str) -> bool: ...


def _decision_event_to_alert_payload(
    event: TradingDecisionEvent,
) -> dict[str, object] | None:
    decision = event.decision
    action = str(decision.action).upper()
    if action not in {"BUY", "SELL"}:
        return None

    metadata_timeframe = event.metadata.get("timeframe")
    timeframe = (
        metadata_timeframe
        if isinstance(metadata_timeframe, str) and metadata_timeframe
        else (event.timeframe.value if event.timeframe else None)
    )

    entry_price = decision.entry_price
    stop_loss = decision.stop_loss
    take_profit = decision.take_profit
    quantity = decision.quantity

    if entry_price is None or stop_loss is None or take_profit is None or quantity is None:
        return None

    side = "long" if action == "BUY" else "short"
    reasons = [r for r in decision.reasoning.split("; ") if r] if decision.reasoning else []

    signal_id = event.metadata.get("signal_id")
    if not isinstance(signal_id, str):
        signal_id = None

    venue = event.metadata.get("venue")
    if not isinstance(venue, str):
        venue = None

    zone = event.metadata.get("zone")
    if not isinstance(zone, dict):
        zone = None

    return {
        "symbol": event.symbol,
        "side": side,
        "timestamp": event.timestamp,
        "timeframe": timeframe,
        "venue": venue,
        "zone": zone,
        "signal_id": signal_id,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "quantity": quantity,
        "confidence": float(decision.confidence)
        if isinstance(decision.confidence, Decimal)
        else decision.confidence,
        "reasons": reasons,
    }


def _order_filled_event_to_order_update_payload(
    event: OrderFilledEvent,
) -> dict[str, object]:
    return {
        "symbol": event.order.symbol,
        "side": str(event.order.side.value).lower(),
        "status": "filled",
        "quantity": event.fill_quantity,
        "filled_price": event.fill_price,
    }


def _normalize_order_update_status(raw: str) -> str:
    status = raw.strip().upper()
    mapping = {
        "NEW": "new",
        "PARTIALLY_FILLED": "partially_filled",
        "FILLED": "filled",
        "CANCELED": "canceled",
        "CANCELLED": "canceled",
        "REJECTED": "rejected",
        "EXPIRED": "expired",
    }
    return mapping.get(status, status.lower())


def _order_update_event_to_order_update_payload(
    event: OrderUpdateEvent,
) -> dict[str, object]:
    upd = event.update
    status = _normalize_order_update_status(upd.status)
    side = upd.side.lower() if isinstance(upd.side, str) else "unknown"

    quantity = upd.quantity if upd.quantity is not None else upd.executed_qty

    payload: dict[str, object] = {
        "symbol": upd.symbol,
        "side": side,
        "status": status,
        "quantity": quantity,
        "price": upd.price,
        "executed_qty": upd.executed_qty,
        "client_order_id": upd.client_order_id,
    }

    if upd.reason:
        payload["reason"] = upd.reason

    if status == "filled" and upd.price is not None:
        payload["filled_price"] = upd.price

    return payload


def _error_event_to_text(event: ErrorEvent) -> str:
    return (
        "🚨 Engine error\n"
        f"Component: {event.component}\n"
        f"Type: {event.error_type}\n"
        f"Symbol: {event.symbol}\n"
        f"Message: {event.error_message}"
    )


DEFAULT_ALERT_EVENT_TYPES: list[EventType] = [
    EventType.TRADING_DECISION,
    EventType.ORDER_FILLED,
    EventType.ERROR,
]

# Event types for execution-enabled mode (alert on order updates)
EXECUTION_ENABLED_EVENT_TYPES: list[EventType] = [
    EventType.ORDER_UPDATE,
    EventType.ERROR,
    EventType.STARTUP_COMPLETE,
]

# Event types for execution-disabled mode (alert on decision, signal-only)
EXECUTION_DISABLED_EVENT_TYPES: list[EventType] = [
    EventType.TRADING_DECISION,
    EventType.ERROR,
    EventType.STARTUP_COMPLETE,
]


class AlertSubscriber:
    """
    Subscribes to trading events and routes to alert channels.

    This class acts as the bridge between the event bus and alert adapters,
    using the correct bus API (subscriber_id, handler, event_types, priority).

    Mode-aware behavior:
    - execution_enabled=True: Subscribes to ORDER_UPDATE (alerts on router/exchange updates)
    - execution_enabled=False: Subscribes to TRADING_DECISION (alerts on signal)
    """

    def __init__(
        self,
        telegram_adapter: TelegramAlertAdapter | None = None,
        event_types: list[EventType] | None = None,
        *,
        execution_enabled: bool = False,
        bff_client: _BffClient | None = None,
        cooldown: SignalCooldown | None = None,
        allowed_decision_sources: set[str] | None = None,
    ) -> None:
        """
        Initialize the alert subscriber.

        Args:
            telegram_adapter: Optional Telegram adapter for sending alerts
            event_types: Optional list of event types to subscribe to.
                         If None, determined by execution_enabled mode.
            execution_enabled: If True, alerts on ORDER_PLACED.
                              If False, alerts on TRADING_DECISION.
            bff_client: Optional BFF client for triggering snapshots.
            cooldown: Optional cooldown tracker for deduplicating alerts.
        """
        self.telegram = telegram_adapter
        self._execution_enabled = execution_enabled
        self._bff_client = bff_client
        self._cooldown = cooldown
        self._allowed_decision_sources = (
            allowed_decision_sources
            if allowed_decision_sources is not None
            else {"retest_decision_publisher"}
        )

        # Mode-dependent default event types if not explicitly provided
        if event_types is not None:
            self._event_types = event_types
        elif execution_enabled:
            self._event_types = EXECUTION_ENABLED_EVENT_TYPES
        else:
            self._event_types = EXECUTION_DISABLED_EVENT_TYPES

        self._subscription_id: str | None = None
        self._event_bus: _EventBus | None = None

    async def register(self, event_bus: _EventBus) -> None:
        """
        Register with the event bus using the correct API.

        Uses configured event_types (or defaults to all alert-relevant types)
        with low priority (alerts are non-critical).
        """
        self._event_bus = event_bus

        self._subscription_id = await event_bus.subscribe(
            subscriber_id="alert-subscriber",
            handler=self._handle_event,
            event_types=self._event_types,
            priority=10,  # Low priority (higher = processed first)
        )

        logger.info(
            "AlertSubscriber registered with subscription_id: %s, event_types: %s",
            self._subscription_id,
            [et.value for et in self._event_types],
        )

    async def unregister(self) -> None:
        """Unregister from the event bus."""
        if self._event_bus and self._subscription_id:
            await self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
            logger.info("AlertSubscriber unregistered")

    async def _handle_event(self, event: BaseEvent) -> None:  # noqa: C901, PLR0911
        try:
            if not self.telegram:
                return

            if isinstance(event, OrderUpdateEvent):
                if not self._is_allowed_trade_alert_event(event):
                    return
                payload = _order_update_event_to_order_update_payload(event)
                await self.telegram._handle_order_update(payload)
                return

            if isinstance(event, TradingDecisionEvent):
                if not self._is_allowed_trade_alert_event(event):
                    return
                # Execution-disabled mode: alert on decision (signal-only)
                payload = _decision_event_to_alert_payload(event)
                if payload is None:
                    return

                # Check cooldown for alert deduplication
                if not self._check_and_record_cooldown(event):
                    return

                # Trigger snapshot FIRST so it's available when telegram fetches it
                if self._bff_client is not None:
                    await self._notify_snapshot_for_decision(event)

                await self.telegram._handle_decision(payload)
                return

            if isinstance(event, OrderFilledEvent):
                payload = _order_filled_event_to_order_update_payload(event)
                await self.telegram._handle_order_update(payload)
                return

            if isinstance(event, ErrorEvent):
                message = _error_event_to_text(event)
                await self.telegram._send_alert(message)
                return

            if isinstance(event, StartupCompleteEvent):
                startup_data = {
                    "phase": event.phase,
                    "symbols": event.symbols,
                    "timeframes": event.timeframes,
                    "candle_counts": event.candle_counts,
                    "duration_seconds": event.duration_seconds,
                }
                await self.telegram.send_startup_alert(startup_data)
                return

            logger.debug("Unhandled event type: %s", event.event_type)

        except Exception:
            logger.exception("Error handling event %s", event.event_type)

    def _is_allowed_trade_alert_event(
        self,
        event: TradingDecisionEvent | OrderUpdateEvent,
    ) -> bool:
        decision_source = event.metadata.get("decision_source")
        if not isinstance(decision_source, str):
            return False
        return decision_source in self._allowed_decision_sources

    async def _notify_snapshot_for_decision(self, event: TradingDecisionEvent) -> None:
        """Trigger snapshot generation via BFF client for decision alerts.

        Only used when execution is disabled (signal-only mode).
        When execution is enabled, snapshots are triggered by RouterExecutionSubscriber.
        """
        if self._bff_client is None:
            return

        decision = event.decision
        side = "BUY" if str(decision.action).upper() == "BUY" else "SELL"

        try:
            payload = {
                "signalId": event.metadata.get("signal_id"),
                "symbol": decision.symbol,
                "venue": event.metadata.get("venue", "SPOT"),
                "side": side,
                "entry": str(decision.entry_price) if decision.entry_price else None,
                "stopLoss": str(decision.stop_loss) if decision.stop_loss else None,
                "takeProfit": str(decision.take_profit) if decision.take_profit else None,
                "confidence": float(decision.confidence) if decision.confidence else None,
                "reasons": decision.reasoning.split("; ") if decision.reasoning else [],
                "timeframe": event.timeframe.value if event.timeframe else None,
                "signalTime": decision.timestamp.isoformat() if decision.timestamp else None,
            }

            await self._bff_client.post("/api/signals/alert", payload)
        except Exception:
            logger.exception("Error triggering snapshot for %s", decision.symbol)

    async def stop(self) -> None:
        """Stop the subscriber and clean up."""
        await self.unregister()
        logger.info("AlertSubscriber stopped")

    def _check_and_record_cooldown(self, event: TradingDecisionEvent) -> bool:
        """Check cooldown for alert deduplication.

        Returns True if alert should proceed, False if blocked by cooldown.
        If allowed and cooldown is configured, records the signal for future checks.
        """
        if self._cooldown is None:
            return True

        from app.engine.core.zone_identity import extract_zone_identity

        zone_identity = extract_zone_identity(event.metadata)
        if zone_identity is None:
            # No zone_id means we can't track cooldown - allow alert
            return True

        # Get direction from decision
        direction = str(event.decision.action).upper()

        # Get timeframe
        timeframe_str = (
            event.timeframe.value if event.timeframe else event.metadata.get("timeframe", "unknown")
        )

        # Check if cooldown allows this signal
        if not self._cooldown.should_allow(
            event.symbol,
            timeframe_str,
            zone_identity.zone_id,
            direction,
        ):
            logger.info(
                "Alert cooldown: skipping %s %s %s",
                event.symbol,
                zone_identity.zone_id,
                direction,
            )
            return False

        # Record signal for future cooldown checks
        self._cooldown.record_signal(
            event.symbol,
            timeframe_str,
            zone_identity.zone_id,
            direction,
        )
        return True
