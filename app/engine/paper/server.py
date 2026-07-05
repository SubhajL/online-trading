"""
Paper Broker Server

Standalone server that runs the paper broker with same API as Go router.
Can be started alongside or instead of the real router for paper trading.
"""

import argparse
import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
import logging
import os
from pathlib import Path
import signal
import sys
from typing import Optional

import aiohttp
import uvicorn
import yaml

from ..backtest.costs import CostCalculator
from ..backtest.fills import FillEngine
from .broker import EventPublisher, PaperBroker, create_paper_broker_app

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

_ORDER_UPDATE_TOPIC = "order_update.v1"
_ORDER_UPDATE_TIMEOUT_SECONDS = 5


def build_cost_calculator(backtest_config: dict) -> CostCalculator:
    """Build the cost calculator from the config's backtest section."""
    return CostCalculator(
        fee_bps_spot=Decimal(str(backtest_config.get("fee_bps_spot", 10))),
        fee_bps_futures=Decimal(str(backtest_config.get("fee_bps_futures", 4))),
        funding_model=backtest_config.get("funding_model", "disabled"),
    )


def build_fill_engine(backtest_config: dict) -> FillEngine:
    """Build the fill engine from the config's backtest section."""
    return FillEngine(slippage_bps=Decimal(str(backtest_config.get("slippage_bps", 2))))


def build_order_update_publisher_from_env(
    environ: dict[str, str],
    timeout_seconds: float = _ORDER_UPDATE_TIMEOUT_SECONDS,
) -> EventPublisher | None:
    """
    Build an order-update publisher POSTing to the engine, mirroring the
    Go router's HTTPEventEmitter (ORDER_UPDATE_URL + ENGINE_INTERNAL_API_TOKEN).
    Returns None when ORDER_UPDATE_URL is unset.
    """
    url = environ.get("ORDER_UPDATE_URL")
    if not url:
        return None
    token = environ.get("ENGINE_INTERNAL_API_TOKEN", "")

    async def publish(topic: str, payload: dict[str, object]) -> bool:
        if topic != _ORDER_UPDATE_TOPIC:
            return True

        headers = {"Authorization": f"Bearer {token}"} if token else {}
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(url, json=payload, headers=headers) as response,
            ):
                if response.status >= 300:
                    body = await response.text()
                    logger.warning(
                        f"Engine rejected order update ({response.status}): {body[:200]}",
                    )
                    return False
                return True
        except (TimeoutError, aiohttp.ClientError) as exc:
            logger.warning(f"Failed to POST order update to engine: {exc!r}")
            return False

    return publish


class PaperBrokerServer:
    """Paper broker server manager"""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.broker: Optional[PaperBroker] = None
        self.app = None

    def _load_config(self) -> dict:
        """Load configuration from YAML"""
        try:
            with open(self.config_path) as file:
                config = yaml.safe_load(file)

            # Validate required config
            required = ["database_url", "server"]
            for key in required:
                if key not in config:
                    raise ValueError(f"Missing required config: {key}")

            return config

        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise

    async def initialize(self):
        """Initialize broker and FastAPI app"""
        backtest_config = self.config.get("backtest", {})

        event_publisher = build_order_update_publisher_from_env(dict(os.environ))
        if event_publisher is None:
            logger.info(
                "ORDER_UPDATE_URL not set; order updates will not reach the engine",
            )

        self.broker = PaperBroker(
            database_url=self.config["database_url"],
            cost_calculator=build_cost_calculator(backtest_config),
            fill_engine=build_fill_engine(backtest_config),
            event_publisher=event_publisher,
        )

        await self.broker.initialize()

        # Create FastAPI app
        self.app = create_paper_broker_app(self.broker)

        logger.info("Paper broker server initialized")

    async def start(self):
        """Start the server"""
        await self.initialize()

        server_config = self.config["server"]
        host = server_config.get("host", "0.0.0.0")
        port = server_config.get("port", 8001)

        # Create lifespan context manager
        @asynccontextmanager
        async def lifespan(app):
            # Startup
            logger.info(f"Paper broker starting on {host}:{port}")
            yield
            # Shutdown
            if self.broker:
                await self.broker.close()
            logger.info("Paper broker stopped")

        # Update app with lifespan
        self.app.router.lifespan_context = lifespan

        # Configure uvicorn
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
        )

        server = uvicorn.Server(config)

        # Setup graceful shutdown
        def signal_handler(sig, frame):
            logger.info("Received shutdown signal")
            server.should_exit = True

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Start server
        await server.serve()

    async def shutdown(self):
        """Shutdown the server"""
        if self.broker:
            await self.broker.close()
        logger.info("Paper broker server shutdown complete")


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="Paper Broker Server")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to config.yaml file",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Server port (default: 8001)",
    )

    args = parser.parse_args()

    # Override config with CLI args
    server = PaperBrokerServer(args.config)
    if "server" not in server.config:
        server.config["server"] = {}
    server.config["server"]["host"] = args.host
    server.config["server"]["port"] = args.port

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
