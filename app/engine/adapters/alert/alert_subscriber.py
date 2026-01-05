"""
AlertSubscriber - Routes trading events to alert adapters.
Subscribes to the event bus and dispatches events to configured alert channels.
"""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import TYPE_CHECKING, Protocol

from app.engine.models import (
    BaseEvent,
    ErrorEvent,
    EventType,
    OrderFilledEvent,
    TradingDecisionEvent,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .telegram import TelegramAlertAdapter

logger = logging.getLogger(__name__)


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


class AlertSubscriber:
    """
    Subscribes to trading events and routes to alert channels.

    This class acts as the bridge between the event bus and alert adapters,
    using the correct bus API (subscriber_id, handler, event_types, priority).
    """

    def __init__(
        self,
        telegram_adapter: TelegramAlertAdapter | None = None,
        event_types: list[EventType] | None = None,
    ) -> None:
        """
        Initialize the alert subscriber.

        Args:
            telegram_adapter: Optional Telegram adapter for sending alerts
            event_types: Optional list of event types to subscribe to.
                         Defaults to TRADING_DECISION, ORDER_FILLED, and ERROR.
        """
        self.telegram = telegram_adapter
        self._event_types = event_types if event_types is not None else DEFAULT_ALERT_EVENT_TYPES
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

    async def _handle_event(self, event: BaseEvent) -> None:
        try:
            if not self.telegram:
                return

            if isinstance(event, TradingDecisionEvent):
                payload = _decision_event_to_alert_payload(event)
                if payload is None:
                    return
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

            logger.debug("Unhandled event type: %s", event.event_type)

        except Exception:
            logger.exception("Error handling event %s", event.event_type)

    async def stop(self) -> None:
        """Stop the subscriber and clean up."""
        await self.unregister()
        logger.info("AlertSubscriber stopped")
