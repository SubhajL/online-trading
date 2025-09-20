"""
Legacy adapter for converting between old and new data formats.
Following C-4: Prefer simple, composable, testable functions.
"""

import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.engine.services.order_service import (
    OrderRequest,
    OrderSide,
    OrderType,
    OrderResponse,
)
from app.engine.services.position_tracker import Position, PositionSide

logger = logging.getLogger(__name__)


def adapt_legacy_order_format(legacy_order: Dict[str, Any]) -> OrderRequest:
    """
    Converts legacy order dictionary format to new strongly-typed OrderRequest model.
    Validates required fields and handles type conversions.
    """
    # Validate required fields
    required_fields = ["symbol", "side", "quantity", "type"]
    missing_fields = [f for f in required_fields if f not in legacy_order]
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    # Convert side
    side_str = legacy_order["side"].upper()
    if side_str not in ["BUY", "SELL"]:
        raise ValueError(f"Invalid side: {side_str}")
    side = OrderSide.BUY if side_str == "BUY" else OrderSide.SELL

    # Convert order type
    type_str = legacy_order["type"].upper()
    try:
        order_type = OrderType[type_str]
    except KeyError:
        raise ValueError(f"Invalid order type: {type_str}")

    # Convert quantities and prices
    quantity = Decimal(str(legacy_order["quantity"]))
    price = (
        None
        if legacy_order.get("price") is None
        else Decimal(str(legacy_order["price"]))
    )
    stop_price = (
        None
        if legacy_order.get("stopPrice") is None
        else Decimal(str(legacy_order["stopPrice"]))
    )

    return OrderRequest(
        symbol=legacy_order["symbol"],
        side=side,
        quantity=quantity,
        order_type=order_type,
        price=price,
        stop_price=stop_price,
    )


def adapt_legacy_position_format(legacy_pos: Dict[str, Any]) -> Position:
    """
    Transforms legacy position representation to new Position model.
    Provides sensible defaults for missing optional fields.
    """
    # Required fields
    symbol = legacy_pos["symbol"]
    side_str = legacy_pos["side"].upper()
    side = PositionSide.LONG if side_str == "LONG" else PositionSide.SHORT
    quantity = Decimal(str(legacy_pos["quantity"]))
    entry_price = Decimal(str(legacy_pos["entryPrice"]))

    # Parse timestamp
    open_time_str = legacy_pos["openTime"]
    if isinstance(open_time_str, str):
        # Parse ISO format timestamp
        open_time = datetime.fromisoformat(open_time_str.replace("Z", "+00:00"))
    else:
        open_time = open_time_str

    # Optional fields with defaults
    realized_pnl = Decimal(str(legacy_pos.get("realizedPnl", "0")))
    total_commission = Decimal(str(legacy_pos.get("commission", "0")))
    stop_loss = (
        None
        if legacy_pos.get("stopLoss") is None
        else Decimal(str(legacy_pos["stopLoss"]))
    )
    take_profit = (
        None
        if legacy_pos.get("takeProfit") is None
        else Decimal(str(legacy_pos["takeProfit"]))
    )
    is_closed = legacy_pos.get("isClosed", False)

    # Parse close time if present
    close_time = None
    if legacy_pos.get("closeTime"):
        close_time_str = legacy_pos["closeTime"]
        if isinstance(close_time_str, str):
            close_time = datetime.fromisoformat(close_time_str.replace("Z", "+00:00"))
        else:
            close_time = close_time_str

    return Position(
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        realized_pnl=realized_pnl,
        total_commission=total_commission,
        open_time=open_time,
        stop_loss=stop_loss,
        take_profit=take_profit,
        is_closed=is_closed,
        close_time=close_time,
    )


def adapt_order_to_legacy_format(order: OrderRequest) -> Dict[str, Any]:
    """
    Converts new OrderRequest to legacy dictionary format.
    Used for backwards compatibility with existing systems.
    """
    return {
        "symbol": order.symbol,
        "side": order.side.value,
        "quantity": str(order.quantity),
        "type": order.order_type.value,
        "price": None if order.price is None else str(order.price),
        "stopPrice": None if order.stop_price is None else str(order.stop_price),
    }


def adapt_position_to_legacy_format(position: Position) -> Dict[str, Any]:
    """
    Converts new Position to legacy dictionary format.
    Used for backwards compatibility with existing systems.
    """
    legacy = {
        "symbol": position.symbol,
        "side": position.side.value,
        "quantity": str(position.quantity),
        "entryPrice": str(position.entry_price),
        "realizedPnl": str(position.realized_pnl),
        "commission": str(position.total_commission),
        "openTime": position.open_time.isoformat().replace("+00:00", "Z"),
        "isClosed": position.is_closed,
    }

    # Add optional fields if present
    if position.stop_loss is not None:
        legacy["stopLoss"] = str(position.stop_loss)
    if position.take_profit is not None:
        legacy["takeProfit"] = str(position.take_profit)
    if position.close_time is not None:
        legacy["closeTime"] = position.close_time.isoformat().replace("+00:00", "Z")

    return legacy


def adapt_order_response_to_legacy(response: OrderResponse) -> Dict[str, Any]:
    """
    Converts OrderResponse to legacy format.
    """
    return {
        "orderId": response.order_id,
        "status": response.status,
        "filledQuantity": str(response.filled_quantity),
        "averagePrice": None
        if response.average_price is None
        else str(response.average_price),
    }
