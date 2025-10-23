"""
Paper Broker - Live trading simulation with same API as Go Router

This module provides a paper trading broker that:
1. Exposes the same HTTP API as the Go router (/place_bracket, /cancel, /close_all)
2. Simulates realistic order fills using live market data
3. Uses the same cost and slippage modeling as backtesting
4. Stores orders/positions in database for persistence
5. Publishes order_update.v1 events like live trading
"""

from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any
import uuid

import asyncpg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_serializer

from ..backtest.costs import CostCalculator
from ..backtest.fills import FillEngine
from ..backtest.types import (
    BacktestFill,
    BacktestOrder,
    FillReason,
    OrderSide,
    OrderStatus,
    OrderType,
)
from ..models import Candle

logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models (Same as Go Router)
# ============================================================================


class PlaceBracketRequest(BaseModel):
    symbol: str
    side: str  # BUY or SELL
    quantity: Decimal
    entry_price: Decimal = Field(default=Decimal(0))
    take_profit_prices: list[Decimal]
    stop_loss_price: Decimal
    order_type: str = "MARKET"  # LIMIT or MARKET
    is_futures: bool = False


class ClientOrderIDs(BaseModel):
    main: str
    take_profits: list[str]
    stop_loss: str


class PlaceBracketResponse(BaseModel):
    bracket_order_id: str
    client_order_ids: ClientOrderIDs
    symbol: str
    side: str
    quantity: Decimal
    created_at: datetime
    partial_failure: bool = False
    errors: list[str] = []

    @field_serializer("quantity")
    def _ser_qty(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("created_at")
    def _ser_created(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()


class CancelRequest(BaseModel):
    symbol: str
    order_id: int | None = None
    client_order_id: str | None = None


class CloseAllRequest(BaseModel):
    symbol: str | None = None
    is_futures: bool = False


class OrderUpdate(BaseModel):
    """Order update event for publishing"""

    event_type: str
    symbol: str
    order_id: int
    client_order_id: str
    status: str
    side: str
    order_type: str
    price: Decimal
    quantity: Decimal
    executed_qty: Decimal
    update_time: datetime
    reason: str | None = None

    @field_serializer("price", "quantity", "executed_qty")
    def _ser_decimals(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("update_time")
    def _ser_update_time(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()


# ============================================================================
# Paper Position Tracker
# ============================================================================


class PaperPosition:
    """Paper trading position tracker"""

    def __init__(self, symbol: str, is_futures: bool = False):
        self.symbol = symbol
        self.is_futures = is_futures
        self.net_quantity = Decimal(0)  # Positive = long, negative = short
        self.avg_entry_price = Decimal(0)
        self.unrealized_pnl = Decimal(0)
        self.total_fees = Decimal(0)
        self.total_funding = Decimal(0)
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def update_position(self, fill: BacktestFill, current_price: Decimal):
        """Update position with new fill"""
        fill_qty = fill.quantity if fill.order.side == OrderSide.BUY else -fill.quantity

        if self.net_quantity.is_zero():
            # Opening new position
            self.net_quantity = fill_qty
            self.avg_entry_price = fill.price
        elif (self.net_quantity > 0 and fill_qty > 0) or (
            self.net_quantity < 0 and fill_qty < 0
        ):
            # Adding to position
            total_value = (self.net_quantity * self.avg_entry_price) + (
                fill_qty * fill.price
            )
            self.net_quantity += fill_qty
            if not self.net_quantity.is_zero():
                self.avg_entry_price = total_value / self.net_quantity
        else:
            # Reducing or closing position
            self.net_quantity += fill_qty
            if self.net_quantity.is_zero():
                self.avg_entry_price = Decimal(0)

        # Update fees
        self.total_fees += fill.fee

        # Update unrealized PnL
        if not self.net_quantity.is_zero():
            if self.net_quantity > 0:
                self.unrealized_pnl = (
                    current_price - self.avg_entry_price
                ) * self.net_quantity
            else:
                self.unrealized_pnl = (self.avg_entry_price - current_price) * abs(
                    self.net_quantity,
                )
        else:
            self.unrealized_pnl = Decimal(0)

        self.updated_at = datetime.now(UTC)


# ============================================================================
# Paper Broker Core
# ============================================================================


class PaperBroker:
    """
    Paper trading broker with same API as Go router.

    Simulates live trading by:
    - Processing bracket orders with realistic fills
    - Managing paper positions
    - Publishing order update events
    - Storing state in database
    """

    def __init__(
        self,
        database_url: str,
        cost_calculator: CostCalculator | None = None,
        fill_engine: FillEngine | None = None,
        event_publisher: Any | None = None,  # Event bus for publishing order updates
    ):
        self.database_url = database_url
        self.cost_calculator = cost_calculator or CostCalculator()
        self.fill_engine = fill_engine or FillEngine()
        self.event_publisher = event_publisher

        # In-memory state
        self.active_orders: dict[str, BacktestOrder] = {}  # client_order_id -> order
        self.positions: dict[str, PaperPosition] = {}  # symbol -> position
        self.bracket_orders: dict[str, list[str]] = {}  # bracket_id -> [order_ids]

        # Database pool
        self.db_pool: asyncpg.Pool | None = None

        # Current market data cache
        self.current_prices: dict[str, Decimal] = {}
        self.latest_candles: dict[str, Candle] = {}

        logger.info("Paper broker initialized")

    async def initialize(self):
        """Initialize database connection and load state"""
        self.db_pool = await asyncpg.create_pool(
            self.database_url, min_size=2, max_size=10,
        )
        await self._load_state_from_db()
        logger.info("Paper broker database initialized")

    async def close(self):
        """Close database connections"""
        if self.db_pool:
            await self.db_pool.close()
        logger.info("Paper broker closed")

    async def _load_state_from_db(self):
        """Load active orders and positions from database"""
        async with self.db_pool.acquire() as conn:
            # Load active orders
            orders = await conn.fetch("""
                SELECT * FROM paper_orders
                WHERE status IN ('PENDING', 'PARTIALLY_FILLED')
                ORDER BY created_at
            """)

            for order_row in orders:
                order = self._order_from_db_row(order_row)
                self.active_orders[order.client_order_id] = order

            # Load positions
            positions = await conn.fetch("""
                SELECT * FROM paper_positions
                WHERE abs(net_quantity) > 0
            """)

            for pos_row in positions:
                position = PaperPosition(pos_row["symbol"], pos_row["is_futures"])
                position.net_quantity = pos_row["net_quantity"]
                position.avg_entry_price = pos_row["avg_entry_price"]
                position.unrealized_pnl = pos_row["unrealized_pnl"]
                position.total_fees = pos_row["total_fees"]
                position.total_funding = pos_row["total_funding"]
                position.created_at = pos_row["created_at"]
                position.updated_at = pos_row["updated_at"]

                self.positions[pos_row["symbol"]] = position

        logger.info(
            f"Loaded {len(self.active_orders)} orders and {len(self.positions)} positions",
        )

    def _order_from_db_row(self, row) -> BacktestOrder:
        """Convert database row to BacktestOrder"""
        return BacktestOrder(
            id=row["id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            type=OrderType(row["type"]),
            quantity=row["quantity"],
            price=row["price"] if row["price"] else Decimal(0),
            stop_price=row["stop_price"] if row["stop_price"] else Decimal(0),
            client_order_id=row["client_order_id"],
            status=OrderStatus(row["status"]),
            created_at=row["created_at"],
            bracket_order_id=row["bracket_order_id"],
        )

    async def update_market_data(self, candle: Candle):
        """Update with latest candle for fill simulation"""
        self.latest_candles[candle.symbol] = candle
        self.current_prices[candle.symbol] = candle.close_price

        # Check for fills on existing orders
        await self._process_pending_fills(candle)

    async def _process_pending_fills(self, candle: Candle):
        """Check if any pending orders can be filled with this candle"""
        symbol_orders = [
            o
            for o in self.active_orders.values()
            if o.symbol == candle.symbol and o.status == OrderStatus.PENDING
        ]

        for order in symbol_orders:
            if self.fill_engine.can_fill_order(order, candle):
                await self._execute_fill(order, candle)

    async def _execute_fill(self, order: BacktestOrder, candle: Candle):
        """Execute a fill for an order"""
        fill_price = self.fill_engine.get_fill_price(order, candle)

        # Calculate costs
        notional = order.quantity * fill_price
        fee = self.cost_calculator.calculate_trading_fee(
            notional,
            is_futures=order.symbol.endswith("USDT") and "PERP" in order.symbol,
            is_maker=(order.type == OrderType.LIMIT),
        )
        slippage = self.cost_calculator.calculate_slippage(
            order.quantity, candle.volume,
        )

        # Create fill
        fill = BacktestFill(
            order=order,
            quantity=order.quantity,
            price=fill_price,
            fee=fee,
            slippage=slippage,
            timestamp=candle.open_time,
            reason=FillReason.MARKET_ORDER
            if order.type == OrderType.MARKET
            else FillReason.LIMIT_TOUCHED,
        )

        # Update order status
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.fill_price = fill_price
        order.updated_at = datetime.now(UTC)

        # Update position
        if order.symbol not in self.positions:
            self.positions[order.symbol] = PaperPosition(
                order.symbol, is_futures=order.symbol.endswith("USDT"),
            )

        self.positions[order.symbol].update_position(fill, candle.close_price)

        # Save to database
        await self._save_fill_to_db(fill)
        await self._update_order_in_db(order)
        await self._update_position_in_db(self.positions[order.symbol])

        # Publish order update event
        await self._publish_order_update(order, "FILLED")

        # Remove from active orders
        del self.active_orders[order.client_order_id]

        logger.info(
            f"Filled order {order.client_order_id}: {order.quantity} {order.symbol} @ {fill_price}",
        )

    async def _save_fill_to_db(self, fill: BacktestFill):
        """Save fill to database"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO paper_fills (
                    id, order_id, symbol, side, quantity, price,
                    fee, slippage, timestamp, reason
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
                fill.id,
                fill.order.id,
                fill.order.symbol,
                fill.order.side.value,
                fill.quantity,
                fill.price,
                fill.fee,
                fill.slippage,
                fill.timestamp,
                fill.reason.value,
            )

    async def _update_order_in_db(self, order: BacktestOrder):
        """Update order in database"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE paper_orders SET
                    status = $2, filled_quantity = $3, fill_price = $4, updated_at = $5
                WHERE id = $1
            """,
                order.id,
                order.status.value,
                order.filled_quantity,
                order.fill_price,
                order.updated_at,
            )

    async def _update_position_in_db(self, position: PaperPosition):
        """Update position in database"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO paper_positions (
                    symbol, is_futures, net_quantity, avg_entry_price,
                    unrealized_pnl, total_fees, total_funding, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (symbol) DO UPDATE SET
                    net_quantity = $3, avg_entry_price = $4, unrealized_pnl = $5,
                    total_fees = $6, total_funding = $7, updated_at = $9
            """,
                position.symbol,
                position.is_futures,
                position.net_quantity,
                position.avg_entry_price,
                position.unrealized_pnl,
                position.total_fees,
                position.total_funding,
                position.created_at,
                position.updated_at,
            )

    async def _publish_order_update(self, order: BacktestOrder, event_type: str):
        """Publish order update event"""
        if not self.event_publisher:
            return

        update = OrderUpdate(
            event_type=event_type,
            symbol=order.symbol,
            order_id=hash(order.id) % 1000000,  # Convert UUID to int
            client_order_id=order.client_order_id,
            status=order.status.value,
            side=order.side.value,
            order_type=order.type.value,
            price=order.price,
            quantity=order.quantity,
            executed_qty=order.filled_quantity,
            update_time=order.updated_at,
            reason=None,
        )

        # Publish via event bus
        await self.event_publisher.publish("order_update.v1", update.dict())

    # ============================================================================
    # API Endpoints (Same as Go Router)
    # ============================================================================

    async def place_bracket_order(
        self, request: PlaceBracketRequest,
    ) -> PlaceBracketResponse:
        """Place bracket order with entry, TPs, and SL"""
        bracket_id = str(uuid.uuid4())
        client_order_ids = ClientOrderIDs(
            main=f"paper_{uuid.uuid4().hex[:8]}",
            take_profits=[
                f"paper_tp_{i}_{uuid.uuid4().hex[:8]}"
                for i in range(len(request.take_profit_prices))
            ],
            stop_loss=f"paper_sl_{uuid.uuid4().hex[:8]}",
        )

        orders = []
        errors = []

        try:
            # 1. Entry order
            entry_order = BacktestOrder(
                symbol=request.symbol,
                side=OrderSide(request.side),
                type=OrderType.MARKET
                if request.order_type == "MARKET"
                else OrderType.LIMIT,
                quantity=request.quantity,
                price=request.entry_price
                if request.order_type == "LIMIT"
                else Decimal(0),
                client_order_id=client_order_ids.main,
                bracket_order_id=bracket_id,
                status=OrderStatus.PENDING,
                created_at=datetime.now(UTC),
            )
            orders.append(entry_order)

            # 2. Take profit orders (OCO with entry)
            for i, tp_price in enumerate(request.take_profit_prices):
                tp_side = OrderSide.SELL if request.side == "BUY" else OrderSide.BUY
                tp_order = BacktestOrder(
                    symbol=request.symbol,
                    side=tp_side,
                    type=OrderType.LIMIT,
                    quantity=request.quantity
                    / len(request.take_profit_prices),  # Split quantity
                    price=tp_price,
                    client_order_id=client_order_ids.take_profits[i],
                    bracket_order_id=bracket_id,
                    status=OrderStatus.PENDING_TRIGGER,  # Will activate after entry fills
                    created_at=datetime.now(UTC),
                )
                orders.append(tp_order)

            # 3. Stop loss order
            sl_side = OrderSide.SELL if request.side == "BUY" else OrderSide.BUY
            sl_order = BacktestOrder(
                symbol=request.symbol,
                side=sl_side,
                type=OrderType.STOP_MARKET,
                quantity=request.quantity,
                stop_price=request.stop_loss_price,
                client_order_id=client_order_ids.stop_loss,
                bracket_order_id=bracket_id,
                status=OrderStatus.PENDING_TRIGGER,
                created_at=datetime.now(UTC),
            )
            orders.append(sl_order)

            # Save orders to database and memory
            for order in orders:
                await self._save_order_to_db(order)
                if order.status == OrderStatus.PENDING:
                    self.active_orders[order.client_order_id] = order

            # Track bracket relationship
            self.bracket_orders[bracket_id] = [o.client_order_id for o in orders]

            # If market order, try immediate fill
            if request.order_type == "MARKET" and request.symbol in self.latest_candles:
                candle = self.latest_candles[request.symbol]
                if self.fill_engine.can_fill_order(entry_order, candle):
                    await self._execute_fill(entry_order, candle)

            response = PlaceBracketResponse(
                bracket_order_id=bracket_id,
                client_order_ids=client_order_ids,
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
                created_at=datetime.now(UTC),
                partial_failure=len(errors) > 0,
                errors=errors,
            )

            logger.info(f"Placed bracket order {bracket_id} for {request.symbol}")
            return response

        except Exception as e:
            logger.error(f"Error placing bracket order: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    async def _save_order_to_db(self, order: BacktestOrder):
        """Save order to database"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO paper_orders (
                    id, symbol, side, type, quantity, price, stop_price,
                    client_order_id, bracket_order_id, status, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """,
                order.id,
                order.symbol,
                order.side.value,
                order.type.value,
                order.quantity,
                order.price,
                order.stop_price,
                order.client_order_id,
                order.bracket_order_id,
                order.status.value,
                order.created_at,
                order.updated_at,
            )

    async def cancel_order(self, request: CancelRequest) -> dict[str, str]:
        """Cancel an order"""
        try:
            client_order_id = request.client_order_id
            if not client_order_id and request.order_id:
                # Find by order_id (not implemented in this simple version)
                raise HTTPException(
                    status_code=400, detail="Cancel by order_id not implemented",
                )

            if client_order_id not in self.active_orders:
                raise HTTPException(status_code=404, detail="Order not found")

            order = self.active_orders[client_order_id]
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now(UTC)

            # Update in database
            await self._update_order_in_db(order)

            # Remove from active orders
            del self.active_orders[client_order_id]

            # Publish event
            await self._publish_order_update(order, "CANCELLED")

            logger.info(f"Cancelled order {client_order_id}")
            return {"status": "success"}

        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            raise HTTPException(status_code=400, detail=str(e))

    async def close_all_positions(self, request: CloseAllRequest) -> dict[str, str]:
        """Close all positions"""
        try:
            symbols_to_close = []

            if request.symbol:
                if request.symbol in self.positions:
                    symbols_to_close = [request.symbol]
            else:
                symbols_to_close = list(self.positions.keys())

            for symbol in symbols_to_close:
                position = self.positions[symbol]
                if position.net_quantity.is_zero():
                    continue

                # Create market order to close position
                close_side = (
                    OrderSide.SELL if position.net_quantity > 0 else OrderSide.BUY
                )
                close_order = BacktestOrder(
                    symbol=symbol,
                    side=close_side,
                    type=OrderType.MARKET,
                    quantity=abs(position.net_quantity),
                    client_order_id=f"paper_close_{uuid.uuid4().hex[:8]}",
                    status=OrderStatus.PENDING,
                    created_at=datetime.now(UTC),
                )

                # Save and activate order
                await self._save_order_to_db(close_order)
                self.active_orders[close_order.client_order_id] = close_order

                # Try immediate fill if market data available
                if symbol in self.latest_candles:
                    candle = self.latest_candles[symbol]
                    if self.fill_engine.can_fill_order(close_order, candle):
                        await self._execute_fill(close_order, candle)

            logger.info(f"Initiated close for {len(symbols_to_close)} positions")
            return {"status": "success"}

        except Exception as e:
            logger.error(f"Error closing positions: {e}")
            raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# FastAPI Application
# ============================================================================


def create_paper_broker_app(broker: PaperBroker) -> FastAPI:
    """Create FastAPI application for paper broker"""
    app = FastAPI(title="Paper Broker", version="1.0.0")

    @app.post("/place_bracket")
    async def place_bracket_endpoint(request: PlaceBracketRequest):
        return await broker.place_bracket_order(request)

    @app.post("/cancel")
    async def cancel_endpoint(request: CancelRequest):
        return await broker.cancel_order(request)

    @app.post("/close_all")
    async def close_all_endpoint(request: CloseAllRequest):
        return await broker.close_all_positions(request)

    @app.get("/healthz")
    async def healthz():
        return {"status": "healthy", "service": "paper-broker"}

    @app.get("/readyz")
    async def readyz():
        return {"status": "ready", "service": "paper-broker"}

    @app.get("/positions")
    async def get_positions():
        """Get current positions"""
        positions = []
        for symbol, pos in broker.positions.items():
            if not pos.net_quantity.is_zero():
                positions.append(
                    {
                        "symbol": symbol,
                        "quantity": str(pos.net_quantity),
                        "avg_price": str(pos.avg_entry_price),
                        "unrealized_pnl": str(pos.unrealized_pnl),
                        "side": "LONG" if pos.net_quantity > 0 else "SHORT",
                    },
                )
        return {"positions": positions}

    @app.get("/orders")
    async def get_orders():
        """Get active orders"""
        orders = []
        for order in broker.active_orders.values():
            orders.append(
                {
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "type": order.type.value,
                    "quantity": str(order.quantity),
                    "price": str(order.price),
                    "status": order.status.value,
                    "client_order_id": order.client_order_id,
                },
            )
        return {"orders": orders}

    return app
