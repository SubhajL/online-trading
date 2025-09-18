"""
Production-grade database layer with connection pooling and transactions.

Provides ACID transactions, connection pooling, optimistic locking,
and comprehensive error handling for PostgreSQL and Redis.
"""

import asyncio
import asyncpg
import redis.asyncio as redis
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, Optional, AsyncGenerator
from urllib.parse import urlparse
import time
from enum import Enum


# Custom Exceptions
class DatabaseError(Exception):
    """Base database error."""
    pass


class ConnectionError(DatabaseError):
    """Connection-related errors."""
    pass


class TransactionError(DatabaseError):
    """Transaction-related errors."""
    pass


class OptimisticLockError(DatabaseError):
    """Optimistic locking conflicts."""
    pass


class PoolExhaustionError(ConnectionError):
    """Connection pool exhausted."""
    pass


@dataclass
class DatabaseConfig:
    """Database configuration with validation."""
    postgres_url: str
    redis_url: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    retry_attempts: int = 3
    retry_delay: float = 0.1
    health_check_interval: int = 30

    def __post_init__(self):
        """Validate configuration."""
        self._validate_urls()
        self._validate_pool_settings()

    def _validate_urls(self) -> None:
        """Validate database URLs."""
        try:
            pg_parsed = urlparse(self.postgres_url)
            if pg_parsed.scheme not in ('postgresql', 'postgres'):
                raise ValueError(f"Invalid PostgreSQL URL scheme: {pg_parsed.scheme}")

            redis_parsed = urlparse(self.redis_url)
            if redis_parsed.scheme != 'redis':
                raise ValueError(f"Invalid Redis URL scheme: {redis_parsed.scheme}")

        except Exception as e:
            raise ValueError(f"Invalid database URL: {e}")

    def _validate_pool_settings(self) -> None:
        """Validate pool configuration."""
        if self.pool_size <= 0:
            raise ValueError("pool_size must be positive")
        if self.max_overflow < 0:
            raise ValueError("max_overflow cannot be negative")
        if self.pool_timeout <= 0:
            raise ValueError("pool_timeout must be positive")


class ConnectionPool:
    """Manages connection pools for PostgreSQL and Redis."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._postgres_pool: Optional[asyncpg.Pool] = None
        self._redis_pool: Optional[redis.Redis] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize connection pools."""
        if self._initialized:
            return

        try:
            # Initialize PostgreSQL pool
            self._postgres_pool = await asyncpg.create_pool(
                self.config.postgres_url,
                min_size=self.config.pool_size,
                max_size=self.config.pool_size + self.config.max_overflow,
                command_timeout=self.config.pool_timeout,
                server_settings={
                    'jit': 'off',  # Disable JIT for better performance on small queries
                    'application_name': 'trading_engine'
                }
            )

            # Initialize Redis pool
            self._redis_pool = redis.from_url(
                self.config.redis_url,
                encoding='utf-8',
                decode_responses=True,
                socket_timeout=self.config.pool_timeout,
                socket_connect_timeout=self.config.pool_timeout,
                retry_on_timeout=True,
                health_check_interval=self.config.health_check_interval
            )

            self._initialized = True
            self.logger.info("Database pools initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize database pools: {e}")
            raise ConnectionError(f"Database initialization failed: {e}")

    @asynccontextmanager
    async def get_postgres_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Get PostgreSQL connection from pool."""
        if not self._initialized:
            raise ConnectionError("Connection pool not initialized")

        try:
            async with self._postgres_pool.acquire() as connection:
                yield connection
        except asyncpg.TooManyConnectionsError:
            raise PoolExhaustionError("PostgreSQL connection pool exhausted")
        except Exception as e:
            raise ConnectionError(f"Failed to acquire PostgreSQL connection: {e}")

    @asynccontextmanager
    async def get_redis_connection(self) -> AsyncGenerator[redis.Redis, None]:
        """Get Redis connection."""
        if not self._initialized:
            raise ConnectionError("Connection pool not initialized")

        try:
            yield self._redis_pool
        except Exception as e:
            raise ConnectionError(f"Redis connection error: {e}")

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all connection pools."""
        health = {"postgres": False, "redis": False}

        # Check PostgreSQL
        try:
            async with self.get_postgres_connection() as conn:
                await conn.fetchval("SELECT 1")
                health["postgres"] = True
        except Exception as e:
            self.logger.warning(f"PostgreSQL health check failed: {e}")

        # Check Redis
        try:
            async with self.get_redis_connection() as redis:
                await redis.ping()
                health["redis"] = True
        except Exception as e:
            self.logger.warning(f"Redis health check failed: {e}")

        return health

    async def close(self) -> None:
        """Close all connection pools."""
        if self._postgres_pool:
            await self._postgres_pool.close()
            self._postgres_pool = None

        if self._redis_pool:
            await self._redis_pool.close()
            self._redis_pool = None

        self._initialized = False
        self.logger.info("Database pools closed")


