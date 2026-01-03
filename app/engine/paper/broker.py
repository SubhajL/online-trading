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
from uuid import UUID, uuid4

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
from .schema import (
    PositionParams,
    build_insert_paper_fill,
    build_insert_paper_order,
    build_upsert_paper_position,
    cancel_oco_siblings_sql,
)

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

    def update_position(self, fill: BacktestFill, current_price: Decimal) -> None:
        """Update position with new fill."""
        fill_qty = fill.quantity if fill.side == OrderSide.BUY else -fill.quantity

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
        paper_session_id: UUID | None = None,
    ):
        self.database_url = database_url
        self.cost_calculator = cost_calculator or CostCalculator()
        self.fill_engine = fill_engine or FillEngine()
        self.event_publisher = event_publisher
        self.paper_session_id = paper_session_id or uuid4()

        # In-memory state
        self.active_orders: dict[str, BacktestOrder] = {}  # client_order_id -> order
        self.positions: dict[str, PaperPosition] = {}  # symbol -> position

        # Database pool
        self.db_pool: asyncpg.Pool | None = None

        # Current market data cache
        self.current_prices: dict[str, Decimal] = {}
        self.latest_candles: dict[str, Candle] = {}

        logger.info("Paper broker initialized with session %s", self.paper_session_id)

    async def initialize(self):
        """Initialize database connection and load state"""
        self.db_pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=10,
        )
        await self._load_state_from_db()
        logger.info("Paper broker database initialized")

    async def close(self):
        """Close database connections"""
        if self.db_pool:
            await self.db_pool.close()
        logger.info("Paper broker closed")

    async def _load_state_from_db(self) -> None:
        """Load active orders and positions from database.

        Uses schema-aligned column names and status values.
        Only loads orders for the current paper_session_id.
        """
        from .schema import status_from_db

        async with self.db_pool.acquire() as conn:
            # Load active orders for this session (using schema-aligned status)
            orders = await conn.fetch(
                """
                SELECT * FROM paper_orders
                WHERE paper_session_id = $1
                  AND status IN ('NEW', 'PARTIALLY_FILLED')
                ORDER BY order_time
                """,
                self.paper_session_id,
            )

            for order_row in orders:
                order = self._order_from_db_row(order_row)
                self.active_orders[order.client_order_id] = order

            # Load positions for this session (using schema-aligned columns)
            positions = await conn.fetch(
                """
                SELECT * FROM paper_positions
                WHERE paper_session_id = $1
                  AND quantity > 0
                """,
                self.paper_session_id,
            )

            for pos_row in positions:
                # Determine is_futures from symbol pattern (no column in schema)
                is_futures = pos_row["symbol"].endswith("USDT")
                position = PaperPosition(pos_row["symbol"], is_futures)
                # Map schema columns to PaperPosition fields
                position.net_quantity = pos_row["quantity"]
                if pos_row["side"] == "SHORT":
                    position.net_quantity = -position.net_quantity
                position.avg_entry_price = pos_row["entry_price"]
                position.unrealized_pnl = pos_row["unrealized_pnl"] or Decimal(0)
                position.total_fees = pos_row["total_fees"] or Decimal(0)
                position.total_funding = pos_row["total_funding"] or Decimal(0)
                position.created_at = pos_row["created_at"]
                position.updated_at = pos_row["updated_at"]

                self.positions[pos_row["symbol"]] = position

        logger.info(
            "Loaded %d orders and %d positions for session %s",
            len(self.active_orders),
            len(self.positions),
            self.paper_session_id,
        )

    def _order_from_db_row(self, row) -> BacktestOrder:
        """Convert database row to BacktestOrder using schema-aligned columns."""
        from .schema import status_from_db

        return BacktestOrder(
            id=row["id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            type=OrderType(row["type"]),
            quantity=row["quantity"],
            price=row["price"],
            stop_price=row["stop_price"],
            client_order_id=row["client_order_id"],
            status=status_from_db(row["status"]),
            filled_quantity=row["filled_quantity"] or Decimal(0),
            remaining_quantity=row["remaining_quantity"],
            reduce_only=row["reduce_only"] or False,
            order_time=row["order_time"],
            fill_time=row["fill_time"],
        )

    async def update_market_data(self, candle: Candle):
        """Update with latest candle for fill simulation"""
        self.latest_candles[candle.symbol] = candle
        self.current_prices[candle.symbol] = candle.close_price

        # Check for fills on existing orders
        await self._process_pending_fills(candle)

    async def _process_pending_fills(self, candle: Candle) -> None:
        """Check if any NEW orders can be filled with this candle."""
        symbol_orders = [
            o
            for o in self.active_orders.values()
            if o.symbol == candle.symbol and o.status == OrderStatus.NEW
        ]

        for order in symbol_orders:
            if self.fill_engine.can_fill_order(order, candle):
                await self._execute_fill(order, candle)

    async def _execute_fill(self, order: BacktestOrder, candle: Candle) -> None:
        """Execute a fill for an order using schema-aligned fields."""
        fill_price = self.fill_engine.get_fill_price(order, candle)
        now = datetime.now(UTC)

        # Calculate costs
        notional = order.quantity * fill_price
        fee = self.cost_calculator.calculate_trading_fee(
            notional,
            is_futures=order.symbol.endswith("USDT") and "PERP" in order.symbol,
            is_maker=(order.type == OrderType.LIMIT),
        )
        slippage = self.cost_calculator.calculate_slippage(
            order.quantity,
            candle.volume,
        )

        # Determine fill reason based on order type
        fill_reason = FillReason.MARKET
        if order.type == OrderType.LIMIT:
            fill_reason = FillReason.LIMIT
        elif order.type in (OrderType.STOP_MARKET, OrderType.STOP_LIMIT):
            fill_reason = FillReason.STOP

        # Create fill with schema-aligned fields
        fill = BacktestFill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            fee=fee,
            slippage=slippage,
            fill_time=now,
            fill_reason=fill_reason,
            candle_open_time=candle.open_time,
            candle_high=candle.high_price,
            candle_low=candle.low_price,
        )

        # Update order status with schema-aligned fields
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.remaining_quantity = Decimal(0)
        order.fill_time = now

        # Update position
        if order.symbol not in self.positions:
            self.positions[order.symbol] = PaperPosition(
                order.symbol,
                is_futures=order.symbol.endswith("USDT"),
            )

        self.positions[order.symbol].update_position(fill, candle.close_price)

        # Save to database using schema-aligned methods
        await self._insert_paper_fill(fill)
        await self._update_order_in_db(order)
        await self._upsert_paper_position(self.positions[order.symbol])

        # Cancel OCO siblings if this is a reduce_only (TP/SL) order
        if order.reduce_only:
            await self._cancel_oco_siblings(order.id, symbol=order.symbol)

        # Publish order update event
        await self._publish_order_update(order, "FILLED")

        # Remove from active orders
        del self.active_orders[order.client_order_id]

        logger.info(
            "Filled order %s: %s %s @ %s",
            order.client_order_id,
            order.quantity,
            order.symbol,
            fill_price,
        )

    async def _insert_paper_fill(
        self,
        fill: BacktestFill,
        position_id: UUID | None = None,
    ) -> None:
        """Insert fill to database using schema-aligned SQL builder."""
        sql, params = build_insert_paper_fill(fill, position_id)
        async with self.db_pool.acquire() as conn:
            await conn.execute(sql, *params)

    async def _update_order_in_db(self, order: BacktestOrder) -> None:
        """Update order status and fill info in database using schema-aligned columns."""
        from .schema import status_to_db

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE paper_orders SET
                    status = $2,
                    filled_quantity = $3,
                    remaining_quantity = $4,
                    fill_time = $5,
                    updated_at = $6
                WHERE id = $1
                """,
                order.id,
                status_to_db(order.status),
                order.filled_quantity,
                order.remaining_quantity,
                order.fill_time,
                datetime.now(UTC),
            )

    async def _upsert_paper_position(self, position: PaperPosition) -> None:
        """Upsert position to database using schema-aligned SQL builder."""
        params = PositionParams(
            symbol=position.symbol,
            paper_session_id=self.paper_session_id,
            side="LONG" if position.net_quantity > 0 else "SHORT" if position.net_quantity < 0 else None,
            quantity=abs(position.net_quantity),
            entry_price=position.avg_entry_price,
            mark_price=position.avg_entry_price,  # Updated on next candle
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=Decimal(0),
            total_fees=position.total_fees,
            total_funding=position.total_funding,
        )
        sql, sql_params = build_upsert_paper_position(params)
        async with self.db_pool.acquire() as conn:
            await conn.execute(sql, *sql_params)

    async def _cancel_oco_siblings(
        self,
        filled_order_id: UUID,
        symbol: str | None = None,
    ) -> None:
        """Cancel OCO sibling orders when one fills (e.g., cancel SL when TP fills).

        Only cancels reduce_only orders for the same symbol within this session.
        This prevents accidentally canceling unrelated orders.
        """
        sql, params = cancel_oco_siblings_sql(
            self.paper_session_id,
            filled_order_id,
        )
        async with self.db_pool.acquire() as conn:
            await conn.execute(sql, *params)

        # Also update in-memory state (only reduce_only orders for same symbol)
        for client_order_id, order in list(self.active_orders.items()):
            if (
                order.id != filled_order_id
                and order.status == OrderStatus.NEW
                and order.reduce_only  # Only cancel TP/SL orders
                and (symbol is None or order.symbol == symbol)  # Same symbol
            ):
                order.status = OrderStatus.CANCELLED
                del self.active_orders[client_order_id]

    async def _publish_order_update(self, order: BacktestOrder, event_type: str) -> None:
        """Publish order update event."""
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
            price=order.price or Decimal(0),
            quantity=order.quantity,
            executed_qty=order.filled_quantity,
            update_time=order.fill_time or datetime.now(UTC),
            reason=None,
        )

        # Publish via event bus
        await self.event_publisher.publish("order_update.v1", update.model_dump())

    # ============================================================================
    # API Endpoints (Same as Go Router)
    # ============================================================================

    async def place_bracket_order(
        self,
        request: PlaceBracketRequest,
    ) -> PlaceBracketResponse:
        """Place bracket order with entry, TPs, and SL.

        All orders in a bracket share the same paper_session_id for OCO tracking.
        TP/SL orders are marked reduce_only=True per schema.
        """
        now = datetime.now(UTC)
        client_order_ids = ClientOrderIDs(
            main=f"paper_{uuid4().hex[:8]}",
            take_profits=[
                f"paper_tp_{i}_{uuid4().hex[:8]}"
                for i in range(len(request.take_profit_prices))
            ],
            stop_loss=f"paper_sl_{uuid4().hex[:8]}",
        )

        orders: list[BacktestOrder] = []
        errors: list[str] = []

        try:
            # 1. Entry order (reduce_only=False)
            entry_order = BacktestOrder(
                symbol=request.symbol,
                side=OrderSide(request.side),
                type=OrderType.MARKET
                if request.order_type == "MARKET"
                else OrderType.LIMIT,
                quantity=request.quantity,
                price=request.entry_price
                if request.order_type == "LIMIT"
                else None,
                client_order_id=client_order_ids.main,
                status=OrderStatus.NEW,
                reduce_only=False,
                order_time=now,
            )
            orders.append(entry_order)

            # 2. Take profit orders (OCO, reduce_only=True)
            tp_side = OrderSide.SELL if request.side == "BUY" else OrderSide.BUY
            tp_qty = request.quantity / len(request.take_profit_prices)
            for i, tp_price in enumerate(request.take_profit_prices):
                tp_order = BacktestOrder(
                    symbol=request.symbol,
                    side=tp_side,
                    type=OrderType.LIMIT,
                    quantity=tp_qty,
                    price=tp_price,
                    client_order_id=client_order_ids.take_profits[i],
                    status=OrderStatus.NEW,
                    reduce_only=True,
                    order_time=now,
                )
                orders.append(tp_order)

            # 3. Stop loss order (OCO, reduce_only=True)
            sl_side = OrderSide.SELL if request.side == "BUY" else OrderSide.BUY
            sl_order = BacktestOrder(
                symbol=request.symbol,
                side=sl_side,
                type=OrderType.STOP_MARKET,
                quantity=request.quantity,
                stop_price=request.stop_loss_price,
                client_order_id=client_order_ids.stop_loss,
                status=OrderStatus.NEW,
                reduce_only=True,
                order_time=now,
            )
            orders.append(sl_order)

            # Insert orders to database and track in memory
            for order in orders:
                await self._insert_paper_order(order)
                self.active_orders[order.client_order_id] = order

            # If market order, try immediate fill
            if request.order_type == "MARKET" and request.symbol in self.latest_candles:
                candle = self.latest_candles[request.symbol]
                if self.fill_engine.can_fill_order(entry_order, candle):
                    await self._execute_fill(entry_order, candle)

            response = PlaceBracketResponse(
                bracket_order_id=str(self.paper_session_id),
                client_order_ids=client_order_ids,
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
                created_at=now,
                partial_failure=len(errors) > 0,
                errors=errors,
            )

            logger.info(
                "Placed bracket order for %s (session=%s)",
                request.symbol,
                self.paper_session_id,
            )
            return response

        except Exception as e:
            logger.error("Error placing bracket order: %s", e)
            raise HTTPException(status_code=400, detail=str(e)) from e

    async def _insert_paper_order(self, order: BacktestOrder) -> None:
        """Insert order to database using schema-aligned SQL builder."""
        sql, params = build_insert_paper_order(order, self.paper_session_id)
        async with self.db_pool.acquire() as conn:
            await conn.execute(sql, *params)

    async def cancel_order(self, request: CancelRequest) -> dict[str, str]:
        """Cancel an order"""
        try:
            client_order_id = request.client_order_id
            if not client_order_id and request.order_id:
                # Find by order_id (not implemented in this simple version)
                raise HTTPException(
                    status_code=400,
                    detail="Cancel by order_id not implemented",
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

            now = datetime.now(UTC)
            for symbol in symbols_to_close:
                position = self.positions[symbol]
                if position.net_quantity.is_zero():
                    continue

                # Create market order to close position (schema-aligned)
                close_side = (
                    OrderSide.SELL if position.net_quantity > 0 else OrderSide.BUY
                )
                close_order = BacktestOrder(
                    symbol=symbol,
                    side=close_side,
                    type=OrderType.MARKET,
                    quantity=abs(position.net_quantity),
                    client_order_id=f"paper_close_{uuid4().hex[:8]}",
                    status=OrderStatus.NEW,
                    reduce_only=True,  # Closing position
                    order_time=now,
                )

                # Save and activate order using schema-aligned method
                await self._insert_paper_order(close_order)
                self.active_orders[close_order.client_order_id] = close_order

                # Try immediate fill if market data available
                if symbol in self.latest_candles:
                    candle = self.latest_candles[symbol]
                    if self.fill_engine.can_fill_order(close_order, candle):
                        await self._execute_fill(close_order, candle)

            logger.info("Initiated close for %d positions", len(symbols_to_close))
            return {"status": "success"}

        except Exception as e:
            logger.exception("Error closing positions")
            raise HTTPException(status_code=400, detail=str(e)) from e


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
