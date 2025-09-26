"""
Pytest configuration and fixtures for integration tests.

Provides real database and Redis connections for testing
against actual infrastructure.
"""

import os
import asyncio
from typing import Any

import pytest
import pytest_asyncio
import asyncpg
import redis.asyncio as redis
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# Database connection parameters
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "trading_platform"),
    "user": os.getenv("POSTGRES_USER", "trading_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "trading_password"),
}


# Redis connection parameters
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
    "password": os.getenv("REDIS_PASSWORD"),
}


class DatabaseConnection:
    """Wrapper for database operations to match test expectations."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch_one(self, query: str, *args) -> dict[str, Any] | None:
        """Fetch a single row as dict."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def fetch_val(self, query: str, *args) -> Any:
        """Fetch a single value."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args) -> str:
        """Execute a query without returning results."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)


class RedisConnection:
    """Wrapper for Redis operations to match test expectations."""

    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    async def set(self, key: str, value: str) -> None:
        """Set a key-value pair."""
        await self._redis.set(key, value)

    async def get(self, key: str) -> str | None:
        """Get a value by key."""
        value = await self._redis.get(key)
        return value.decode() if value else None

    async def setex(self, key: str, seconds: int, value: str) -> None:
        """Set a key with expiration."""
        await self._redis.setex(key, seconds, value)

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a channel."""
        return await self._redis.publish(channel, message)

    def pubsub(self) -> redis.client.PubSub:
        """Get a pubsub instance."""
        return self._redis.pubsub()


@pytest_asyncio.fixture
async def real_db():
    """Provide a real PostgreSQL database connection."""
    # Create connection pool
    pool = await asyncpg.create_pool(
        **DB_CONFIG,
        min_size=2,
        max_size=10,
        command_timeout=60
    )

    try:
        yield DatabaseConnection(pool)
    finally:
        await pool.close()


@pytest_asyncio.fixture
async def real_redis():
    """Provide a real Redis connection."""
    # Create Redis connection
    redis_client = redis.Redis(
        host=REDIS_CONFIG["host"],
        port=REDIS_CONFIG["port"],
        password=REDIS_CONFIG["password"],
        decode_responses=False  # We'll handle decoding in wrapper
    )

    try:
        yield RedisConnection(redis_client)
    finally:
        await redis_client.close()


@pytest_asyncio.fixture
async def clean_test_data(real_db):
    """Clean up test data before and after tests."""
    # Clean before test
    await real_db.execute("""
        DELETE FROM candles
        WHERE symbol LIKE 'TEST%'
           OR (symbol = 'BTCUSDT' AND time > NOW() - INTERVAL '1 hour')
    """)

    yield

    # Clean after test
    await real_db.execute("""
        DELETE FROM candles
        WHERE symbol LIKE 'TEST%'
           OR (symbol = 'BTCUSDT' AND time > NOW() - INTERVAL '1 hour')
    """)


# Configure async test runner
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()