class TransactionContext:
    """Context manager for PostgreSQL transactions with ACID guarantees."""

    def __init__(self, connection: asyncpg.Connection):
        self.connection = connection
        self.transaction: Optional[asyncpg.Transaction] = None
        self.logger = logging.getLogger(__name__)

    async def __aenter__(self) -> 'TransactionContext':
        """Start transaction."""
        try:
            self.transaction = self.connection.transaction()
            await self.transaction.start()
            return self
        except asyncpg.DeadlockDetectedError as e:
            raise TransactionError(f"Transaction deadlock detected: {e}")
        except Exception as e:
            raise TransactionError(f"Failed to start transaction: {e}")

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Commit or rollback transaction."""
        if not self.transaction:
            return

        try:
            if exc_type is None:
                await self.transaction.commit()
                self.logger.debug("Transaction committed successfully")
            else:
                await self.transaction.rollback()
                self.logger.debug(f"Transaction rolled back due to: {exc_val}")
        except Exception as e:
            self.logger.error(f"Transaction cleanup failed: {e}")
            # Don't raise here as it might mask original exception
        finally:
            self.transaction = None

    async def execute(self, query: str, *args) -> str:
        """Execute query within transaction."""
        if not self.transaction:
            raise TransactionError("No active transaction")

        try:
            return await self.connection.execute(query, *args)
        except Exception as e:
            self.logger.error(f"Query execution failed: {e}")
            raise

    async def fetch(self, query: str, *args) -> list:
        """Fetch query results within transaction."""
        if not self.transaction:
            raise TransactionError("No active transaction")

        try:
            return await self.connection.fetch(query, *args)
        except Exception as e:
            self.logger.error(f"Query fetch failed: {e}")
            raise

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch single row within transaction."""
        if not self.transaction:
            raise TransactionError("No active transaction")

        try:
            return await self.connection.fetchrow(query, *args)
        except Exception as e:
            self.logger.error(f"Query fetchrow failed: {e}")
            raise


class OptimisticLockMixin:
    """Mixin providing optimistic locking functionality."""

    async def update_with_version(
        self,
        connection: asyncpg.Connection,
        query: str,
        *args
    ) -> bool:
        """
        Execute update with version check for optimistic locking.

        Args:
            connection: Database connection
            query: UPDATE query with version in WHERE clause
            *args: Query parameters

        Returns:
            True if update succeeded

        Raises:
            OptimisticLockError: If no rows were updated (version conflict)
        """
        try:
            result = await connection.execute(query, *args)

            # Extract number of affected rows
            if hasattr(result, 'split'):
                rows_affected = int(result.split()[-1])
            else:
                rows_affected = 0

            if rows_affected == 0:
                raise OptimisticLockError(
                    "Optimistic lock conflict - row was modified by another transaction"
                )

            return True

        except OptimisticLockError:
            raise
        except Exception as e:
            raise DatabaseError(f"Update with version check failed: {e}")

    async def increment_version(
        self,
        connection: asyncpg.Connection,
        table: str,
        where_clause: str,
        *args
    ) -> int:
        """
        Increment version field and return new version.

        Args:
            connection: Database connection
            table: Table name
            where_clause: WHERE clause without WHERE keyword
            *args: WHERE clause parameters

        Returns:
            New version number
        """
        query = f"""
        UPDATE {table}
        SET version = version + 1, updated_at = NOW()
        WHERE {where_clause}
        RETURNING version
        """

        try:
            result = await connection.fetchval(query, *args)
            if result is None:
                raise OptimisticLockError("No row found to increment version")
            return result
        except Exception as e:
            raise DatabaseError(f"Version increment failed: {e}")


