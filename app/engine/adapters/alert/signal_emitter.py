"""Emits trading signals with snapshot requirements."""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid


logger = logging.getLogger(__name__)


class SignalEmitter:
    """Emit trading signals that trigger snapshots and alerts."""

    def __init__(self, event_bus: Any, bff_client: Any) -> None:
        self.event_bus = event_bus
        self.bff_client = bff_client

    async def emit_signal(
        self,
        symbol: str,
        venue: str,
        side: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        confidence: float,
        reasons: List[str],
        timeframe: str = "15m",
        decision_time: Optional[datetime] = None,
    ) -> str:
        """
        Emit a trading signal that will trigger alerts and snapshots.

        Args:
            symbol: Trading pair symbol
            venue: Trading venue (SPOT or USD_M)
            side: Signal side (long or short)
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
            decision_time = decision_time or datetime.now()

            # Create decision event
            decision_event = {
                'signal_id': signal_id,
                'symbol': symbol,
                'venue': venue,
                'side': side,
                'entry_price': entry,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'quantity': 0.01,  # Default minimal quantity
                'confidence': confidence,
                'reasons': reasons,
                'timeframe': timeframe,
                'timestamp': decision_time.isoformat(),
                'decision_time': decision_time.isoformat(),
            }

            # Publish decision event
            await self.event_bus.publish('decision.v1', decision_event)

            # Notify BFF to generate snapshot
            await self._notify_snapshot(decision_event)

            logger.info(
                f"Emitted signal {signal_id}: {side} {symbol} @ {entry} "
                f"(SL: {stop_loss}, TP: {take_profit})"
            )

            return signal_id

        except Exception as e:
            logger.error(f"Error emitting signal: {e}", exc_info=True)
            raise

    async def _notify_snapshot(self, decision: Dict[str, Any]) -> None:
        """Notify BFF to generate a snapshot for this signal."""
        try:
            payload = {
                'signalId': decision['signal_id'],
                'symbol': decision['symbol'],
                'venue': decision['venue'],
                'side': 'BUY' if decision['side'] == 'long' else 'SELL',
                'entry': decision['entry_price'],
                'stopLoss': decision['stop_loss'],
                'takeProfit': decision['take_profit'],
                'confidence': decision['confidence'],
                'reasons': decision['reasons'],
                'timeframe': decision['timeframe'],
                'signalTime': decision['decision_time'],
            }

            # Call BFF signal alert endpoint
            await self.bff_client.post('/api/signals/alert', payload)

        except Exception as e:
            logger.error(
                f"Error notifying snapshot for signal {decision['signal_id']}: {e}",
                exc_info=True
            )
            # Don't raise - snapshot is nice to have but shouldn't block signal


class MockBffClient:
    """Mock BFF client for testing."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.posted_signals = []

    async def post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Mock POST request."""
        self.posted_signals.append({
            'endpoint': endpoint,
            'payload': payload,
            'timestamp': datetime.now().isoformat()
        })

        logger.info(f"Mock BFF POST to {endpoint}: {payload['signalId']}")

        return {
            'success': True,
            'signalId': payload['signalId'],
            'imageUrl': f"/snapshots/{payload['signalId']}.png"
        }


async def emit_test_signal():
    """Emit a test signal for demonstration."""
    from unittest.mock import Mock, AsyncMock

    # Create mock components
    event_bus = Mock(
        publish=AsyncMock(),
        subscribe=AsyncMock()
    )
    bff_client = MockBffClient("http://localhost:3000", "test-key")

    # Create signal emitter
    emitter = SignalEmitter(event_bus, bff_client)

    # Subscribe to decision events
    async def handle_decision(event: Dict[str, Any]) -> None:
        logger.info(f"Received decision event: {event['signal_id']}")

    await event_bus.subscribe('decision.v1', handle_decision)

    # Emit test signal
    signal_id = await emitter.emit_signal(
        symbol="BTCUSDT",
        venue="SPOT",
        side="long",
        entry=50000,
        stop_loss=49000,
        take_profit=52000,
        confidence=0.85,
        reasons=["SMC Breaker", "Bullish OB Retest", "Trend Alignment"],
        timeframe="15m"
    )

    logger.info(f"Test signal emitted: {signal_id}")

    # Check mock client
    if bff_client.posted_signals:
        logger.info(f"BFF notified: {bff_client.posted_signals[0]}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    asyncio.run(emit_test_signal())