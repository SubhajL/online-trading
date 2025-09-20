"""Unit tests for ConnectionPool class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, create_autospec

import pytest
import asyncpg
from asyncpg import Connection, Pool

from app.engine.adapters.db.connection_pool import ConnectionPool, DBConfig


@pytest.fixture
def db_config():
    return DBConfig(
        host="localhost",
        port=5432,
        database="test_db",
        username="test_user",
        password="test_password",
        pool_size=5,
        max_retries=3,
        retry_delay=0.1,
    )


class TestConnectionPool:
    @pytest.mark.asyncio
    async def test_pool_creation_success(self, db_config):
        """Pool initializes successfully with valid config."""
        mock_pool = AsyncMock(spec=Pool)

        async def async_create_pool(*args, **kwargs):
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=async_create_pool) as mock_create:
            pool = ConnectionPool(db_config)
            await pool.initialize()

            mock_create.assert_called_once_with(
                host=db_config.host,
                port=db_config.port,
                database=db_config.database,
                user=db_config.username,
                password=db_config.password,
                min_size=1,
                max_size=db_config.pool_size,
                command_timeout=60,
                server_settings={"application_name": "trading_engine"},
            )

            assert pool.is_initialized

    @pytest.mark.asyncio
    async def test_pool_creation_retry(self, db_config):
        """Pool retries on initial connection failure."""
        mock_pool = AsyncMock(spec=Pool)

        async def async_side_effect(*args, **kwargs):
            # Track calls
            if not hasattr(async_side_effect, "call_count"):
                async_side_effect.call_count = 0
            async_side_effect.call_count += 1

            if async_side_effect.call_count < 3:
                raise Exception("Connection failed")
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=async_side_effect) as mock_create:
            pool = ConnectionPool(db_config)
            await pool.initialize()

            assert mock_create.call_count == 3
            assert pool.is_initialized

    @pytest.mark.asyncio
    async def test_pool_creation_max_retries_exceeded(self, db_config):
        """Pool raises exception after max retries exceeded."""

        async def async_fail(*args, **kwargs):
            raise Exception("Connection failed")

        with patch("asyncpg.create_pool", side_effect=async_fail) as mock_create:

            pool = ConnectionPool(db_config)
            with pytest.raises(Exception, match="Connection failed"):
                await pool.initialize()

            assert mock_create.call_count == db_config.max_retries
            assert not pool.is_initialized

    @pytest.mark.asyncio
    async def test_acquire_release_cycle(self, db_config):
        """Connections can be acquired and released properly."""
        mock_pool = AsyncMock(spec=Pool)
        mock_conn = AsyncMock(spec=Connection)
        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_pool.release = AsyncMock()

        async def async_create_pool(*args, **kwargs):
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=async_create_pool):
            pool = ConnectionPool(db_config)
            await pool.initialize()

            # Acquire connection
            async with pool.acquire() as conn:
                assert conn == mock_conn

            # Verify acquire and release were called
            mock_pool.acquire.assert_called_once()
            mock_pool.release.assert_called_once_with(mock_conn)

    @pytest.mark.asyncio
    async def test_acquire_without_initialization(self, db_config):
        """Acquire raises error if pool not initialized."""
        pool = ConnectionPool(db_config)

        with pytest.raises(RuntimeError, match="Connection pool not initialized"):
            async with pool.acquire():
                pass

    @pytest.mark.asyncio
    async def test_health_check_success(self, db_config):
        """Health check returns True when pool is healthy."""
        mock_pool = AsyncMock(spec=Pool)
        mock_conn = AsyncMock(spec=Connection)
        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_pool.release = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)

        async def async_create_pool(*args, **kwargs):
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=async_create_pool):
            pool = ConnectionPool(db_config)
            await pool.initialize()

            result = await pool.health_check()

            assert result is True
            mock_conn.fetchval.assert_called_once_with("SELECT 1")

    @pytest.mark.asyncio
    async def test_health_check_failure(self, db_config):
        """Health check returns False when pool is unhealthy."""
        mock_pool = AsyncMock(spec=Pool)
        mock_pool.acquire.side_effect = Exception("Pool is closed")

        async def async_create_pool(*args, **kwargs):
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=async_create_pool):
            pool = ConnectionPool(db_config)
            await pool.initialize()

            result = await pool.health_check()

            assert result is False

    @pytest.mark.asyncio
    async def test_close_pool(self, db_config):
        """Pool can be closed gracefully."""
        mock_pool = AsyncMock(spec=Pool)

        async def async_create_pool(*args, **kwargs):
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=async_create_pool):
            pool = ConnectionPool(db_config)
            await pool.initialize()

            await pool.close()

            mock_pool.close.assert_called_once()
            assert not pool.is_initialized

    @pytest.mark.asyncio
    async def test_connection_context_manager(self, db_config):
        """Connection context manager handles exceptions properly."""
        mock_pool = AsyncMock(spec=Pool)
        mock_conn = AsyncMock(spec=Connection)
        mock_pool.acquire = AsyncMock(return_value=mock_conn)
        mock_pool.release = AsyncMock()

        async def async_create_pool(*args, **kwargs):
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=async_create_pool):
            pool = ConnectionPool(db_config)
            await pool.initialize()

            # Test exception handling in context manager
            with pytest.raises(ValueError):
                async with pool.acquire() as conn:
                    raise ValueError("Test error")

            # Ensure connection was still released
            mock_pool.release.assert_called_once_with(mock_conn)
