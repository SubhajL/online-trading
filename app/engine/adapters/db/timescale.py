"""
Lightweight TimescaleDB DAL helpers for trading platform.

Provides async database operations with connection pooling and retry logic.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID

import asyncpg
from asyncpg import Connection

from ...types import Candle, TechnicalIndicators, TimeFrame, SupplyDemandZone
from .connection_pool import ConnectionPool, DBConfig

logger = logging.getLogger(__name__)

# Global connection pool instance
_pool: Optional[ConnectionPool] = None


async def initialize_pool(config: DBConfig) -> None:
    """
    Initialize the global connection pool.

    Args:
        config: Database configuration
    """
    global _pool
    if _pool is None:
        _pool = ConnectionPool(config)
        await _pool.initialize()
        logger.info("Database connection pool initialized")


async def close_pool() -> None:
    """Close the global connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


def get_pool() -> ConnectionPool:
    """
    Get the global connection pool instance.

    Returns:
        ConnectionPool instance

    Raises:
        RuntimeError: If pool is not initialized
    """
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call initialize_pool first.")
    return _pool


async def upsert_candle(candle: Candle, venue: str = "binance") -> bool:
    """
    Idempotent candle insert handling conflicts on (venue, symbol, tf, open_time).

    Args:
        candle: Candle data to insert/update
        venue: Exchange venue (default: binance)

    Returns:
        True if successful, False otherwise
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO candles (
                    venue, symbol, timeframe, open_time, close_time,
                    open_price, high_price, low_price, close_price,
                    volume, quote_volume, trades,
                    taker_buy_base_volume, taker_buy_quote_volume
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (venue, symbol, timeframe, open_time)
                DO UPDATE SET
                    close_time = EXCLUDED.close_time,
                    open_price = EXCLUDED.open_price,
                    high_price = EXCLUDED.high_price,
                    low_price = EXCLUDED.low_price,
                    close_price = EXCLUDED.close_price,
                    volume = EXCLUDED.volume,
                    quote_volume = EXCLUDED.quote_volume,
                    trades = EXCLUDED.trades,
                    taker_buy_base_volume = EXCLUDED.taker_buy_base_volume,
                    taker_buy_quote_volume = EXCLUDED.taker_buy_quote_volume,
                    updated_at = CURRENT_TIMESTAMP
            """,
                venue,
                candle.symbol,
                candle.timeframe.value,
                candle.open_time,
                candle.close_time,
                candle.open_price,
                candle.high_price,
                candle.low_price,
                candle.close_price,
                candle.volume,
                candle.quote_volume,
                candle.trades,
                candle.taker_buy_base_volume,
                candle.taker_buy_quote_volume,
            )
            return True

    except Exception as e:
        logger.error(f"Error upserting candle: {e}")
        return False


