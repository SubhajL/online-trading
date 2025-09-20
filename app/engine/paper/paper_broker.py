"""
Paper trading broker for simulation.
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import uuid4

from ..types import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TradingDecision,
    OrderFilledEvent,
    PositionUpdateEvent,
    EventType,
)
from ..bus import EventBus


class PaperBroker:
    """
    Paper trading broker that simulates order execution.
    """

    def __init__(
        self, event_bus: EventBus, initial_balance: Decimal = Decimal("10000")
    ):
        self.event_bus = event_bus
        self.balance = initial_balance
        self.available_balance = initial_balance
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        self.order_history: List[Order] = []

        # Simulation parameters
        self.market_slippage_pct = Decimal("0.001")  # 0.1%
        self.limit_fill_probability = 0.95
        self.maker_fee_pct = Decimal("0.001")  # 0.1%
        self.taker_fee_pct = Decimal("0.001")  # 0.1%

    async def place_order(self, decision: TradingDecision) -> Order:
        """
        Place a paper order based on trading decision.
        """
        order = Order(
            client_order_id=f"paper_{uuid4().hex[:8]}",
            symbol=decision.symbol,
            side=OrderSide.BUY if decision.action == "BUY" else OrderSide.SELL,
            type=decision.order_type or OrderType.MARKET,
            quantity=decision.quantity or Decimal("0"),
            price=decision.entry_price,
            stop_price=decision.stop_loss,
            status=OrderStatus.NEW,
            created_at=datetime.utcnow(),
            decision_id=decision.decision_id,
        )

        self.orders[order.client_order_id] = order

        # Simulate immediate market order fill
        if order.type == OrderType.MARKET:
            await self._fill_market_order(order)

        return order

    async def _fill_market_order(self, order: Order):
        """
        Simulate market order fill with slippage.
        """
        # Apply slippage
        if order.side == OrderSide.BUY:
            fill_price = order.price * (Decimal("1") + self.market_slippage_pct)
        else:
            fill_price = order.price * (Decimal("1") - self.market_slippage_pct)

        # Calculate fees
        fee = order.quantity * fill_price * self.taker_fee_pct

        # Update balance
        if order.side == OrderSide.BUY:
            cost = order.quantity * fill_price + fee
            if cost > self.available_balance:
                order.status = OrderStatus.REJECTED
                return
            self.available_balance -= cost
        else:
            proceeds = order.quantity * fill_price - fee
            self.available_balance += proceeds

        # Update order
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.average_fill_price = fill_price
        order.updated_at = datetime.utcnow()

        # Update or create position
        await self._update_position(order, fill_price)

        # Emit fill event
        await self.event_bus.publish(
            OrderFilledEvent(
                event_type=EventType.ORDER_FILLED,
                timestamp=datetime.utcnow(),
                symbol=order.symbol,
                order=order,
                fill_price=fill_price,
                fill_quantity=order.quantity,
                fill_timestamp=datetime.utcnow(),
            )
        )

        self.order_history.append(order)

    async def _update_position(self, order: Order, fill_price: Decimal):
        """
        Update position based on filled order.
        """
        symbol = order.symbol

        if symbol not in self.positions:
            # Create new position
            self.positions[symbol] = Position(
                symbol=symbol,
                side=order.side,
                size=order.filled_quantity,
                entry_price=fill_price,
                current_price=fill_price,
                unrealized_pnl=Decimal("0"),
                margin_used=order.filled_quantity * fill_price,
                opened_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                decision_id=order.decision_id,
            )
        else:
            position = self.positions[symbol]

            if order.side == position.side:
                # Add to position
                total_cost = (
                    position.size * position.entry_price
                    + order.filled_quantity * fill_price
                )
                position.size += order.filled_quantity
                position.entry_price = total_cost / position.size
            else:
                # Reduce or close position
                if order.filled_quantity >= position.size:
                    # Close position
                    pnl = self._calculate_pnl(position, fill_price)
                    position.realized_pnl += pnl
                    del self.positions[symbol]
                    return
                else:
                    # Partial close
                    partial_pnl = self._calculate_pnl(
                        position, fill_price, order.filled_quantity
                    )
                    position.realized_pnl += partial_pnl
                    position.size -= order.filled_quantity

            position.updated_at = datetime.utcnow()

        # Emit position update
        if symbol in self.positions:
            await self.event_bus.publish(
                PositionUpdateEvent(
                    event_type=EventType.POSITION_UPDATE,
                    timestamp=datetime.utcnow(),
                    symbol=symbol,
                    position=self.positions[symbol],
                )
            )

    def _calculate_pnl(
        self, position: Position, price: Decimal, quantity: Optional[Decimal] = None
    ) -> Decimal:
        """
        Calculate P&L for a position.
        """
        qty = quantity or position.size

        if position.side == OrderSide.BUY:
            return qty * (price - position.entry_price)
        else:
            return qty * (position.entry_price - price)

    async def update_market_prices(self, prices: Dict[str, Decimal]):
        """
        Update market prices and calculate unrealized P&L.
        """
        for symbol, price in prices.items():
            if symbol in self.positions:
                position = self.positions[symbol]
                position.current_price = price
                position.unrealized_pnl = self._calculate_pnl(position, price)
                position.updated_at = datetime.utcnow()

    def get_account_summary(self) -> Dict:
        """
        Get account summary including balance and positions.
        """
        total_unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        total_realized_pnl = sum(p.realized_pnl for p in self.positions.values())

        return {
            "balance": self.balance,
            "available_balance": self.available_balance,
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_realized_pnl": total_realized_pnl,
            "equity": self.balance + total_unrealized_pnl + total_realized_pnl,
            "positions": len(self.positions),
            "open_orders": len(
                [o for o in self.orders.values() if o.status == OrderStatus.NEW]
            ),
        }

    async def cancel_order(self, client_order_id: str) -> bool:
        """
        Cancel a paper order.
        """
        if client_order_id in self.orders:
            order = self.orders[client_order_id]
            if order.status == OrderStatus.NEW:
                order.status = OrderStatus.CANCELED
                order.updated_at = datetime.utcnow()
                return True
        return False

    async def close_all_positions(self):
        """
        Close all open positions at market.
        """
        for symbol, position in list(self.positions.items()):
            # Create opposite order to close
            close_order = Order(
                client_order_id=f"close_{uuid4().hex[:8]}",
                symbol=symbol,
                side=(
                    OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY
                ),
                type=OrderType.MARKET,
                quantity=position.size,
                price=position.current_price,
                status=OrderStatus.NEW,
                created_at=datetime.utcnow(),
            )

            await self._fill_market_order(close_order)
