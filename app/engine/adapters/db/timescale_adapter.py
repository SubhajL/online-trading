"""
TimescaleDB Adapter

Database adapter for TimescaleDB that handles time-series data storage and retrieval
for trading data including candles, indicators, signals, and trading events.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from contextlib import asynccontextmanager

import asyncpg
from asyncpg import Connection, Pool

from ...types import (
    Candle,
    TechnicalIndicators,
    SMCSignal,
    TradingDecision,
    Order,
    Position,
    TimeFrame,
    OrderSide,
    OrderType,
    OrderStatus,
    ZoneType,
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

    def __init__(
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

        self._pool: Optional[Pool] = None
        self._initialized = False

        logger.info(f"TimescaleDBAdapter configured for {host}:{port}/{database}")

    async def initialize(self):
        """Initialize the database connection pool and create tables"""
        if self._initialized:
            return

        try:
            # Create connection pool
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.username,
                password=self.password,
                min_size=1,
                max_size=self.pool_size,
                command_timeout=self.pool_timeout,
            )

            # Create tables and hypertables
            await self._create_tables()
            await self._create_hypertables()
            await self._create_indexes()

            self._initialized = True
            logger.info("TimescaleDB adapter initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing TimescaleDB adapter: {e}")
            raise

    async def close(self):
        """Close the database connection pool"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._initialized = False
            logger.info("TimescaleDB adapter closed")

    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection from the pool"""
        if not self._pool:
            raise RuntimeError("Database not initialized")

        async with self._pool.acquire() as connection:
            yield connection

    # ============================================================================
    # Table Creation and Management
    # ============================================================================

    async def _create_tables(self):
        """Create all required tables"""
        async with self.get_connection() as conn:
            # Candles table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    timestamp TIMESTAMPTZ NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    timeframe VARCHAR(5) NOT NULL,
                    open_price DECIMAL(20,8) NOT NULL,
                    high_price DECIMAL(20,8) NOT NULL,
                    low_price DECIMAL(20,8) NOT NULL,
                    close_price DECIMAL(20,8) NOT NULL,
                    volume DECIMAL(20,8) NOT NULL,
                    quote_volume DECIMAL(20,8) NOT NULL,
                    trades INTEGER NOT NULL,
                    taker_buy_base_volume DECIMAL(20,8) NOT NULL,
                    taker_buy_quote_volume DECIMAL(20,8) NOT NULL,
                    UNIQUE(timestamp, symbol, timeframe)
                );
            """
            )

            # Technical indicators table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS technical_indicators (
                    timestamp TIMESTAMPTZ NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    timeframe VARCHAR(5) NOT NULL,
                    ema_9 DECIMAL(20,8),
                    ema_21 DECIMAL(20,8),
                    ema_50 DECIMAL(20,8),
                    ema_200 DECIMAL(20,8),
                    rsi_14 DECIMAL(10,6),
                    macd_line DECIMAL(20,8),
                    macd_signal DECIMAL(20,8),
                    macd_histogram DECIMAL(20,8),
                    atr_14 DECIMAL(20,8),
                    bb_upper DECIMAL(20,8),
                    bb_middle DECIMAL(20,8),
                    bb_lower DECIMAL(20,8),
                    bb_width DECIMAL(10,6),
                    bb_percent DECIMAL(10,6),
                    UNIQUE(timestamp, symbol, timeframe)
                );
            """
            )

            # SMC signals table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS smc_signals (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    timestamp TIMESTAMPTZ NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    timeframe VARCHAR(5) NOT NULL,
                    signal_type VARCHAR(50) NOT NULL,
                    direction VARCHAR(4) NOT NULL,
                    entry_price DECIMAL(20,8) NOT NULL,
                    stop_loss DECIMAL(20,8),
                    take_profit DECIMAL(20,8),
                    confidence DECIMAL(4,3) NOT NULL,
                    reasoning TEXT,
                    zone_id UUID,
                    zone_type VARCHAR(30),
                    zone_top_price DECIMAL(20,8),
                    zone_bottom_price DECIMAL(20,8),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """
            )

            # Trading decisions table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_decisions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    timestamp TIMESTAMPTZ NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    action VARCHAR(10) NOT NULL,
                    entry_price DECIMAL(20,8),
                    quantity DECIMAL(20,8),
                    order_type VARCHAR(20),
                    stop_loss DECIMAL(20,8),
                    take_profit DECIMAL(20,8),
                    confidence DECIMAL(4,3) NOT NULL,
                    reasoning TEXT,
                    risk_reward_ratio DECIMAL(10,4),
                    market_regime VARCHAR(20),
                    news_sentiment VARCHAR(20),
                    funding_rate_impact DECIMAL(10,6),
                    volatility_filter BOOLEAN,
                    is_executed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """
            )

            # Orders table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    client_order_id VARCHAR(50) UNIQUE NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(4) NOT NULL,
                    type VARCHAR(20) NOT NULL,
                    quantity DECIMAL(20,8) NOT NULL,
                    price DECIMAL(20,8),
                    stop_price DECIMAL(20,8),
                    time_in_force VARCHAR(10) DEFAULT 'GTC',
                    status VARCHAR(20) DEFAULT 'NEW',
                    filled_quantity DECIMAL(20,8) DEFAULT 0,
                    average_fill_price DECIMAL(20,8),
                    decision_id UUID,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """
            )

            # Positions table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(4) NOT NULL,
                    size DECIMAL(20,8) NOT NULL,
                    entry_price DECIMAL(20,8) NOT NULL,
                    current_price DECIMAL(20,8) NOT NULL,
                    unrealized_pnl DECIMAL(20,8) NOT NULL,
                    realized_pnl DECIMAL(20,8) DEFAULT 0,
                    margin_used DECIMAL(20,8) NOT NULL,
                    leverage DECIMAL(10,2) DEFAULT 1,
                    stop_loss DECIMAL(20,8),
                    take_profit DECIMAL(20,8),
                    decision_id UUID,
                    opened_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    closed_at TIMESTAMPTZ,
                    is_active BOOLEAN DEFAULT TRUE
                );
            """
            )

            # Events table for audit trail
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    timestamp TIMESTAMPTZ NOT NULL,
                    event_type VARCHAR(50) NOT NULL,
                    symbol VARCHAR(20),
                    timeframe VARCHAR(5),
                    event_data JSONB,
                    metadata JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """
            )

    async def _create_hypertables(self):
        """Create TimescaleDB hypertables for time-series data"""
        async with self.get_connection() as conn:
            try:
                # Create hypertables (only if not already created)
                hypertables = [
                    ("candles", "timestamp"),
                    ("technical_indicators", "timestamp"),
                    ("events", "timestamp"),
                ]

                for table_name, time_column in hypertables:
                    try:
                        await conn.execute(
                            f"""
                            SELECT create_hypertable('{table_name}', '{time_column}',
                                                    if_not_exists => TRUE);
                        """
                        )
                        logger.info(f"Created hypertable for {table_name}")
                    except Exception as e:
                        if "already a hypertable" not in str(e):
                            logger.warning(
                                f"Error creating hypertable for {table_name}: {e}"
                            )

            except Exception as e:
                logger.error(f"Error creating hypertables: {e}")

    async def _create_indexes(self):
        """Create indexes for better query performance"""
        async with self.get_connection() as conn:
            indexes = [
                # Candles indexes
                "CREATE INDEX IF NOT EXISTS idx_candles_symbol_timeframe ON candles (symbol, timeframe, timestamp DESC);",
                "CREATE INDEX IF NOT EXISTS idx_candles_timestamp ON candles (timestamp DESC);",
                # Technical indicators indexes
                "CREATE INDEX IF NOT EXISTS idx_indicators_symbol_timeframe ON technical_indicators (symbol, timeframe, timestamp DESC);",
                # SMC signals indexes
                "CREATE INDEX IF NOT EXISTS idx_smc_signals_symbol_timestamp ON smc_signals (symbol, timestamp DESC);",
                "CREATE INDEX IF NOT EXISTS idx_smc_signals_active ON smc_signals (is_active, timestamp DESC);",
                # Trading decisions indexes
                "CREATE INDEX IF NOT EXISTS idx_decisions_symbol_timestamp ON trading_decisions (symbol, timestamp DESC);",
                "CREATE INDEX IF NOT EXISTS idx_decisions_executed ON trading_decisions (is_executed, timestamp DESC);",
                # Orders indexes
                "CREATE INDEX IF NOT EXISTS idx_orders_symbol_status ON orders (symbol, status, created_at DESC);",
                "CREATE INDEX IF NOT EXISTS idx_orders_decision ON orders (decision_id);",
                # Positions indexes
                "CREATE INDEX IF NOT EXISTS idx_positions_symbol_active ON positions (symbol, is_active, opened_at DESC);",
                "CREATE INDEX IF NOT EXISTS idx_positions_decision ON positions (decision_id);",
                # Events indexes
                "CREATE INDEX IF NOT EXISTS idx_events_type_timestamp ON events (event_type, timestamp DESC);",
                "CREATE INDEX IF NOT EXISTS idx_events_symbol ON events (symbol, timestamp DESC) WHERE symbol IS NOT NULL;",
            ]

            for index_sql in indexes:
                try:
                    await conn.execute(index_sql)
                except Exception as e:
                    logger.warning(f"Error creating index: {e}")

    # ============================================================================
    # Candle Data Operations
    # ============================================================================

    async def insert_candle(self, candle: Candle) -> bool:
        """Insert a single candle"""
        try:
            async with self.get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO candles (
                        timestamp, symbol, timeframe, open_price, high_price, low_price,
                        close_price, volume, quote_volume, trades,
                        taker_buy_base_volume, taker_buy_quote_volume
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (timestamp, symbol, timeframe) DO UPDATE SET
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
                    candle.open_time,
                    candle.symbol,
                    candle.timeframe.value,
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

    async def insert_candles_batch(self, candles: List[Candle]) -> int:
        """Insert multiple candles in a batch"""
        if not candles:
            return 0

        try:
            async with self.get_connection() as conn:
                records = [
                    (
                        c.open_time,
                        c.symbol,
                        c.timeframe.value,
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
                        timestamp, symbol, timeframe, open_price, high_price, low_price,
                        close_price, volume, quote_volume, trades,
                        taker_buy_base_volume, taker_buy_quote_volume
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (timestamp, symbol, timeframe) DO NOTHING
                """,
                    records,
                )

                return len(candles)

        except Exception as e:
            logger.error(f"Error inserting candles batch: {e}")
            return 0

    async def get_latest_candle(
        self,
        symbol: str,
        timeframe: TimeFrame
    ) -> Optional[Candle]:
        """
        Get the latest candle for a symbol and timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe

        Returns:
            Latest candle or None if no data
        """
        candles = await self.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=1
        )
        return candles[0] if candles else None

    async def get_candles(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Candle]:
        """Retrieve candles for a symbol and timeframe"""
        try:
            async with self.get_connection() as conn:
                query = """
                    SELECT timestamp, symbol, timeframe, open_price, high_price, low_price,
                           close_price, volume, quote_volume, trades,
                           taker_buy_base_volume, taker_buy_quote_volume
                    FROM candles
                    WHERE symbol = $1 AND timeframe = $2
                """
                params = [symbol, timeframe.value]

                if start_time:
                    query += " AND timestamp >= $" + str(len(params) + 1)
                    params.append(start_time)

                if end_time:
                    query += " AND timestamp <= $" + str(len(params) + 1)
                    params.append(end_time)

                query += " ORDER BY timestamp DESC LIMIT $" + str(len(params) + 1)
                params.append(limit)

                rows = await conn.fetch(query, *params)

                candles = []
                for row in rows:
                    candle = Candle(
                        symbol=row["symbol"],
                        timeframe=TimeFrame(row["timeframe"]),
                        open_time=row["timestamp"],
                        close_time=row["timestamp"],  # Simplified
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
        self, indicators: TechnicalIndicators
    ) -> bool:
        """Insert technical indicators"""
        try:
            async with self.get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO technical_indicators (
                        timestamp, symbol, timeframe, ema_9, ema_21, ema_50, ema_200,
                        rsi_14, macd_line, macd_signal, macd_histogram, atr_14,
                        bb_upper, bb_middle, bb_lower, bb_width, bb_percent
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                    ON CONFLICT (timestamp, symbol, timeframe) DO UPDATE SET
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
                    indicators.timestamp,
                    indicators.symbol,
                    indicators.timeframe.value,
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
                        id, timestamp, symbol, action, entry_price, quantity, order_type,
                        stop_loss, take_profit, confidence, reasoning, risk_reward_ratio,
                        market_regime, news_sentiment, funding_rate_impact, volatility_filter
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
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
                )
                return True

        except Exception as e:
            logger.error(f"Error inserting trading decision: {e}")
            return False

    async def get_recent_decisions(
        self, symbol: Optional[str] = None, limit: int = 100
    ) -> List[Dict]:
        """Get recent trading decisions"""
        try:
            async with self.get_connection() as conn:
                query = """
                    SELECT * FROM trading_decisions
                """
                params = []

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

    # ============================================================================
    # Health and Maintenance
    # ============================================================================

    async def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the database"""
        try:
            async with self.get_connection() as conn:
                # Test basic connectivity
                await conn.execute("SELECT 1")

                # Get database size
                size_result = await conn.fetchrow(
                    """
                    SELECT pg_size_pretty(pg_database_size(current_database())) as size
                """
                )

                # Get table stats
                stats_result = await conn.fetch(
                    """
                    SELECT schemaname, tablename, n_tup_ins as inserts, n_tup_upd as updates
                    FROM pg_stat_user_tables
                    WHERE tablename IN ('candles', 'technical_indicators', 'trading_decisions', 'orders', 'positions')
                """
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
                    "timestamp": datetime.utcnow().isoformat(),
                }

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def get_database_stats(self) -> Dict[str, Any]:
        """Get detailed database statistics"""
        try:
            async with self.get_connection() as conn:
                # Get candle counts by symbol and timeframe
                candle_counts = await conn.fetch(
                    """
                    SELECT symbol, timeframe, COUNT(*) as count,
                           MIN(timestamp) as oldest,
                           MAX(timestamp) as newest
                    FROM candles
                    GROUP BY symbol, timeframe
                    ORDER BY symbol, timeframe
                """
                )

                # Get recent activity
                recent_activity = await conn.fetchrow(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM candles WHERE timestamp > NOW() - INTERVAL '1 hour') as candles_last_hour,
                        (SELECT COUNT(*) FROM technical_indicators WHERE timestamp > NOW() - INTERVAL '1 hour') as indicators_last_hour,
                        (SELECT COUNT(*) FROM trading_decisions WHERE created_at > NOW() - INTERVAL '1 hour') as decisions_last_hour
                """
                )

                return {
                    "candle_counts": [dict(row) for row in candle_counts],
                    "recent_activity": dict(recent_activity) if recent_activity else {},
                    "timestamp": datetime.utcnow().isoformat(),
                }

        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {}

    async def cleanup_old_data(self, days_to_keep: int = 90) -> Dict[str, int]:
        """Clean up old data beyond retention period"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
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

    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