async def get_candles(
    symbol: str,
    timeframe: TimeFrame,
    venue: str = "binance",
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """
    Query candles with symbol/timeframe filters and time range.

    Args:
        symbol: Trading symbol
        timeframe: Candle timeframe
        venue: Exchange venue (default: binance)
        start_time: Start time filter
        end_time: End time filter
        limit: Maximum number of results

    Returns:
        List of candle dictionaries with Decimal precision preserved
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            query = """
                SELECT
                    venue, symbol, timeframe, open_time, close_time,
                    open_price, high_price, low_price, close_price,
                    volume, quote_volume, trades,
                    taker_buy_base_volume, taker_buy_quote_volume
                FROM candles
                WHERE venue = $1 AND symbol = $2 AND timeframe = $3
            """
            params = [venue, symbol, timeframe.value]

            if start_time:
                query += f" AND open_time >= ${len(params) + 1}"
                params.append(start_time)

            if end_time:
                query += f" AND open_time <= ${len(params) + 1}"
                params.append(end_time)

            query += f" ORDER BY open_time DESC LIMIT ${len(params) + 1}"
            params.append(limit)

            rows = await conn.fetch(query, *params)

            # Convert to list of dicts with Decimal types preserved
            candles = []
            for row in rows:
                candles.append(
                    {
                        "venue": row["venue"],
                        "symbol": row["symbol"],
                        "timeframe": row["timeframe"],
                        "open_time": row["open_time"],
                        "close_time": row["close_time"],
                        "open_price": row["open_price"],  # Keep as Decimal
                        "high_price": row["high_price"],  # Keep as Decimal
                        "low_price": row["low_price"],  # Keep as Decimal
                        "close_price": row["close_price"],  # Keep as Decimal
                        "volume": row["volume"],  # Keep as Decimal
                        "quote_volume": row["quote_volume"],  # Keep as Decimal
                        "trades": row["trades"],
                        "taker_buy_base_volume": row[
                            "taker_buy_base_volume"
                        ],  # Keep as Decimal
                        "taker_buy_quote_volume": row[
                            "taker_buy_quote_volume"
                        ],  # Keep as Decimal
                    }
                )

            return list(reversed(candles))  # Return chronological order

    except Exception as e:
        logger.error(f"Error getting candles: {e}")
        return []


async def upsert_indicator(
    indicator: TechnicalIndicators, venue: str = "binance"
) -> bool:
    """
    Save calculated technical indicators.

    Args:
        indicator: Technical indicators to save
        venue: Exchange venue (default: binance)

    Returns:
        True if successful, False otherwise
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO indicators (
                    venue, symbol, timeframe, timestamp,
                    ema_9, ema_21, ema_50, ema_200,
                    rsi_14, macd_line, macd_signal, macd_histogram,
                    atr_14, bb_upper, bb_middle, bb_lower, bb_width, bb_percent
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                ON CONFLICT (venue, symbol, timeframe, timestamp)
                DO UPDATE SET
                    ema_9 = EXCLUDED.ema_9,
                    ema_21 = EXCLUDED.ema_21,
                    ema_50 = EXCLUDED.ema_50,
                    ema_200 = EXCLUDED.ema_200,
                    rsi_14 = EXCLUDED.rsi_14,
                    macd_line = EXCLUDED.macd_line,
                    macd_signal = EXCLUDED.macd_signal,
                    macd_histogram = EXCLUDED.macd_histogram,
                    atr_14 = EXCLUDED.atr_14,
                    bb_upper = EXCLUDED.bb_upper,
                    bb_middle = EXCLUDED.bb_middle,
                    bb_lower = EXCLUDED.bb_lower,
                    bb_width = EXCLUDED.bb_width,
                    bb_percent = EXCLUDED.bb_percent,
                    updated_at = CURRENT_TIMESTAMP
            """,
                venue,
                indicator.symbol,
                indicator.timeframe.value,
                indicator.timestamp,
                indicator.ema_9,
                indicator.ema_21,
                indicator.ema_50,
                indicator.ema_200,
                indicator.rsi_14,
                indicator.macd_line,
                indicator.macd_signal,
                indicator.macd_histogram,
                indicator.atr_14,
                indicator.bb_upper,
                indicator.bb_middle,
                indicator.bb_lower,
                indicator.bb_width,
                indicator.bb_percent,
            )
            return True

    except Exception as e:
        logger.error(f"Error upserting indicator: {e}")
        return False


async def upsert_zone(zone: SupplyDemandZone, venue: str = "binance") -> bool:
    """
    Save supply/demand zones.

    Args:
        zone: Zone data to save
        venue: Exchange venue (default: binance)

    Returns:
        True if successful, False otherwise
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO zones (
                    zone_id, venue, symbol, timeframe, zone_type,
                    top_price, bottom_price, created_at,
                    strength, volume_profile, touches, is_active, tested_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (zone_id)
                DO UPDATE SET
                    touches = EXCLUDED.touches,
                    is_active = EXCLUDED.is_active,
                    tested_at = EXCLUDED.tested_at,
                    updated_at = CURRENT_TIMESTAMP
            """,
                zone.zone_id,
                venue,
                zone.symbol,
                zone.timeframe.value,
                zone.zone_type.value,
                zone.top_price,
                zone.bottom_price,
                zone.created_at,
                zone.strength,
                zone.volume_profile,
                zone.touches,
                zone.is_active,
                zone.tested_at,
            )
            return True

    except Exception as e:
        logger.error(f"Error upserting zone: {e}")
        return False


async def upsert_order(order_data: Dict[str, Any], venue: str = "binance") -> bool:
    """
    Track order lifecycle with client order ID uniqueness.

    Args:
        order_data: Dictionary containing order fields
        venue: Exchange venue (default: binance)

    Returns:
        True if successful, False otherwise
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            # Extract required fields with defaults
            order_id = order_data.get("order_id")
            client_order_id = order_data["client_order_id"]
            symbol = order_data["symbol"]
            side = order_data["side"]
            order_type = order_data["type"]
            quantity = Decimal(str(order_data["quantity"]))
            status = order_data.get("status", "NEW")
            created_at = order_data.get("created_at", datetime.utcnow())

            # Optional fields
            price = (
                Decimal(str(order_data["price"])) if order_data.get("price") else None
            )
            stop_price = (
                Decimal(str(order_data["stop_price"]))
                if order_data.get("stop_price")
                else None
            )
            filled_quantity = Decimal(str(order_data.get("filled_quantity", 0)))
            average_fill_price = (
                Decimal(str(order_data["average_fill_price"]))
                if order_data.get("average_fill_price")
                else None
            )

            await conn.execute(
                """
                INSERT INTO orders (
                    order_id, client_order_id, venue, symbol, side, type,
                    quantity, price, stop_price, status,
                    filled_quantity, average_fill_price, created_at,
                    decision_id, exchange_order_id, commission, commission_asset
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                ON CONFLICT (venue, client_order_id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    filled_quantity = EXCLUDED.filled_quantity,
                    average_fill_price = EXCLUDED.average_fill_price,
                    exchange_order_id = COALESCE(EXCLUDED.exchange_order_id, orders.exchange_order_id),
                    updated_at = CURRENT_TIMESTAMP
            """,
                order_id,
                client_order_id,
                venue,
                symbol,
                side,
                order_type,
                quantity,
                price,
                stop_price,
                status,
                filled_quantity,
                average_fill_price,
                created_at,
                order_data.get("decision_id"),
                order_data.get("exchange_order_id"),
                Decimal(str(order_data.get("commission", 0))),
                order_data.get("commission_asset"),
            )
            return True

    except Exception as e:
        logger.error(f"Error upserting order: {e}")
        return False


async def get_active_positions(
    venue: str = "binance", symbol: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Query open positions.

    Args:
        venue: Exchange venue (default: binance)
        symbol: Optional symbol filter

    Returns:
        List of active position dictionaries with Decimal precision preserved
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            query = """
                SELECT
                    position_id, venue, symbol, side, size,
                    entry_price, current_price, unrealized_pnl, realized_pnl,
                    margin_used, leverage, opened_at, updated_at,
                    stop_loss, take_profit, decision_id
                FROM positions
                WHERE venue = $1 AND is_active = TRUE
            """
            params = [venue]

            if symbol:
                query += f" AND symbol = ${len(params) + 1}"
                params.append(symbol)

            query += " ORDER BY opened_at DESC"

            rows = await conn.fetch(query, *params)

            positions = []
            for row in rows:
                positions.append(
                    {
                        "position_id": row["position_id"],
                        "venue": row["venue"],
                        "symbol": row["symbol"],
                        "side": row["side"],
                        "size": row["size"],  # Keep as Decimal
                        "entry_price": row["entry_price"],  # Keep as Decimal
                        "current_price": row["current_price"],  # Keep as Decimal
                        "unrealized_pnl": row["unrealized_pnl"],  # Keep as Decimal
                        "realized_pnl": row["realized_pnl"],  # Keep as Decimal
                        "margin_used": row["margin_used"],  # Keep as Decimal
                        "leverage": row["leverage"],  # Keep as Decimal
                        "opened_at": row["opened_at"],
                        "updated_at": row["updated_at"],
                        "stop_loss": (
                            row["stop_loss"] if row["stop_loss"] else None
                        ),  # Keep as Decimal
                        "take_profit": (
                            row["take_profit"] if row["take_profit"] else None
                        ),  # Keep as Decimal
                        "decision_id": row["decision_id"],
                    }
                )

            return positions

    except Exception as e:
        logger.error(f"Error getting active positions: {e}")
        return []
