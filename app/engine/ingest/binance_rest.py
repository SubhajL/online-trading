"""
Binance REST API Client

Handles historical data fetching, account information, and order management
via Binance REST API.
"""

import asyncio
import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
from aiohttp import ClientSession

from ..types import Candle, Order, Position, TimeFrame, OrderSide, OrderType, OrderStatus


logger = logging.getLogger(__name__)


class BinanceRestClient:
    """
    Binance REST API client for historical data and trading operations.

    Supports:
    - Historical kline/candlestick data
    - Account information
    - Order management
    - Market data queries
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://api.binance.com",
        testnet: bool = False,
        request_timeout: int = 30,
        rate_limit_per_minute: int = 1200
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        if testnet:
            self.base_url = "https://testnet.binance.vision"
        else:
            self.base_url = base_url

        self.request_timeout = request_timeout
        self.rate_limit_per_minute = rate_limit_per_minute

        # Rate limiting
        self._request_timestamps: List[float] = []
        self._rate_limit_lock = asyncio.Lock()

        # Session management
        self._session: Optional[ClientSession] = None

        logger.info(f"BinanceRestClient initialized (testnet: {testnet})")

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop()

    async def start(self):
        """Start the REST client"""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        logger.info("Binance REST client started")

    async def stop(self):
        """Stop the REST client"""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Binance REST client stopped")

    async def _rate_limit_check(self):
        """Check and enforce rate limits"""
        async with self._rate_limit_lock:
            now = time.time()

            # Remove timestamps older than 1 minute
            cutoff = now - 60
            self._request_timestamps = [ts for ts in self._request_timestamps if ts > cutoff]

            # Check if we're at the rate limit
            if len(self._request_timestamps) >= self.rate_limit_per_minute:
                sleep_time = 60 - (now - self._request_timestamps[0])
                if sleep_time > 0:
                    logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                    await asyncio.sleep(sleep_time)

            # Add current timestamp
            self._request_timestamps.append(now)

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Generate HMAC SHA256 signature for authenticated requests"""
        query_string = urlencode(params)
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False
    ) -> Dict[str, Any]:
        """Make HTTP request to Binance API"""
        if not self._session:
            raise RuntimeError("Client not started. Use async context manager or call start()")

        await self._rate_limit_check()

        params = params or {}
        url = f"{self.base_url}{endpoint}"

        # Add timestamp for signed requests
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._generate_signature(params)

        # Set headers
        headers = {}
        if self.api_key:
            headers['X-MBX-APIKEY'] = self.api_key

        try:
            if method.upper() == 'GET':
                async with self._session.get(url, params=params, headers=headers) as response:
                    return await self._handle_response(response)
            elif method.upper() == 'POST':
                async with self._session.post(url, data=params, headers=headers) as response:
                    return await self._handle_response(response)
            elif method.upper() == 'DELETE':
                async with self._session.delete(url, params=params, headers=headers) as response:
                    return await self._handle_response(response)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {method} {endpoint}")
            raise
        except Exception as e:
            logger.error(f"Request error for {method} {endpoint}: {e}")
            raise

    async def _handle_response(self, response: aiohttp.ClientResponse) -> Dict[str, Any]:
        """Handle HTTP response"""
        try:
            data = await response.json()

            if response.status == 200:
                return data
            else:
                error_msg = data.get('msg', f'HTTP {response.status}')
                logger.error(f"API error {response.status}: {error_msg}")
                raise Exception(f"Binance API error: {error_msg}")

        except Exception as e:
            logger.error(f"Error handling response: {e}")
            raise

    # ============================================================================
    # Market Data Methods
    # ============================================================================

    async def get_server_time(self) -> datetime:
        """Get server time"""
        data = await self._make_request('GET', '/api/v3/time')
        return datetime.fromtimestamp(data['serverTime'] / 1000)

    async def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get exchange information"""
        params = {}
        if symbol:
            params['symbol'] = symbol
        return await self._make_request('GET', '/api/v3/exchangeInfo', params)

    async def get_klines(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Candle]:
        """
        Get historical kline/candlestick data

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            timeframe: Kline interval
            start_time: Start time for historical data
            end_time: End time for historical data
            limit: Number of klines to return (max 1000)

        Returns:
            List of Candle objects
        """
        params = {
            'symbol': symbol,
            'interval': timeframe.value,
            'limit': min(limit, 1000)
        }

        if start_time:
            params['startTime'] = int(start_time.timestamp() * 1000)
        if end_time:
            params['endTime'] = int(end_time.timestamp() * 1000)

        data = await self._make_request('GET', '/api/v3/klines', params)

        candles = []
        for kline in data:
            candle = Candle(
                symbol=symbol,
                timeframe=timeframe,
                open_time=datetime.fromtimestamp(kline[0] / 1000),
                close_time=datetime.fromtimestamp(kline[6] / 1000),
                open_price=Decimal(kline[1]),
                high_price=Decimal(kline[2]),
                low_price=Decimal(kline[3]),
                close_price=Decimal(kline[4]),
                volume=Decimal(kline[5]),
                quote_volume=Decimal(kline[7]),
                trades=int(kline[8]),
                taker_buy_base_volume=Decimal(kline[9]),
                taker_buy_quote_volume=Decimal(kline[10])
            )
            candles.append(candle)

        return candles

    async def get_historical_data(
        self,
        symbol: str,
        timeframe: TimeFrame,
        days_back: int
    ) -> List[Candle]:
        """
        Get historical data for specified number of days

        Args:
            symbol: Trading symbol
            timeframe: Kline interval
            days_back: Number of days to go back

        Returns:
            List of Candle objects
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days_back)

        all_candles = []
        current_start = start_time

        # Fetch data in chunks (1000 klines max per request)
        while current_start < end_time:
            candles = await self.get_klines(
                symbol=symbol,
                timeframe=timeframe,
                start_time=current_start,
                end_time=end_time,
                limit=1000
            )

            if not candles:
                break

            all_candles.extend(candles)

            # Update start time for next batch
            current_start = candles[-1].close_time + timedelta(minutes=1)

            # Rate limiting between requests
            await asyncio.sleep(0.1)

        return all_candles

    async def get_ticker_24hr(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get 24hr ticker price change statistics"""
        params = {}
        if symbol:
            params['symbol'] = symbol
        return await self._make_request('GET', '/api/v3/ticker/24hr', params)

    async def get_price(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get latest price for symbol(s)"""
        params = {}
        if symbol:
            params['symbol'] = symbol
        return await self._make_request('GET', '/api/v3/ticker/price', params)

    async def get_order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """Get order book depth"""
        params = {
            'symbol': symbol,
            'limit': limit
        }
        return await self._make_request('GET', '/api/v3/depth', params)

    # ============================================================================
    # Account and Trading Methods (Require API key and secret)
    # ============================================================================

    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information"""
        return await self._make_request('GET', '/api/v3/account', signed=True)

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get open orders"""
        params = {}
        if symbol:
            params['symbol'] = symbol
        return await self._make_request('GET', '/api/v3/openOrders', params, signed=True)

    async def get_all_orders(
        self,
        symbol: str,
        limit: int = 500,
        order_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get all orders for a symbol"""
        params = {
            'symbol': symbol,
            'limit': limit
        }
        if order_id:
            params['orderId'] = order_id
        return await self._make_request('GET', '/api/v3/allOrders', params, signed=True)

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        time_in_force: str = "GTC"
    ) -> Dict[str, Any]:
        """
        Place a new order

        Args:
            symbol: Trading symbol
            side: Order side (BUY or SELL)
            order_type: Order type
            quantity: Order quantity
            price: Order price (required for LIMIT orders)
            stop_price: Stop price (required for STOP orders)
            time_in_force: Time in force

        Returns:
            Order response from API
        """
        params = {
            'symbol': symbol,
            'side': side.value,
            'type': order_type.value,
            'quantity': str(quantity),
            'timeInForce': time_in_force
        }

        if price:
            params['price'] = str(price)
        if stop_price:
            params['stopPrice'] = str(stop_price)

        return await self._make_request('POST', '/api/v3/order', params, signed=True)

    async def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel an order"""
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        return await self._make_request('DELETE', '/api/v3/order', params, signed=True)

    async def cancel_all_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Cancel all open orders for a symbol"""
        params = {'symbol': symbol}
        return await self._make_request('DELETE', '/api/v3/openOrders', params, signed=True)

    async def get_order_status(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Get order status"""
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        return await self._make_request('GET', '/api/v3/order', params, signed=True)

    # ============================================================================
    # Utility Methods
    # ============================================================================

    async def test_connectivity(self) -> bool:
        """Test API connectivity"""
        try:
            await self._make_request('GET', '/api/v3/ping')
            return True
        except Exception as e:
            logger.error(f"Connectivity test failed: {e}")
            return False

    async def health_check(self) -> Dict[str, Any]:
        """Get health status"""
        connectivity = await self.test_connectivity()

        return {
            "connected": connectivity,
            "session_active": self._session is not None,
            "testnet": self.testnet,
            "base_url": self.base_url,
            "rate_limit_status": {
                "requests_in_last_minute": len(self._request_timestamps),
                "rate_limit": self.rate_limit_per_minute
            }
        }