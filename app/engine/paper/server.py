"""
Paper Broker Server

Standalone server that runs the paper broker with same API as Go router.
Can be started alongside or instead of the real router for paper trading.
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

import uvicorn
import yaml
from contextlib import asynccontextmanager

from ..backtest.costs import CostCalculator
from ..backtest.fills import FillEngine
from .broker import PaperBroker, create_paper_broker_app

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
            with open(self.config_path, 'r') as file:
                config = yaml.safe_load(file)

            # Validate required config
            required = ['database_url', 'server']
            for key in required:
                if key not in config:
                    raise ValueError(f"Missing required config: {key}")

            return config

        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise

    async def initialize(self):
        """Initialize broker and FastAPI app"""
        # Create cost calculator from config
        backtest_config = self.config.get('backtest', {})
        cost_calc = CostCalculator(
            spot_fee_rate=backtest_config.get('fee_bps_spot', 10) / 10000,
            futures_fee_rate=backtest_config.get('fee_bps_futures', 4) / 10000,
            slippage_bps=backtest_config.get('slippage_bps', 2)
        )

        # Create fill engine
        fill_engine = FillEngine()

        # Create broker
        self.broker = PaperBroker(
            database_url=self.config['database_url'],
            cost_calculator=cost_calc,
            fill_engine=fill_engine
        )

        await self.broker.initialize()

        # Create FastAPI app
        self.app = create_paper_broker_app(self.broker)

        logger.info("Paper broker server initialized")

    async def start(self):
        """Start the server"""
        await self.initialize()

        server_config = self.config['server']
        host = server_config.get('host', '0.0.0.0')
        port = server_config.get('port', 8001)

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
            access_log=True
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
    parser = argparse.ArgumentParser(description='Paper Broker Server')
    parser.add_argument(
        '--config',
        required=True,
        help='Path to config.yaml file'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Server host (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8001,
        help='Server port (default: 8001)'
    )

    args = parser.parse_args()

    # Override config with CLI args
    server = PaperBrokerServer(args.config)
    if 'server' not in server.config:
        server.config['server'] = {}
    server.config['server']['host'] = args.host
    server.config['server']['port'] = args.port

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()