class DatabaseManager:
    """
    Main database manager providing high-level database operations.

    Coordinates connection pooling, transactions, and provides
    unified interface for all database operations.
    """

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._pool = ConnectionPool(config)
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database manager."""
        if self._initialized:
            return

        try:
            await self._pool.initialize()
            self._initialized = True
            self.logger.info("Database manager initialized successfully")
        except Exception as e:
            self.logger.error(f"Database manager initialization failed: {e}")
            raise

    @asynccontextmanager
    async def get_connection(self, retry: bool = True) -> AsyncGenerator[asyncpg.Connection, None]:
        """
        Get database connection with retry logic.

        Args:
            retry: Whether to retry on connection failures

        Yields:
            Database connection

        Raises:
            ConnectionError: If connection cannot be established
        """
        if not self._initialized:
            raise ConnectionError("Database manager not initialized")

        last_error = None
        attempts = self.config.retry_attempts if retry else 1

        for attempt in range(attempts):
            try:
                async with self._pool.get_postgres_connection() as conn:
                    yield conn
                    return  # Success, exit retry loop
            except Exception as e:
                last_error = e
                if attempt < attempts - 1:
                    await asyncio.sleep(self.config.retry_delay * (2 ** attempt))
                    self.logger.warning(f"Connection attempt {attempt + 1} failed, retrying: {e}")

        raise ConnectionError(f"Failed to get connection after {attempts} attempts: {last_error}")

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[TransactionContext, None]:
        """
        Create transaction context manager.

        Yields:
            TransactionContext for executing queries within transaction
        """
        if not self._initialized:
            raise TransactionError("Database manager not initialized")

        async with self._pool.get_postgres_connection() as conn:
            async with TransactionContext(conn) as tx:
                yield tx

    @asynccontextmanager
    async def redis_connection(self) -> AsyncGenerator[redis.Redis, None]:
        """Get Redis connection."""
        if not self._initialized:
            raise ConnectionError("Database manager not initialized")

        async with self._pool.get_redis_connection() as redis_conn:
            yield redis_conn

    async def execute_with_retry(
        self,
        query: str,
        *args,
        max_retries: int = None
    ) -> str:
        """
        Execute query with automatic retry on transient failures.

        Args:
            query: SQL query
            *args: Query parameters
            max_retries: Maximum retry attempts (uses config default if None)

        Returns:
            Query execution result
        """
        max_retries = max_retries or self.config.retry_attempts
        last_error = None

        for attempt in range(max_retries):
            try:
                async with self._pool.get_postgres_connection() as conn:
                    return await conn.execute(query, *args)
            except (asyncpg.ConnectionDoesNotExistError,
                    asyncpg.InterfaceError,
                    ConnectionError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = self.config.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    self.logger.warning(f"Query retry {attempt + 1}/{max_retries} after {delay}s: {e}")
            except Exception as e:
                # Don't retry on non-transient errors
                raise DatabaseError(f"Query execution failed: {e}")

        raise DatabaseError(f"Query failed after {max_retries} retries: {last_error}")

    async def health_check(self) -> Dict[str, Any]:
        """
        Comprehensive health check of database systems.

        Returns:
            Health status dictionary
        """
        if not self._initialized:
            return {
                "postgres": False,
                "redis": False,
                "overall": False,
                "error": "Database manager not initialized"
            }

        try:
            pool_health = await self._pool.health_check()
            overall_health = all(pool_health.values())

            return {
                **pool_health,
                "overall": overall_health,
                "timestamp": time.time(),
                "pool_info": {
                    "pool_size": self.config.pool_size,
                    "max_overflow": self.config.max_overflow
                }
            }
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "postgres": False,
                "redis": False,
                "overall": False,
                "error": str(e)
            }

    async def shutdown(self) -> None:
        """Gracefully shutdown database manager."""
        if not self._initialized:
            return

        try:
            await self._pool.close()
            self._initialized = False
            self.logger.info("Database manager shut down successfully")
        except Exception as e:
            self.logger.error(f"Database shutdown error: {e}")
            raise

    def __del__(self):
        """Cleanup on garbage collection."""
        if self._initialized and self._pool:
            # Log warning about ungraceful shutdown
            self.logger.warning(
                "DatabaseManager deleted without explicit shutdown. "
                "Call shutdown() before deleting."
            )