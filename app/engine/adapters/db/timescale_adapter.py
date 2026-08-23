"""
TimescaleDB Adapter

Database adapter for TimescaleDB that handles time-series data storage and retrieval
for trading data including candles, indicators, signals, and trading events.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import logging
import os
from types import TracebackType
from typing import Any, NamedTuple
from uuid import uuid4

import asyncpg
from asyncpg import Pool

from ...models import (
    Candle,
    TechnicalIndicators,
    TimeFrame,
    TradingDecision,
)

logger = logging.getLogger(__name__)


class DuplicateGuardLookupError(RuntimeError):
    """Raised when duplicate-guard state cannot be read reliably."""


class PaperEquityComponents(NamedTuple):
    """Aggregated equity components from paper_positions."""

    total_fees: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_funding: Decimal


def _to_naive_utc(dt: datetime) -> datetime:
    """Convert datetime to naive UTC for asyncpg TIMESTAMP columns.

    asyncpg requires naive datetimes for TIMESTAMP WITHOUT TIME ZONE columns
    (which is what the candles table uses for open_time and close_time).

    This helper ensures tz-aware datetimes are converted to UTC then stripped,
    while naive datetimes pass through unchanged (assumed to already be UTC).

    Args:
        dt: datetime that may or may not have tzinfo. Naive datetimes are
            assumed to already be in UTC.

    Returns:
        Naive datetime in UTC
    """
    if dt.tzinfo is None:
        return dt
    # Convert to UTC then strip timezone
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.replace(tzinfo=None)


class TimescaleDBAdapter:
    """
    TimescaleDB adapter for storing and retrieving trading time-series data.

    Features:
    - Hypertable management for time-series data
    - Optimized queries for OHLCV data
    - Batch insert operations
    - Connection pooling
    - Automatic data retention policies
    """

    def __init__(  # noqa: PLR0913
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout

        # Backward-compatible single pool (write) and split pools
        self._pool: Pool | None = None  # write pool (legacy accessor)
        self._read_pool: Pool | None = None
        self._write_pool: Pool | None = None
        self._initialized = False

        logger.info(f"TimescaleDBAdapter configured for {host}:{port}/{database}")

    async def initialize(self) -> None:
        """Initialize the database connection pools.

        Schema is managed by SQL migrations (one-shot migrate), not by runtime auto-DDL.
        """
        if self._initialized:
            return

        try:
            # Create write pool (higher timeout)
            self._write_pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.username,
                password=self.password,
                min_size=1,
                max_size=self.pool_size,
                command_timeout=self.pool_timeout,
                statement_cache_size=1000,
            )
            # Keep legacy reference for get_connection
            self._pool = self._write_pool

            # Create read pool (tighter timeout)
            self._read_pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.username,
                password=self.password,
                min_size=1,
                max_size=self.pool_size,
                command_timeout=5,  # tightened for reads
                statement_cache_size=1000,
            )

            await self._ensure_migrations_applied()

            self._initialized = True
            logger.info("TimescaleDB adapter initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing TimescaleDB adapter: {e}")
            raise

    async def _ensure_migrations_applied(self) -> None:
        async with self.get_connection() as conn:
            schema_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.schemata
                    WHERE schema_name = '_migration'
                )
                """,
            )
            if not schema_exists:
                raise RuntimeError(
                    "Database schema is not migrated. "
                    "Run `app/engine/scripts/migrate_db.py` before starting services.",
                )

    async def close(self) -> None:
        """Close the database connection pool"""
        if self._read_pool:
            await self._read_pool.close()
            self._read_pool = None
        if self._write_pool:
            await self._write_pool.close()
            self._write_pool = None
        self._pool = None
        self._initialized = False
        logger.info("TimescaleDB adapter closed")

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[asyncpg.Connection]:
        """Get a database connection from the pool"""
        if not self._pool:
            raise RuntimeError("Database not initialized")

        async with self._pool.acquire() as connection:  # connection: asyncpg.Connection
            yield connection

    @asynccontextmanager
    async def get_read_connection(self) -> AsyncIterator[asyncpg.Connection]:
        """Acquire a connection from the read pool."""
        if not self._read_pool:
            raise RuntimeError("Database not initialized")
        async with self._read_pool.acquire() as connection:
            yield connection

    @asynccontextmanager
    async def get_write_connection(self) -> AsyncIterator[asyncpg.Connection]:
        """Acquire a connection from the write pool."""
        if not self._write_pool:
            raise RuntimeError("Database not initialized")
        async with self._write_pool.acquire() as connection:
            yield connection

    # ============================================================================
    # Candle Data Operations
    # ============================================================================

    async def insert_candle(self, candle: Candle) -> bool:
        """Insert a single candle using the canonical schema (db/migrations)."""
        try:
            async with self.get_write_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO candles (
                        venue, symbol, timeframe, open_time, close_time,
                        open_price, high_price, low_price, close_price,
                        volume, quote_volume, trades,
                        taker_buy_base_volume, taker_buy_quote_volume
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
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
                """,
                    candle.venue,
                    candle.symbol,
                    candle.timeframe.value,
                    _to_naive_utc(candle.open_time),
                    _to_naive_utc(candle.close_time),
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
            logger.error(f"Error inserting candle: {e}")
            return False

    async def insert_candles_batch(self, candles: list[Candle]) -> int:
        """Insert multiple candles in a batch"""
        if not candles:
            return 0

        try:
            # Choose COPY for large batches by threshold (env configurable)
            import os

            threshold = int(os.getenv("TIMESCALE_COPY_THRESHOLD", "1000"))
            if len(candles) >= threshold:
                return await self.insert_candles_copy(candles)

            async with self.get_write_connection() as conn:
                records = [
                    (
                        c.venue,
                        c.symbol,
                        c.timeframe.value,
                        _to_naive_utc(c.open_time),
                        _to_naive_utc(c.close_time),
                        c.open_price,
                        c.high_price,
                        c.low_price,
                        c.close_price,
                        c.volume,
                        c.quote_volume,
                        c.trades,
                        c.taker_buy_base_volume,
                        c.taker_buy_quote_volume,
                    )
                    for c in candles
                ]

                await conn.executemany(
                    """
                    INSERT INTO candles (
                        venue, symbol, timeframe, open_time, close_time,
                        open_price, high_price, low_price, close_price,
                        volume, quote_volume, trades,
                        taker_buy_base_volume, taker_buy_quote_volume
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    ON CONFLICT (venue, symbol, timeframe, open_time) DO NOTHING
                """,
                    records,
                )

                return len(candles)

        except Exception as e:
            logger.error(f"Error inserting candles batch: {e}")
            return 0

    # ============================================================================
    # External Captain Benchmark Operations
    # ============================================================================

    async def upsert_external_telegram_message(  # noqa: PLR0913
        self,
        *,
        source: str,
        chat_id: int,
        message_id: int,
        grouped_id: int | None,
        timestamp: datetime,
        text: str | None,
        has_photo: bool,
        photo_path: str | None,
        raw_json: dict[str, Any] | None,
    ) -> None:
        """Insert or update a raw external Telegram message record."""
        async with self.get_write_connection() as conn:
            await conn.execute(
                """
                INSERT INTO external_telegram_messages (
                    source,
                    chat_id,
                    message_id,
                    grouped_id,
                    timestamp,
                    text,
                    has_photo,
                    photo_path,
                    raw_json,
                    updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                ON CONFLICT (source, chat_id, message_id)
                DO UPDATE SET
                    grouped_id = EXCLUDED.grouped_id,
                    timestamp = EXCLUDED.timestamp,
                    text = EXCLUDED.text,
                    has_photo = EXCLUDED.has_photo,
                    photo_path = EXCLUDED.photo_path,
                    raw_json = EXCLUDED.raw_json,
                    updated_at = NOW();
            """,
                source,
                chat_id,
                message_id,
                grouped_id,
                timestamp,
                text,
                has_photo,
                photo_path,
                json.dumps(raw_json) if raw_json else None,
            )

    async def upsert_external_telegram_signal(  # noqa: PLR0913
        self,
        *,
        source: str,
        chat_id: int,
        message_id: int,
        timestamp: datetime,
        kind: str,
        strategy: str | None,
        symbol: str | None,
        timeframe: str | None,
        direction: str | None,
        entry_price: str | None,
        stop_loss: str | None,
        take_profits: list[str] | None,
        parse_confidence: float | None,
        parse_sources: list[str] | None,
        ocr_raw_text: str | None,
    ) -> None:
        """Insert or update a parsed external Telegram signal."""
        async with self.get_write_connection() as conn:
            await conn.execute(
                """
                INSERT INTO external_telegram_signals (
                    source,
                    chat_id,
                    message_id,
                    timestamp,
                    kind,
                    strategy,
                    symbol,
                    timeframe,
                    direction,
                    entry_price,
                    stop_loss,
                    take_profits,
                    parse_confidence,
                    parse_sources,
                    ocr_raw_text,
                    updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,NOW())
                ON CONFLICT (source, chat_id, message_id)
                DO UPDATE SET
                    timestamp = EXCLUDED.timestamp,
                    kind = EXCLUDED.kind,
                    strategy = EXCLUDED.strategy,
                    symbol = EXCLUDED.symbol,
                    timeframe = EXCLUDED.timeframe,
                    direction = EXCLUDED.direction,
                    entry_price = EXCLUDED.entry_price,
                    stop_loss = EXCLUDED.stop_loss,
                    take_profits = EXCLUDED.take_profits,
                    parse_confidence = EXCLUDED.parse_confidence,
                    parse_sources = EXCLUDED.parse_sources,
                    ocr_raw_text = EXCLUDED.ocr_raw_text,
                    updated_at = NOW();
            """,
                source,
                chat_id,
                message_id,
                timestamp,
                kind,
                strategy,
                symbol,
                timeframe,
                direction,
                entry_price,
                stop_loss,
                take_profits,
                parse_confidence,
                parse_sources,
                ocr_raw_text,
            )

    async def upsert_external_telegram_signal_validation(  # noqa: PLR0913
        self,
        *,
        source: str,
        chat_id: int,
        message_id: int,
        timestamp: datetime,
        internal_kind: str | None,
        internal_id: str | None,
        internal_timestamp: datetime | None,
        score: float,
        breakdown: dict[str, Any] | None,
    ) -> None:
        """Insert or update agreement scoring for an external Telegram signal."""
        async with self.get_write_connection() as conn:
            await conn.execute(
                """
                INSERT INTO external_telegram_signal_validations (
                    source,
                    chat_id,
                    message_id,
                    timestamp,
                    internal_kind,
                    internal_id,
                    internal_timestamp,
                    score,
                    breakdown,
                    updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW())
                ON CONFLICT (source, chat_id, message_id)
                DO UPDATE SET
                    timestamp = EXCLUDED.timestamp,
                    internal_kind = EXCLUDED.internal_kind,
                    internal_id = EXCLUDED.internal_id,
                    internal_timestamp = EXCLUDED.internal_timestamp,
                    score = EXCLUDED.score,
                    breakdown = EXCLUDED.breakdown,
                    updated_at = NOW();
            """,
                source,
                chat_id,
                message_id,
                timestamp,
                internal_kind,
                internal_id,
                internal_timestamp,
                score,
                json.dumps(breakdown) if breakdown is not None else None,
            )

    async def insert_outbound_alert_audit(  # noqa: PLR0913
        self,
        *,
        channel: str,
        alert_type: str,
        delivery_method: str,
        status: str,
        reason: str | None,
        chat_id: str | None,
        dedup_key: str | None,
        telegram_message_id: int | None,
        message_text: str | None,
        response_status: int | None,
        response_body: str | None,
        payload: dict[str, Any] | None,
        attempted_at: datetime,
    ) -> None:
        """Insert one immutable outbound alert audit row."""
        async with self.get_write_connection() as conn:
            await conn.execute(
                """
                INSERT INTO outbound_alert_audit (
                    attempted_at,
                    channel,
                    alert_type,
                    delivery_method,
                    status,
                    reason,
                    chat_id,
                    dedup_key,
                    telegram_message_id,
                    message_text,
                    response_status,
                    response_body,
                    payload
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                """,
                attempted_at,
                channel,
                alert_type,
                delivery_method,
                status,
                reason,
                chat_id,
                dedup_key,
                telegram_message_id,
                message_text,
                response_status,
                response_body,
                json.dumps(payload) if payload is not None else None,
            )

    async def get_external_telegram_signals(
        self,
        *,
        source: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> list[dict[Any, Any]]:
        """Get external Telegram signals for a source and time window."""
        try:
            async with self.get_read_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM external_telegram_signals
                    WHERE source = $1
                      AND timestamp >= $2
                      AND timestamp <= $3
                    ORDER BY timestamp DESC
                    LIMIT $4
                """,
                    source,
                    start_time,
                    end_time,
                    limit,
                )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error retrieving external telegram signals: {e}")
            return []

    async def get_external_telegram_signal_validations(
        self,
        *,
        source: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> list[dict[Any, Any]]:
        """Get external signal validations for a source and time window."""
        try:
            async with self.get_read_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM external_telegram_signal_validations
                    WHERE source = $1
                      AND timestamp >= $2
                      AND timestamp <= $3
                    ORDER BY timestamp DESC
                    LIMIT $4
                """,
                    source,
                    start_time,
                    end_time,
                    limit,
                )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error retrieving external telegram validations: {e}")
            return []

    async def insert_candles_copy(self, candles: list[Candle]) -> int:
        """Insert multiple candles using COPY for high throughput."""
        try:
            async with self.get_write_connection() as conn:
                columns = [
                    "venue",
                    "symbol",
                    "timeframe",
                    "open_time",
                    "close_time",
                    "open_price",
                    "high_price",
                    "low_price",
                    "close_price",
                    "volume",
                    "quote_volume",
                    "trades",
                    "taker_buy_base_volume",
                    "taker_buy_quote_volume",
                ]
                records = [
                    (
                        c.venue,
                        c.symbol,
                        c.timeframe.value,
                        _to_naive_utc(c.open_time),
                        _to_naive_utc(c.close_time),
                        c.open_price,
                        c.high_price,
                        c.low_price,
                        c.close_price,
                        c.volume,
                        c.quote_volume,
                        int(c.trades),
                        c.taker_buy_base_volume,
                        c.taker_buy_quote_volume,
                    )
                    for c in candles
                ]

                # asyncpg supports copy_records_to_table on connections
                await conn.copy_records_to_table(
                    "candles",
                    records=records,
                    columns=columns,
                )
                return len(candles)
        except Exception as e:
            logger.error(f"Error inserting candles via COPY: {e}")
            return 0

    async def get_latest_candle(
        self,
        symbol: str,
        timeframe: TimeFrame,
        venue: str | None = None,
    ) -> Candle | None:
        """
        Get the latest candle for a symbol and timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            venue: Trading venue (optional for backward compatibility)

        Returns:
            Latest candle or None if no data
        """
        candles = await self.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            venue=venue,
            limit=1,
        )
        return candles[0] if candles else None

    async def get_candles(  # noqa: PLR0913
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 1000,
        venue: str | None = None,
    ) -> list[Candle]:
        """Retrieve candles for a symbol and timeframe."""
        try:
            async with self.get_read_connection() as conn:
                query = """
                    SELECT
                        venue,
                        symbol,
                        timeframe,
                        open_time,
                        close_time,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                        volume,
                        quote_volume,
                        trades,
                        taker_buy_base_volume,
                        taker_buy_quote_volume
                    FROM candles
                    WHERE symbol = $1 AND timeframe = $2
                """
                params: list[Any] = [symbol, timeframe.value]

                if venue:
                    query += " AND venue = $" + str(len(params) + 1)
                    params.append(venue)

                if start_time:
                    query += " AND open_time >= $" + str(len(params) + 1)
                    params.append(start_time)

                if end_time:
                    query += " AND open_time <= $" + str(len(params) + 1)
                    params.append(end_time)

                query += " ORDER BY open_time DESC LIMIT $" + str(len(params) + 1)
                params.append(limit)

                rows = await conn.fetch(query, *params)

                candles = []
                for row in rows:
                    tf = TimeFrame(row["timeframe"])
                    candle = Candle(
                        venue=row["venue"],
                        symbol=row["symbol"],
                        timeframe=tf,
                        open_time=row["open_time"],
                        close_time=row["close_time"],
                        open_price=row["open_price"],
                        high_price=row["high_price"],
                        low_price=row["low_price"],
                        close_price=row["close_price"],
                        volume=row["volume"],
                        quote_volume=row["quote_volume"],
                        trades=row["trades"],
                        taker_buy_base_volume=row["taker_buy_base_volume"],
                        taker_buy_quote_volume=row["taker_buy_quote_volume"],
                    )
                    candles.append(candle)

                return list(reversed(candles))  # Return in chronological order

        except Exception as e:
            logger.error(f"Error retrieving candles: {e}")
            return []

    # ============================================================================
    # Technical Indicators Operations
    # ============================================================================

    async def insert_technical_indicators(
        self,
        venue: str,
        indicators: TechnicalIndicators,
    ) -> bool:
        """Insert technical indicators into the canonical indicators table."""
        try:
            async with self.get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO indicators (
                        venue, symbol, timeframe, timestamp,
                        ema_9, ema_21, ema_50, ema_200,
                        rsi_14, macd_line, macd_signal, macd_histogram, atr_14,
                        bb_upper, bb_middle, bb_lower, bb_width, bb_percent
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9,
                        $10, $11, $12, $13, $14, $15, $16, $17, $18
                    )
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
                """,
                    venue,
                    indicators.symbol,
                    indicators.timeframe.value,
                    indicators.timestamp,
                    indicators.ema_9,
                    indicators.ema_21,
                    indicators.ema_50,
                    indicators.ema_200,
                    indicators.rsi_14,
                    indicators.macd_line,
                    indicators.macd_signal,
                    indicators.macd_histogram,
                    indicators.atr_14,
                    indicators.bb_upper,
                    indicators.bb_middle,
                    indicators.bb_lower,
                    indicators.bb_width,
                    indicators.bb_percent,
                )
                return True

        except Exception as e:
            logger.error(f"Error inserting technical indicators: {e}")
            return False

    # ============================================================================
    # Trading Operations
    # ============================================================================

    async def insert_trading_decision(self, decision: TradingDecision) -> bool:
        """Insert a trading decision"""
        try:
            async with self.get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO trading_decisions (
                        decision_id, timestamp, symbol, action, entry_price, quantity, order_type,
                        stop_loss, take_profit, confidence, reasoning, risk_reward_ratio,
                        market_regime, news_sentiment, funding_rate_impact, volatility_filter, venue
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9,
                        $10, $11, $12, $13, $14, $15, $16, $17
                    )
                    ON CONFLICT (decision_id) DO NOTHING
                """,
                    decision.decision_id,
                    decision.timestamp,
                    decision.symbol,
                    decision.action,
                    decision.entry_price,
                    decision.quantity,
                    decision.order_type.value if decision.order_type else None,
                    decision.stop_loss,
                    decision.take_profit,
                    decision.confidence,
                    decision.reasoning,
                    decision.risk_reward_ratio,
                    decision.market_regime.value if decision.market_regime else None,
                    decision.news_sentiment,
                    decision.funding_rate_impact,
                    decision.volatility_filter,
                    decision.venue,
                )
                return True

        except Exception as e:
            logger.error(f"Error inserting trading decision: {e}")
            return False

    async def get_execution_intent_for_request(
        self,
        idempotency_key: str,
        *,
        venue: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Load and hash-verify an existing execution intent for a replay request."""
        payload_json = json.dumps(request_payload, sort_keys=True, default=str)
        request_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT request_hash, request_payload, response_payload, state
                FROM execution_intents
                WHERE venue = $1 AND idempotency_key = $2
                """,
                venue,
                idempotency_key,
            )
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise RuntimeError(
                f"execution intent request hash mismatch for idempotency_key={idempotency_key}"
            )

        def _normalize_json_object(value: Any, field_name: str) -> dict[str, Any] | None:
            if value is None:
                return None
            if isinstance(value, (str, bytes, bytearray)):
                try:
                    value = json.loads(value)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"execution intent {field_name} payload is malformed"
                    ) from exc
            if not isinstance(value, dict):
                raise RuntimeError(f"execution intent {field_name} payload is malformed")
            return value

        stored_request_payload = _normalize_json_object(row["request_payload"], "request")
        if stored_request_payload is None:
            raise RuntimeError("execution intent request payload is malformed")
        return {
            "request_payload": stored_request_payload,
            "response_payload": _normalize_json_object(row["response_payload"], "response"),
            "state": row["state"],
        }

    async def prepare_execution_intent(self, intent: dict[str, Any]) -> bool:
        """Persist PREPARED before the router can submit to the exchange."""
        try:
            payload_json = json.dumps(intent["request_payload"], sort_keys=True, default=str)
            request_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            async with self.get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO execution_intents (
                        idempotency_key, decision_id, signal_id, venue, symbol,
                        request_hash, request_payload, state
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,'PREPARED')
                    ON CONFLICT (venue, idempotency_key) DO NOTHING
                    """,
                    intent["idempotency_key"],
                    intent["decision_id"],
                    intent.get("signal_id"),
                    intent["venue"],
                    intent["symbol"],
                    request_hash,
                    payload_json,
                )
                row = await conn.fetchrow(
                    """
                    SELECT request_hash, state
                    FROM execution_intents
                    WHERE venue = $1 AND idempotency_key = $2
                    """,
                    intent["venue"],
                    intent["idempotency_key"],
                )
            return bool(
                row
                and row["request_hash"] == request_hash
                and row["state"] in {"PREPARED", "SUBMITTING", "AMBIGUOUS"}
            )
        except Exception:
            logger.exception(
                "Error preparing execution intent: idempotency_key=%s",
                intent.get("idempotency_key"),
            )
            return False

    async def transition_execution_intent(
        self,
        idempotency_key: str,
        state: str,
        *,
        venue: str,
        response_payload: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Apply a guarded durable execution-intent state transition."""
        expected_states = {
            "SUBMITTING": ("PREPARED", "SUBMITTING", "AMBIGUOUS"),
            "ACKNOWLEDGED": ("SUBMITTING",),
            "REJECTED": ("PREPARED", "SUBMITTING"),
            "AMBIGUOUS": ("PREPARED", "SUBMITTING"),
        }
        expected = expected_states.get(state)
        if expected is None:
            return False
        try:
            response_json = (
                json.dumps(response_payload, sort_keys=True, default=str)
                if response_payload is not None
                else None
            )
            async with self.get_connection() as conn:
                result = await conn.execute(
                    """
                    UPDATE execution_intents
                    SET state = $3,
                        response_payload = COALESCE($4::jsonb, response_payload),
                        error_message = COALESCE($5, error_message),
                        recovery_lease_expires_at = CASE
                            WHEN $3 = ANY(ARRAY['ACKNOWLEDGED', 'REJECTED']::text[])
                            THEN NULL
                            WHEN $3 = 'AMBIGUOUS'
                            THEN COALESCE(
                                recovery_lease_expires_at,
                                CURRENT_TIMESTAMP + INTERVAL '60 seconds'
                            )
                            ELSE recovery_lease_expires_at
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE venue = $1
                      AND idempotency_key = $2
                      AND state = ANY($6::text[])
                    """,
                    venue,
                    idempotency_key,
                    state,
                    response_json,
                    error_message,
                    list(expected),
                )
            return result == "UPDATE 1"
        except Exception:
            logger.exception(
                "Error transitioning execution intent: idempotency_key=%s state=%s",
                idempotency_key,
                state,
            )
            return False

    async def claim_next_execution_intent_recovery(
        self,
        *,
        venue: str,
    ) -> dict[str, Any] | None:
        """Claim one stale incomplete execution intent for restart recovery."""
        async with self.get_write_connection() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                WITH candidate AS (
                    SELECT idempotency_key
                    FROM execution_intents
                    WHERE venue = $1
                      AND state IN ('SUBMITTING', 'AMBIGUOUS')
                      AND (
                          recovery_lease_expires_at IS NULL
                          OR recovery_lease_expires_at <= CURRENT_TIMESTAMP
                      )
                      AND (
                          state = 'AMBIGUOUS'
                          OR updated_at <= CURRENT_TIMESTAMP - INTERVAL '5 seconds'
                      )
                    ORDER BY updated_at ASC, idempotency_key ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE execution_intents AS intent
                SET recovery_attempts = intent.recovery_attempts + 1,
                    recovery_lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '60 seconds',
                    updated_at = CURRENT_TIMESTAMP
                FROM candidate
                WHERE intent.venue = $1
                  AND intent.idempotency_key = candidate.idempotency_key
                RETURNING intent.idempotency_key,
                          intent.venue,
                          intent.state,
                          intent.request_payload
                """,
                venue,
            )
        if row is None:
            return None
        request_payload = row["request_payload"]
        if isinstance(request_payload, (str, bytes, bytearray)):
            try:
                request_payload = json.loads(request_payload)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    "execution intent recovery request payload is malformed"
                ) from exc
        if not isinstance(request_payload, dict):
            raise RuntimeError("execution intent recovery request payload is malformed")
        return {
            "idempotency_key": row["idempotency_key"],
            "venue": row["venue"],
            "state": row["state"],
            "request_payload": request_payload,
        }

    async def has_incomplete_execution_intent_outside_venue(self, active_venue: str) -> bool:
        """Return whether another venue has an incomplete execution intent."""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM execution_intents
                    WHERE venue <> $1
                      AND state = ANY($2::text[])
                ) AS has_incomplete_intent
                """,
                active_venue,
                ["SUBMITTING", "AMBIGUOUS"],
            )
        return bool(row and row["has_incomplete_intent"])

    async def claim_order_update_inbox(
        self,
        *,
        event_id: str,
        aggregate_id: str,
        sequence: int,
        event_version: int,
        payload: dict[str, Any],
        payload_hash: str,
    ) -> str:
        """Insert and exclusively claim one ordered, idempotent inbox event."""
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        async with self.get_write_connection() as conn, conn.transaction():
            await conn.execute(
                """
                INSERT INTO engine_order_update_inbox (
                    event_id, aggregate_id, sequence, event_version, payload, payload_hash
                ) VALUES ($1::uuid,$2,$3,$4,$5::jsonb,$6)
                ON CONFLICT DO NOTHING
                """,
                event_id,
                aggregate_id,
                sequence,
                event_version,
                payload_json,
                payload_hash,
            )
            row = await conn.fetchrow(
                """
                SELECT event_id::text, payload_hash, state, processing_started_at
                FROM engine_order_update_inbox
                WHERE event_id = $1::uuid OR (aggregate_id = $2 AND sequence = $3)
                FOR UPDATE
                """,
                event_id,
                aggregate_id,
                sequence,
            )
            if row is None or row["event_id"] != event_id or row["payload_hash"] != payload_hash:
                return "CONFLICT"
            if row["state"] == "PROCESSED":
                return "DUPLICATE"
            if (
                row["state"] == "PROCESSING"
                and row["processing_started_at"] is not None
                and row["processing_started_at"] > datetime.now(UTC) - timedelta(seconds=60)
            ):
                return "IN_PROGRESS"

            prior = await conn.fetchrow(
                """
                SELECT sequence, payload
                FROM engine_order_update_inbox
                WHERE aggregate_id = $1 AND state = 'PROCESSED' AND sequence < $2
                ORDER BY sequence DESC LIMIT 1
                """,
                aggregate_id,
                sequence,
            )
            expected_sequence = 1 if prior is None else int(prior["sequence"]) + 1
            if sequence != expected_sequence:
                await conn.execute(
                    """
                    UPDATE engine_order_update_inbox
                    SET state = 'PARKED', last_error = $2
                    WHERE event_id = $1::uuid
                    """,
                    event_id,
                    f"sequence gap: expected {expected_sequence}, got {sequence}",
                )
                return "GAP"

            from ...execution.order_update_inbox import is_terminal_transition_allowed

            prior_payload = None if prior is None else prior["payload"]
            if isinstance(prior_payload, (str, bytes, bytearray)):
                try:
                    prior_payload = json.loads(prior_payload)
                except (TypeError, ValueError):
                    prior_payload = {}
            if not isinstance(prior_payload, dict):
                prior_payload = {} if prior is not None else None

            if not is_terminal_transition_allowed(prior_payload, payload):
                await conn.execute(
                    """
                    UPDATE engine_order_update_inbox
                    SET state = 'PARKED', last_error = 'terminal state regression'
                    WHERE event_id = $1::uuid
                    """,
                    event_id,
                )
                return "REGRESSION"

            await conn.execute(
                """
                UPDATE engine_order_update_inbox
                SET state = 'PROCESSING', processing_started_at = CURRENT_TIMESTAMP,
                    last_error = NULL
                WHERE event_id = $1::uuid
                """,
                event_id,
            )
            return "CLAIMED"

    async def complete_order_update_inbox(self, *, event_id: str) -> None:
        async with self.get_write_connection() as conn:
            result = await conn.execute(
                """
                UPDATE engine_order_update_inbox
                SET state = 'PROCESSED', processed_at = CURRENT_TIMESTAMP, last_error = NULL
                WHERE event_id = $1::uuid AND state = 'PROCESSING'
                """,
                event_id,
            )
        if result != "UPDATE 1":
            raise RuntimeError(f"inbox event {event_id} was not processing")

    async def fail_order_update_inbox(self, *, event_id: str, error_message: str) -> None:
        async with self.get_write_connection() as conn:
            await conn.execute(
                """
                UPDATE engine_order_update_inbox
                SET state = 'FAILED', last_error = $2
                WHERE event_id = $1::uuid AND state = 'PROCESSING'
                """,
                event_id,
                error_message[:1000],
            )

    async def _upsert_order_with_connection(
        self,
        conn: asyncpg.Connection,
        order: dict[str, Any],
    ) -> None:
        """Upsert one order row on a supplied connection without swallowing errors."""

        def _to_decimal(val: Any) -> Decimal | None:
            if val is None:
                return None
            if isinstance(val, Decimal):
                return val
            return Decimal(str(val))

        venue = order.get("venue")
        client_order_id = order.get("client_order_id")
        symbol = order.get("symbol")
        side = order.get("side")
        order_type = order.get("type")
        quantity = _to_decimal(order.get("quantity"))

        if not isinstance(venue, str) or not venue:
            raise ValueError("order.venue is required")
        if not isinstance(client_order_id, str) or not client_order_id:
            raise ValueError("order.client_order_id is required")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("order.symbol is required")
        if not isinstance(side, str) or not side:
            raise ValueError("order.side is required")
        if not isinstance(order_type, str) or not order_type:
            raise ValueError("order.type is required")
        if quantity is None or quantity <= 0:
            raise ValueError("order.quantity must be > 0")

        zone = order.get("zone")
        zone_json = json.dumps(zone) if zone is not None else None

        await conn.execute(
            """
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
                last_update_time,
                reject_reason,
                signal_id,
                timeframe,
                zone
            ) VALUES (
                COALESCE($1::uuid, gen_random_uuid()),
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9,
                COALESCE($10, 'NEW'),
                COALESCE($11::numeric, 0::numeric),
                $12,
                COALESCE($13, NOW()),
                $14,
                $15,
                COALESCE($16::numeric, 0::numeric),
                $17,
                $18,
                $19,
                $20,
                $21,
                $22::jsonb
            )
            ON CONFLICT (venue, client_order_id) DO UPDATE SET
                symbol = COALESCE(EXCLUDED.symbol, orders.symbol),
                side = COALESCE(EXCLUDED.side, orders.side),
                type = COALESCE(EXCLUDED.type, orders.type),
                quantity = COALESCE(EXCLUDED.quantity, orders.quantity),
                price = COALESCE(EXCLUDED.price, orders.price),
                stop_price = COALESCE(EXCLUDED.stop_price, orders.stop_price),
                status = CASE
                    WHEN orders.status IN ('FILLED', 'REJECTED') THEN orders.status
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED')
                        AND EXCLUDED.status = 'FILLED'
                        AND EXCLUDED.filled_quantity = EXCLUDED.quantity
                        AND EXCLUDED.filled_quantity > orders.filled_quantity
                        AND EXCLUDED.last_update_time IS NOT NULL
                        AND orders.last_update_time IS NOT NULL
                        AND EXCLUDED.last_update_time >= orders.last_update_time
                        THEN EXCLUDED.status
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED') THEN orders.status
                    WHEN orders.status = 'PARTIALLY_FILLED' AND EXCLUDED.status = 'NEW' THEN orders.status
                    WHEN $10 IS NULL THEN orders.status
                    WHEN orders.last_update_time IS NOT NULL
                        AND ($18 IS NULL OR $18 < orders.last_update_time) THEN orders.status
                    ELSE EXCLUDED.status
                END,
                filled_quantity = CASE
                    WHEN orders.status IN ('FILLED', 'REJECTED') THEN orders.filled_quantity
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED')
                        AND NOT (
                            EXCLUDED.status = 'FILLED'
                            AND EXCLUDED.filled_quantity = EXCLUDED.quantity
                            AND EXCLUDED.filled_quantity > orders.filled_quantity
                            AND EXCLUDED.last_update_time IS NOT NULL
                            AND orders.last_update_time IS NOT NULL
                            AND EXCLUDED.last_update_time >= orders.last_update_time
                        ) THEN orders.filled_quantity
                    WHEN $11::numeric IS NULL THEN orders.filled_quantity
                    WHEN orders.last_update_time IS NOT NULL
                        AND ($18 IS NULL OR $18 < orders.last_update_time) THEN orders.filled_quantity
                    ELSE GREATEST(EXCLUDED.filled_quantity, orders.filled_quantity)
                END,
                average_fill_price = CASE
                    WHEN orders.status = 'REJECTED' THEN orders.average_fill_price
                    WHEN orders.status = 'FILLED' THEN CASE
                        WHEN EXCLUDED.status = 'FILLED'
                            AND EXCLUDED.filled_quantity = orders.filled_quantity
                            AND EXCLUDED.average_fill_price IS NOT NULL
                            AND EXCLUDED.average_fill_price > 0
                            AND EXCLUDED.last_update_time IS NOT NULL
                            AND (orders.last_update_time IS NULL OR EXCLUDED.last_update_time > orders.last_update_time)
                            THEN EXCLUDED.average_fill_price
                        ELSE orders.average_fill_price
                    END
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED')
                        AND NOT (
                            EXCLUDED.status = 'FILLED'
                            AND EXCLUDED.filled_quantity = EXCLUDED.quantity
                            AND EXCLUDED.filled_quantity > orders.filled_quantity
                            AND EXCLUDED.last_update_time IS NOT NULL
                            AND orders.last_update_time IS NOT NULL
                            AND EXCLUDED.last_update_time >= orders.last_update_time
                        ) THEN orders.average_fill_price
                    WHEN $12::numeric IS NULL THEN orders.average_fill_price
                    WHEN orders.last_update_time IS NOT NULL
                        AND ($18 IS NULL OR $18 < orders.last_update_time) THEN orders.average_fill_price
                    ELSE COALESCE(EXCLUDED.average_fill_price, orders.average_fill_price)
                END,
                decision_id = COALESCE(EXCLUDED.decision_id, orders.decision_id),
                exchange_order_id = COALESCE(EXCLUDED.exchange_order_id, orders.exchange_order_id),
                commission = CASE
                    WHEN $16::numeric IS NULL THEN orders.commission
                    WHEN orders.last_update_time IS NOT NULL
                        AND ($18 IS NULL OR $18 < orders.last_update_time) THEN orders.commission
                    ELSE GREATEST(EXCLUDED.commission, orders.commission)
                END,
                commission_asset = COALESCE(EXCLUDED.commission_asset, orders.commission_asset),
                last_update_time = CASE
                    WHEN orders.status = 'REJECTED' THEN orders.last_update_time
                    WHEN orders.status = 'FILLED' THEN CASE
                        WHEN EXCLUDED.status = 'FILLED'
                            AND EXCLUDED.filled_quantity = orders.filled_quantity
                            AND EXCLUDED.average_fill_price IS NOT NULL
                            AND EXCLUDED.average_fill_price > 0
                            AND EXCLUDED.last_update_time IS NOT NULL
                            AND (orders.last_update_time IS NULL OR EXCLUDED.last_update_time > orders.last_update_time)
                            THEN EXCLUDED.last_update_time
                        ELSE orders.last_update_time
                    END
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED')
                        AND NOT (
                            EXCLUDED.status = 'FILLED'
                            AND EXCLUDED.filled_quantity = EXCLUDED.quantity
                            AND EXCLUDED.filled_quantity > orders.filled_quantity
                            AND EXCLUDED.last_update_time IS NOT NULL
                            AND orders.last_update_time IS NOT NULL
                            AND EXCLUDED.last_update_time >= orders.last_update_time
                        ) THEN orders.last_update_time
                    WHEN $18 IS NULL THEN orders.last_update_time
                    WHEN orders.last_update_time IS NULL THEN EXCLUDED.last_update_time
                    ELSE GREATEST(EXCLUDED.last_update_time, orders.last_update_time)
                END,
                reject_reason = CASE
                    WHEN orders.status IN ('FILLED', 'REJECTED') THEN orders.reject_reason
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED')
                        THEN CASE
                            WHEN EXCLUDED.status = 'FILLED'
                                AND EXCLUDED.filled_quantity = EXCLUDED.quantity
                                AND EXCLUDED.filled_quantity > orders.filled_quantity
                                AND EXCLUDED.last_update_time IS NOT NULL
                                AND orders.last_update_time IS NOT NULL
                                AND EXCLUDED.last_update_time >= orders.last_update_time
                                THEN NULL
                            ELSE orders.reject_reason
                        END
                    WHEN orders.last_update_time IS NOT NULL
                        AND ($18 IS NULL OR $18 < orders.last_update_time) THEN orders.reject_reason
                    ELSE COALESCE(EXCLUDED.reject_reason, orders.reject_reason)
                END,
                signal_id = COALESCE(EXCLUDED.signal_id, orders.signal_id),
                timeframe = COALESCE(EXCLUDED.timeframe, orders.timeframe),
                zone = COALESCE(EXCLUDED.zone, orders.zone),
                updated_at = NOW()
            """,
            order.get("order_id"),
            client_order_id,
            venue,
            symbol,
            side,
            order_type,
            quantity,
            _to_decimal(order.get("price")),
            _to_decimal(order.get("stop_price")),
            order.get("status"),
            _to_decimal(order.get("filled_quantity", 0)),
            _to_decimal(order.get("average_fill_price")),
            order.get("created_at"),
            order.get("decision_id"),
            order.get("exchange_order_id"),
            _to_decimal(order.get("commission")),
            order.get("commission_asset"),
            order.get("last_update_time"),
            order.get("reject_reason"),
            order.get("signal_id"),
            order.get("timeframe"),
            zone_json,
        )

    async def upsert_order(self, order: dict[str, Any]) -> bool:
        """Upsert an order row using unique key (venue, client_order_id)."""
        try:
            async with self.get_connection() as conn:
                await self._upsert_order_with_connection(conn, order)
            return True
        except Exception:
            logger.exception(
                "Error upserting order: client_order_id=%s", order.get("client_order_id")
            )
            return False

    async def upsert_order_update(self, order: dict[str, Any]) -> bool:
        async with self.get_write_connection() as conn, conn.transaction():
            await self._upsert_order_update_with_connection(conn, order)
        return True

    async def _upsert_order_update_with_connection(
        self,
        conn: asyncpg.Connection,
        order: dict[str, Any],
    ) -> None:
        def _to_decimal(value: Any) -> Decimal | None:
            if value is None:
                return None
            if isinstance(value, Decimal):
                return value
            return Decimal(str(value))

        venue = order.get("venue")
        client_order_id = order.get("client_order_id")
        symbol = order.get("symbol")
        side = order.get("side")
        order_type = order.get("type")
        quantity = _to_decimal(order.get("quantity"))
        price = _to_decimal(order.get("price"))
        stop_price = _to_decimal(order.get("stop_price"))
        exchange_order_id = order.get("exchange_order_id")
        if exchange_order_id is not None:
            exchange_order_id = str(exchange_order_id).strip() or None

        if not isinstance(venue, str) or not venue:
            raise ValueError("order.venue is required")
        if not isinstance(client_order_id, str) or not client_order_id:
            raise ValueError("order.client_order_id is required")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("order.symbol is required")
        if not isinstance(side, str) or not side:
            raise ValueError("order.side is required")
        if not isinstance(order_type, str) or not order_type:
            raise ValueError("order.type is required")
        if quantity is None or quantity <= 0:
            raise ValueError("order.quantity must be > 0")

        zone = order.get("zone")
        zone_json = (
            json.dumps(zone, sort_keys=True, separators=(",", ":"), default=str)
            if zone is not None
            else None
        )
        await conn.execute(
            """
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
                last_update_time,
                reject_reason,
                signal_id,
                timeframe,
                zone
            ) VALUES (
                COALESCE($1::uuid, gen_random_uuid()),
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9,
                COALESCE($10, 'NEW'),
                COALESCE($11::numeric, 0::numeric),
                $12,
                COALESCE($13, NOW()),
                $14,
                $15,
                COALESCE($16::numeric, 0::numeric),
                $17,
                $18,
                $19,
                $20,
                $21,
                $22::jsonb
            )
            ON CONFLICT (venue, client_order_id) DO NOTHING
            """,
            order.get("order_id"),
            client_order_id,
            venue,
            symbol,
            side,
            order_type,
            quantity,
            price,
            stop_price,
            order.get("status"),
            _to_decimal(order.get("filled_quantity", 0)),
            _to_decimal(order.get("average_fill_price")),
            order.get("created_at"),
            order.get("decision_id"),
            exchange_order_id,
            _to_decimal(order.get("commission")),
            order.get("commission_asset"),
            order.get("last_update_time"),
            order.get("reject_reason"),
            order.get("signal_id"),
            order.get("timeframe"),
            zone_json,
        )

        existing = await conn.fetchrow(
            """
            SELECT order_id, venue, client_order_id, symbol, side, type,
                   quantity, price, stop_price, decision_id, signal_id,
                   timeframe, zone, exchange_order_id
            FROM orders
            WHERE venue = $1 AND client_order_id = $2
            FOR UPDATE
            """,
            venue,
            client_order_id,
        )
        if existing is None:
            raise RuntimeError("order projection was not available after insert")

        identity_values = {
            "venue": (venue, existing["venue"]),
            "client_order_id": (client_order_id, existing["client_order_id"]),
            "symbol": (symbol.strip().upper(), str(existing["symbol"]).strip().upper()),
            "side": (side.strip().upper(), str(existing["side"]).strip().upper()),
            "type": (order_type.strip().upper(), str(existing["type"]).strip().upper()),
            "quantity": (quantity, _to_decimal(existing["quantity"])),
            "price": (price, _to_decimal(existing["price"])),
            "stop_price": (stop_price, _to_decimal(existing["stop_price"])),
        }
        for field_name, (expected, actual) in identity_values.items():
            if expected != actual:
                raise RuntimeError(f"order identity conflict for {field_name}")

        existing_decision_id = existing["decision_id"]
        incoming_decision_id = order.get("decision_id")
        if (
            existing_decision_id is not None
            and incoming_decision_id is not None
            and str(existing_decision_id) != str(incoming_decision_id)
        ):
            raise RuntimeError("order identity conflict for decision_id")
        existing_signal_id = existing["signal_id"]
        incoming_signal_id = order.get("signal_id")
        if (
            existing_signal_id is not None
            and incoming_signal_id is not None
            and str(existing_signal_id) != str(incoming_signal_id)
        ):
            raise RuntimeError("order identity conflict for signal_id")
        existing_timeframe = existing["timeframe"]
        incoming_timeframe = order.get("timeframe")
        if (
            existing_timeframe is not None
            and incoming_timeframe is not None
            and str(existing_timeframe) != str(incoming_timeframe)
        ):
            raise RuntimeError("order identity conflict for timeframe")

        def _canonical_zone(value: Any) -> str | None:
            if value is None:
                return None
            if isinstance(value, (str, bytes, bytearray)):
                try:
                    value = json.loads(value)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError("order identity conflict for zone") from exc
            if not isinstance(value, dict):
                raise RuntimeError("order identity conflict for zone")
            return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

        existing_zone = _canonical_zone(existing["zone"])
        incoming_zone = _canonical_zone(zone)
        if (
            existing_zone is not None
            and incoming_zone is not None
            and existing_zone != incoming_zone
        ):
            raise RuntimeError("order identity conflict for zone")

        existing_exchange_order_id = str(existing["exchange_order_id"] or "").strip()
        incoming_exchange_order_id = str(exchange_order_id or "").strip()
        if (
            existing_exchange_order_id
            and incoming_exchange_order_id
            and existing_exchange_order_id != incoming_exchange_order_id
        ):
            raise RuntimeError("order identity conflict for exchange_order_id")
        if incoming_exchange_order_id and incoming_exchange_order_id != existing_exchange_order_id:
            owner = await conn.fetchval(
                """
                SELECT order_id
                FROM orders
                WHERE venue = $1
                  AND symbol = $2
                  AND exchange_order_id = $3
                  AND order_id <> $4
                FOR UPDATE
                """,
                venue,
                symbol,
                incoming_exchange_order_id,
                existing["order_id"],
            )
            if owner is not None:
                raise RuntimeError("order identity conflict for exchange_order_id ownership")

        await conn.execute(
            """
            UPDATE orders
            SET status = CASE
                    WHEN orders.status IN ('FILLED', 'REJECTED') THEN orders.status
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED')
                        AND $1 = 'FILLED'
                        AND $2::numeric = orders.quantity
                        AND $2::numeric > orders.filled_quantity
                        AND $3::timestamptz IS NOT NULL
                        AND orders.last_update_time IS NOT NULL
                        AND $3::timestamptz >= orders.last_update_time
                        THEN 'FILLED'
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED') THEN orders.status
                    WHEN orders.status = 'PARTIALLY_FILLED' AND $1 = 'NEW' THEN orders.status
                    WHEN $1 IS NULL THEN orders.status
                    WHEN orders.last_update_time IS NOT NULL
                        AND ($3::timestamptz IS NULL OR $3::timestamptz < orders.last_update_time) THEN orders.status
                    ELSE $1
                END,
                filled_quantity = CASE
                    WHEN orders.status IN ('FILLED', 'REJECTED') THEN orders.filled_quantity
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED')
                        AND NOT (
                            $1 = 'FILLED'
                            AND $2::numeric = orders.quantity
                            AND $2::numeric > orders.filled_quantity
                            AND $3::timestamptz IS NOT NULL
                            AND orders.last_update_time IS NOT NULL
                            AND $3::timestamptz >= orders.last_update_time
                        ) THEN orders.filled_quantity
                    WHEN $2::numeric IS NULL THEN orders.filled_quantity
                    WHEN orders.last_update_time IS NOT NULL
                        AND ($3::timestamptz IS NULL OR $3::timestamptz < orders.last_update_time) THEN orders.filled_quantity
                    ELSE GREATEST($2::numeric, orders.filled_quantity)
                END,
                average_fill_price = CASE
                    WHEN orders.status = 'REJECTED' THEN orders.average_fill_price
                    WHEN orders.status = 'FILLED' THEN CASE
                        WHEN $1 = 'FILLED'
                            AND $2::numeric = orders.filled_quantity
                            AND $4::numeric IS NOT NULL
                            AND $4::numeric > 0
                            AND $3::timestamptz IS NOT NULL
                            AND (orders.last_update_time IS NULL OR $3::timestamptz > orders.last_update_time)
                            THEN $4::numeric
                        ELSE orders.average_fill_price
                    END
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED')
                        AND NOT (
                            $1 = 'FILLED'
                            AND $2::numeric = orders.quantity
                            AND $2::numeric > orders.filled_quantity
                            AND $3::timestamptz IS NOT NULL
                            AND orders.last_update_time IS NOT NULL
                            AND $3::timestamptz >= orders.last_update_time
                        ) THEN orders.average_fill_price
                    WHEN $4::numeric IS NULL THEN orders.average_fill_price
                    WHEN orders.last_update_time IS NOT NULL
                        AND ($3::timestamptz IS NULL OR $3::timestamptz < orders.last_update_time) THEN orders.average_fill_price
                    ELSE COALESCE($4::numeric, orders.average_fill_price)
                END,
                exchange_order_id = COALESCE(NULLIF($5, ''), orders.exchange_order_id),
                decision_id = COALESCE(orders.decision_id, $6),
                signal_id = COALESCE(orders.signal_id, $7),
                timeframe = COALESCE(orders.timeframe, $8),
                zone = COALESCE(orders.zone, $9::jsonb),
                commission = CASE
                    WHEN $10::numeric IS NULL THEN orders.commission
                    WHEN orders.last_update_time IS NOT NULL
                        AND ($3::timestamptz IS NULL OR $3::timestamptz < orders.last_update_time) THEN orders.commission
                    ELSE GREATEST($10::numeric, orders.commission)
                END,
                commission_asset = COALESCE($11, orders.commission_asset),
                last_update_time = CASE
                    WHEN orders.status = 'REJECTED' THEN orders.last_update_time
                    WHEN orders.status = 'FILLED' THEN CASE
                        WHEN $1 = 'FILLED'
                            AND $2::numeric = orders.filled_quantity
                            AND $4::numeric IS NOT NULL
                            AND $4::numeric > 0
                            AND $3::timestamptz IS NOT NULL
                            AND (orders.last_update_time IS NULL OR $3::timestamptz > orders.last_update_time)
                            THEN $3::timestamptz
                        ELSE orders.last_update_time
                    END
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED')
                        AND NOT (
                            $1 = 'FILLED'
                            AND $2::numeric = orders.quantity
                            AND $2::numeric > orders.filled_quantity
                            AND $3::timestamptz IS NOT NULL
                            AND orders.last_update_time IS NOT NULL
                            AND $3::timestamptz >= orders.last_update_time
                        ) THEN orders.last_update_time
                    WHEN $3::timestamptz IS NULL THEN orders.last_update_time
                    WHEN orders.last_update_time IS NULL THEN $3::timestamptz
                    ELSE GREATEST($3::timestamptz, orders.last_update_time)
                END,
                reject_reason = CASE
                    WHEN orders.status IN ('FILLED', 'REJECTED') THEN orders.reject_reason
                    WHEN orders.status IN ('CANCELED', 'CANCELLED', 'EXPIRED')
                        THEN CASE
                            WHEN $1 = 'FILLED'
                                AND $2::numeric = orders.quantity
                                AND $2::numeric > orders.filled_quantity
                                AND $3::timestamptz IS NOT NULL
                                AND orders.last_update_time IS NOT NULL
                                AND $3::timestamptz >= orders.last_update_time
                                THEN NULL
                            ELSE orders.reject_reason
                        END
                    WHEN orders.last_update_time IS NOT NULL
                        AND ($3::timestamptz IS NULL OR $3::timestamptz < orders.last_update_time) THEN orders.reject_reason
                    ELSE COALESCE($12, orders.reject_reason)
                END,
                updated_at = NOW()
            WHERE order_id = $13
            """,
            order.get("status"),
            _to_decimal(order.get("filled_quantity", 0)),
            order.get("last_update_time"),
            _to_decimal(order.get("average_fill_price")),
            incoming_exchange_order_id,
            incoming_decision_id,
            incoming_signal_id,
            incoming_timeframe,
            zone_json,
            _to_decimal(order.get("commission")),
            order.get("commission_asset"),
            order.get("reject_reason"),
            existing["order_id"],
        )

    async def _insert_or_validate_order_with_connection(
        self,
        conn: asyncpg.Connection,
        order: dict[str, Any],
    ) -> None:
        """Adopt an ACK projection only when its immutable identity matches."""

        def _to_decimal(val: Any) -> Decimal | None:
            if val is None:
                return None
            if isinstance(val, Decimal):
                return val
            return Decimal(str(val))

        venue = order.get("venue")
        client_order_id = order.get("client_order_id")
        symbol = order.get("symbol")
        side = order.get("side")
        order_type = order.get("type")
        quantity = _to_decimal(order.get("quantity"))
        price = _to_decimal(order.get("price"))
        stop_price = _to_decimal(order.get("stop_price"))

        if not isinstance(venue, str) or not venue:
            raise ValueError("order.venue is required")
        if not isinstance(client_order_id, str) or not client_order_id:
            raise ValueError("order.client_order_id is required")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("order.symbol is required")
        if not isinstance(side, str) or not side:
            raise ValueError("order.side is required")
        if not isinstance(order_type, str) or not order_type:
            raise ValueError("order.type is required")
        if quantity is None or quantity <= 0:
            raise ValueError("order.quantity must be > 0")

        zone = order.get("zone")
        zone_json = (
            json.dumps(zone, sort_keys=True, separators=(",", ":"), default=str)
            if zone is not None
            else None
        )
        await conn.execute(
            """
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
                last_update_time,
                reject_reason,
                signal_id,
                timeframe,
                zone
            ) VALUES (
                COALESCE($1::uuid, gen_random_uuid()),
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9,
                COALESCE($10, 'NEW'),
                COALESCE($11::numeric, 0::numeric),
                $12,
                COALESCE($13, NOW()),
                $14,
                $15,
                COALESCE($16::numeric, 0::numeric),
                $17,
                $18,
                $19,
                $20,
                $21,
                $22::jsonb
            )
            ON CONFLICT (venue, client_order_id) DO NOTHING
            """,
            order.get("order_id"),
            client_order_id,
            venue,
            symbol,
            side,
            order_type,
            quantity,
            price,
            stop_price,
            order.get("status"),
            _to_decimal(order.get("filled_quantity", 0)),
            _to_decimal(order.get("average_fill_price")),
            order.get("created_at"),
            order.get("decision_id"),
            order.get("exchange_order_id"),
            _to_decimal(order.get("commission")),
            order.get("commission_asset"),
            order.get("last_update_time"),
            order.get("reject_reason"),
            order.get("signal_id"),
            order.get("timeframe"),
            zone_json,
        )

        existing = await conn.fetchrow(
            """
            SELECT venue, client_order_id, symbol, side, type,
                   quantity, price, stop_price, decision_id, signal_id,
                   timeframe, zone
            FROM orders
            WHERE venue = $1 AND client_order_id = $2
            FOR UPDATE
            """,
            venue,
            client_order_id,
        )
        if existing is None:
            return

        identity_values = {
            "venue": (venue, existing["venue"]),
            "client_order_id": (client_order_id, existing["client_order_id"]),
            "symbol": (symbol, existing["symbol"]),
            "side": (side, existing["side"]),
            "type": (order_type, existing["type"]),
            "quantity": (quantity, _to_decimal(existing["quantity"])),
            "price": (price, _to_decimal(existing["price"])),
            "stop_price": (stop_price, _to_decimal(existing["stop_price"])),
        }
        for field_name, (expected, actual) in identity_values.items():
            if expected != actual:
                raise RuntimeError(f"order identity conflict for {field_name}")

        existing_decision_id = existing["decision_id"]
        incoming_decision_id = order.get("decision_id")
        if (
            existing_decision_id is not None
            and incoming_decision_id is not None
            and str(existing_decision_id) != str(incoming_decision_id)
        ):
            raise RuntimeError("order identity conflict for decision_id")
        existing_signal_id = existing["signal_id"]
        incoming_signal_id = order.get("signal_id")
        if (
            existing_signal_id is not None
            and incoming_signal_id is not None
            and str(existing_signal_id) != str(incoming_signal_id)
        ):
            raise RuntimeError("order identity conflict for signal_id")

        existing_timeframe = existing["timeframe"]
        incoming_timeframe = order.get("timeframe")
        if existing_timeframe is not None and (
            incoming_timeframe is None or str(existing_timeframe) != str(incoming_timeframe)
        ):
            raise RuntimeError("order identity conflict for timeframe")

        def _canonical_zone(value: Any) -> str | None:
            if value is None:
                return None
            if isinstance(value, (str, bytes, bytearray)):
                try:
                    value = json.loads(value)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError("order identity conflict for zone") from exc
            if not isinstance(value, dict):
                raise RuntimeError("order identity conflict for zone")
            return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

        existing_zone = _canonical_zone(existing["zone"])
        incoming_zone = _canonical_zone(zone)
        if existing_zone is not None and existing_zone != incoming_zone:
            raise RuntimeError("order identity conflict for zone")

        if (
            (existing_decision_id is None and incoming_decision_id is not None)
            or (existing_signal_id is None and incoming_signal_id is not None)
            or (existing_timeframe is None and incoming_timeframe is not None)
            or (existing_zone is None and incoming_zone is not None)
        ):
            await conn.execute(
                """
                UPDATE orders
                SET decision_id = COALESCE(decision_id, $3),
                    signal_id = COALESCE(signal_id, $4),
                    timeframe = COALESCE(timeframe, $5),
                    zone = COALESCE(zone, $6::jsonb),
                    updated_at = NOW()
                WHERE venue = $1 AND client_order_id = $2
                """,
                venue,
                client_order_id,
                incoming_decision_id,
                incoming_signal_id,
                incoming_timeframe,
                zone_json,
            )

    async def commit_execution_ack(
        self,
        idempotency_key: str,
        *,
        venue: str,
        response_payload: dict[str, Any],
        order_rows: list[dict[str, Any]],
        deliveries: list[dict[str, Any]],
    ) -> bool:
        """Atomically persist projections, router ACK, and pending success deliveries."""
        response_json = json.dumps(response_payload, sort_keys=True, default=str)
        async with self.get_write_connection() as conn, conn.transaction():
            for order in order_rows:
                await self._insert_or_validate_order_with_connection(conn, order)

            result = await conn.execute(
                """
                UPDATE execution_intents
                SET state = 'ACKNOWLEDGED',
                    response_payload = $3::jsonb,
                    error_message = NULL,
                    recovery_lease_expires_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE venue = $1
                  AND idempotency_key = $2
                  AND state = 'SUBMITTING'
                """,
                venue,
                idempotency_key,
                response_json,
            )
            if result != "UPDATE 1":
                raise RuntimeError(
                    "execution intent ACKNOWLEDGED transition expected SUBMITTING state"
                )

            for delivery in deliveries:
                delivery_kind = delivery.get("delivery_kind")
                delivery_payload = delivery.get("delivery_payload")
                if not isinstance(delivery_kind, str) or delivery_kind not in {
                    "SNAPSHOT",
                    "ORDER_PLACED",
                }:
                    raise ValueError("invalid success delivery kind")
                if not isinstance(delivery_payload, dict):
                    raise ValueError("success delivery payload is required")
                await conn.execute(
                    """
                    INSERT INTO execution_success_deliveries (
                        venue,
                        idempotency_key,
                        delivery_kind,
                        state,
                        attempts,
                        delivery_payload
                    ) VALUES ($1, $2, $3, 'PENDING', 0, $4::jsonb)
                    ON CONFLICT (venue, idempotency_key, delivery_kind) DO NOTHING
                    """,
                    venue,
                    idempotency_key,
                    delivery_kind,
                    json.dumps(delivery_payload, sort_keys=True, default=str),
                )
        return True

    async def _claim_execution_success_delivery(
        self,
        idempotency_key: str | None,
        *,
        venue: str,
    ) -> dict[str, Any] | None:
        """Claim the next eligible success delivery with a 60-second lease."""
        lease_token = str(uuid4())
        async with self.get_write_connection() as conn:
            row = await conn.fetchrow(
                """
                WITH candidate AS (
                    SELECT d.venue, d.idempotency_key, d.delivery_kind
                    FROM execution_success_deliveries AS d
                    WHERE d.venue = $1
                      AND ($2::text IS NULL OR d.idempotency_key = $2)
                      AND (
                          (d.state = 'PENDING' AND d.next_attempt_at <= CURRENT_TIMESTAMP)
                          OR (
                              d.state = 'DELIVERING'
                              AND d.lease_expires_at <= CURRENT_TIMESTAMP
                          )
                      )
                      AND (
                          d.delivery_kind = 'SNAPSHOT'
                          OR (
                              d.delivery_kind = 'ORDER_PLACED'
                              AND NOT EXISTS (
                                  SELECT 1
                                  FROM execution_success_deliveries AS snapshot
                                  WHERE snapshot.venue = d.venue
                                    AND snapshot.idempotency_key = d.idempotency_key
                                    AND snapshot.delivery_kind = 'SNAPSHOT'
                                    AND snapshot.state <> 'DELIVERED'
                              )
                          )
                      )
                    ORDER BY
                        d.next_attempt_at,
                        d.created_at,
                        d.delivery_kind
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE execution_success_deliveries AS d
                SET state = 'DELIVERING',
                    attempts = d.attempts + 1,
                    lease_token = $3,
                    lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '60 seconds',
                    last_error = NULL,
                    delivered_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                FROM candidate
                WHERE d.venue = candidate.venue
                  AND d.idempotency_key = candidate.idempotency_key
                  AND d.delivery_kind = candidate.delivery_kind
                RETURNING d.venue, d.idempotency_key, d.delivery_kind, d.lease_token,
                          d.delivery_payload, d.next_attempt_at
                """,
                venue,
                idempotency_key,
                lease_token,
            )
        if row is None:
            return None
        delivery_payload = row["delivery_payload"]
        if isinstance(delivery_payload, (str, bytes, bytearray)):
            try:
                delivery_payload = json.loads(delivery_payload)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("success delivery payload is malformed") from exc
        if not isinstance(delivery_payload, dict):
            raise RuntimeError("success delivery payload is malformed")

        def _row_value(name: str, default: Any = None) -> Any:
            try:
                return row[name]
            except (KeyError, IndexError):
                return default

        claimed_idempotency_key = (
            idempotency_key if idempotency_key is not None else row["idempotency_key"]
        )
        return {
            "venue": _row_value("venue", venue),
            "idempotency_key": claimed_idempotency_key,
            "delivery_kind": row["delivery_kind"],
            "lease_token": row["lease_token"],
            "delivery_payload": delivery_payload,
            "next_attempt_at": _row_value("next_attempt_at"),
        }

    async def claim_execution_success_delivery(
        self,
        idempotency_key: str,
        *,
        venue: str,
    ) -> dict[str, Any] | None:
        claim = await self._claim_execution_success_delivery(idempotency_key, venue=venue)
        if claim is None:
            return None
        claim.pop("idempotency_key", None)
        claim.pop("venue", None)
        claim.pop("next_attempt_at", None)
        return claim

    async def claim_next_execution_success_delivery(
        self,
        *,
        venue: str,
    ) -> dict[str, Any] | None:
        return await self._claim_execution_success_delivery(None, venue=venue)

    async def complete_execution_success_delivery(
        self,
        idempotency_key: str,
        *,
        venue: str,
        delivery_kind: str,
        lease_token: str,
    ) -> None:
        """Mark a delivery delivered only when its active lease still matches."""
        async with self.get_write_connection() as conn:
            result = await conn.execute(
                """
                UPDATE execution_success_deliveries
                SET state = 'DELIVERED',
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    delivered_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    last_error = NULL
                WHERE venue = $1
                  AND idempotency_key = $2
                  AND delivery_kind = $3
                  AND state = 'DELIVERING'
                  AND lease_token = $4
                """,
                venue,
                idempotency_key,
                delivery_kind,
                lease_token,
            )
        if result != "UPDATE 1":
            raise RuntimeError("success delivery lease is no longer valid")

    async def fail_execution_success_delivery(
        self,
        idempotency_key: str,
        *,
        venue: str,
        delivery_kind: str,
        lease_token: str,
        error_message: str,
    ) -> None:
        """Return a leased delivery to pending when its effect fails."""
        async with self.get_write_connection() as conn:
            result = await conn.execute(
                """
                UPDATE execution_success_deliveries
                SET state = 'PENDING',
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    delivered_at = NULL,
                    last_error = $5,
                    next_attempt_at = CURRENT_TIMESTAMP
                        + LEAST(
                            300.0,
                            POWER(2.0, attempts)
                                * (0.75 + random() * 0.25)
                        ) * INTERVAL '1 second',
                    updated_at = CURRENT_TIMESTAMP
                WHERE venue = $1
                  AND idempotency_key = $2
                  AND delivery_kind = $3
                  AND state = 'DELIVERING'
                  AND lease_token = $4
                """,
                venue,
                idempotency_key,
                delivery_kind,
                lease_token,
                error_message[:1000],
            )
        if result != "UPDATE 1":
            raise RuntimeError("success delivery lease is no longer valid")

    async def has_pending_execution_success_delivery(
        self,
        idempotency_key: str,
        *,
        venue: str,
    ) -> bool:
        """Return whether any success-delivery obligation is not yet delivered."""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM execution_success_deliveries
                    WHERE venue = $1
                      AND idempotency_key = $2
                      AND state <> 'DELIVERED'
                ) AS has_pending
                """,
                venue,
                idempotency_key,
            )
        return bool(row and row["has_pending"])

    async def get_order_by_client_order_id(
        self,
        *,
        client_order_id: str,
        venue: str | None = None,
    ) -> dict[Any, Any] | None:
        """Get a single order row by client_order_id, optionally scoped by venue."""
        try:
            async with self.get_read_connection() as conn:
                if venue:
                    row = await conn.fetchrow(
                        """
                        SELECT
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
                            decision_id::text AS decision_id,
                            exchange_order_id,
                            signal_id,
                            timeframe,
                            zone,
                            last_update_time
                        FROM orders
                        WHERE client_order_id = $1
                          AND venue = $2
                        ORDER BY updated_at DESC
                        LIMIT 1
                    """,
                        client_order_id,
                        venue,
                    )
                else:
                    row = await conn.fetchrow(
                        """
                        SELECT
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
                            decision_id::text AS decision_id,
                            exchange_order_id,
                            signal_id,
                            timeframe,
                            zone,
                            last_update_time
                        FROM orders
                        WHERE client_order_id = $1
                        ORDER BY updated_at DESC
                        LIMIT 1
                    """,
                        client_order_id,
                    )
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving order by client_order_id: {e}")
            return None

    async def get_active_order_for_setup(
        self,
        *,
        venue: str,
        symbol: str,
        side: str,
        timeframe: str,
        zone_id: str,
    ) -> dict[Any, Any] | None:
        """Get an active entry order for the same setup identity."""
        try:
            async with self.get_read_connection() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT client_order_id, status
                    FROM orders
                    WHERE venue = $1
                      AND symbol = $2
                      AND side = $3
                      AND timeframe = $4
                      AND zone->>'zone_id' = $5
                      AND status IN ('NEW', 'PARTIALLY_FILLED')
                    ORDER BY created_at DESC
                    LIMIT 1
                """,
                    venue,
                    symbol,
                    side,
                    timeframe,
                    zone_id,
                )
                return dict(row) if row else None
        except Exception:
            logger.exception(
                "Error retrieving active order for setup venue=%s symbol=%s timeframe=%s zone_id=%s",
                venue,
                symbol,
                timeframe,
                zone_id,
            )
            raise DuplicateGuardLookupError(
                f"active order lookup unavailable for {venue} {symbol} {timeframe} {zone_id}"
            ) from None

    async def get_active_position_for_setup(
        self,
        *,
        venue: str,
        symbol: str,
        side: str,
        timeframe: str,
        zone_id: str,
    ) -> dict[Any, Any] | None:
        """Get an active position whose opening order matches the same setup identity."""
        try:
            async with self.get_read_connection() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT p.position_id, p.entry_order_id, p.side, p.size
                    FROM positions p
                    JOIN orders o ON o.order_id = p.entry_order_id
                    WHERE p.venue = $1
                      AND p.symbol = $2
                      AND p.side = $3
                      AND p.is_active = TRUE
                      AND p.size > 0
                      AND o.timeframe = $4
                      AND o.zone->>'zone_id' = $5
                    ORDER BY p.opened_at DESC
                    LIMIT 1
                """,
                    venue,
                    symbol,
                    side,
                    timeframe,
                    zone_id,
                )
                return dict(row) if row else None
        except Exception:
            logger.exception(
                "Error retrieving active position for setup venue=%s symbol=%s timeframe=%s zone_id=%s",
                venue,
                symbol,
                timeframe,
                zone_id,
            )
            raise DuplicateGuardLookupError(
                f"active position lookup unavailable for {venue} {symbol} {timeframe} {zone_id}"
            ) from None

    async def get_recent_decisions(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[dict[Any, Any]]:
        """Get recent trading decisions"""
        try:
            async with self.get_connection() as conn:
                query = """
                    SELECT * FROM trading_decisions
                """
                params: list[Any] = []

                if symbol:
                    query += " WHERE symbol = $1"
                    params.append(symbol)

                query += " ORDER BY timestamp DESC LIMIT $" + str(len(params) + 1)
                params.append(limit)

                rows = await conn.fetch(query, *params)
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Error retrieving recent decisions: {e}")
            return []

    async def get_trading_decisions_in_window(
        self,
        *,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> list[dict[Any, Any]]:
        """Get trading decisions for a symbol in a time window."""
        try:
            async with self.get_read_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM trading_decisions
                    WHERE symbol = $1
                      AND timestamp >= $2
                      AND timestamp <= $3
                    ORDER BY timestamp DESC
                    LIMIT $4
                """,
                    symbol,
                    start_time,
                    end_time,
                    limit,
                )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error retrieving trading decisions: {e}")
            return []

    async def get_trading_decision_by_id(
        self,
        decision_id: str,
    ) -> dict[Any, Any] | None:
        """Get a single trading decision by its ID."""
        try:
            async with self.get_read_connection() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT *
                    FROM trading_decisions
                    WHERE decision_id = $1::uuid
                """,
                    decision_id,
                )
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving trading decision by id: {e}")
            return None

    async def get_smc_signals_in_window(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
    ) -> list[dict[Any, Any]]:
        """Get SMC signals for a symbol/timeframe in a time window."""
        try:
            async with self.get_read_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM smc_signals
                    WHERE symbol = $1
                      AND timeframe = $2
                      AND timestamp >= $3
                      AND timestamp <= $4
                    ORDER BY timestamp DESC
                    LIMIT $5
                """,
                    symbol,
                    timeframe,
                    start_time,
                    end_time,
                    limit,
                )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error retrieving smc signals: {e}")
            return []

    # ============================================================================
    # Validation Snapshots
    # ============================================================================

    async def get_active_zones_at_time(
        self,
        *,
        symbol: str,
        timestamp: datetime,
        lookback_bars: int = 100,
        max_zones: int = 20,
    ) -> list[dict[Any, Any]]:
        """Get active zones valid at the given timestamp.

        Returns zones created before timestamp that are still active
        (not invalidated) at that time.
        """
        try:
            async with self.get_read_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        zone_id::text as zone_id,
                        zone_type,
                        top_price,
                        bottom_price,
                        strength,
                        is_active,
                        created_at
                    FROM zones
                    WHERE symbol = $1
                      AND created_at <= $2
                      AND (is_active = TRUE OR invalidated_at > $2)
                    ORDER BY strength DESC, created_at DESC
                    LIMIT LEAST($3, $4)
                """,
                    symbol,
                    timestamp,
                    max_zones,
                    lookback_bars,
                )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error retrieving zones at time: {e}")
            return []

    async def get_structure_events_at_time(
        self,
        *,
        symbol: str,
        timeframe: str | None,
        timestamp: datetime,
        lookback_bars: int = 50,
        max_events: int = 30,
    ) -> list[dict[Any, Any]]:
        """Get SMC structure events (CHOCH/BOS) near the given timestamp.

        Returns events within lookback window before timestamp.
        """
        try:
            async with self.get_read_connection() as conn:
                if timeframe:
                    rows = await conn.fetch(
                        """
                            SELECT
                                venue || '-' || symbol || '-' || timeframe || '-' || timestamp::text
                                    as event_id,
                                event_type,
                                timestamp,
                                trend_direction as direction,
                                price
                        FROM smc_events
                        WHERE symbol = $1
                          AND timeframe = $2
                          AND timestamp <= $3
                        ORDER BY timestamp DESC
                        LIMIT LEAST($4, $5)
                    """,
                        symbol,
                        timeframe,
                        timestamp,
                        max_events,
                        lookback_bars,
                    )
                else:
                    rows = await conn.fetch(
                        """
                            SELECT
                                venue || '-' || symbol || '-' || timeframe || '-' || timestamp::text
                                    as event_id,
                                event_type,
                                timestamp,
                                trend_direction as direction,
                                price
                        FROM smc_events
                        WHERE symbol = $1
                          AND timestamp <= $2
                        ORDER BY timestamp DESC
                        LIMIT LEAST($3, $4)
                    """,
                        symbol,
                        timestamp,
                        max_events,
                        lookback_bars,
                    )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error retrieving structure events: {e}")
            return []

    async def upsert_benchmark_validation_snapshot(  # noqa: PLR0913
        self,
        *,
        source: str,
        chat_id: int,
        message_id: int,
        validated_at: datetime,
        symbol: str,
        timeframe: str | None,
        payload: dict[Any, Any],
    ) -> str | None:
        """Insert or update a benchmark validation snapshot.

        Returns the snapshot_id on success, None on failure.
        """
        import json
        from uuid import uuid4

        try:
            async with self.get_connection() as conn:
                snapshot_id = str(uuid4())
                snapshot_version = payload.get("version", 1)

                await conn.execute(
                    """
                    INSERT INTO benchmark_validation_snapshots (
                        id, source, chat_id, message_id, validated_at,
                        symbol, timeframe, snapshot_version, payload
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                    ON CONFLICT (source, chat_id, message_id, validated_at, snapshot_version)
                    DO UPDATE SET
                        symbol = EXCLUDED.symbol,
                        timeframe = EXCLUDED.timeframe,
                        payload = EXCLUDED.payload
                """,
                    snapshot_id,
                    source,
                    chat_id,
                    message_id,
                    validated_at,
                    symbol,
                    timeframe,
                    snapshot_version,
                    json.dumps(payload),
                )
                return snapshot_id
        except Exception as e:
            logger.error(f"Error upserting validation snapshot: {e}")
            return None

    async def get_benchmark_validation_snapshot(
        self,
        snapshot_id: str,
    ) -> dict[Any, Any] | None:
        """Fetch a single validation snapshot by ID."""
        try:
            async with self.get_read_connection() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        id::text as snapshot_id,
                        source,
                        chat_id,
                        message_id,
                        validated_at,
                        symbol,
                        timeframe,
                        snapshot_version,
                        payload,
                        created_at
                    FROM benchmark_validation_snapshots
                    WHERE id = $1::uuid
                """,
                    snapshot_id,
                )
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving validation snapshot: {e}")
            return None

    async def get_benchmark_validation_snapshots(
        self,
        *,
        source: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[Any, Any]]:
        """Fetch validation snapshots in a time range."""
        try:
            async with self.get_read_connection() as conn:
                # Build query dynamically based on filters
                conditions = []
                params: list[Any] = []
                param_idx = 1

                if source:
                    conditions.append(f"source = ${param_idx}")
                    params.append(source)
                    param_idx += 1

                if start_time:
                    conditions.append(f"validated_at >= ${param_idx}")
                    params.append(start_time)
                    param_idx += 1

                if end_time:
                    conditions.append(f"validated_at <= ${param_idx}")
                    params.append(end_time)
                    param_idx += 1

                where_clause = " AND ".join(conditions) if conditions else "TRUE"
                params.append(limit)

                query = f"""
                    SELECT
                        id::text as snapshot_id,
                        source,
                        chat_id,
                        message_id,
                        validated_at,
                        symbol,
                        timeframe,
                        snapshot_version,
                        payload,
                        created_at
                    FROM benchmark_validation_snapshots
                    WHERE {where_clause}
                    ORDER BY validated_at DESC
                    LIMIT ${param_idx}
                """  # noqa: S608

                rows = await conn.fetch(query, *params)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error retrieving validation snapshots: {e}")
            return []

    # ============================================================================
    # SMC Events (smc_events.v1 contract)
    # ============================================================================

    async def insert_smc_event_v1(self, payload: dict[str, Any]) -> None:
        """Insert an SMC event into smc_events_v1 using contract schema shape."""
        async with self.get_write_connection() as conn:
            await conn.execute(
                """
                INSERT INTO smc_events_v1 (
                    venue, symbol, timeframe, event_time,
                    event_type, direction, price_level,
                    previous_pivot_price, previous_pivot_time,
                    broken_pivot_price, broken_pivot_time,
                    version
                ) VALUES (
                    $1, $2, $3, $4,
                    $5, $6, $7,
                    $8, $9,
                    $10, $11,
                    $12
                )
                ON CONFLICT DO NOTHING
                """,
                payload["venue"],
                payload["symbol"],
                payload["timeframe"],
                datetime.fromisoformat(payload["event_time"].replace("Z", "+00:00")),
                payload["event_type"].upper(),
                payload["direction"],
                Decimal(payload["price_level"]),
                Decimal(payload["previous_pivot_price"]),
                datetime.fromisoformat(
                    payload["previous_pivot_time"].replace("Z", "+00:00"),
                ),
                Decimal(payload["broken_pivot_price"]),
                datetime.fromisoformat(
                    payload["broken_pivot_time"].replace("Z", "+00:00"),
                ),
                payload.get("version", "1.0.0"),
            )

    # ============================================================================
    # Health and Maintenance
    # ============================================================================

    async def get_latest_equity_sample(self) -> tuple[Decimal, datetime] | None:
        """Return latest equity sample as (equity, timestamp)."""
        try:
            async with self.get_read_connection() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT equity, timestamp
                      FROM equity_samples
                  ORDER BY timestamp DESC
                     LIMIT 1
                    """,
                )
                if row is None:
                    return None
                return row["equity"], row["timestamp"]
        except Exception:
            logger.exception("Error retrieving latest equity sample")
            return None

    async def insert_equity_sample(
        self,
        equity: Decimal,
        timestamp: datetime,
        source_timestamp: datetime | None = None,
    ) -> bool:
        """Insert an equity sample row."""
        try:
            async with self.get_write_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO equity_samples (timestamp, equity, source_timestamp)
                    VALUES ($1, $2, $3)
                    """,
                    timestamp,
                    equity,
                    source_timestamp,
                )
            return True
        except Exception:
            logger.exception("Error inserting equity sample")
            return False

    async def get_equity_sample_at_or_after(self, timestamp: datetime) -> Decimal | None:
        """Return equity from the first sample at/after timestamp."""
        try:
            async with self.get_read_connection() as conn:
                value = await conn.fetchval(
                    """
                    SELECT equity
                      FROM equity_samples
                     WHERE timestamp >= $1
                  ORDER BY timestamp ASC
                     LIMIT 1
                    """,
                    timestamp,
                )
                return value
        except Exception:
            logger.exception("Error retrieving equity sample at/after %s", timestamp)
            return None

    async def get_peak_equity_since(self, timestamp: datetime) -> Decimal | None:
        """Return MAX(equity) since timestamp (inclusive)."""
        try:
            async with self.get_read_connection() as conn:
                value = await conn.fetchval(
                    """
                    SELECT MAX(equity)
                      FROM equity_samples
                     WHERE timestamp >= $1
                    """,
                    timestamp,
                )
                return value
        except Exception:
            logger.exception("Error retrieving peak equity since %s", timestamp)
            return None

    async def get_paper_equity_components(self) -> PaperEquityComponents:
        """Return aggregated equity components from paper_positions.

        Returns:
            PaperEquityComponents with total_fees, realized_pnl, unrealized_pnl, total_funding.
            All values are Decimal, with COALESCE to zero for NULL/empty rows.
        """
        zero = PaperEquityComponents(
            total_fees=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_funding=Decimal("0"),
        )
        try:
            async with self.get_read_connection() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COALESCE(SUM(total_fees), 0) AS total_fees,
                        COALESCE(SUM(realized_pnl), 0) AS realized_pnl,
                        COALESCE(SUM(unrealized_pnl), 0) AS unrealized_pnl,
                        COALESCE(SUM(total_funding), 0) AS total_funding
                    FROM paper_positions
                    """,
                )
                if row is None:
                    return zero
                return PaperEquityComponents(
                    total_fees=Decimal(str(row["total_fees"])),
                    realized_pnl=Decimal(str(row["realized_pnl"])),
                    unrealized_pnl=Decimal(str(row["unrealized_pnl"])),
                    total_funding=Decimal(str(row["total_funding"])),
                )
        except Exception:
            logger.exception("Error retrieving paper equity components")
            return zero

    async def get_active_positions(self, venue: str) -> list[dict[str, Any]]:
        """Return active positions for venue.

        Minimal columns are returned for exposure calculations.
        """
        try:
            async with self.get_read_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT symbol, side, size, current_price, COALESCE(entry_order_id::text, '') AS entry_order_id
                      FROM positions
                     WHERE venue = $1
                       AND is_active = TRUE
                       AND size > 0
                    """,
                    venue,
                )
                return [dict(row) for row in rows]
        except Exception:
            logger.exception("Error retrieving active positions for venue=%s", venue)
            raise DuplicateGuardLookupError(
                f"active positions lookup unavailable for venue={venue}"
            ) from None

    async def health_check(self) -> dict[str, Any]:
        """Perform a health check on the database"""
        try:
            async with self.get_connection() as conn:
                # Test basic connectivity
                await conn.execute("SELECT 1")

                # Get database size
                size_result = await conn.fetchrow(
                    """
                    SELECT pg_size_pretty(pg_database_size(current_database())) as size
                """,
                )

                # Get table stats
                # Note: PostgreSQL 16+ uses 'relname' instead of 'tablename' in pg_stat_user_tables
                stats_result = await conn.fetch(
                    """
                    SELECT
                        schemaname,
                        relname as tablename,
                        n_tup_ins as inserts,
                        n_tup_upd as updates
                    FROM pg_stat_user_tables
                    WHERE relname IN (
                        'candles',
                        'indicators',
                        'trading_decisions',
                        'orders',
                        'positions',
                        'smc_signals'
                    )
                """,
                )

                table_stats = {
                    row["tablename"]: {
                        "inserts": row["inserts"],
                        "updates": row["updates"],
                    }
                    for row in stats_result
                }

                return {
                    "status": "healthy",
                    "database_size": size_result["size"] if size_result else "unknown",
                    "pool_size": self._pool.get_size() if self._pool else 0,
                    "table_statistics": table_stats,
                    "timestamp": datetime.now(UTC).isoformat(),
                }

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def get_database_stats(self) -> dict[str, Any]:
        """Get detailed database statistics"""
        try:
            async with self.get_connection() as conn:
                # Get candle counts by symbol and timeframe
                candle_counts = await conn.fetch(
                    """
                    SELECT symbol, timeframe, COUNT(*) as count,
                           MIN(open_time) as oldest,
                           MAX(open_time) as newest
                    FROM candles
                    GROUP BY symbol, timeframe
                    ORDER BY symbol, timeframe
                """,
                )

                # Get recent activity
                recent_activity = await conn.fetchrow(
                    """
                    SELECT
                        (
                            SELECT COUNT(*)
                            FROM candles
                            WHERE open_time > NOW() - INTERVAL '1 hour'
                        ) as candles_last_hour,
                        (
                            SELECT COUNT(*)
                            FROM indicators
                            WHERE timestamp > NOW() - INTERVAL '1 hour'
                        ) as indicators_last_hour,
                        (
                            SELECT COUNT(*)
                            FROM trading_decisions
                            WHERE created_at > NOW() - INTERVAL '1 hour'
                        ) as decisions_last_hour
                """,
                )

                return {
                    "candle_counts": [dict(row) for row in candle_counts],
                    "recent_activity": dict(recent_activity) if recent_activity else {},
                    "timestamp": datetime.now(UTC).isoformat(),
                }

        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {}

    async def cleanup_old_data(self, days_to_keep: int = 90) -> dict[str, int]:
        """Clean up old data beyond retention period"""
        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=days_to_keep)
            cleanup_results = {}

            async with self.get_connection() as conn:
                # Clean up old events
                result = await conn.execute(
                    """
                    DELETE FROM events WHERE timestamp < $1
                """,
                    cutoff_date,
                )
                cleanup_results["events"] = int(result.split()[-1])

                # Clean up old inactive signals
                result = await conn.execute(
                    """
                    DELETE FROM smc_signals
                    WHERE timestamp < $1 AND is_active = FALSE
                """,
                    cutoff_date,
                )
                cleanup_results["smc_signals"] = int(result.split()[-1])

                logger.info(f"Cleaned up old data: {cleanup_results}")
                return cleanup_results

        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return {}

    # ============================================================================
    # Context Manager Support
    # ============================================================================

    async def __aenter__(self) -> None:
        """Async context manager entry"""
        await self.initialize()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit"""
        await self.close()
