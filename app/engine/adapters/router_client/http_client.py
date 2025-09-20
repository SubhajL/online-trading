"""
HTTP Router Client

HTTP client for communicating with the router service for order execution,
position management, and account operations.
"""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

import aiohttp
from aiohttp import ClientSession, ClientTimeout

from ...models import Order, Position, OrderSide, OrderType, TradingDecision


logger = logging.getLogger(__name__)


class RouterHTTPClient:
    """
    HTTP client for router service communication.

    Handles:
    - Order placement and management
    - Position queries and updates
    - Account information retrieval
    - Portfolio management
    - Risk monitoring
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay

        self._session: Optional[ClientSession] = None
        self._initialized = False

        logger.info(f"RouterHTTPClient configured for {base_url}")

    async def initialize(self):
        """Initialize the HTTP client"""
        if self._initialized:
            return

        try:
            timeout = ClientTimeout(total=self.timeout)
            self._session = ClientSession(timeout=timeout)
            self._initialized = True
            logger.info("Router HTTP client initialized")

        except Exception as e:
            logger.error(f"Error initializing router HTTP client: {e}")
            raise

    async def close(self):
        """Close the HTTP client"""
        if self._session:
            await self._session.close()
            self._session = None

        self._initialized = False
        logger.info("Router HTTP client closed")

    def _ensure_initialized(self):
        """Ensure client is initialized"""
        if not self._initialized or not self._session:
            raise RuntimeError("Router HTTP client not initialized")

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for requests"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "TradingEngine/1.0",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic"""
        self._ensure_initialized()

        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        headers = self._get_headers()

        for attempt in range(self.retry_attempts):
            try:
                async with self._session.request(
                    method=method, url=url, json=data, params=params, headers=headers
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        logger.warning(f"Endpoint not found: {endpoint}")
                        return {"error": "endpoint_not_found", "status": 404}
                    elif response.status >= 400:
                        error_text = await response.text()
                        logger.error(f"HTTP {response.status} error: {error_text}")
                        return {"error": error_text, "status": response.status}

            except asyncio.TimeoutError:
                logger.warning(
                    f"Request timeout for {method} {endpoint} (attempt {attempt + 1})"
                )
                if attempt == self.retry_attempts - 1:
                    raise
                await asyncio.sleep(self.retry_delay * (attempt + 1))

            except Exception as e:
                logger.error(f"Request error for {method} {endpoint}: {e}")
                if attempt == self.retry_attempts - 1:
                    raise
                await asyncio.sleep(self.retry_delay * (attempt + 1))

        raise Exception(
            f"Failed to complete request after {self.retry_attempts} attempts"
        )

    # ============================================================================
    # Order Management
    # ============================================================================

    async def place_order(self, decision: TradingDecision) -> Dict[str, Any]:
        """Place a trading order based on decision"""
        try:
            order_data = {
                "symbol": decision.symbol,
                "side": decision.action,  # BUY/SELL
                "type": decision.order_type.value if decision.order_type else "MARKET",
                "quantity": str(decision.quantity) if decision.quantity else None,
                "price": str(decision.entry_price) if decision.entry_price else None,
                "stop_loss": str(decision.stop_loss) if decision.stop_loss else None,
                "take_profit": (
                    str(decision.take_profit) if decision.take_profit else None
                ),
                "decision_id": str(decision.decision_id),
                "timestamp": decision.timestamp.isoformat(),
                "reasoning": decision.reasoning,
            }

            # Remove None values
            order_data = {k: v for k, v in order_data.items() if v is not None}

            result = await self._make_request("POST", "/orders", data=order_data)
            logger.info(f"Placed order for {decision.symbol}: {result}")
            return result

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return {"error": str(e), "success": False}

    async def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order status by ID"""
        try:
            result = await self._make_request("GET", f"/orders/{order_id}")
            return result

        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        try:
            result = await self._make_request("DELETE", f"/orders/{order_id}")
            return result.get("success", False)

        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            return False

    async def get_open_orders(
        self, symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get open orders"""
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol

            result = await self._make_request("GET", "/orders/open", params=params)

            if isinstance(result, dict) and "orders" in result:
                return result["orders"]
            elif isinstance(result, list):
                return result
            else:
                return []

        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []

    async def get_order_history(
        self, symbol: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get order history"""
        try:
            params = {"limit": limit}
            if symbol:
                params["symbol"] = symbol

            result = await self._make_request("GET", "/orders/history", params=params)

            if isinstance(result, dict) and "orders" in result:
                return result["orders"]
            elif isinstance(result, list):
                return result
            else:
                return []

        except Exception as e:
            logger.error(f"Error getting order history: {e}")
            return []

    # ============================================================================
    # Position Management
    # ============================================================================

    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get current positions"""
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol

            result = await self._make_request("GET", "/positions", params=params)

            if isinstance(result, dict) and "positions" in result:
                return result["positions"]
            elif isinstance(result, list):
                return result
            else:
                return []

        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    async def close_position(
        self, symbol: str, quantity: Optional[Decimal] = None
    ) -> bool:
        """Close a position"""
        try:
            data = {"symbol": symbol}
            if quantity:
                data["quantity"] = str(quantity)

            result = await self._make_request("POST", "/positions/close", data=data)
            return result.get("success", False)

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False

    async def update_position_sl_tp(
        self,
        symbol: str,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
    ) -> bool:
        """Update position stop loss and take profit"""
        try:
            data = {"symbol": symbol}

            if stop_loss:
                data["stop_loss"] = str(stop_loss)
            if take_profit:
                data["take_profit"] = str(take_profit)

            result = await self._make_request("PUT", "/positions/sl-tp", data=data)
            return result.get("success", False)

        except Exception as e:
            logger.error(f"Error updating position SL/TP: {e}")
            return False

    # ============================================================================
    # Account Information
    # ============================================================================

    async def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get account information"""
        try:
            result = await self._make_request("GET", "/account")
            return result

        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None

    async def get_balance(self) -> Optional[Dict[str, Any]]:
        """Get account balance"""
        try:
            result = await self._make_request("GET", "/account/balance")
            return result

        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return None

    async def get_portfolio_summary(self) -> Optional[Dict[str, Any]]:
        """Get portfolio summary"""
        try:
            result = await self._make_request("GET", "/portfolio/summary")
            return result

        except Exception as e:
            logger.error(f"Error getting portfolio summary: {e}")
            return None

    # ============================================================================
    # Risk Management
    # ============================================================================

    async def get_risk_metrics(self) -> Optional[Dict[str, Any]]:
        """Get risk metrics"""
        try:
            result = await self._make_request("GET", "/risk/metrics")
            return result

        except Exception as e:
            logger.error(f"Error getting risk metrics: {e}")
            return None

    async def check_risk_limits(self, decision: TradingDecision) -> Dict[str, Any]:
        """Check if decision passes risk limits"""
        try:
            risk_data = {
                "symbol": decision.symbol,
                "action": decision.action,
                "quantity": str(decision.quantity) if decision.quantity else None,
                "entry_price": (
                    str(decision.entry_price) if decision.entry_price else None
                ),
                "stop_loss": str(decision.stop_loss) if decision.stop_loss else None,
                "confidence": str(decision.confidence),
            }

            # Remove None values
            risk_data = {k: v for k, v in risk_data.items() if v is not None}

            result = await self._make_request("POST", "/risk/check", data=risk_data)
            return result

        except Exception as e:
            logger.error(f"Error checking risk limits: {e}")
            return {"approved": False, "error": str(e)}

    # ============================================================================
    # Market Data
    # ============================================================================

    async def get_market_prices(self, symbols: List[str]) -> Dict[str, Decimal]:
        """Get current market prices for symbols"""
        try:
            params = {"symbols": ",".join(symbols)}
            result = await self._make_request("GET", "/market/prices", params=params)

            if isinstance(result, dict) and "prices" in result:
                # Convert string prices to Decimal
                prices = {}
                for symbol, price_str in result["prices"].items():
                    try:
                        prices[symbol] = Decimal(str(price_str))
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid price for {symbol}: {price_str}")
                        continue
                return prices
            else:
                return {}

        except Exception as e:
            logger.error(f"Error getting market prices: {e}")
            return {}

    async def get_trading_fees(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get trading fees for symbol"""
        try:
            result = await self._make_request("GET", f"/market/fees/{symbol}")
            return result

        except Exception as e:
            logger.error(f"Error getting trading fees: {e}")
            return None

    # ============================================================================
    # Health and Status
    # ============================================================================

    async def health_check(self) -> Dict[str, Any]:
        """Check router service health"""
        try:
            result = await self._make_request("GET", "/health")
            return result

        except Exception as e:
            logger.error(f"Router health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def get_service_status(self) -> Dict[str, Any]:
        """Get detailed service status"""
        try:
            result = await self._make_request("GET", "/status")
            return result

        except Exception as e:
            logger.error(f"Error getting service status: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    # ============================================================================
    # Utility Methods
    # ============================================================================

    async def test_connection(self) -> bool:
        """Test connection to router service"""
        try:
            health = await self.health_check()
            return health.get("status") == "healthy"

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def is_initialized(self) -> bool:
        """Check if client is initialized"""
        return self._initialized and self._session is not None

    # ============================================================================
    # Context Manager Support
    # ============================================================================

    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
