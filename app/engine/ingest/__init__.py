"""
Data Ingestion Module

Handles real-time data ingestion from Binance WebSocket feeds
and historical data backfilling via REST API.
"""

from .binance_ws import BinanceWebSocketClient
from .binance_rest import BinanceRestClient
from .binance_spot import BinanceSpotIngester
from .binance_usdm import BinanceUSDMIngester
from .ingest_service import IngestService

__all__ = [
    "BinanceWebSocketClient",
    "BinanceRestClient",
    "BinanceSpotIngester",
    "BinanceUSDMIngester",
    "IngestService"
]
