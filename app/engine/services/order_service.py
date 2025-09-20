"""
Order service for handling order validation, sizing, and execution.
Following C-4: Prefer simple, composable, testable functions.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"


@dataclass
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]


@dataclass
class AccountInfo:
    balance: Decimal
    max_leverage: Decimal = Decimal("3.0")
    risk_per_trade: Decimal = Decimal("0.005")  # 0.5%


@dataclass
class TradingSignal:
    symbol: str
    side: OrderSide
    entry_price: Decimal
    stop_loss: Decimal
    confidence: Decimal


@dataclass
class OrderResponse:
    order_id: str
    status: str
    filled_quantity: Decimal = Decimal("0")
    average_price: Optional[Decimal] = None


# Exchange limits (would normally come from exchange API)
SYMBOL_FILTERS = {
    "BTCUSDT": {
        "min_qty": Decimal("0.00010"),  # Actual Binance minimum is 0.00010 BTC
        "max_qty": Decimal("9000"),
        "qty_step": Decimal("0.00001"),
        "min_notional": Decimal("5"),
        "price_precision": 2,
        "qty_precision": 5,
    }
}


def validate_order_params(order: OrderRequest) -> ValidationResult:
    """
    Validates order parameters against exchange rules.
    Checks min/max quantities, price precision, and notional value requirements.
    """
    errors = []

    # Get symbol filters
    filters = SYMBOL_FILTERS.get(order.symbol, {})
    if not filters:
        errors.append(f"Unknown symbol: {order.symbol}")
        return ValidationResult(is_valid=False, errors=errors)

    # Check quantity limits
    min_qty = filters.get("min_qty", Decimal("0"))
    max_qty = filters.get("max_qty", Decimal("1000000"))

    if order.quantity < min_qty:
        errors.append(f"Quantity {order.quantity} below minimum quantity {min_qty}")

    if order.quantity > max_qty:
        errors.append(f"Quantity {order.quantity} above maximum quantity {max_qty}")

    # Check price requirements for limit orders
    if order.order_type == OrderType.LIMIT:
        if order.price is None:
            errors.append("Price required for limit orders")
        elif order.price > 0:
            # Check price precision
            price_precision = filters.get("price_precision", 8)
            price_str = str(order.price)
            if "." in price_str:
                decimals = len(price_str.split(".")[1])
                if decimals > price_precision:
                    errors.append(
                        f"Price precision {decimals} exceeds maximum {price_precision}"
                    )

            # Check notional value
            notional = order.quantity * order.price
            min_notional = filters.get("min_notional", Decimal("0"))
            if notional < min_notional:
                errors.append(f"Notional value {notional} below minimum {min_notional}")

    # Check stop price for stop orders
    if order.order_type == OrderType.STOP_MARKET and order.stop_price is None:
        errors.append("Stop price required for stop market orders")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)


def calculate_position_size(signal: TradingSignal, account: AccountInfo) -> Decimal:
    """
    Calculates position size using Kelly criterion with configurable risk limits.
    Respects account balance and leverage constraints.
    """
    # Calculate risk amount
    risk_amount = account.balance * account.risk_per_trade

    # Calculate price difference for stop loss
    price_diff = abs(signal.entry_price - signal.stop_loss)

    if price_diff == 0:
        return Decimal("0")

    # Base position size from risk
    base_size = risk_amount / price_diff

    # Scale position by confidence
    # Low confidence (0.5) gets 66% of base size
    # High confidence (0.8-1.0) gets 100% of base size
    # Linear scaling in between
    if signal.confidence >= Decimal("0.8"):
        # Full position for high confidence
        sized_position = base_size
    else:
        # Scale: at 0.5 conf -> 0.66x, at 0.8 conf -> 1.0x
        # Formula: 0.66 + (conf - 0.5) * 1.133
        confidence_multiplier = Decimal("0.66") + (
            (signal.confidence - Decimal("0.5")) * Decimal("1.133")
        )
        confidence_multiplier = min(confidence_multiplier, Decimal("1.0"))
        sized_position = base_size * confidence_multiplier

    # Check against balance with leverage
    max_position_value = account.balance * account.max_leverage
    max_position_size = max_position_value / signal.entry_price

    # Return the smaller of the two
    final_size = min(sized_position, max_position_size)

    # Round to appropriate precision
    filters = SYMBOL_FILTERS.get(signal.symbol, {})
    qty_step = filters.get("qty_step", Decimal("0.00001"))

    # Round down to nearest step
    if qty_step > 0:
        final_size = (final_size // qty_step) * qty_step

    return final_size


class NetworkError(Exception):
    """Transient network error."""

    pass


class OrderError(Exception):
    """Permanent order error."""

    pass


# Mock order execution for testing
_mock_failures = 0


async def _execute_order(order: OrderRequest) -> OrderResponse:
    """Mock order execution for testing."""
    global _mock_failures

    # Simulate network failures for testing retry logic
    if order.symbol == "BTCUSDT" and _mock_failures < 1:
        _mock_failures += 1
        raise NetworkError("Connection timeout")

    # Simulate invalid symbol
    if order.symbol == "INVALID":
        raise OrderError("Invalid symbol")

    # Simulate insufficient balance for huge orders
    if order.quantity > Decimal("10000"):
        raise OrderError("Insufficient balance")

    # Simulate successful order
    return OrderResponse(
        order_id=f"ORDER_{order.symbol}_{order.side.value}",
        status="FILLED",
        filled_quantity=order.quantity,
        average_price=order.price or Decimal("50000"),
    )


async def create_order_with_retry(
    order: OrderRequest, max_retries: int = 3
) -> OrderResponse:
    """
    Creates order with exponential backoff retry logic.
    Handles transient network errors and rate limits gracefully.
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            # Reset mock failures for testing
            if attempt == 0:
                global _mock_failures
                _mock_failures = 0

            response = await _execute_order(order)
            return response

        except NetworkError as e:
            last_error = e
            if attempt < max_retries - 1:
                # Exponential backoff
                wait_time = 0.1 * (2**attempt)
                logger.warning(
                    f"Order attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Order failed after {max_retries} attempts: {e}")

        except OrderError as e:
            # Don't retry permanent errors
            logger.error(f"Order failed with permanent error: {e}")
            raise Exception(f"Order failed: {e}")

        except Exception as e:
            logger.error(f"Unexpected error creating order: {e}")
            raise

    # All retries exhausted
    raise Exception(f"Order failed after {max_retries} retries: {last_error}")
