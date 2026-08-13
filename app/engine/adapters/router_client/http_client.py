"""
HTTP Router Client

HTTP client for communicating with the router service for order execution,
position management, and account operations.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import logging
from types import TracebackType
from typing import Any
from urllib.parse import urljoin

from aiohttp import ClientError, ClientSession, ClientTimeout

from ...decision.idempotency import generate_client_order_id
from ...models import TradingDecision
from ...resilience.thread_safe_circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)

logger = logging.getLogger(__name__)


class RouterError(RuntimeError):
    """Base failure returned by the live order router boundary."""


class RouterCircuitOpenError(RouterError):
    """The endpoint circuit is open and no request was attempted."""


class RouterTransportError(RouterError):
    """The transport failed before a trustworthy response was received."""


class RouterHTTPError(RouterError):
    """The router returned a non-success HTTP status."""

    def __init__(self, status: int, message: str):
        super().__init__(f"Router returned HTTP {status}: {message}")
        self.status = status

    @property
    def retryable(self) -> bool:
        return self.status == 429 or self.status >= 500


class RouterProtocolError(RouterError):
    """A successful HTTP response violated the placement contract."""


@dataclass(frozen=True)
class BracketClientOrderIDs:
    main: str
    take_profits: tuple[str, ...]
    stop_loss: str


@dataclass(frozen=True)
class BracketPlacementResult:
    bracket_order_id: str
    client_order_ids: BracketClientOrderIDs
    symbol: str
    side: str
    quantity: Decimal
    created_at: datetime
    partial_failure: bool
    errors: tuple[str, ...]
    legs_pending_trigger: bool
    stop_loss_limit_price: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bracket_order_id": self.bracket_order_id,
            "client_order_ids": {
                "main": self.client_order_ids.main,
                "take_profits": list(self.client_order_ids.take_profits),
                "stop_loss": self.client_order_ids.stop_loss,
            },
            "symbol": self.symbol,
            "side": self.side,
            "quantity": str(self.quantity),
            "created_at": self.created_at.isoformat(),
            "partial_failure": self.partial_failure,
            "errors": list(self.errors),
            "legs_pending_trigger": self.legs_pending_trigger,
            "stop_loss_limit_price": (
                str(self.stop_loss_limit_price) if self.stop_loss_limit_price is not None else None
            ),
        }


def _bounded_router_error_body(value: str, limit: int = 512) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _require_non_empty_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RouterProtocolError(f"Router placement response missing {field}")
    return value.strip()


def _parse_bracket_placement(payload: dict[str, Any]) -> BracketPlacementResult:
    bracket_order_id = _require_non_empty_string(payload, "bracket_order_id")
    symbol = _require_non_empty_string(payload, "symbol").upper()
    side = _require_non_empty_string(payload, "side").upper()

    raw_client_ids = payload.get("client_order_ids")
    if not isinstance(raw_client_ids, dict):
        raise RouterProtocolError("Router placement response missing client_order_ids")
    main = _require_non_empty_string(raw_client_ids, "main")
    stop_loss = _require_non_empty_string(raw_client_ids, "stop_loss")
    raw_take_profits = raw_client_ids.get("take_profits")
    if not isinstance(raw_take_profits, list) or not raw_take_profits:
        raise RouterProtocolError("Router placement response missing take-profit client IDs")
    if not all(isinstance(value, str) and value.strip() for value in raw_take_profits):
        raise RouterProtocolError("Router placement response has invalid take-profit client IDs")

    try:
        quantity = Decimal(str(payload["quantity"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise RouterProtocolError("Router placement response has invalid quantity") from exc
    if not quantity.is_finite() or quantity <= 0:
        raise RouterProtocolError("Router placement response quantity must be positive")

    created_at_raw = payload.get("created_at")
    if not isinstance(created_at_raw, str) or not created_at_raw:
        raise RouterProtocolError("Router placement response missing created_at")
    try:
        created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RouterProtocolError("Router placement response has invalid created_at") from exc
    if created_at.tzinfo is None:
        raise RouterProtocolError("Router placement response created_at must include a timezone")

    partial_failure = payload.get("partial_failure")
    legs_pending_trigger = payload.get("legs_pending_trigger")
    if not isinstance(partial_failure, bool) or not isinstance(legs_pending_trigger, bool):
        raise RouterProtocolError("Router placement response has invalid boolean fields")
    raw_errors = payload.get("errors")
    if not isinstance(raw_errors, list) or not all(isinstance(value, str) for value in raw_errors):
        raise RouterProtocolError("Router placement response has invalid errors")

    stop_loss_limit_price: Decimal | None = None
    stop_loss_limit_raw = payload.get("stop_loss_limit_price")
    if stop_loss_limit_raw not in (None, ""):
        try:
            stop_loss_limit_price = Decimal(str(stop_loss_limit_raw))
        except (ValueError, TypeError) as exc:
            raise RouterProtocolError(
                "Router placement response has invalid stop_loss_limit_price"
            ) from exc

    return BracketPlacementResult(
        bracket_order_id=bracket_order_id,
        client_order_ids=BracketClientOrderIDs(
            main=main,
            take_profits=tuple(value.strip() for value in raw_take_profits),
            stop_loss=stop_loss,
        ),
        symbol=symbol,
        side=side,
        quantity=quantity,
        created_at=created_at,
        partial_failure=partial_failure,
        errors=tuple(raw_errors),
        legs_pending_trigger=legs_pending_trigger,
        stop_loss_limit_price=stop_loss_limit_price,
    )


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
        retry_transport: bool = True,
    ) -> dict[str, Any]:
        """Make an HTTP request and return a JSON object for any 2xx response."""
        self._ensure_initialized()

        url = urljoin(self.base_url + "/", endpoint.lstrip("/"))
        headers = self._get_headers()

        # Circuit breaker pre-check (per-endpoint)
        breaker = self._get_breaker_for(method, endpoint)
        if not await breaker.should_allow_request():
            logger.error("Circuit breaker open for RouterHTTPClient")
            raise RouterCircuitOpenError(f"Router circuit is open for {method.upper()} {endpoint}")

        attempts = self.retry_attempts if retry_transport else 1
        for attempt in range(attempts):
            try:
                async with self._session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    headers=headers,
                ) as response:
                    if 200 <= response.status < 300:
                        try:
                            payload = await response.json()
                        except Exception as exc:
                            await breaker.record_failure()
                            raise RouterProtocolError(
                                f"Router returned non-JSON {response.status} for {endpoint}"
                            ) from exc
                        if not isinstance(payload, dict):
                            await breaker.record_failure()
                            raise RouterProtocolError(
                                f"Router returned non-object {response.status} for {endpoint}"
                            )
                        await breaker.record_success()
                        return payload
                    error_text = _bounded_router_error_body(await response.text())
                    if response.status not in (418, 429):
                        await breaker.record_failure()
                    raise RouterHTTPError(response.status, error_text or "empty response body")

            except (RouterHTTPError, RouterProtocolError):
                raise
            except (TimeoutError, ClientError) as exc:
                logger.warning(
                    f"Request timeout for {method} {endpoint} (attempt {attempt + 1})",
                )
                await breaker.record_failure()
                if attempt == attempts - 1:
                    raise RouterTransportError(
                        f"Router transport failed for {method.upper()} {endpoint}: {exc}"
                    ) from exc
                await asyncio.sleep(self.retry_delay * (attempt + 1))

            except Exception as e:
                logger.error(f"Request error for {method} {endpoint}: {e}")
                await breaker.record_failure()
                if attempt == attempts - 1:
                    raise RouterTransportError(
                        f"Router transport failed for {method.upper()} {endpoint}: {e}"
                    ) from e
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

    async def place_bracket_order(self, payload: dict[str, Any]) -> BracketPlacementResult:
        """Place a bracket order via the router /place_bracket endpoint."""
        response = await self._make_request(
            "POST",
            "/place_bracket",
            data=payload,
            retry_transport=False,
        )
        result = _parse_bracket_placement(response)
        logger.info(
            "Placed bracket order for %s: %s",
            payload.get("symbol"),
            result.bracket_order_id,
        )
        return result

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
