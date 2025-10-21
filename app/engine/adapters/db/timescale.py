"""
Module-level TimescaleDB adapter functions expected by unit tests.

Provides a simple API on top of ConnectionPool for common operations
like initializing the pool, upserting candles/orders, and querying data.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.engine.adapters.db.connection_pool import ConnectionPool, DBConfig
from app.engine.models import Candle, TimeFrame, TechnicalIndicators, SupplyDemandZone

# Default venue used by module-level DAL
_DEFAULT_VENUE = "binance"

_pool: ConnectionPool | None = None


async def initialize_pool(config: DBConfig) -> None:
    global _pool
    _pool = ConnectionPool(config)
    await _pool.initialize()


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


@asynccontextmanager
async def acquire_connection():  # noqa: D401
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn


async def upsert_candle(candle: Candle) -> bool:
    """Insert or update a candle row using schema from migrations (001_candles.sql)."""
    query = """
        INSERT INTO candles (
            venue, symbol, timeframe, open_time, close_time,
            open_price, high_price, low_price, close_price,
            volume, quote_volume, trades,
            taker_buy_base_volume, taker_buy_quote_volume
        ) VALUES ($1, $2, $3, to_timestamp($4), to_timestamp($5), $6, $7, $8, $9, $10, $11, $12, $13, $14)
        ON CONFLICT (venue, symbol, timeframe, open_time) DO UPDATE SET
            close_time = EXCLUDED.close_time,
            open_price = EXCLUDED.open_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            close_price = EXCLUDED.close_price,
            volume = EXCLUDED.volume,
            quote_volume = EXCLUDED.quote_volume,
            trades = EXCLUDED.trades,
            taker_buy_base_volume = EXCLUDED.taker_buy_base_volume,
            taker_buy_quote_volume = EXCLUDED.taker_buy_quote_volume
        """
    try:
        ot = (candle.open_time.replace(tzinfo=timezone.utc).timestamp() if candle.open_time.tzinfo is None else candle.open_time.timestamp())
        ct = (candle.close_time.replace(tzinfo=timezone.utc).timestamp() if candle.close_time.tzinfo is None else candle.close_time.timestamp())
        async with acquire_connection() as conn:
            await conn.execute(
                query,
                _DEFAULT_VENUE,
                candle.symbol,
                candle.timeframe.value,
                ot,
                ct,
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
    except Exception:
        return False


async def get_candles(
    symbol: str,
    timeframe: TimeFrame,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Retrieve candles as dictionaries preserving Decimal types.

    Returns rows ordered by open_time ASC.
    """
    where = ["venue = $1", "symbol = $2", "timeframe = $3"]
    params: list[Any] = [_DEFAULT_VENUE, symbol, timeframe.value]
    next_idx = 4
    if start_time is not None:
        where.append(f"open_time >= to_timestamp(${next_idx})")
        params.append(_to_epoch_seconds(start_time))
        next_idx += 1
    if end_time is not None:
        where.append(f"open_time <= to_timestamp(${next_idx})")
        params.append(_to_epoch_seconds(end_time))
        next_idx += 1
    query = f"SELECT * FROM candles WHERE {' AND '.join(where)} ORDER BY open_time ASC"
    if limit is not None:
        query += f" LIMIT ${next_idx}"
        params.append(limit)

    async with acquire_connection() as conn:
        rows = await conn.fetch(query, *params)

    result: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r) if not isinstance(r, dict) else r
        # Normalize to naive datetimes for tests
        if "open_time" in d and isinstance(d["open_time"], datetime) and d["open_time"].tzinfo:
            d["open_time"] = d["open_time"].replace(tzinfo=None)
        if "close_time" in d and isinstance(d["close_time"], datetime) and d["close_time"].tzinfo:
            d["close_time"] = d["close_time"].replace(tzinfo=None)
        result.append(d)
    return result


