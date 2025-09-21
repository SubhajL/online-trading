"""
Data Ingestion Module

Handles real-time data ingestion from Binance WebSocket feeds
and historical data backfilling via REST API.
"""

from .binance_rest import BinanceRestClient
from .binance_spot import BinanceSpotIngester
from .binance_usdm import BinanceUSDMIngester
from .binance_ws import BinanceWebSocketClient
from .ingest_service import IngestService

__all__ = [
    "BinanceRestClient",
    "BinanceSpotIngester",
    "BinanceUSDMIngester",
    "BinanceWebSocketClient",
    "IngestService",
]
