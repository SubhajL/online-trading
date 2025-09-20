"""Connection pool management for TimescaleDB."""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional

import asyncpg
from asyncpg import Connection, Pool

logger = logging.getLogger(__name__)


@dataclass
class DBConfig:
    """Database connection configuration."""

    host: str
    port: int
    database: str
    username: str
    password: str
    pool_size: int = 10
    max_retries: int = 3
    retry_delay: float = 1.0


class ConnectionPool:
    """Manages database connection pooling with retry logic."""

    def __init__(self, config: DBConfig):
        self.config = config
        self._pool: Optional[Pool] = None

    @property
    def is_initialized(self) -> bool:
        """Check if pool is initialized."""
        return self._pool is not None

    async def initialize(self) -> None:
        """Initialize connection pool with retry logic."""
        for attempt in range(self.config.max_retries):
            try:
                self._pool = await asyncpg.create_pool(
                    host=self.config.host,
                    port=self.config.port,
                    database=self.config.database,
                    user=self.config.username,
                    password=self.config.password,
                    min_size=1,
                    max_size=self.config.pool_size,
                    command_timeout=60,
                    server_settings={
                        "application_name": "trading_engine",
                    },
                )
                logger.info(
                    f"Database pool created: {self.config.host}:{self.config.port}/{self.config.database}"
                )
                return

            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    raise

    @asynccontextmanager
    async def acquire(self):
        """Acquire connection from pool."""
        if not self.is_initialized:
            raise RuntimeError("Connection pool not initialized")

        conn = await self._pool.acquire()
        try:
            yield conn
        finally:
            await self._pool.release(conn)

    async def health_check(self) -> bool:
        """Check if pool is healthy by executing simple query."""
        try:
            async with self.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close connection pool gracefully."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Database pool closed")
