"""
DecisionPublisher

Converts retest signals into TradingDecision events for downstream execution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import TYPE_CHECKING

from app.engine.bus import get_event_bus
from app.engine.decision.pretrade_risk import evaluate_pretrade_risk
from app.engine.decision.risk_state import build_risk_snapshot
from app.engine.models import (
    ErrorEvent,
    EventType,
    RetestSignalEvent,
    TradingDecision,
    TradingDecisionEvent,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter
    from app.engine.models import RiskParameters


class DecisionPublisher:
    def __init__(
        self,
        *,
        db_adapter: TimescaleDBAdapter,
        risk: RiskParameters,
        venue: str,
    ) -> None:
        self._event_bus = get_event_bus()
        self._db_adapter = db_adapter
        self._risk = risk
        self._venue = venue
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
            serialize_by_key=True,
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

        snapshot, errors = await build_risk_snapshot(
            db_adapter=self._db_adapter,
            venue=self._venue,
            now=datetime.now(UTC),
            risk=self._risk,
        )
        if snapshot is None:
            message = (
                "; ".join(f"{e.error_type}:{e.message}" for e in errors)
                or "risk snapshot unavailable"
            )
            error_event = ErrorEvent(
                event_type=EventType.ERROR,
                timestamp=datetime.now(UTC),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                error_type="risk_snapshot_unavailable",
                error_message=message,
                component="decision_publisher",
                metadata={
                    "signal_id": str(signal.signal_id),
                },
            )
            try:
                await self._event_bus.publish(error_event, priority=7)
            except Exception:
                logger.exception("Error publishing risk snapshot error")
            return

        entry_price = signal.level_price
        stop_loss = signal.stop_loss
        stop_distance = abs(entry_price - stop_loss)

        if entry_price <= 0 or stop_distance == 0:
            return

        risk_amount = snapshot.equity * self._risk.risk_per_trade
        quantity = risk_amount / stop_distance

        max_qty_notional = snapshot.equity * self._risk.max_position_notional_pct / entry_price
        symbol_headroom_usd = (
            snapshot.equity * self._risk.max_symbol_exposure_pct
            - snapshot.symbol_exposure_usd.get(signal.symbol, Decimal(0))
        )
        max_qty_symbol = symbol_headroom_usd / entry_price
        total_headroom_usd = (
            snapshot.equity * self._risk.max_total_exposure_leverage - snapshot.total_exposure_usd
        )
        max_qty_total = total_headroom_usd / entry_price

        quantity = min(quantity, max_qty_notional, max_qty_symbol, max_qty_total)
        if quantity <= 0:
            return

        decision = TradingDecision(
            venue=self._venue,
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

        ok, reasons = evaluate_pretrade_risk(snapshot=snapshot, decision=decision, risk=self._risk)
        if not ok:
            error_event = ErrorEvent(
                event_type=EventType.ERROR,
                timestamp=datetime.now(UTC),
                symbol=signal.symbol,
                timeframe=signal.timeframe,
                error_type="risk_limit_exceeded",
                error_message="; ".join(reasons),
                component="decision_publisher",
                metadata={
                    "signal_id": str(signal.signal_id),
                },
            )
            try:
                await self._event_bus.publish(error_event, priority=7)
            except Exception:
                logger.exception("Error publishing pretrade risk error")
            return

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
