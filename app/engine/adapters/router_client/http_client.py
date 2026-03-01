"""
HTTP Router Client

HTTP client for communicating with the router service for order execution,
position management, and account operations.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import logging
from types import TracebackType
from typing import Any
from urllib.parse import urljoin

from aiohttp import ClientSession, ClientTimeout

from ...decision.idempotency import generate_client_order_id
from ...models import TradingDecision
from ...resilience.thread_safe_circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)

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

    def __init__(  # noqa: PLR0913
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 30,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        per_endpoint_breakers_config: dict[str, CircuitBreakerConfig] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay

        self._session: ClientSession | None = None
        self._initialized = False

        # Default circuit breaker config and per-endpoint breakers
        self._default_breaker_config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=2,
            timeout_seconds=60,
        )
        self._endpoint_breaker_cfgs = per_endpoint_breakers_config or {}
        self._breakers: dict[str, CircuitBreaker] = {}

        logger.info(f"RouterHTTPClient configured for {base_url}")

    async def initialize(self) -> None:
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

    async def close(self) -> None:
        """Close the HTTP client"""
        if self._session:
            await self._session.close()
            self._session = None

        self._initialized = False
        logger.info("Router HTTP client closed")

    def _ensure_initialized(self) -> None:
        """Ensure client is initialized"""
        if not self._initialized or not self._session:
            raise RuntimeError("Router HTTP client not initialized")

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers for requests"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "TradingEngine/1.0",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    def _breaker_key(self, method: str, endpoint: str) -> str:
        """Normalized breaker key: METHOD:/top-level-segment"""
        seg = endpoint.strip().lstrip("/").split("/", 1)[0]
        top = f"/{seg}" if seg else "/"
        return f"{method.upper()}:{top}"

    def _get_breaker_for(self, method: str, endpoint: str) -> CircuitBreaker:
        key = self._breaker_key(method, endpoint)
        br = self._breakers.get(key)
        if br is not None:
            return br
        cfg = self._endpoint_breaker_cfgs.get(key, self._default_breaker_config)
        br = CircuitBreaker(cfg)
        self._breakers[key] = br
        return br

    async def get_breaker_metrics(self) -> dict[str, dict[str, Any]]:
        """Return per-endpoint circuit breaker metrics for observability."""
        metrics: dict[str, dict[str, Any]] = {}
        for key, br in self._breakers.items():
            stats = await br.get_stats()
            state = await br.get_state()
            metrics[key] = {
                "state": state.name,
                "failure_count": stats.failure_count,
                "success_count": stats.success_count,
                "consecutive_failures": stats.consecutive_failures,
                "consecutive_successes": stats.consecutive_successes,
                "last_failure_time": (
                    stats.last_failure_time.isoformat() if stats.last_failure_time else None
                ),
                "last_success_time": (
                    stats.last_success_time.isoformat() if stats.last_success_time else None
                ),
            }
        return metrics

    async def _make_request(  # noqa: C901
        self,
        method: str,
        endpoint: str,
        data: dict[Any, Any] | None = None,
        params: dict[Any, Any] | None = None,
    ) -> dict[str, Any]:
        """Make HTTP request with retry logic"""
        self._ensure_initialized()

        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        headers = self._get_headers()

        # Circuit breaker pre-check (per-endpoint)
        breaker = self._get_breaker_for(method, endpoint)
        if not await breaker.should_allow_request():
            logger.error("Circuit breaker open for RouterHTTPClient")
            return {"error": "circuit_breaker_open", "status": 503}

        for attempt in range(self.retry_attempts):
            try:
                async with self._session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        payload = await response.json()
                        await breaker.record_success()
                        return payload
                    if response.status in (418, 429):
                        # Throttling or banned; do not count towards breaker failures
                        warn_text = await response.text()
                        logger.warning(
                            f"Throttled/banned ({response.status}) for {endpoint}: {warn_text}",
                        )
                        return {"error": "throttled", "status": response.status}
                    if response.status == 404:
                        logger.warning(f"Endpoint not found: {endpoint}")
                        await breaker.record_failure()
                        return {"error": "endpoint_not_found", "status": 404}
                    if response.status >= 400:
                        error_text = await response.text()
                        logger.error(f"HTTP {response.status} error: {error_text}")
                        await breaker.record_failure()
                        return {"error": error_text, "status": response.status}

            except TimeoutError:
                logger.warning(
                    f"Request timeout for {method} {endpoint} (attempt {attempt + 1})",
                )
                await breaker.record_failure()
                if attempt == self.retry_attempts - 1:
                    raise
                await asyncio.sleep(self.retry_delay * (attempt + 1))

            except Exception as e:
                logger.error(f"Request error for {method} {endpoint}: {e}")
                await breaker.record_failure()
                if attempt == self.retry_attempts - 1:
                    raise
                await asyncio.sleep(self.retry_delay * (attempt + 1))

        raise RuntimeError(
            f"Failed to complete request after {self.retry_attempts} attempts",
        )

    # ============================================================================
    # Order Management
    # ============================================================================

    async def place_order(self, decision: TradingDecision) -> dict[str, Any]:
        """Place a trading order based on decision"""
        try:
            client_order_id = generate_client_order_id(decision.decision_id, "entry")

            order_data = {
                "newClientOrderId": client_order_id,
                "symbol": decision.symbol,
                "side": decision.action,  # BUY/SELL
                "type": decision.order_type.value if decision.order_type else "MARKET",
                "quantity": str(decision.quantity) if decision.quantity else None,
                "price": str(decision.entry_price) if decision.entry_price else None,
                "stop_loss": str(decision.stop_loss) if decision.stop_loss else None,
                "take_profit": (str(decision.take_profit) if decision.take_profit else None),
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

    async def get_order_status(self, order_id: str) -> dict[str, Any] | None:
        """Get order status by ID"""
        try:
            result = await self._make_request("GET", f"/orders/{order_id}")
            return result

        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            return None

    async def place_bracket_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Place a bracket order via the router /place_bracket endpoint."""
        try:
            result = await self._make_request("POST", "/place_bracket", data=payload)
            logger.info("Placed bracket order for %s: %s", payload.get("symbol"), result)
            return result
        except Exception as e:
            logger.error("Error placing bracket order: %s", e)
            return {"error": str(e), "success": False}

    async def get_internal_equity(self, *, venue: str | None = None) -> tuple[Decimal, datetime]:
        """Fetch live equity snapshot from router.

        Returns:
            (equity_usd, timestamp)
        """
        params = {"venue": venue} if venue else None
        payload = await self._make_request("GET", "/internal/equity", params=params)

        equity_raw = payload.get("equity_usd")
        if equity_raw is None:
            raise ValueError("Router /internal/equity missing equity_usd")
        try:
            equity = Decimal(str(equity_raw))
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"Invalid equity_usd from router: {equity_raw}") from e

        ts_raw = payload.get("timestamp")
        if isinstance(ts_raw, str) and ts_raw:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
        else:
            ts = datetime.now(UTC)

        return equity, ts

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        try:
            result = await self._make_request("DELETE", f"/orders/{order_id}")
            return result.get("success", False)

        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            return False

    async def get_open_orders(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get open orders"""
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol

            result = await self._make_request("GET", "/orders/open", params=params)

            if isinstance(result, dict) and "orders" in result:
                return result["orders"]
            if isinstance(result, list):
                return result
            return []

        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []

    async def get_order_history(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get order history"""
        try:
            params: dict[str, Any] = {"limit": limit}
            if symbol:
                params["symbol"] = symbol

            result = await self._make_request("GET", "/orders/history", params=params)

            if isinstance(result, dict) and "orders" in result:
                return result["orders"]
            if isinstance(result, list):
                return result
            return []

        except Exception as e:
            logger.error(f"Error getting order history: {e}")
            return []

    # ============================================================================
    # Position Management
    # ============================================================================

    async def get_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Get current positions"""
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol

            result = await self._make_request("GET", "/positions", params=params)

            if isinstance(result, dict) and "positions" in result:
                return result["positions"]
            if isinstance(result, list):
                return result
            return []

        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    async def close_position(
        self,
        symbol: str,
        quantity: Decimal | None = None,
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
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
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

    async def get_account_info(self) -> dict[str, Any] | None:
        """Get account information"""
        try:
            result = await self._make_request("GET", "/account")
            return result

        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None

    async def get_balance(self) -> dict[str, Any] | None:
        """Get account balance"""
        try:
            result = await self._make_request("GET", "/account/balance")
            return result

        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return None

    async def get_portfolio_summary(self) -> dict[str, Any] | None:
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

    async def get_risk_metrics(self) -> dict[str, Any] | None:
        """Get risk metrics"""
        try:
            result = await self._make_request("GET", "/risk/metrics")
            return result

        except Exception as e:
            logger.error(f"Error getting risk metrics: {e}")
            return None

    async def check_risk_limits(self, decision: TradingDecision) -> dict[str, Any]:
        """Check if decision passes risk limits"""
        try:
            risk_data = {
                "symbol": decision.symbol,
                "action": decision.action,
                "quantity": str(decision.quantity) if decision.quantity else None,
                "entry_price": (str(decision.entry_price) if decision.entry_price else None),
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

    async def get_market_prices(self, symbols: list[str]) -> dict[str, Decimal]:
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
            return {}

        except Exception as e:
            logger.error(f"Error getting market prices: {e}")
            return {}

    async def get_trading_fees(self, symbol: str) -> dict[str, Any] | None:
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

    async def health_check(self) -> dict[str, Any]:
        """Check router service health"""
        try:
            result = await self._make_request("GET", "/healthz")
            return result

        except Exception as e:
            logger.error(f"Router health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def get_service_status(self) -> dict[str, Any]:
        """Get detailed service status"""
        try:
            result = await self._make_request("GET", "/status")
            return result

        except Exception as e:
            logger.error(f"Error getting service status: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
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

    async def __aenter__(self) -> None:
        """Async context manager entry"""
        await self.initialize()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit"""
        await self.close()
