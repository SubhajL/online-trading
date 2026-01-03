"""
Schema-aligned SQL builders for paper trading tables.

This module provides pure functions that build SQL statements and parameters
aligned with db/migrations/020_reports.sql schema. Key mappings:

- OrderStatus.CANCELLED (Python) → 'CANCELED' (DB schema uses single L)
- order_time/fill_time (not created_at/updated_at)
- paper_session_id (not bracket_order_id)
- FillReason enum values are lowercase strings
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, TypedDict
from uuid import UUID

from app.engine.backtest.types import (
    BacktestFill,
    BacktestOrder,
    FillReason,
    OrderStatus,
)

PositionSide = Literal["LONG", "SHORT"]


class PositionParams(TypedDict):
    """Parameters for paper position upsert."""

    symbol: str
    paper_session_id: UUID
    side: PositionSide | None
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_fees: Decimal
    total_funding: Decimal


def status_to_db(status: OrderStatus) -> str:
    """Map Python OrderStatus to DB string.

    DB schema uses 'CANCELED' (single L), but Python enum uses 'CANCELLED'.
    """
    if status == OrderStatus.CANCELLED:
        return "CANCELED"
    return status.value


def status_from_db(db_status: str) -> OrderStatus:
    """Map DB status string to Python OrderStatus.

    DB schema uses 'CANCELED' (single L), but Python enum uses 'CANCELLED'.
    """
    if db_status == "CANCELED":
        return OrderStatus.CANCELLED
    return OrderStatus(db_status)


def fill_reason_to_db(reason: FillReason) -> str:
    """Map FillReason enum to DB string.

    Schema expects lowercase: 'market', 'limit', 'stop', 'liquidation'.
    """
    return reason.value


def build_insert_paper_order(
    order: BacktestOrder,
    paper_session_id: UUID,
    now: datetime | None = None,
) -> tuple[str, list[object]]:
    """Build INSERT SQL for paper_orders table.

    Uses schema-aligned column names:
    - order_time (not created_at) for trade timing
    - paper_session_id (not bracket_order_id) for bracket grouping
    - remaining_quantity, reduce_only for order state
    - created_at/updated_at for audit columns

    Args:
        order: The BacktestOrder to insert
        paper_session_id: The bracket/session grouping ID
        now: Optional timestamp for testing; defaults to current UTC time
    """
    sql = """
        INSERT INTO paper_orders (
            id, client_order_id, symbol, side, type,
            quantity, price, stop_price, status,
            filled_quantity, remaining_quantity,
            order_time, fill_time,
            reduce_only, paper_session_id,
            created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11,
            $12, $13,
            $14, $15,
            $16, $17
        )
    """

    if now is None:
        now = datetime.now(UTC)

    params: list[object] = [
        order.id,
        order.client_order_id,
        order.symbol,
        order.side.value,
        order.type.value,
        order.quantity,
        order.price,
        order.stop_price,
        status_to_db(order.status),
        order.filled_quantity,
        order.remaining_quantity,
        order.order_time,
        order.fill_time,
        order.reduce_only,
        paper_session_id,
        now,
        now,
    ]

    return sql, params


def build_insert_paper_fill(
    fill: BacktestFill,
    position_id: UUID | None,
    now: datetime | None = None,
) -> tuple[str, list[object]]:
    """Build INSERT SQL for paper_fills table.

    Uses schema-aligned column names:
    - fill_time (not timestamp) for execution time
    - fill_reason (not reason) for fill type
    - candle_open_time, candle_high, candle_low for market context

    Args:
        fill: The BacktestFill to insert
        position_id: Optional position ID to link to
        now: Optional timestamp for testing; defaults to current UTC time
    """
    sql = """
        INSERT INTO paper_fills (
            id, order_id, position_id,
            symbol, side, quantity, price,
            fee, slippage,
            fill_time, fill_reason,
            candle_open_time, candle_high, candle_low,
            created_at
        ) VALUES (
            $1, $2, $3,
            $4, $5, $6, $7,
            $8, $9,
            $10, $11,
            $12, $13, $14,
            $15
        )
    """

    if now is None:
        now = datetime.now(UTC)

    params: list[object] = [
        fill.id,
        fill.order_id,
        position_id,
        fill.symbol,
        fill.side.value,
        fill.quantity,
        fill.price,
        fill.fee,
        fill.slippage,
        fill.fill_time,
        fill_reason_to_db(fill.fill_reason),
        fill.candle_open_time,
        fill.candle_high,
        fill.candle_low,
        now,
    ]

    return sql, params


def build_upsert_paper_position(
    position: PositionParams,
    now: datetime | None = None,
) -> tuple[str, list[object]]:
    """Build UPSERT SQL for paper_positions table.

    Uses (symbol, paper_session_id) as unique constraint per schema.

    Args:
        position: The position parameters to upsert
        now: Optional timestamp for testing; defaults to current UTC time
    """
    sql = """
        INSERT INTO paper_positions (
            symbol, paper_session_id,
            side, quantity, entry_price, mark_price,
            unrealized_pnl, realized_pnl,
            total_fees, total_funding,
            opened_at, created_at, updated_at
        ) VALUES (
            $1, $2,
            $3, $4, $5, $6,
            $7, $8,
            $9, $10,
            $11, $12, $13
        )
        ON CONFLICT (symbol, paper_session_id) DO UPDATE SET
            side = EXCLUDED.side,
            quantity = EXCLUDED.quantity,
            entry_price = EXCLUDED.entry_price,
            mark_price = EXCLUDED.mark_price,
            unrealized_pnl = EXCLUDED.unrealized_pnl,
            realized_pnl = EXCLUDED.realized_pnl,
            total_fees = EXCLUDED.total_fees,
            total_funding = EXCLUDED.total_funding,
            updated_at = EXCLUDED.updated_at
    """

    if now is None:
        now = datetime.now(UTC)

    params: list[object] = [
        position["symbol"],
        position["paper_session_id"],
        position["side"],
        position["quantity"],
        position["entry_price"],
        position["mark_price"],
        position["unrealized_pnl"],
        position["realized_pnl"],
        position["total_fees"],
        position["total_funding"],
        now,  # opened_at
        now,  # created_at
        now,  # updated_at
    ]

    return sql, params


def cancel_oco_siblings_sql(
    paper_session_id: UUID,
    filled_order_id: UUID,
    now: datetime | None = None,
) -> tuple[str, list[object]]:
    """Build SQL to cancel OCO siblings when one order fills.

    Cancels all NEW orders in the same paper_session_id except the filled one.
    Uses 'CANCELED' (single L) per schema.

    Args:
        paper_session_id: The bracket/session grouping ID
        filled_order_id: The order that just filled (to exclude)
        now: Optional timestamp for testing; defaults to current UTC time
    """
    sql = """
        UPDATE paper_orders
        SET status = $1, updated_at = $2
        WHERE paper_session_id = $3
          AND id != $4
          AND status = $5
    """

    if now is None:
        now = datetime.now(UTC)

    params: list[object] = [
        status_to_db(OrderStatus.CANCELLED),
        now,
        paper_session_id,
        filled_order_id,
        status_to_db(OrderStatus.NEW),
    ]

    return sql, params
