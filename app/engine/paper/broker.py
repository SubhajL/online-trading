"""
Paper Broker - Live trading simulation with same API as Go Router

This module provides a paper trading broker that:
1. Exposes the same HTTP API as the Go router (/place_bracket, /cancel, /close_all)
2. Simulates realistic order fills using live market data
3. Uses the same cost and slippage modeling as backtesting
4. Stores orders/positions in database for persistence
5. Publishes order_update.v1 events like live trading
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import NoReturn
from uuid import UUID, uuid4

import asyncpg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_serializer

from app.engine.backtest.costs import CostCalculator
from app.engine.backtest.fills import FillEngine
from app.engine.backtest.types import (
    BacktestFill,
    BacktestOrder,
    OrderSide,
    OrderStatus,
    OrderType,
)
from app.engine.models import Candle

from .schema import (
    PositionParams,
    build_insert_paper_fill,
    build_insert_paper_order,
    build_upsert_paper_position,
    cancel_oco_siblings_sql,
    status_from_db,
    status_to_db,
)

logger = logging.getLogger(__name__)

EventPublisher = Callable[[str, dict[str, object]], Awaitable[bool]]


def _raise_http(status_code: int, detail: str) -> NoReturn:
    raise HTTPException(status_code=status_code, detail=detail)


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

    def __init__(self, symbol: str, is_futures: bool = False) -> None:
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
        elif (self.net_quantity > 0 and fill_qty > 0) or (self.net_quantity < 0 and fill_qty < 0):
            # Adding to position
            total_value = (self.net_quantity * self.avg_entry_price) + (fill_qty * fill.price)
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
                self.unrealized_pnl = (current_price - self.avg_entry_price) * self.net_quantity
            else:
                self.unrealized_pnl = (self.avg_entry_price - current_price) * abs(
                    self.net_quantity,
                )
        else:
            self.unrealized_pnl = Decimal(0)

        self.updated_at = datetime.now(UTC)


class MissingBracketIdError(RuntimeError):
    def __init__(self, client_order_id: str) -> None:
        super().__init__(f"Missing bracket id for order {client_order_id}")


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
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self.database_url = database_url
        self.cost_calculator = cost_calculator or CostCalculator()
        self.fill_engine = fill_engine or FillEngine()
        self.event_publisher = event_publisher

        # In-memory state
        self.active_orders: dict[str, BacktestOrder] = {}  # client_order_id -> order
        self._order_bracket_ids: dict[str, UUID] = {}  # client_order_id -> bracket id
        # Positions keyed by (symbol, bracket_id).
        self.positions: dict[tuple[str, UUID], PaperPosition] = {}

        # Database pool
        self.db_pool: asyncpg.Pool | None = None

        # Current market data cache
        self.current_prices: dict[str, Decimal] = {}
        self.latest_candles: dict[str, Candle] = {}

        logger.info("Paper broker initialized")

    async def initialize(self) -> None:
        """Initialize database connection and load state"""
        self.db_pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=10,
        )
        await self._load_state_from_db()
        logger.info("Paper broker database initialized")

    async def close(self) -> None:
        """Close database connections"""
        if self.db_pool:
            await self.db_pool.close()
        logger.info("Paper broker closed")

    async def _load_state_from_db(self) -> None:
        """Load active orders and positions from database.

        Uses schema-aligned column names and status values.
        Loads all active orders and open positions.
        """
        async with self.db_pool.acquire() as conn:
            # Load active orders (using schema-aligned status)
            orders = await conn.fetch(
                """
                SELECT * FROM paper_orders
                WHERE status IN ('NEW', 'PARTIALLY_FILLED')
                ORDER BY order_time
                """,
            )

            for order_row in orders:
                bracket_id = order_row.get("paper_session_id")
                if bracket_id is None:
                    logger.warning(
                        "Skipping paper_order %s without paper_session_id",
                        order_row.get("client_order_id"),
                    )
                    continue
                order = self._order_from_db_row(order_row)
                self.active_orders[order.client_order_id] = order
                self._order_bracket_ids[order.client_order_id] = bracket_id

            # Load positions (using schema-aligned columns)
            positions = await conn.fetch(
                """
                SELECT * FROM paper_positions
                WHERE quantity > 0
                """,
            )

            for pos_row in positions:
                bracket_id = pos_row.get("paper_session_id")
                if bracket_id is None:
                    logger.warning(
                        "Skipping paper_position %s without paper_session_id",
                        pos_row.get("symbol"),
                    )
                    continue
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

                self.positions[(pos_row["symbol"], bracket_id)] = position

        logger.info(
            "Loaded %d orders and %d positions",
            len(self.active_orders),
            len(self.positions),
        )

    def _order_from_db_row(self, row: asyncpg.Record) -> BacktestOrder:
        """Convert database row to BacktestOrder using schema-aligned columns."""
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

    async def update_market_data(self, candle: Candle) -> None:
        """Update with latest candle for fill simulation"""
        self.latest_candles[candle.symbol] = candle
        self.current_prices[candle.symbol] = candle.close_price

        # Check for fills on existing orders
        await self._process_pending_fills(candle)

    def _is_order_fill_eligible(self, order: BacktestOrder) -> bool:
        """
        Gate fills that would violate bracket lifecycle invariants.

        Reduce-only exit orders (TP/SL) must not fill until there is a position
        to reduce. This prevents TP/SL from filling before the entry.
        """
        if not order.reduce_only:
            return True

        bracket_id = self._order_bracket_ids.get(order.client_order_id)
        if bracket_id is None:
            return False

        position = self.positions.get((order.symbol, bracket_id))
        return position is not None and not position.net_quantity.is_zero()

    async def _process_pending_fills(self, candle: Candle) -> None:
        """Check if any NEW orders can be filled with this candle."""
        symbol_orders = [
            o
            for o in self.active_orders.values()
            if o.symbol == candle.symbol
            and o.status == OrderStatus.NEW
            and self._is_order_fill_eligible(o)
        ]

        fills = self.fill_engine.process_order_fills(symbol_orders, candle)
        if not fills:
            return

        orders_by_id = {o.id: o for o in symbol_orders}
        for fill in fills:
            order = orders_by_id.get(fill.order_id)
            if order is None:
                continue
            await self._apply_fill(order, fill, candle)

    async def _apply_fill(
        self,
        order: BacktestOrder,
        fill: BacktestFill,
        candle: Candle,
    ) -> None:
        """Apply a fill to broker state and persist it."""
        bracket_id = self._order_bracket_ids.get(order.client_order_id)
        if bracket_id is None:
            raise MissingBracketIdError(order.client_order_id)

        position_key = (order.symbol, bracket_id)

        # Calculate trading fee from notional (slippage is already in fill.slippage)
        notional = fill.quantity * fill.price
        fee = self.cost_calculator.calculate_trading_fee(
            notional,
            is_futures=order.symbol.endswith("USDT") and "PERP" in order.symbol,
            is_maker=(order.type == OrderType.LIMIT),
        )
        fill.fee = fee

        # Snapshot state for rollback on DB failure
        prev_status = order.status
        prev_filled_qty = order.filled_quantity
        prev_remaining_qty = order.remaining_quantity
        prev_fill_time = order.fill_time
        had_position = position_key in self.positions

        # Mutate order/position so DB helpers can read current values
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.remaining_quantity = Decimal(0)
        order.fill_time = fill.fill_time

        if position_key not in self.positions:
            self.positions[position_key] = PaperPosition(
                order.symbol,
                is_futures=order.symbol.endswith("USDT"),
            )

        self.positions[position_key].update_position(fill, candle.close_price)

        # Persist in a single transaction; revert memory on failure
        try:
            async with self.db_pool.acquire() as conn:
                async with conn.transaction():
                    await self._insert_paper_fill(fill, conn=conn)
                    await self._update_order_in_db(order, conn=conn)
                    await self._upsert_paper_position(
                        self.positions[position_key],
                        bracket_id,
                        conn=conn,
                    )
        except Exception:
            order.status = prev_status
            order.filled_quantity = prev_filled_qty
            order.remaining_quantity = prev_remaining_qty
            order.fill_time = prev_fill_time
            if not had_position:
                self.positions.pop(position_key, None)
            raise

        # Cancel OCO siblings if this is a reduce_only (TP/SL) order
        if order.reduce_only:
            await self._cancel_oco_siblings(
                order.id,
                bracket_id=bracket_id,
                symbol=order.symbol,
            )

        # Publish order update event
        await self._publish_order_update(order, "FILLED")

        # Remove from active orders
        del self.active_orders[order.client_order_id]
        del self._order_bracket_ids[order.client_order_id]

        logger.info(
            "Filled order %s: %s %s @ %s",
            order.client_order_id,
            order.quantity,
            order.symbol,
            fill.price,
        )

    async def _insert_paper_fill(
        self,
        fill: BacktestFill,
        position_id: UUID | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        """Insert fill to database using schema-aligned SQL builder."""
        sql, params = build_insert_paper_fill(fill, position_id)
        if conn is not None:
            await conn.execute(sql, *params)
        else:
            async with self.db_pool.acquire() as c:
                await c.execute(sql, *params)

    async def _update_order_in_db(
        self,
        order: BacktestOrder,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        """Update order status and fill info in database."""
        query = """
            UPDATE paper_orders SET
                status = $2,
                filled_quantity = $3,
                remaining_quantity = $4,
                fill_time = $5,
                updated_at = $6
            WHERE id = $1
        """
        params = (
            order.id,
            status_to_db(order.status),
            order.filled_quantity,
            order.remaining_quantity,
            order.fill_time,
            datetime.now(UTC),
        )
        if conn is not None:
            await conn.execute(query, *params)
        else:
            async with self.db_pool.acquire() as c:
                await c.execute(query, *params)

    async def _upsert_paper_position(
        self,
        position: PaperPosition,
        bracket_id: UUID,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        """Upsert position to database using schema-aligned SQL builder."""
        side: str | None
        if position.net_quantity > 0:
            side = "LONG"
        elif position.net_quantity < 0:
            side = "SHORT"
        else:
            side = None
        params = PositionParams(
            symbol=position.symbol,
            paper_session_id=bracket_id,
            side=side,  # type: ignore[typeddict-item]
            quantity=abs(position.net_quantity),
            entry_price=position.avg_entry_price,
            mark_price=position.avg_entry_price,  # Updated on next candle
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=Decimal(0),
            total_fees=position.total_fees,
            total_funding=position.total_funding,
        )
        sql, sql_params = build_upsert_paper_position(params)
        if conn is not None:
            await conn.execute(sql, *sql_params)
        else:
            async with self.db_pool.acquire() as c:
                await c.execute(sql, *sql_params)

    async def _cancel_oco_siblings(
        self,
        filled_order_id: UUID,
        *,
        bracket_id: UUID,
        symbol: str,
    ) -> None:
        """Cancel OCO sibling orders when one fills (e.g., cancel SL when TP fills).

        Cancels reduce-only sibling orders for the same symbol and bracket.
        """
        sql, params = cancel_oco_siblings_sql(
            bracket_id,
            filled_order_id,
            symbol=symbol,
        )
        async with self.db_pool.acquire() as conn:
            await conn.execute(sql, *params)

        # Also update in-memory state (reduce-only orders for same symbol + bracket)
        for client_order_id, order in list(self.active_orders.items()):
            order_bracket_id = self._order_bracket_ids.get(client_order_id)
            if (
                order_bracket_id == bracket_id
                and order.id != filled_order_id
                and order.status == OrderStatus.NEW
                and order.reduce_only
                and order.symbol == symbol
            ):
                order.status = OrderStatus.CANCELLED
                del self.active_orders[client_order_id]
                del self._order_bracket_ids[client_order_id]

    async def _publish_order_update(
        self,
        order: BacktestOrder,
        event_type: str,
    ) -> None:
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

        payload: dict[str, object] = update.model_dump()
        await self.event_publisher("order_update.v1", payload)

    # ============================================================================
    # API Endpoints (Same as Go Router)
    # ============================================================================

    async def place_bracket_order(
        self,
        request: PlaceBracketRequest,
    ) -> PlaceBracketResponse:
        """Place bracket order with entry, TP, and SL.

        All orders in a bracket share the same paper_session_id for OCO tracking.
        TP/SL orders are marked reduce_only=True per schema.
        """
        if len(request.take_profit_prices) != 1:
            _raise_http(400, "Exactly one take profit price is required")

        now = datetime.now(UTC)
        bracket_id = uuid4()
        client_order_ids = ClientOrderIDs(
            main=f"paper_{uuid4().hex[:8]}",
            take_profits=[f"paper_tp_{uuid4().hex[:8]}"],
            stop_loss=f"paper_sl_{uuid4().hex[:8]}",
        )

        orders: list[BacktestOrder] = []
        errors: list[str] = []

        try:
            # 1. Entry order (reduce_only=False)
            entry_order = BacktestOrder(
                symbol=request.symbol,
                side=OrderSide(request.side),
                type=OrderType.MARKET if request.order_type == "MARKET" else OrderType.LIMIT,
                quantity=request.quantity,
                price=request.entry_price if request.order_type == "LIMIT" else None,
                client_order_id=client_order_ids.main,
                status=OrderStatus.NEW,
                reduce_only=False,
                order_time=now,
            )
            orders.append(entry_order)

            # 2. Take profit orders (OCO, reduce_only=True)
            tp_side = OrderSide.SELL if request.side == "BUY" else OrderSide.BUY
            tp_order = BacktestOrder(
                symbol=request.symbol,
                side=tp_side,
                type=OrderType.LIMIT,
                quantity=request.quantity,
                price=request.take_profit_prices[0],
                client_order_id=client_order_ids.take_profits[0],
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
                await self._insert_paper_order(order, bracket_id)
                self.active_orders[order.client_order_id] = order
                self._order_bracket_ids[order.client_order_id] = bracket_id

            # If market order, try immediate fill
            if request.order_type == "MARKET" and request.symbol in self.latest_candles:
                candle = self.latest_candles[request.symbol]
                await self._process_pending_fills(candle)

            response = PlaceBracketResponse(
                bracket_order_id=str(bracket_id),
                client_order_ids=client_order_ids,
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
                created_at=now,
                partial_failure=len(errors) > 0,
                errors=errors,
            )

            logger.info(
                "Placed bracket order for %s (bracket=%s)",
                request.symbol,
                bracket_id,
            )

        except Exception as e:
            logger.exception("Error placing bracket order")
            raise HTTPException(status_code=400, detail=str(e)) from e
        else:
            return response

    async def _insert_paper_order(
        self,
        order: BacktestOrder,
        bracket_id: UUID,
    ) -> None:
        """Insert order to database using schema-aligned SQL builder."""
        sql, params = build_insert_paper_order(order, bracket_id)
        async with self.db_pool.acquire() as conn:
            await conn.execute(sql, *params)

    async def cancel_order(self, request: CancelRequest) -> dict[str, str]:
        """Cancel an order"""
        try:
            client_order_id = request.client_order_id
            if not client_order_id and request.order_id:
                # Find by order_id (not implemented in this simple version)
                _raise_http(400, "Cancel by order_id not implemented")

            if client_order_id not in self.active_orders:
                _raise_http(404, "Order not found")

            order = self.active_orders[client_order_id]
            order.status = OrderStatus.CANCELLED

            # Update in database
            await self._update_order_in_db(order)

            # Remove from active orders
            del self.active_orders[client_order_id]

            # Publish event
            await self._publish_order_update(order, "CANCELLED")

            logger.info("Cancelled order %s", client_order_id)

        except Exception as e:
            logger.exception("Error canceling order")
            raise HTTPException(status_code=400, detail=str(e)) from e
        else:
            return {"status": "success"}

    async def close_all_positions(self, request: CloseAllRequest) -> dict[str, str]:
        """Close all positions"""
        try:
            keys_to_close: list[tuple[str, UUID]]
            if request.symbol:
                keys_to_close = [key for key in self.positions if key[0] == request.symbol]
            else:
                keys_to_close = list(self.positions.keys())

            now = datetime.now(UTC)
            for symbol, bracket_id in keys_to_close:
                position = self.positions[(symbol, bracket_id)]
                if position.net_quantity.is_zero():
                    continue

                # Create market order to close position (schema-aligned)
                close_side = OrderSide.SELL if position.net_quantity > 0 else OrderSide.BUY
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
                await self._insert_paper_order(close_order, bracket_id)
                self.active_orders[close_order.client_order_id] = close_order
                self._order_bracket_ids[close_order.client_order_id] = bracket_id

                # Try immediate fill if market data available
                if symbol in self.latest_candles:
                    candle = self.latest_candles[symbol]
                    await self._process_pending_fills(candle)

            logger.info("Initiated close for %d positions", len(keys_to_close))

        except Exception as e:
            logger.exception("Error closing positions")
            raise HTTPException(status_code=400, detail=str(e)) from e
        else:
            return {"status": "success"}


# ============================================================================
# FastAPI Application
# ============================================================================


def create_paper_broker_app(broker: PaperBroker) -> FastAPI:
    """Create FastAPI application for paper broker"""
    app = FastAPI(title="Paper Broker", version="1.0.0")

    @app.post("/place_bracket")
    async def place_bracket_endpoint(
        request: PlaceBracketRequest,
    ) -> PlaceBracketResponse:
        return await broker.place_bracket_order(request)

    @app.post("/cancel")
    async def cancel_endpoint(request: CancelRequest) -> dict[str, str]:
        return await broker.cancel_order(request)

    @app.post("/close_all")
    async def close_all_endpoint(request: CloseAllRequest) -> dict[str, str]:
        return await broker.close_all_positions(request)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "healthy", "service": "paper-broker"}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        return {"status": "ready", "service": "paper-broker"}

    @app.get("/positions")
    async def get_positions() -> dict[str, list[dict[str, str]]]:
        """Get current positions"""
        positions = [
            {
                "symbol": symbol,
                "paper_session_id": str(bracket_id),
                "quantity": str(pos.net_quantity),
                "avg_price": str(pos.avg_entry_price),
                "unrealized_pnl": str(pos.unrealized_pnl),
                "side": "LONG" if pos.net_quantity > 0 else "SHORT",
            }
            for (symbol, bracket_id), pos in broker.positions.items()
            if not pos.net_quantity.is_zero()
        ]
        return {"positions": positions}

    @app.get("/orders")
    async def get_orders() -> dict[str, list[dict[str, str]]]:
        """Get active orders"""
        orders = [
            {
                "symbol": order.symbol,
                "side": order.side.value,
                "type": order.type.value,
                "quantity": str(order.quantity),
                "price": str(order.price),
                "status": order.status.value,
                "client_order_id": order.client_order_id,
            }
            for order in broker.active_orders.values()
        ]
        return {"orders": orders}

    return app
