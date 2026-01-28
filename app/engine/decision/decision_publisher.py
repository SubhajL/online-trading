"""
DecisionPublisher

Converts retest signals into TradingDecision events for downstream execution.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import TYPE_CHECKING

from app.engine.bus import get_event_bus
from app.engine.models import (
    EventType,
    RetestSignalEvent,
    TradingDecision,
    TradingDecisionEvent,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from decimal import Decimal


class DecisionPublisher:
    def __init__(
        self,
        *,
        account_balance: Decimal,
        risk_per_trade: Decimal,
    ) -> None:
        self._event_bus = get_event_bus()
        self._account_balance = account_balance
        self._risk_per_trade = risk_per_trade
        self._running = False
        self._subscription_id: str | None = None

    async def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._subscription_id = await self._event_bus.subscribe(
            subscriber_id="decision_publisher",
            handler=self._on_retest_signal,
            event_types=[EventType.RETEST_SIGNAL],
            priority=6,
        )
        logger.info("DecisionPublisher started")

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        if self._subscription_id is not None:
            await self._event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
        logger.info("DecisionPublisher stopped")

    async def _on_retest_signal(self, event: RetestSignalEvent) -> None:
        signal = event.signal
        entry_price = signal.level_price
        stop_loss = signal.stop_loss
        stop_distance = abs(entry_price - stop_loss)

        if stop_distance == 0:
            return

        risk_amount = self._account_balance * self._risk_per_trade
        quantity = risk_amount / stop_distance

        decision = TradingDecision(
            symbol=signal.symbol,
            timestamp=signal.timestamp,
            action=signal.direction,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=signal.take_profit,
            confidence=signal.success_probability,
            reasoning="; ".join(signal.confluence_factors) or signal.retest_type,
            signals=[signal],
        )

        # Forward zone metadata from retest signal for cooldown keying
        signal_metadata = event.metadata or {}
        decision_event = TradingDecisionEvent(
            timestamp=datetime.now(UTC),
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            metadata={
                "signal_id": str(signal.signal_id),
                "decision_source": "retest_decision_publisher",
                "zone": signal_metadata.get("zone"),
                "timeframe": signal_metadata.get("timeframe"),
            },
            decision=decision,
        )

        try:
            await self._event_bus.publish(decision_event, priority=7)
        except Exception:
            logger.exception("Error publishing trading decision")
