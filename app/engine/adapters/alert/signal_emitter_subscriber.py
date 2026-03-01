"""Subscriber that bridges SMC signals to SignalEmitter."""

import logging
from typing import TYPE_CHECKING, Any, Literal, Protocol

from app.engine.models import EventType, OrderSide, SMCSignalEvent

if TYPE_CHECKING:
    from app.engine.adapters.alert.signal_emitter import SignalEmitter

logger = logging.getLogger(__name__)


class EventBusProtocol(Protocol):
    """Protocol for event bus subscription."""

    async def subscribe(
        self,
        subscriber_id: str,
        handler: Any,
        event_types: list[EventType] | None = None,
        priority: int = 0,
    ) -> str: ...

    async def unsubscribe(self, subscription_id: str) -> bool: ...


class SignalEmitterSubscriber:
    """Subscribe to SMC_SIGNAL events and emit trading decisions."""

    def __init__(
        self,
        bus: EventBusProtocol,
        signal_emitter: "SignalEmitter",
        venue: str = "SPOT",
    ) -> None:
        """Initialize subscriber.

        Args:
            bus: Event bus to subscribe to
            signal_emitter: SignalEmitter instance to call
            venue: Default venue for signals (SPOT or USD_M)
        """
        self._bus = bus
        self._signal_emitter = signal_emitter
        self._venue = venue
        self._subscription_id: str | None = None

    async def start(self) -> None:
        """Subscribe to SMC_SIGNAL events."""
        self._subscription_id = await self._bus.subscribe(
            subscriber_id="signal_emitter_subscriber",
            handler=self._handle_smc_signal,
            event_types=[EventType.SMC_SIGNAL],
            priority=5,
        )
        logger.info("SignalEmitterSubscriber started")

    async def stop(self) -> None:
        """Unsubscribe from events."""
        if self._subscription_id is not None:
            await self._bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
            logger.info("SignalEmitterSubscriber stopped")

    async def _handle_smc_signal(self, event: SMCSignalEvent) -> None:
        """Handle incoming SMC signal event.

        Only emits if signal has both stop_loss and take_profit.
        """
        signal = event.signal

        # Skip signals without required SL/TP
        if signal.stop_loss is None:
            logger.debug(
                "Skipping SMC signal %s: missing stop_loss",
                signal.signal_id,
            )
            return

        if signal.take_profit is None:
            logger.debug(
                "Skipping SMC signal %s: missing take_profit",
                signal.signal_id,
            )
            return

        # Map direction to side
        side: Literal["long", "short"] = "long" if signal.direction == OrderSide.BUY else "short"

        # Split reasoning into list
        reasons = [r.strip() for r in signal.reasoning.split(";")]

        zone = signal.zone
        zone_evidence: dict[str, Any] | None = None
        if zone is not None:
            zone_evidence = {
                "zone_id": str(zone.zone_id),
                "zone_type": zone.zone_type.value,
                "top_price": zone.top_price,
                "bottom_price": zone.bottom_price,
            }

        try:
            await self._signal_emitter.emit_signal(
                symbol=signal.symbol,
                venue=self._venue,
                side=side,
                entry=float(signal.entry_price),
                stop_loss=float(signal.stop_loss),
                take_profit=float(signal.take_profit),
                confidence=float(signal.confidence),
                reasons=reasons,
                timeframe=signal.timeframe.value,
                decision_time=signal.timestamp,
                zone=zone_evidence,
            )
        except Exception:
            logger.exception(
                "Error emitting signal for SMC signal %s",
                signal.signal_id,
            )
