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
from datetime import UTC, datetime
from decimal import Decimal
import logging
import os
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from app.engine.adapters.alert.alert_subscriber import AlertSubscriber
from app.engine.adapters.alert.telegram import TelegramAlertAdapter
from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter
from app.engine.bus import create_event_bus, publish_event, set_event_bus
from app.engine.decision.decision_publisher import DecisionPublisher
from app.engine.features.feature_service import FeatureService
from app.engine.ingest.binance_ws import BinanceWebSocketClient
from app.engine.models import (
    Candle,
    CandleOrigin,
    CandleUpdateEvent,
    EventType,
    RiskParameters,
    TimeFrame,
    TradingDecisionEvent,
)
from app.engine.paper.broker import PaperBroker, PlaceBracketRequest
from app.engine.retest.engine import RetestEngine
from app.engine.smc.engine import SMCEngine

# Max latency samples to keep in memory
MAX_LATENCY_SAMPLES = 1000

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    StopFn = Callable[[], Awaitable[None]]

logger = logging.getLogger(__name__)


@dataclass
class HarnessConfig:
    """Configuration for LivePaperTradingHarness."""

    symbols: list[str]
    timeframes: list[TimeFrame]
    database_url: str
    testnet: bool = True
    telegram_adapter: TelegramAlertAdapter | None = None
    paper_session_id: UUID = field(default_factory=uuid4)
    paper_account_balance: Decimal = Decimal(10_000)
    paper_risk_per_trade: Decimal = Decimal("0.01")


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
                - paper_session_id: Optional UUID for harness-run correlation
        """
        self._config = self._parse_config(config)
        self._metrics = HarnessMetrics()
        self._running = False

        # Unique session ID for this harness run (not the per-bracket OCO group id)
        self.paper_session_id = self._config.paper_session_id

        # Create event bus
        self.event_bus = create_event_bus()
        set_event_bus(self.event_bus)

        # Create WebSocket client (uses config.testnet)
        self.ws_client = BinanceWebSocketClient(
            testnet=self._config.testnet,
            event_bus=self.event_bus,
        )

        # Create TimescaleDBAdapter from database_url
        self.db_adapter = self._create_db_adapter(self._config.database_url)

        # PaperBroker assigns a per-bracket `paper_session_id` (OCO scope) internally.
        self.broker = PaperBroker(
            database_url=self._config.database_url,
            event_publisher=publish_event,
        )

        # Create alert subscriber with TRADING_DECISION only
        self.alert_subscriber = AlertSubscriber(
            telegram_adapter=self._config.telegram_adapter,
            event_types=[EventType.TRADING_DECISION],
        )

        self.feature_service: FeatureService | None = None
        self.smc_service: SMCEngine | None = None
        self.retest_engine: RetestEngine | None = None
        self.decision_publisher: DecisionPublisher | None = None

        logger.info(
            "LivePaperTradingHarness initialized with session %s",
            self.paper_session_id,
        )

    def _parse_config(self, config: dict[str, Any]) -> HarnessConfig:
        """Parse configuration dictionary into HarnessConfig."""
        # Parse paper_session_id if provided (can be UUID or string)
        session_id = config.get("paper_session_id")
        if session_id is not None and not isinstance(session_id, UUID):
            session_id = UUID(session_id)

        return HarnessConfig(
            symbols=config.get("symbols", ["BTCUSDT"]),
            timeframes=config.get("timeframes", [TimeFrame.M1]),
            database_url=config.get(
                "database_url",
                "postgresql://localhost:5432/trading",
            ),
            testnet=config.get("testnet", True),
            telegram_adapter=config.get("telegram_adapter"),
            paper_session_id=session_id or uuid4(),
            paper_account_balance=Decimal(
                str(config.get("paper_account_balance", "10000")),
            ),
            paper_risk_per_trade=Decimal(
                str(config.get("paper_risk_per_trade", "0.01")),
            ),
        )

    async def _stop_component(
        self,
        errors: list[str],
        *,
        name: str,
        stop_fn: StopFn | None,
    ) -> None:
        if stop_fn is None:
            return
        try:
            await stop_fn()
        except Exception:
            logger.exception("Error stopping %s", name)
            errors.append(name)

    def _create_db_adapter(self, database_url: str) -> TimescaleDBAdapter:
        """Create TimescaleDBAdapter from database URL.

        Parses postgresql://user:pass@host:port/dbname into adapter config.
        """
        parsed = urlparse(database_url)
        return TimescaleDBAdapter(
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            database=parsed.path.lstrip("/") or "trading",
            username=parsed.username or "postgres",
            password=parsed.password or "",
            pool_size=5,
        )

    async def _maybe_create_telegram_adapter_from_env(
        self,
    ) -> TelegramAlertAdapter | None:
        if self._config.telegram_adapter is not None:
            return self._config.telegram_adapter

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not bot_token or not chat_id:
            return None

        adapter = TelegramAlertAdapter(
            bot_token=bot_token,
            chat_id=chat_id,
        )
        await adapter.start()
        return adapter

    async def start(self) -> None:
        """Start the harness.

        Initializes resources in order: db_adapter → broker → event_bus → subscriptions.
        On partial failure, cleans up already-initialized resources.
        """
        if self._running:
            logger.warning("Harness already running")
            return

        db_initialized = False
        broker_initialized = False

        try:
            # Initialize db_adapter first (for decision persistence)
            await self.db_adapter.initialize()
            db_initialized = True

            # Initialize broker (uses its own pool for paper_orders)
            await self.broker.initialize()
            broker_initialized = True

            # Start event bus
            await self.event_bus.start()

            # Wire pipeline subscriptions
            await self._wire_pipeline()

            # Start Telegram adapter (if configured via env)
            telegram_adapter = await self._maybe_create_telegram_adapter_from_env()
            if telegram_adapter is not None:
                self._config.telegram_adapter = telegram_adapter
                self.alert_subscriber.telegram = telegram_adapter

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

            self._running = True
            logger.info("LivePaperTradingHarness started")

        except Exception:
            logger.exception("Failed to start harness, cleaning up")
            # Clean up in reverse order
            if broker_initialized:
                try:
                    await self.broker.close()
                except Exception:
                    logger.exception("Error closing broker during startup rollback")
            if db_initialized:
                try:
                    await self.db_adapter.close()
                except Exception:
                    logger.exception("Error closing db_adapter during startup rollback")
            raise

    async def stop(self) -> None:
        """Stop the harness gracefully.

        Always attempts to close all resources even if some fail.
        Logs errors but does not raise to ensure complete cleanup.
        """
        if not self._running:
            return

        self._running = False
        errors: list[str] = []

        await self._stop_component(
            errors,
            name="ws_client",
            stop_fn=self.ws_client.stop,
        )

        await self._stop_component(
            errors,
            name="decision_publisher",
            stop_fn=self.decision_publisher.stop if self.decision_publisher else None,
        )
        await self._stop_component(
            errors,
            name="retest_engine",
            stop_fn=self.retest_engine.stop if self.retest_engine else None,
        )
        await self._stop_component(
            errors,
            name="smc_service",
            stop_fn=self.smc_service.stop if self.smc_service else None,
        )
        await self._stop_component(
            errors,
            name="feature_service",
            stop_fn=self.feature_service.stop if self.feature_service else None,
        )

        await self._stop_component(
            errors,
            name="alert_subscriber",
            stop_fn=self.alert_subscriber.stop,
        )
        await self._stop_component(
            errors,
            name="telegram_adapter",
            stop_fn=self._config.telegram_adapter.stop if self._config.telegram_adapter else None,
        )
        await self._stop_component(
            errors,
            name="event_bus",
            stop_fn=self.event_bus.stop,
        )
        await self._stop_component(errors, name="broker", stop_fn=self.broker.close)
        await self._stop_component(
            errors,
            name="db_adapter",
            stop_fn=self.db_adapter.close,
        )

        if errors:
            logger.warning(
                "LivePaperTradingHarness stopped with errors in: %s",
                ", ".join(errors),
            )
        else:
            logger.info("LivePaperTradingHarness stopped")

    async def _wire_pipeline(self) -> None:
        """Wire the trading pipeline subscriptions.

        Pipeline: candles → features → smc → retest → decision
        Each stage publishes to the bus and the next stage subscribes.
        """
        if self.feature_service is None:
            self.feature_service = FeatureService(db_adapter=self.db_adapter)
        if self.smc_service is None:
            self.smc_service = SMCEngine()
        if self.retest_engine is None:
            self.retest_engine = RetestEngine(config={"retest": {}})
        if self.decision_publisher is None:
            now = datetime.now(UTC)
            await self.db_adapter.insert_equity_sample(
                equity=self._config.paper_account_balance,
                timestamp=now,
            )
            risk = RiskParameters(
                max_position_size=Decimal("999999"),
                max_daily_loss=Decimal("1"),
                max_drawdown=Decimal("1"),
                risk_per_trade=self._config.paper_risk_per_trade,
                max_correlation=Decimal("1"),
                max_open_positions=100,
                max_total_exposure_leverage=Decimal("100"),
                max_symbol_exposure_pct=Decimal("1"),
                max_position_notional_pct=Decimal("1"),
                risk_data_max_age_seconds=86400,
                drawdown_lookback_days=30,
            )
            self.decision_publisher = DecisionPublisher(
                db_adapter=self.db_adapter,
                risk=risk,
                venue="SPOT",
            )

        await self.feature_service.start()
        await self.smc_service.start()
        await self.retest_engine.start()
        await self.decision_publisher.start()

        logger.info("Trading pipeline wired and started")

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
                take_profit_prices=[decision.take_profit] if decision.take_profit else [],
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

        Increments error_count if insert fails.
        """
        decision = event.decision
        try:
            success = await self.db_adapter.insert_trading_decision(decision)
            if success:
                logger.info(
                    "Persisted decision %s: %s %s @ %s",
                    decision.decision_id,
                    decision.action,
                    decision.symbol,
                    decision.entry_price,
                )
            else:
                logger.error(
                    "Failed to persist decision %s: insert returned False",
                    decision.decision_id,
                )
                self._metrics.error_count += 1
        except Exception:
            logger.exception("Error persisting decision %s", decision.decision_id)
            self._metrics.error_count += 1

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
