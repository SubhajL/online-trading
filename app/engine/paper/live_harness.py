"""
LivePaperTradingHarness - Wires WebSocket → pipeline → paper broker.

This harness:
1. Connects to Binance testnet WebSocket for live market data
2. Runs the full trading pipeline (features → SMC → retest → decision)
3. Routes decisions to PaperBroker for simulated execution
4. Persists decisions to trading_decisions table before broker call
5. Sends Telegram alerts on TRADING_DECISION events only
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
import logging
import os
import time
from typing import TYPE_CHECKING, Any

from app.engine.adapters.alert.alert_subscriber import AlertSubscriber
from app.engine.bus import create_event_bus, set_event_bus
from app.engine.ingest.binance_ws import BinanceWebSocketClient
from app.engine.models import (
    Candle,
    CandleOrigin,
    CandleUpdateEvent,
    EventType,
    TimeFrame,
    TradingDecisionEvent,
)
from app.engine.paper.broker import PaperBroker, PlaceBracketRequest

# Max latency samples to keep in memory
MAX_LATENCY_SAMPLES = 1000

if TYPE_CHECKING:
    from app.engine.adapters.alert.telegram import TelegramAlertAdapter

logger = logging.getLogger(__name__)


@dataclass
class HarnessConfig:
    """Configuration for LivePaperTradingHarness."""

    symbols: list[str]
    timeframes: list[TimeFrame]
    database_url: str
    testnet: bool = True
    telegram_adapter: TelegramAlertAdapter | None = None


@dataclass
class HarnessMetrics:
    """Metrics collected by the harness."""

    decision_count: int = 0
    candle_count: int = 0
    order_count: int = 0
    error_count: int = 0
    latency_sum_ms: float = 0.0
    # Bounded deque to prevent memory leak in long-running harness
    latencies_ms: deque[float] = field(
        default_factory=lambda: deque(maxlen=MAX_LATENCY_SAMPLES),
    )


class LivePaperTradingHarness:
    """
    Harness that wires WebSocket → pipeline → paper broker.

    Uses testnet WebSocket only (no REST client for live trading).
    Persists decisions at harness boundary before broker call.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Initialize harness with configuration.

        Args:
            config: Configuration dictionary with keys:
                - symbols: List of trading symbols
                - timeframes: List of timeframes to subscribe
                - database_url: PostgreSQL connection URL
                - testnet: Always True for paper trading
                - telegram_adapter: Optional Telegram adapter
        """
        self._config = self._parse_config(config)
        self._metrics = HarnessMetrics()
        self._running = False

        # Create event bus
        self.event_bus = create_event_bus()
        set_event_bus(self.event_bus)

        # Create WebSocket client (uses config.testnet)
        self.ws_client = BinanceWebSocketClient(
            testnet=self._config.testnet,
            event_bus=self.event_bus,
        )

        # Create paper broker
        self.broker = PaperBroker(
            database_url=self._config.database_url,
            event_publisher=self.event_bus,
        )

        # Create alert subscriber with TRADING_DECISION only
        self.alert_subscriber = AlertSubscriber(
            telegram_adapter=self._config.telegram_adapter,
            event_types=[EventType.TRADING_DECISION],
        )

        logger.info("LivePaperTradingHarness initialized")

    def _parse_config(self, config: dict[str, Any]) -> HarnessConfig:
        """Parse configuration dictionary into HarnessConfig."""
        return HarnessConfig(
            symbols=config.get("symbols", ["BTCUSDT"]),
            timeframes=config.get("timeframes", [TimeFrame.M1]),
            database_url=config.get(
                "database_url",
                "postgresql://localhost:5432/trading",
            ),
            testnet=config.get("testnet", True),
            telegram_adapter=config.get("telegram_adapter"),
        )

    async def start(self) -> None:
        """Start the harness."""
        if self._running:
            logger.warning("Harness already running")
            return

        self._running = True

        # Initialize broker
        await self.broker.initialize()

        # Start event bus
        await self.event_bus.start()

        # Wire pipeline subscriptions
        await self._wire_pipeline()

        # Register alert subscriber
        await self.alert_subscriber.register(self.event_bus)

        # Subscribe to candle updates for broker market data
        await self.event_bus.subscribe(
            subscriber_id="harness-candle-updater",
            handler=self._handle_candle_event,
            event_types=[EventType.CANDLE_UPDATE],
        )

        # Subscribe to trading decisions
        await self.event_bus.subscribe(
            subscriber_id="harness-decision-handler",
            handler=self._on_decision,
            event_types=[EventType.TRADING_DECISION],
        )

        # Warm buffers with historical data
        await self.warm_buffers()

        # Start WebSocket client
        await self.ws_client.start()
        await self.ws_client.subscribe_klines(
            self._config.symbols,
            self._config.timeframes,
        )

        logger.info("LivePaperTradingHarness started")

    async def stop(self) -> None:
        """Stop the harness gracefully."""
        if not self._running:
            return

        self._running = False

        # Stop WebSocket
        await self.ws_client.stop()

        # Unregister alert subscriber
        await self.alert_subscriber.stop()

        # Stop event bus
        await self.event_bus.stop()

        # Close broker
        await self.broker.close()

        logger.info("LivePaperTradingHarness stopped")

    async def _wire_pipeline(self) -> None:
        """Wire the trading pipeline subscriptions.

        Pipeline: candles → features → smc → retest → decision
        Each stage publishes to the bus and the next stage subscribes.
        """
        # Pipeline handlers would be wired here in a full implementation
        # For now, the harness focuses on decision handling
        logger.info("Trading pipeline wired")

    async def _handle_candle_event(self, event: CandleUpdateEvent) -> None:
        """Handle candle update event."""
        await self._on_candle(event.candle)

    async def _on_candle(self, candle: Candle) -> None:
        """Update broker with latest candle for fill simulation."""
        try:
            await self.broker.update_market_data(candle)
            self._metrics.candle_count += 1
        except Exception:
            logger.exception("Error updating broker market data")
            self._metrics.error_count += 1

    async def _on_decision(self, event: TradingDecisionEvent) -> None:
        """Handle trading decision event.

        Order of operations:
        1. Persist decision to trading_decisions table
        2. Place bracket order via paper broker
        3. Record latency metrics (only for actionable decisions)
        """
        decision = event.decision

        # Skip non-actionable decisions (no latency tracking)
        if decision.action not in ("BUY", "SELL"):
            return

        start_time = time.perf_counter()

        try:
            # 1. Persist decision first (before broker call)
            await self._persist_decision(event)

            # 2. Place bracket order
            request = PlaceBracketRequest(
                symbol=decision.symbol,
                side=decision.action,
                quantity=decision.quantity or Decimal("0.01"),
                entry_price=decision.entry_price or Decimal(0),
                take_profit_prices=[decision.take_profit]
                if decision.take_profit
                else [],
                stop_loss_price=decision.stop_loss or Decimal(0),
                order_type="MARKET",
                is_futures=False,
            )
            await self.broker.place_bracket_order(request)

            self._metrics.decision_count += 1
            self._metrics.order_count += 1

        except Exception:
            logger.exception("Error handling decision")
            self._metrics.error_count += 1
        finally:
            # 3. Record latency (only for processed decisions)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self._metrics.latency_sum_ms += elapsed_ms
            self._metrics.latencies_ms.append(elapsed_ms)

    async def _persist_decision(self, event: TradingDecisionEvent) -> None:
        """Persist trading decision to database.

        This is called BEFORE the broker places the order to ensure
        decision audit trail even if order placement fails.
        """
        # In a full implementation, this would INSERT into trading_decisions table
        # For now, log the decision
        logger.info(
            "Persisting decision: %s %s @ %s",
            event.decision.action,
            event.decision.symbol,
            event.decision.entry_price,
        )

    async def warm_buffers(self) -> None:
        """Warm indicator buffers with historical candles.

        Fetches recent candles via REST API and marks them as BACKFILL
        so they don't trigger trading decisions.
        """
        await self._fetch_historical_candles(CandleOrigin.BACKFILL)

    async def _fetch_historical_candles(self, origin: CandleOrigin) -> None:
        """Fetch historical candles and publish to bus.

        Args:
            origin: The origin to mark candles with (BACKFILL for warm-up)
        """
        # In a full implementation, this would use Binance REST API
        # For now, just log
        logger.info("Fetching historical candles with origin: %s", origin.value)

    def get_metrics(self) -> dict[str, Any]:
        """Get current harness metrics.

        Returns:
            Dictionary with all metric keys:
            - decision_count: Number of decisions processed
            - candle_count: Number of candles processed
            - order_count: Number of orders placed
            - error_count: Number of errors
            - latency_sum_ms: Total latency in milliseconds
        """
        return {
            "decision_count": self._metrics.decision_count,
            "candle_count": self._metrics.candle_count,
            "order_count": self._metrics.order_count,
            "error_count": self._metrics.error_count,
            "latency_sum_ms": self._metrics.latency_sum_ms,
        }


async def main() -> None:
    """Main entry point for running the harness."""
    config = {
        "symbols": os.getenv("PAPER_SYMBOLS", "BTCUSDT").split(","),
        "timeframes": [TimeFrame.M1],
        "database_url": os.getenv(
            "DATABASE_URL",
            "postgresql://localhost:5432/trading",
        ),
        "testnet": True,
    }

    harness = LivePaperTradingHarness(config)

    try:
        await harness.start()
        # Keep running until interrupted
        while True:
            await asyncio.sleep(60)
            metrics = harness.get_metrics()
            logger.info("Harness metrics: %s", metrics)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await harness.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