def _to_epoch_seconds(dt: datetime) -> float:
    """Convert a datetime to epoch seconds in UTC.

    Treats naive datetimes as UTC; if tz-aware, converts to UTC first.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).timestamp()
    return dt.astimezone(timezone.utc).timestamp()


async def upsert_indicator(ind: TechnicalIndicators) -> bool:
    """Upsert into indicators table (002_indicators.sql)."""
    query = """
        INSERT INTO indicators (
            venue, symbol, timeframe, timestamp,
            ema_9, ema_21, ema_50, ema_200,
            rsi_14, macd_line, macd_signal, macd_histogram,
            atr_14, bb_upper, bb_middle, bb_lower, bb_width, bb_percent
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
        ON CONFLICT (venue, symbol, timeframe, timestamp) DO UPDATE SET
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
            bb_percent = EXCLUDED.bb_percent
    """
    async with acquire_connection() as conn:
        await conn.execute(
            query,
            _DEFAULT_VENUE,
            ind.symbol,
            ind.timeframe.value,
            ind.timestamp,
            ind.ema_9,
            ind.ema_21,
            ind.ema_50,
            ind.ema_200,
            ind.rsi_14,
            ind.macd_line,
            ind.macd_signal,
            ind.macd_histogram,
            ind.atr_14,
            ind.bb_upper,
            ind.bb_middle,
            ind.bb_lower,
            ind.bb_width,
            ind.bb_percent,
        )
    return True


async def upsert_zone(zone: SupplyDemandZone) -> bool:
    """Upsert into zones table (005_zones.sql)."""
    query = """
        INSERT INTO zones (
            zone_id, venue, symbol, timeframe, zone_type,
            top_price, bottom_price, created_at, strength,
            volume_profile, touches, is_active, tested_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
        ON CONFLICT (created_at, zone_id) DO UPDATE SET
            symbol = EXCLUDED.symbol,
            timeframe = EXCLUDED.timeframe,
            zone_type = EXCLUDED.zone_type,
            top_price = EXCLUDED.top_price,
            bottom_price = EXCLUDED.bottom_price,
            strength = EXCLUDED.strength,
            volume_profile = EXCLUDED.volume_profile,
            touches = EXCLUDED.touches,
            is_active = EXCLUDED.is_active,
            tested_at = EXCLUDED.tested_at
    """
    async with acquire_connection() as conn:
        await conn.execute(
            query,
            str(zone.zone_id),
            _DEFAULT_VENUE,
            zone.symbol,
            zone.timeframe.value,
            zone.zone_type.value,
            zone.top_price,
            zone.bottom_price,
            zone.created_at,
            int(zone.strength) if isinstance(zone.strength, (int,)) else zone.strength,
            zone.volume_profile,
            zone.touches,
            zone.is_active,
            zone.tested_at,
        )
    return True


def _to_decimal(val: Any) -> Decimal | None:
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    # Convert via str to avoid float precision issues
    return Decimal(str(val))


async def upsert_order(order: dict[str, Any]) -> bool:
    """Upsert an order; aligns parameter positions with unit tests.

    Uses unique key (venue, client_order_id) for conflict handling.
    """
    query = """
        INSERT INTO orders (
            order_id,
            client_order_id,
            venue,
            symbol,
            side,
            type,
            quantity,
            price,
            stop_price,
            status,
            filled_quantity,
            average_fill_price,
            created_at,
            decision_id,
            exchange_order_id,
            commission,
            commission_asset,
            last_update_time
        ) VALUES (
            COALESCE($1, gen_random_uuid()),
            $2,
            $3,
            $4,
            $5,
            $6,
            $7,
            $8,
            $9,
            COALESCE($10, 'NEW'),
            COALESCE($11, 0),
            $12,
            COALESCE($13, NOW()),
            $14,
            $15,
            COALESCE($16, 0),
            $17,
            $18
        )
        ON CONFLICT (venue, client_order_id) DO UPDATE SET
            status = COALESCE(EXCLUDED.status, orders.status),
            price = COALESCE(EXCLUDED.price, orders.price),
            filled_quantity = COALESCE(EXCLUDED.filled_quantity, orders.filled_quantity),
            average_fill_price = COALESCE(EXCLUDED.average_fill_price, orders.average_fill_price),
            commission = COALESCE(EXCLUDED.commission, orders.commission),
            commission_asset = COALESCE(EXCLUDED.commission_asset, orders.commission_asset),
            last_update_time = COALESCE(EXCLUDED.last_update_time, orders.last_update_time),
            updated_at = NOW()
    """
    values = [
        order.get("order_id"),
        order.get("client_order_id"),
        _DEFAULT_VENUE,
        order.get("symbol"),
        order.get("side"),
        order.get("type"),
        _to_decimal(order.get("quantity")),
        _to_decimal(order.get("price")),
        _to_decimal(order.get("stop_price")),
        order.get("status"),
        _to_decimal(order.get("filled_quantity", 0)),
        _to_decimal(order.get("average_fill_price")),
        order.get("created_at"),
        order.get("decision_id"),
        order.get("exchange_order_id"),
        _to_decimal(order.get("commission", 0)),
        order.get("commission_asset"),
        order.get("last_update_time"),
    ]
    async with acquire_connection() as conn:
        await conn.execute(query, *values)
    return True


async def get_active_positions(symbol: str | None = None) -> list[dict[str, Any]]:
    where = ["is_active = TRUE", "venue = $1"]
    params: list[Any] = [_DEFAULT_VENUE]
    if symbol:
        where.append("symbol = $2")
        params.append(symbol)
    query = (
        f"SELECT * FROM positions WHERE {' AND '.join(where)} ORDER BY opened_at DESC"
    )
    async with acquire_connection() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]
