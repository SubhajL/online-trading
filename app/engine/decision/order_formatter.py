"""
Order formatter for exchange compatibility.

Ensures all orders meet exchange requirements:
- Price rounded to tick size
- Quantity rounded to step size
- Minimum notional value met
- Values within min/max bounds
"""

from dataclasses import dataclass
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExchangeInfo:
    """Exchange trading rules for a symbol."""

    symbol: str
    base_asset: str
    quote_asset: str

    # Price constraints
    price_tick_size: Decimal
    price_min: Decimal
    price_max: Decimal

    # Quantity constraints
    qty_step_size: Decimal
    qty_min: Decimal
    qty_max: Decimal

    # Minimum order value
    min_notional: Decimal

    # Optional futures-specific
    contract_size: Decimal | None = None
    max_leverage: int | None = None


class OrderFormatter:
    """Formats orders to meet exchange requirements."""

    def __init__(self, exchange_info: dict[str, ExchangeInfo]):
        self.exchange_info = exchange_info

    def round_price(self, symbol: str, price: Decimal) -> Decimal:
        """Round price down to nearest tick size."""
        if symbol not in self.exchange_info:
            raise ValueError(f"Unknown symbol: {symbol}")

        info = self.exchange_info[symbol]
        if info.price_tick_size.is_zero():
            return price

        # Round down to nearest tick
        quotient = price / info.price_tick_size
        rounded = quotient.to_integral_value(rounding="ROUND_DOWN")
        return rounded * info.price_tick_size

    def round_quantity(self, symbol: str, quantity: Decimal) -> Decimal:
        """Round quantity down to nearest step size."""
        if symbol not in self.exchange_info:
            raise ValueError(f"Unknown symbol: {symbol}")

        info = self.exchange_info[symbol]
        if info.qty_step_size.is_zero():
            return quantity

        # Round down to nearest step
        quotient = quantity / info.qty_step_size
        rounded = quotient.to_integral_value(rounding="ROUND_DOWN")
        return rounded * info.qty_step_size

    def validate_price(self, symbol: str, price: Decimal) -> tuple[bool, str]:
        """Validate price is within bounds."""
        if symbol not in self.exchange_info:
            return False, f"Unknown symbol: {symbol}"

        info = self.exchange_info[symbol]

        if price < info.price_min:
            return False, f"Price {price} below minimum {info.price_min}"

        if price > info.price_max:
            return False, f"Price {price} above maximum {info.price_max}"

        # Check tick size precision
        if not info.price_tick_size.is_zero():
            remainder = price % info.price_tick_size
            if not remainder.is_zero():
                return (
                    False,
                    f"Price {price} not aligned to tick size {info.price_tick_size}",
                )

        return True, "Price valid"

    def validate_quantity(self, symbol: str, quantity: Decimal) -> tuple[bool, str]:
        """Validate quantity is within bounds."""
        if symbol not in self.exchange_info:
            return False, f"Unknown symbol: {symbol}"

        info = self.exchange_info[symbol]

        if quantity < info.qty_min:
            return False, f"Quantity {quantity} below minimum {info.qty_min}"

        if quantity > info.qty_max:
            return False, f"Quantity {quantity} above maximum {info.qty_max}"

        # Check step size precision
        if not info.qty_step_size.is_zero():
            remainder = quantity % info.qty_step_size
            if not remainder.is_zero():
                return (
                    False,
                    f"Quantity {quantity} not aligned to step size {info.qty_step_size}",
                )

        return True, "Quantity valid"

    def validate_notional(
        self,
        symbol: str,
        price: Decimal,
        quantity: Decimal,
    ) -> tuple[bool, str]:
        """Validate order meets minimum notional value."""
        if symbol not in self.exchange_info:
            return False, f"Unknown symbol: {symbol}"

        info = self.exchange_info[symbol]
        notional = price * quantity

        if notional < info.min_notional:
            return False, f"Notional {notional} below minimum {info.min_notional}"

        return True, f"Notional {notional} valid"

    def adjust_quantity_for_notional(
        self,
        symbol: str,
        price: Decimal,
        quantity: Decimal,
    ) -> Decimal:
        """Adjust quantity up to meet minimum notional if needed."""
        if symbol not in self.exchange_info:
            raise ValueError(f"Unknown symbol: {symbol}")

        info = self.exchange_info[symbol]
        notional = price * quantity

        if notional < info.min_notional:
            # Calculate minimum quantity needed
            min_qty_for_notional = info.min_notional / price
            # Round up to step size
            quotient = min_qty_for_notional / info.qty_step_size
            rounded_up = quotient.to_integral_value(rounding="ROUND_UP")
            adjusted_qty = rounded_up * info.qty_step_size

            # Ensure we don't exceed max quantity
            return min(adjusted_qty, info.qty_max)

        return quantity

    def format_order(self, order: dict) -> dict:
        """Format a complete order to meet exchange requirements."""
        symbol = order["symbol"]

        # Round price and quantity
        formatted = order.copy()

        if order.get("price"):
            formatted["price"] = self.round_price(symbol, order["price"])

        if order.get("quantity"):
            formatted["quantity"] = self.round_quantity(symbol, order["quantity"])

        if order.get("stop_loss"):
            formatted["stop_loss"] = self.round_price(symbol, order["stop_loss"])

        if order.get("take_profit"):
            formatted["take_profit"] = self.round_price(symbol, order["take_profit"])

        # Adjust quantity for min notional if needed (only for limit orders)
        if order.get("type") == "LIMIT" and "price" in formatted and "quantity" in formatted:
            adjusted_qty = self.adjust_quantity_for_notional(
                symbol,
                formatted["price"],
                formatted["quantity"],
            )
            if adjusted_qty != formatted["quantity"]:
                logger.info(
                    f"Adjusted quantity from {formatted['quantity']} to {adjusted_qty} for min notional",
                )
                formatted["quantity"] = adjusted_qty

        return formatted

    def format_futures_order(self, order: dict) -> dict:
        """Format a futures order with leverage."""
        # Start with standard formatting
        formatted = self.format_order(order)

        # Add futures-specific fields
        if "leverage" in order:
            formatted["leverage"] = order["leverage"]

        if "reduce_only" in order:
            formatted["reduce_only"] = order["reduce_only"]

        return formatted

    def validate_order(self, order: dict) -> tuple[bool, list]:
        """Validate complete order meets all exchange requirements."""
        errors = []
        symbol = order.get("symbol")

        if not symbol:
            errors.append("Missing symbol")
            return False, errors

        # Validate price (for limit orders)
        if order.get("type") == "LIMIT" and "price" in order:
            is_valid, reason = self.validate_price(symbol, order["price"])
            if not is_valid:
                errors.append(f"Price: {reason}")

        # Validate quantity
        if "quantity" in order:
            is_valid, reason = self.validate_quantity(symbol, order["quantity"])
            if not is_valid:
                errors.append(f"Quantity: {reason}")

        # Validate notional (for limit orders)
        if order.get("type") == "LIMIT" and "price" in order and "quantity" in order:
            is_valid, reason = self.validate_notional(
                symbol,
                order["price"],
                order["quantity"],
            )
            if not is_valid:
                errors.append(f"Notional: {reason}")

        # Validate stop loss
        if order.get("stop_loss"):
            is_valid, reason = self.validate_price(symbol, order["stop_loss"])
            if not is_valid:
                errors.append(f"Stop loss: {reason}")

        # Validate take profit
        if order.get("take_profit"):
            is_valid, reason = self.validate_price(symbol, order["take_profit"])
            if not is_valid:
                errors.append(f"Take profit: {reason}")

        return len(errors) == 0, errors

    def get_min_order_size(self, symbol: str, price: Decimal) -> Decimal:
        """Get minimum order size for a symbol at given price."""
        if symbol not in self.exchange_info:
            raise ValueError(f"Unknown symbol: {symbol}")

        info = self.exchange_info[symbol]

        # Minimum from quantity constraint
        min_from_qty = info.qty_min

        # Minimum from notional constraint
        min_from_notional = info.min_notional / price

        # Take the larger and round up to step size
        min_required = max(min_from_qty, min_from_notional)

        quotient = min_required / info.qty_step_size
        rounded_up = quotient.to_integral_value(rounding="ROUND_UP")
        return rounded_up * info.qty_step_size
