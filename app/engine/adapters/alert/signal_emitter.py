"""Emits trading signals with snapshot requirements."""

from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any, Literal
import uuid

from app.engine.models import TradingDecision, TradingDecisionEvent

logger = logging.getLogger(__name__)


class SignalEmitter:
    """Emit trading signals that trigger snapshots and alerts."""

    def __init__(self, event_bus: Any, bff_client: Any) -> None:
        self.event_bus = event_bus
        self.bff_client = bff_client

    async def emit_signal(  # noqa: PLR0913
        self,
        symbol: str,
        venue: str,
        side: Literal["long", "short"],
        entry: float,
        stop_loss: float,
        take_profit: float,
        confidence: float,
        reasons: list[str],
        timeframe: str = "15m",
        decision_time: datetime | None = None,
        zone: dict[str, Any] | None = None,
    ) -> str:
        """
        Emit a trading signal that will trigger alerts and snapshots.

        Args:
            symbol: Trading pair symbol
            venue: Trading venue (SPOT or USD_M)
            side: Signal side ("long" or "short")
            entry: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            confidence: Signal confidence (0-1)
            reasons: List of reasons for the signal
            timeframe: Timeframe for the signal
            decision_time: Time of the signal (defaults to now)

        Returns:
            signal_id: Unique ID for the signal
        """
        try:
            signal_id = f"sig_{uuid.uuid4().hex[:12]}"
            if decision_time is None:
                decision_time = datetime.now(UTC)
            elif decision_time.tzinfo is None:
                decision_time = decision_time.replace(tzinfo=UTC)

            action = "BUY" if side == "long" else "SELL"

            decision = TradingDecision(
                venue=venue,
                symbol=symbol,
                timestamp=decision_time,
                action=action,
                entry_price=Decimal(str(entry)),
                quantity=Decimal("0.01"),
                stop_loss=Decimal(str(stop_loss)),
                take_profit=Decimal(str(take_profit)),
                confidence=Decimal(str(confidence)),
                reasoning="; ".join(reasons),
            )

            event = TradingDecisionEvent(
                symbol=symbol,
                timestamp=decision_time,
                decision=decision,
                metadata={
                    "signal_id": signal_id,
                    "decision_source": "signal_emitter_bypass",
                    "venue": venue,
                    "timeframe": timeframe,
                    **({"zone": zone} if zone is not None else {}),
                },
            )

            await self.event_bus.publish(event)

            snapshot_data = {
                "signal_id": signal_id,
                "symbol": symbol,
                "venue": venue,
                "side": side,
                "entry_price": entry,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "confidence": confidence,
                "reasons": reasons,
                "timeframe": timeframe,
                "decision_time": decision_time.isoformat(),
            }
            await self._notify_snapshot(snapshot_data)

            logger.info(
                "Emitted signal %s: %s %s @ %s (SL: %s, TP: %s)",
                signal_id,
                side,
                symbol,
                entry,
                stop_loss,
                take_profit,
            )
        except Exception:
            logger.exception("Error emitting signal")
            raise
        else:
            return signal_id

    async def _notify_snapshot(self, decision: dict[str, Any]) -> None:
        """Notify BFF to generate a snapshot for this signal."""
        try:
            payload = {
                "signalId": decision["signal_id"],
                "symbol": decision["symbol"],
                "venue": decision["venue"],
                "side": "BUY" if decision["side"] == "long" else "SELL",
                "entry": decision["entry_price"],
                "stopLoss": decision["stop_loss"],
                "takeProfit": decision["take_profit"],
                "confidence": decision["confidence"],
                "reasons": decision["reasons"],
                "timeframe": decision["timeframe"],
                "signalTime": decision["decision_time"],
            }

            # Call BFF signal alert endpoint
            await self.bff_client.post("/api/signals/alert", payload)

        except Exception:
            logger.exception(
                "Error notifying snapshot for signal %s",
                decision["signal_id"],
            )
            # Don't raise - snapshot is nice to have but shouldn't block signal


class MockBffClient:
    """Mock BFF client for testing."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.posted_signals: list[dict[str, Any]] = []

    async def post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Mock POST request."""
        self.posted_signals.append(
            {
                "endpoint": endpoint,
                "payload": payload,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        logger.info("Mock BFF POST to %s: %s", endpoint, payload["signalId"])

        return {
            "success": True,
            "signalId": payload["signalId"],
            "imageUrl": f"/api/snapshots/{payload['signalId']}.png",
        }


async def emit_test_signal() -> None:
    """Emit a test signal for demonstration."""
    from unittest.mock import AsyncMock, Mock

    event_bus = Mock(
        publish=AsyncMock(),
        subscribe=AsyncMock(),
    )
    bff_client = MockBffClient("http://localhost:3000", "test-key")

    emitter = SignalEmitter(event_bus, bff_client)

    async def handle_decision(event: dict[str, Any]) -> None:
        logger.info("Received decision event: %s", event["signal_id"])

    await event_bus.subscribe("decision.v1", handle_decision)

    signal_id = await emitter.emit_signal(
        symbol="BTCUSDT",
        venue="SPOT",
        side="long",
        entry=50000,
        stop_loss=49000,
        take_profit=52000,
        confidence=0.85,
        reasons=["SMC Breaker", "Bullish OB Retest", "Trend Alignment"],
        timeframe="15m",
    )

    logger.info("Test signal emitted: %s", signal_id)

    if bff_client.posted_signals:
        logger.info("BFF notified: %s", bff_client.posted_signals[0])


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    asyncio.run(emit_test_signal())
