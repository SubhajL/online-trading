"""
TimescaleDB Adapter

Database adapter for TimescaleDB that handles time-series data storage and retrieval
for trading data including candles, indicators, signals, and trading events.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import logging
import os
from types import TracebackType
from typing import Any

import asyncpg
from asyncpg import Pool

from ...models import (
    Candle,
    TechnicalIndicators,
    TimeFrame,
    TradingDecision,
)

logger = logging.getLogger(__name__)


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
                        c.open_time,
                        c.close_time,
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
                        c.open_time,
                        c.close_time,
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
                    os.getenv("TRADING_VENUE"),
                )
                return True

        except Exception as e:
            logger.error(f"Error inserting trading decision: {e}")
            return False

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

    async def insert_equity_sample(self, equity: Decimal, timestamp: datetime) -> bool:
        """Insert an equity sample row."""
        try:
            async with self.get_write_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO equity_samples (timestamp, equity)
                    VALUES ($1, $2)
                    """,
                    timestamp,
                    equity,
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

    async def get_active_positions(self, venue: str) -> list[dict[str, Any]]:
        """Return active positions for venue.

        Minimal columns are returned for exposure calculations.
        """
        try:
            async with self.get_read_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT symbol, size, current_price
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
            return []

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
